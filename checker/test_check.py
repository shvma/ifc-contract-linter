"""Тесты линтера на настоящем контракте v0.34.0 (= v0.37.0), на моделях replay/ и на синтетических случаях."""
import json
import unittest
from pathlib import Path

import check_contract

HERE = Path(__file__).resolve().parent
INV = json.loads((HERE / "inventory.json").read_text(encoding="utf-8"))
G = "mcp/claude_ai_Google_Drive/"


def tool(name, requires=None):
    t = {"name": G + name, "delta": {}}
    if requires is not None:
        t["requires"] = requires
    return t


def contract(*tools):
    return {"policy": {"version": 2, "tool": list(tools)}}


class SyntheticTest(unittest.TestCase):
    def test_write_without_review_flagged(self):
        fs = check_contract.findings(contract(tool("create_file", {"trust": "trusted"})), INV)
        self.assertEqual([(f["tool"], f["gap"]) for f in fs], [(G + "create_file", "write_without_review")])

    def test_write_with_review_clean(self):
        c = contract(tool("create_file", {"trust": "trusted", "attention": ["review"]}))
        self.assertEqual(check_contract.findings(c, INV), [])

    def test_empty_attention_is_not_review(self):
        c = contract(tool("copy_file", {"trust": "trusted", "attention": []}))
        self.assertEqual(len(check_contract.findings(c, INV)), 1)

    def test_understated_effects_still_flagged(self):
        # Контракт без effects у записи: линтер опирается на inventory, а не на effects.
        c = contract(tool("update_file", {"trust": "trusted"}))
        self.assertEqual(len(check_contract.findings(c, INV)), 1)

    def test_exempt_not_flagged(self):
        self.assertEqual(check_contract.findings(contract(tool("trash_file", {"trust": "trusted"})), INV), [])

    def test_unclassified_write_flagged(self):
        fs = check_contract.findings(contract(tool("rename_file", {"trust": "trusted"})), INV)
        self.assertEqual([f["gap"] for f in fs], ["unclassified_write"])

    def test_read_without_requires_clean(self):
        self.assertEqual(check_contract.findings(contract(tool("read_file_content")), INV), [])

    def test_selector_judged_by_base_name(self):
        # Сужение по аргументу не выводит правило из-под проверки.
        fs = check_contract.findings(contract(tool("create_file(parentId:X)", {"trust": "trusted"})), INV)
        self.assertEqual([f["gap"] for f in fs], ["write_without_review"])

    def test_allowed_selector_clean(self):
        name = G + "create_file(parentId:X)"
        c = contract(tool("create_file(parentId:X)", {"trust": "trusted"}))
        self.assertEqual(check_contract.findings(c, INV, {name: "внутренняя папка"}), [])

    def test_allowlist_is_exact_name(self):
        # Белый список на одну папку не покрывает правило на любую папку.
        c = contract(tool("update_file(parentId:*)", {"trust": "trusted"}))
        self.assertEqual(len(check_contract.findings(c, INV, {G + "update_file(parentId:X)": "x"})), 1)


def load(rel):
    with open(HERE.parent / rel, "rb") as f:
        return check_contract.tomllib.load(f)


SHIPPED = "results/google-workspace-appa-v0.34.0.toml"
LINEAR = "results/linear-appa-v0.37.0.toml"
WRITES = {G + n for n in ("create_file", "copy_file", "update_file")}


def drive(c):
    return [t for t in c["policy"]["tool"] if t["name"].startswith(G)]


def named(c, name):
    return [t for t in c["policy"]["tool"] if t["name"] == name]


@unittest.skipIf(check_contract.tomllib is None, "нет парсера TOML: Python 3.11+ или tomli")
class RealContractTest(unittest.TestCase):
    def test_shipped_v0_34_0(self):
        fs = check_contract.findings(load(SHIPPED), INV)
        self.assertEqual(sorted((f["tool"], f["gap"]) for f in fs),
                         [(G + n, "write_without_review") for n in ("copy_file", "create_file", "update_file")])

    def test_gap_model_matches_shipped(self):
        # replay/gap — не пересказ: правила инструментов и селекторы источника те же, что в поставляемом.
        shipped, gap = load(SHIPPED), load("replay/gap/contract.toml")
        self.assertEqual(len(drive(shipped)), 11)
        self.assertEqual(drive(gap), drive(shipped))
        self.assertEqual(gap["externals"]["audience"]["google-workspace"]["selectors"],
                         shipped["externals"]["audience"]["google-workspace"]["selectors"])

    def test_models_add_only_linear_source(self):
        # Кроме правил Drive в моделях одно правило — get_diff из батареи linear, дословно.
        upstream = named(load(LINEAR), "mcp/linear/get_diff")
        self.assertEqual(len(upstream), 1)
        for rel in ("replay/gap/contract.toml", "replay/fixed/contract.toml"):
            c = load(rel)
            self.assertEqual([t for t in c["policy"]["tool"] if not t["name"].startswith(G)], upstream, rel)

    def test_fixed_model_changes_only_writes(self):
        shipped, fixed = load(SHIPPED), load("replay/fixed/contract.toml")
        keep = lambda c: [t for t in drive(c) if check_contract.base_name(t["name"]) not in WRITES]
        self.assertEqual(keep(fixed), keep(shipped))
        self.assertTrue(any(t["name"] not in [s["name"] for s in drive(shipped)] for t in drive(fixed)))

    def test_fixed_model_clean_with_allowlist(self):
        allowed = json.loads((HERE.parent / "replay/fixed/allowlist.json").read_text(encoding="utf-8"))
        fs = check_contract.findings(load("replay/fixed/contract.toml"), INV, allowed["allowed_without_review"])
        self.assertEqual(fs, [])


if __name__ == "__main__":
    unittest.main()
