"""Тесты линтера на настоящем контракте v0.34.0 (= v0.37.0), на моделях replay/ и на синтетических случаях."""
import json
import unittest
from pathlib import Path

import check_contract

HERE = Path(__file__).resolve().parent
INV = json.loads((HERE / "inventory.json").read_text(encoding="utf-8"))
G = "mcp/claude_ai_Google_Drive/"


def tool(name, requires=None, **extra):
    t = {"name": G + name, "delta": {}, **extra}
    if requires is not None:
        t["requires"] = requires
    return t


def annotated(name, annotator="drive-readers"):
    return {"name": G + name, "annotator": annotator}


FOLDER = {"trust": "trusted", "audience": {"contains": ["@google-workspace:folder/$parentId"]}}


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

    def test_other_attention_is_not_review(self):
        c = contract(tool("copy_file", {"attention": ["audit"]}))
        self.assertEqual(len(check_contract.findings(c, INV)), 1)

    def test_unknown_tool_without_requires_is_not_clean(self):
        self.assertEqual(check_contract.findings(contract(tool("unknown_writer")), INV)[0]["gap"], "unclassified_tool")

    def test_invalid_or_empty_contract_is_not_clean(self):
        for value in ({}, {"policy": {}}, contract(), {"policy": {"version": 99, "tool": [tool("create_file")]}}):
            with self.assertRaises(ValueError):
                check_contract.findings(value, INV)

    def test_invalid_attention_and_duplicate_rule_are_errors(self):
        for value in (contract(tool("create_file", {"attention": "review"})),
                      contract(tool("create_file"), tool("create_file"))):
            with self.assertRaises(ValueError):
                check_contract.findings(value, INV)

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
        c = contract(tool("create_file(parentId:*)", {"trust": "trusted"}))
        self.assertEqual(len(check_contract.findings(c, INV, {G + "create_file(parentId:X)": "x"})), 1)

    def test_target_audience_from_argument_is_a_measure(self):
        # Аудитория папки из аргумента, как @slack:channel/$channel_id в батарее slack.
        self.assertEqual(check_contract.findings(contract(tool("create_file", FOLDER)), INV), [])

    def test_audience_from_a_non_target_argument_is_not_a_measure(self):
        c = contract(tool("create_file", {"audience": {"contains": ["@google-workspace:folder/$title"]}}))
        self.assertEqual([f["gap"] for f in check_contract.findings(c, INV)], ["write_without_review"])

    def test_static_mention_is_not_bound_to_the_target(self):
        c = contract(tool("create_file", {"audience": {"contains": ["@google-workspace:group/eng@corp.com"]}}))
        self.assertEqual([f["gap"] for f in check_contract.findings(c, INV)], ["write_without_review"])

    def test_copy_needs_forwards_beside_target_audience(self):
        no_forwards = contract(tool("copy_file", FOLDER))
        self.assertEqual([f["gap"] for f in check_contract.findings(no_forwards, INV)], ["content_not_forwarded"])
        with_forwards = contract(tool("copy_file", FOLDER, forwards={"audience": ["self"]}))
        self.assertEqual(check_contract.findings(with_forwards, INV), [])

    def test_allowlisted_copy_still_needs_forwards(self):
        # Регрессия ревью 2026-10-30: copy_file(parentId:<папка из списка>) без ревью пропускал
        # копию файла узкой группы в папку организации (replay/fixed/critic-restricted-copy.appa).
        name = "copy_file(parentId:FOLDER_INTERNAL_REPORTS)"
        fs = check_contract.findings(contract(tool(name, {"trust": "trusted"})), INV, {G + name: "внутренняя"})
        self.assertEqual([f["gap"] for f in fs], ["content_not_forwarded"])

    def test_allowlisted_update_is_an_access_change(self):
        # Регрессия ревью 2026-10-30: update_file(parentId:<папка из списка>) без ревью пропускал
        # writersCanShare и inheritedPermissionsDisabled: false того же вызова (replay/fixed/critic-*.appa).
        name = "update_file(parentId:FOLDER_INTERNAL_REPORTS)"
        fs = check_contract.findings(contract(tool(name, {"trust": "trusted"})), INV, {G + name: "внутренняя"})
        self.assertEqual([f["gap"] for f in fs], ["access_change_without_review"])

    def test_update_with_target_audience_is_still_an_access_change(self):
        c = contract(tool("update_file", FOLDER, forwards={"audience": ["self"]}))
        self.assertEqual([f["gap"] for f in check_contract.findings(c, INV)], ["access_change_without_review"])

    def test_annotator_is_flagged_unchecked_not_clean_and_not_a_gap(self):
        fs = check_contract.findings(contract(annotated("create_file")), INV)
        self.assertEqual([f["gap"] for f in fs], ["annotated_unchecked"])
        self.assertNotIn("annotated_unchecked", check_contract.GAPS)

    def test_annotator_with_static_fields_is_an_error(self):
        with self.assertRaises(ValueError):
            check_contract.findings(contract(dict(annotated("create_file"), requires={"trust": "trusted"})), INV)

    def test_unknown_annotated_tool_is_unclassified(self):
        fs = check_contract.findings(contract(annotated("rename_file")), INV)
        self.assertEqual([f["gap"] for f in fs], ["unclassified_tool"])


def load(rel):
    with open(HERE.parent / rel, "rb") as f:
        return check_contract.tomllib.load(f)


SHIPPED = "results/google-workspace-appa-v0.34.0.toml"
LINEAR = "results/linear-appa-v0.37.0.toml"
PR750 = "results/upstream-pr750-2a9397b/appa.toml"
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
                         [(G + "copy_file", "write_without_review"), (G + "create_file", "write_without_review"),
                          (G + "update_file", "access_change_without_review")])

    def test_pr750_contract_only_unchecked(self):
        # PR #750: три записи отданы аннотатору — пробелов нет, но и чистыми линтер их не зовёт.
        fs = check_contract.findings(load(PR750), INV)
        self.assertEqual(sorted((f["tool"], f["gap"]) for f in fs),
                         [(G + n, "annotated_unchecked") for n in ("copy_file", "create_file", "update_file")])

    def test_pr750_model_matches_pr(self):
        # replay/pr750 — не пересказ: правила Drive и объявление аннотатора те же, что в PR;
        # отличается только команда аннотатора (фикстура вместо Drive API).
        pr, model = load(PR750), load("replay/pr750/contract.toml")
        self.assertEqual(drive(model), drive(pr))
        self.assertEqual(model["policy"]["annotator"], pr["policy"]["annotator"])
        bind = lambda c: dict(c["externals"]["annotators"]["google-workspace.drive-readers"], command=None)
        self.assertEqual(bind(model), bind(pr))
        self.assertEqual(model["externals"]["audience"]["google-workspace"]["selectors"],
                         pr["externals"]["audience"]["google-workspace"]["selectors"])

    def test_slack_battery_v0_37_0(self):
        # Чужая батарея: запись в канал с @slack:channel/$channel_id — мера; без привязки к цели — нет.
        inv = json.loads((HERE / "inventory-slack.json").read_text(encoding="utf-8"))
        fs = check_contract.findings(load("results/slack-appa-v0.37.0.toml"), inv)
        flagged = sorted(f["tool"].rsplit("/", 1)[1] for f in fs)
        self.assertEqual(flagged, ["slack_add_reaction", "slack_create_canvas", "slack_create_conversation",
                                   "slack_update_canvas"])
        self.assertTrue(all(f["gap"] == "write_without_review" for f in fs))

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
        for rel in ("replay/gap/contract.toml", "replay/fixed/contract.toml", "replay/pr750/contract.toml"):
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
