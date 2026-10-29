"""Заглушка источника аудитории google-workspace для appa replay: без сети и токена.

Протокол и проверка объявленных шаблонов как у audience-source.py из батареи
(OpenAPPA v0.37.0). Участники фиксированные: viewer — один человек, full-members —
он и коллега. Поэтому `internal` шире `self`, как в настоящей организации.
"""
import json
import sys

SOURCE_NAME = "google-workspace"
SERVED_TEMPLATES = ["viewer", "full-members", "group/<group-address>"]
MEMBERS = {
    "viewer": ["viewer@corp.example"],
    "full-members": ["viewer@corp.example", "colleague@corp.example"],
}


def main():
    request = json.load(sys.stdin)
    if request.get("version") != 1 or request.get("kind") != "audience" or request.get("name") != SOURCE_NAME:
        raise ValueError("unexpected consult")
    if request.get("declaration", {}).get("templates") != SERVED_TEMPLATES:
        print("audience stub: declared templates differ", file=sys.stderr)
        raise SystemExit(2)
    artifact = request.get("artifact") or {}
    if "member" in artifact:
        answer = {"principal": None}
    elif artifact.get("selector") in MEMBERS:
        answer = {"members": MEMBERS[artifact["selector"]]}
    else:
        raise ValueError(f"{artifact!r} names no collection this stub serves")
    json.dump({"version": 1, "answer": answer}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"audience stub: {error}", file=sys.stderr)
        raise SystemExit(1)
