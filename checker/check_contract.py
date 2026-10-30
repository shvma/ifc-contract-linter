#!/usr/bin/env python3
"""Линтер контракта OpenAPPA: инструменты, которые расширяют круг читателей, требуют меры.

  python3 check_contract.py inventory.json [--allow allow.json] appa.toml [appa.toml ...]

Какие инструменты расширяют круг читателей, берётся из inventory.json, а не из поля effects
самого контракта: контракт, который преуменьшает эффект, иначе прошёл бы чисто.
Правило с селектором аргументов (`create_file(parentId:X)`) судится по имени инструмента до скобки.

Мера у правила инструмента из widens_readers — одно из:
  - ревью: непустой attention с меткой из review_gates;
  - запись в allowed_without_review файла --allow (точное полное имя правила);
  - аудитория цели из аргумента: в requires.audience.contains есть `$<арг>` или
    `@provider:selector/$<арг>`, и <арг> перечислен в target_args инструмента. Для инструмента
    из sends_content (содержимое едет на стороне сервиса, мимо траектории) нужен ещё forwards
    с непустой audience: иначе узкий источник уходит в цель шире него.
У инструмента из access_args (аргументы, которые меняют доступ, не меняя цель) мера — только ревью:
ни белый список, ни аудитория цели такие аргументы не покрывают.
Правило с annotator линтер не судит: решение принимает код аннотатора. Такое правило — не пробел,
а пометка annotated_unchecked; проверять его трассами (replay/pr750 — пример).

Находки (код выхода 1):
  write_without_review   правило из widens_readers без меры;
  content_not_forwarded  цель покрыта (белый список или аудитория из аргумента), а forwards
                         у инструмента из sends_content нет;
  access_change_without_review  правило инструмента из access_args без ревью (белый список
                         или аудитория цели не в счёт);
  unclassified_write     инструмента нет в inventory.json, у правила есть requires;
  unclassified_tool      инструмента нет в inventory.json, requires нет.
Пометки (код выхода не меняют):
  annotated_unchecked    правило из widens_readers отдано аннотатору.

Граница: любой инструмент, которого нет в inventory.json, — находка, с requires или без.
Якорь доверия — inventory.json: инструменты, расширяющие круг читателей, их аргументы цели
и то, какие из них переносят содержимое, перечисляет человек. Что аннотатор отвечает верно,
линтер не знает.

Нужен tomllib (Python 3.11+) или пакет tomli.
"""
import argparse
import json
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

GAPS = ("write_without_review", "content_not_forwarded", "access_change_without_review", "unclassified_write", "unclassified_tool")
ARG = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def base_name(name):
    return name.split("(", 1)[0]


def bound_args(contains):
    """Аргументы, из которых contains читает аудиторию: `$to` или `@slack:channel/$channel_id`."""
    out = set()
    for entry in contains if isinstance(contains, list) else []:
        if isinstance(entry, str) and (entry.startswith("$") or entry.startswith("@")):
            out.update(ARG.findall(entry))
    return out


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
    targets = inventory.get("target_args", {})
    sends = inventory.get("sends_content", [])
    access = inventory.get("access_args", {})
    if not isinstance(targets, dict) or any(not isinstance(v, list) for v in targets.values()):
        raise ValueError("target_args must map tools to argument lists")
    if not isinstance(sends, list):
        raise ValueError("sends_content must be a list of tools")
    if not isinstance(access, dict) or any(not isinstance(v, list) for v in access.values()):
        raise ValueError("access_args must map tools to argument lists")
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
        annotator = tool.get("annotator")
        if annotator is not None and (not isinstance(annotator, str) or not annotator):
            raise ValueError("annotator must be a nonempty string: " + name)
        if annotator and any(k in tool for k in ("delta", "requires", "forwards", "effects")):
            # docs/contracts.md: «Combining them causes a load error».
            raise ValueError("annotator and static contract fields in one rule: " + name)
        base = base_name(name)
        if base in widens:
            if annotator:
                out.append({"tool": name, "gap": "annotated_unchecked",
                            "why": f"решает аннотатор {annotator}; линтер его код не проверяет — нужны трассы"})
                continue
            if set(attention).intersection(inventory.get("review_gates", ["review"])):
                continue
            if access.get(base):
                out.append({"tool": name, "gap": "access_change_without_review",
                            "why": "аргументы " + ", ".join(access[base]) + " меняют доступ в том же вызове; "
                                   "селектор их не различает, поэтому правилу без ревью они проходят"})
                continue
            audience = (requires or {}).get("audience", {})
            bound = bound_args(audience.get("contains") if isinstance(audience, dict) else None)
            if name not in allowed and not bound.intersection(targets.get(base, [])):
                out.append({"tool": name, "gap": "write_without_review", "why": widens[base]})
                continue
            # Цель покрыта (белым списком или аудиторией из аргумента), источник — только forwards.
            forwards = tool.get("forwards")
            if base in sends and not (isinstance(forwards, dict) and forwards.get("audience")):
                out.append({"tool": name, "gap": "content_not_forwarded",
                            "why": "цель покрыта, но содержимое источника едет без forwards: " + widens[base]})
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
        gaps = [x for x in fs if x["gap"] in GAPS]
        notes = [x for x in fs if x["gap"] not in GAPS]
        summary = "пробелов нет" if not gaps else str(len(gaps)) + " пробел(ов)"
        if notes:
            summary += f", {len(notes)} к проверке трассами"
        print(f"{p}: {summary}")
        for x in gaps + notes:
            print(f"  - {x['tool']}: {x['gap']} — {x['why']}")
        if gaps:
            code = 1
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
