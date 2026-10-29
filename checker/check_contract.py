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
import argparse
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
    if not isinstance(contract, dict) or not isinstance(contract.get("policy"), dict):
        raise ValueError("contract must contain a policy table")
    policy = contract["policy"]
    if type(policy.get("version")) is not int or policy["version"] != 2:
        raise ValueError("unsupported or missing policy version")
    tools = policy.get("tool")
    if not isinstance(tools, list) or not tools:
        raise ValueError("policy.tool must be a nonempty array")
    if not isinstance(inventory, dict) or not all(isinstance(inventory.get(k), dict)
                                                for k in ("widens_readers", "exempt", "read_only")):
        raise ValueError("inventory must classify writes, exemptions and reads")
    widens, exempt, allowed = inventory["widens_readers"], inventory["exempt"], allowed or {}
    if not isinstance(allowed, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not v.strip()
                                            for k, v in allowed.items()):
        raise ValueError("allowlist entries require exact names and nonempty justifications")
    out = []
    seen = set()
    for tool in tools:
        if not isinstance(tool, dict) or not isinstance(tool.get("name"), str) or not tool["name"]:
            raise ValueError("each policy tool needs a nonempty name")
        name, requires = tool["name"], tool.get("requires")
        if name in seen:
            raise ValueError("duplicate tool rule: " + name)
        seen.add(name)
        if requires is not None and not isinstance(requires, dict):
            raise ValueError("requires must be a table: " + name)
        attention = (requires or {}).get("attention", [])
        if not isinstance(attention, list) or any(not isinstance(a, str) for a in attention):
            raise ValueError("attention must be an array of strings: " + name)
        base = base_name(name)
        if base in widens:
            if not set(attention).intersection(inventory.get("review_gates", ["review"])) and name not in allowed:
                out.append({"tool": name, "gap": "write_without_review", "why": widens[base]})
        elif base not in exempt and base not in inventory["read_only"]:
            out.append({"tool": name, "gap": "unclassified_write" if requires is not None else "unclassified_tool",
                        "why": "инструмент не классифицирован в inventory.json"})
    return out


def main(inv_path, paths, allow_path=None):
    if tomllib is None:
        print("нет парсера TOML: нужен Python 3.11+ или пакет tomli", file=sys.stderr)
        return 2
    with open(inv_path, encoding="utf-8") as source:
        inventory = json.load(source)
    allowed = {}
    if allow_path:
        with open(allow_path, encoding="utf-8") as source:
            allowed = json.load(source)["allowed_without_review"]
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory")
    parser.add_argument("--allow")
    parser.add_argument("contracts", nargs="+")
    args = parser.parse_args()
    try:
        code = main(args.inventory, args.contracts, args.allow)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("invalid input: " + str(exc), file=sys.stderr)
        code = 2
    sys.exit(code)
