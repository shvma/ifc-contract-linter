#!/usr/bin/env python3
"""Линтер контракта OpenAPPA: инструменты, которые расширяют круг читателей, требуют ревью.

  python3 check_contract.py inventory.json [--allow allow.json] appa.toml [appa.toml ...]

Какие инструменты расширяют круг читателей, берётся из inventory.json, а не из поля effects
самого контракта: контракт, который преуменьшает эффект, иначе прошёл бы чисто.
Правило с селектором аргументов (`create_file(parentId:X)`) судится по имени инструмента до скобки.
Находки:
  write_without_review   правило инструмента из widens_readers без непустого attention,
                         если его полного имени нет в allowed_without_review файла --allow;
  unclassified_write     у инструмента есть requires, но его нет ни в widens_readers, ни в exempt.

Граница: неизвестный инструмент (нет в inventory.json) судится по наличию `requires` — инструмент записи вовсе без `requires` линтер пропускает, потому что неотличим от чтения. Якорь доверия — inventory.json: инструменты, расширяющие круг читателей, перечисляет человек.

Нужен tomllib (Python 3.11+) или пакет tomli.
"""
import json
import sys

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None


def base_name(name):
    return name.split("(", 1)[0]


def findings(contract, inventory, allowed=None):
    widens, exempt, allowed = inventory["widens_readers"], inventory["exempt"], allowed or {}
    out = []
    for tool in contract.get("policy", {}).get("tool", []):
        name, requires = tool.get("name", "<безымянный>"), tool.get("requires")
        base = base_name(name)
        if base in widens:
            if not (requires or {}).get("attention") and name not in allowed:
                out.append({"tool": name, "gap": "write_without_review", "why": widens[base]})
        elif requires is not None and base not in exempt:
            out.append({"tool": name, "gap": "unclassified_write",
                        "why": "пишет, но не классифицирован в inventory.json"})
    return out


def main(inv_path, paths):
    if tomllib is None:
        print("нет парсера TOML: нужен Python 3.11+ или пакет tomli", file=sys.stderr)
        return 2
    inventory = json.load(open(inv_path, encoding="utf-8"))
    allowed = {}
    if paths[:1] == ["--allow"]:
        allowed = json.load(open(paths[1], encoding="utf-8"))["allowed_without_review"]
        paths = paths[2:]
    code = 0
    for p in paths:
        with open(p, "rb") as f:
            fs = findings(tomllib.load(f), inventory, allowed)
        print(f"{p}: {'пробелов нет' if not fs else str(len(fs)) + ' пробел(ов)'}")
        for x in fs:
            print(f"  - {x['tool']}: {x['gap']} — {x['why']}")
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
