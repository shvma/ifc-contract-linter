"""Аннотатор google-workspace.drive-readers из PR OpenAPPA#750 на фикстуре вместо Google.

Исполняет настоящий drive-readers.py из снимка PR (../results/upstream-pr750-2a9397b/,
голова 2a9397b, sha256 сверяется перед загрузкой): разбор запроса, проверку мандата и
функцию answer() — без правок. Подменён только HTTP-клиент: вместо Drive API и Admin SDK
отвечает таблица ниже. Токен не нужен и не читается.

Фикстура (выдумана, id те же, что в трассах):
  viewer@corp.example         зритель, домен Workspace corp.example
  colleague@corp.example      активный пользователь Workspace
  finance@corp.example        группа: только зритель
  FOLDER_INTERNAL_REPORTS     зритель + домен corp.example
  FOLDER_SHARED_ANYONE_WITH_LINK  зритель + anyone
  FILE_INTERNAL_DIFF          зритель + домен corp.example, лежит в FOLDER_INTERNAL_REPORTS
  FILE_FINANCE_ONLY           зритель + группа finance
  FOLDER_FINANCE_RESTRICTED   зритель + группа finance, наследование выключено, лежит в
                              FOLDER_SHARED_ANYONE_WITH_LINK (аннотатор родителя не спрашивает)
Любой другой id — 404, как у Drive для неизвестного файла: аннотатор падает, вызов отклоняется.

Если задан DRIVE_READERS_LOG, каждый запрос и ответ дописывается туда строкой JSON.
"""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

UPSTREAM = Path(__file__).resolve().parent.parent / "results" / "upstream-pr750-2a9397b"
PINNED = {
    "drive-readers.py": "443b078e452a7cc1f8cab4a6af287f458aed4cd138ff3b897d78a99aa61e104e",
    "audience-source.py": "b4aa6fce6490a1f3719bf62e0db8402ab646f56791320e212c3ff5fbc38a3cd1",
}

for name, digest in PINNED.items():
    got = hashlib.sha256((UPSTREAM / name).read_bytes()).hexdigest()
    if got != digest:
        print(f"drive-readers fixture: {name} changed: {got}", file=sys.stderr)
        raise SystemExit(2)

sys.dont_write_bytecode = True  # снимок в results/ остаётся как скачан
SPEC = importlib.util.spec_from_file_location("drive_readers", UPSTREAM / "drive-readers.py")
ANNOTATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANNOTATOR)
SOURCE = ANNOTATOR.SOURCE

DOMAIN = "corp.example"
VIEWER = "viewer@corp.example"
USERS = {VIEWER: {"primaryEmail": VIEWER}, "colleague@corp.example": {"primaryEmail": "colleague@corp.example"}}
GROUPS = {"finance@corp.example": [{"type": "USER", "email": VIEWER}]}
ME = {"type": "user", "emailAddress": VIEWER}
ORG = {"type": "domain", "domain": DOMAIN}
FINANCE = {"type": "group", "emailAddress": "finance@corp.example"}
FILES = {
    "FOLDER_INTERNAL_REPORTS": {"permissions": [ME, ORG], "parents": []},
    "FOLDER_SHARED_ANYONE_WITH_LINK": {"permissions": [ME, {"type": "anyone"}], "parents": []},
    "FILE_INTERNAL_DIFF": {"permissions": [ME, ORG], "parents": ["FOLDER_INTERNAL_REPORTS"]},
    "FILE_FINANCE_ONLY": {"permissions": [ME, FINANCE], "parents": ["FOLDER_INTERNAL_REPORTS"]},
    "FOLDER_FINANCE_RESTRICTED": {"permissions": [ME, FINANCE], "parents": ["FOLDER_SHARED_ANYONE_WITH_LINK"]},
}


def call(url, **params):
    if url == SOURCE.USERINFO_URL:
        return {"email": VIEWER, "email_verified": True, "hd": DOMAIN}
    directory = SOURCE.DIRECTORY_ROOT + "/"
    if url.startswith(directory + "users/"):
        email = url[len(directory + "users/"):].replace("%40", "@")
        if email in USERS:
            return USERS[email]
        raise SOURCE.NotFound(url)
    if url.startswith(directory + "groups/") and url.endswith("/members"):
        group = url[len(directory + "groups/"):-len("/members")].replace("%40", "@")
        if group in GROUPS:
            return {"members": GROUPS[group]}
        raise SOURCE.NotFound(url)
    drive = ANNOTATOR.DRIVE_ROOT + "/files/"
    if url.startswith(drive):
        rest = url[len(drive):]
        file_id, _, tail = rest.partition("/")
        if file_id not in FILES:
            raise SOURCE.NotFound(url)
        if tail == "permissions":
            return {"permissions": FILES[file_id]["permissions"]}
        if tail == "" and params.get("fields") == "parents":
            return {"parents": FILES[file_id]["parents"]}
    raise RuntimeError(f"fixture has no answer for {url} {params}")


def main():
    consult = json.load(sys.stdin)
    tool, arguments = ANNOTATOR.call_of(consult)
    ANNOTATOR.check_declaration(consult)
    answer = ANNOTATOR.answer(ANNOTATOR.Drive(call), tool, arguments)
    log = os.environ.get("DRIVE_READERS_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as out:
            out.write(json.dumps({"tool": tool, "arguments": arguments, "answer": answer}, ensure_ascii=False) + "\n")
    json.dump({"version": 1, "answer": answer}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as error:
        print(f"{ANNOTATOR.NAME} (fixture): {error}", file=sys.stderr)
        raise SystemExit(1)
