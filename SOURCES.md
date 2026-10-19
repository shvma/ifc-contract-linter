# Источники

2026-10-19. Каналы: GitHub (`gh`, авторизован), raw.githubusercontent.com по тегу, страница справки Google. Реестры пакетов не нужны: свой код здесь только линтер. Утверждения о платформе — с дословными цитатами из первоисточника; интерпретации помечены отдельно.

## Факты

**Контракт на зафиксированной версии.** `archestra-ai/openappa`, тег `v0.34.0` (коммит `4b62ce09427682bb9ea7de4609f394f050b01ba7`), файл `marketplace/batteries/google-workspace/appa.toml`. Снимок: `results/google-workspace-appa-v0.34.0.toml`, sha256 `dc3d120d…e8c117`. Прошлое чтение 2026-10-16 шло по ветке `main` без коммита; с этого момента всё опирается на тег, а не на подвижную ветку.

- Чтения (`read_file_content`, `download_file_content`, `get_file_metadata`, `get_file_permissions`, `search_files`, `list_recent_files`): `delta = { trust = "suspicious", audience = ["self"] }`.
- Записи (`create_file`, `copy_file`, `update_file`, `trash_file`): `requires = { trust = "trusted", audience = { contains = ["internal"] } }`, `effects = ["google-workspace.changed"]`, ревью нет.
- `share_file`: `requires = { trust = "trusted", audience = { contains = ["public"] }, attention = ["google-workspace-review"] }`.
- Инструмента с именем `move` в батарее нет (README батареи: «all 11 of its tools»). **Поправка 2026-10-29:** перенос всё же есть — он спрятан в `update_file` с аргументом `parentId`, см. блок «Установлено 2026-10-29» ниже.

**Что авторы сами пишут об ограничениях** (README батареи, тот же тег; снимок `results/google-workspace-README-v0.34.0.md`, sha256 `34a1482d…6cc7`; в исходнике цитаты разбиты переносами строк):
> "The connector keeps its own Drive token, and no tool reports who can see a file"

> "A trajectory that reads a file cannot then write to Drive or send what it read to `internal` without a remedy."

> "`share_file` exposes the whole file, which is not a value the policy tracks."

**Поведение Google Drive** ([справка «Share and manage access to files and folders in Google Drive»](https://support.google.com/drive/answer/7166529?hl=en), загружено 2026-10-19):
> "When you share a folder, all files and subfolders inside it inherit those same sharing permissions."

> "If your file is inside a shared folder, the folder’s permissions override any settings you choose for the file."

Гипотеза кейса про наследование доступа папкой подтверждена первоисточником.

**Воспроизведение без модели есть готовое.** `appa replay` гоняет сценарии `.appa`: цепочка вызовов `инструмент { аргументы }`, после каждого `expect allow|deny`. Пример `examples/tests/secret-stays-inside/` на том же теге. Контракт умеет сужать инструмент по аргументу: `name = "mcp/files/read(path:/hr/*)"` и связывать требование с аргументом: `requires = { audience = { contains = ["$to"] } }`.

**Установлено 2026-10-29** (схема 11 инструментов коннектора claude.ai Google Drive снята, `results/connector-tools-list-2026-10-29.json`; ни один инструмент не вызывался):
- У `create_file`, `copy_file`, `update_file` есть аргумент папки-получателя `parentId`.
- Перенос в батарее **есть**: это `update_file` с `parentId` («If the file has an existing parent, it will be replaced, resulting in a folder move»). Ревью ему не нужно, как `create_file` и `copy_file`.
- Контракт сверен на v0.37.0 и `main` (коммит `fe49707`, 2026-10-29): sha256 тот же, что на v0.34.0 (`results/pin-check-2026-10-29.txt`).
- `appa` 0.34.0 (`appa-aarch64-apple-darwin`, сборка из релизов OpenAPPA) поставлен в `~/.local/bin/appa`; replay прогоняется через `./run.sh`.

## Что это меняет в кейсе (не проверено на живом развёртывании)

1. **Зазор уже, чем в постановке.** Постановка описывает «внутренние данные уходят наружу без ревью». Но после любого чтения из Drive контекст помечен `suspicious`, а записи требуют `trusted`. Поэтому сценарий «инъекция в документе Drive → агент кладёт файл в общую папку» монитор **блокирует**. Авторы это закладывали (цитата выше).
2. **Где зазор остаётся.** (а) Данные из другого источника, помеченные `trusted` и `internal`, записываются через `create_file` или `update_file` в папку, у которой есть внешний доступ: контракт считает читателями `internal`, а по Google их больше. (б) `copy_file` переносит содержимое внутри Drive, не проходя через контекст агента. Метки прочитанного его не касаются, а копия в общей папке получает её доступ. Оговорка: id исходного файла агент обычно получает через `search_files`, а это помечает контекст `suspicious`, и запись запрещается; путь реален, только когда id даёт пользователь.
3. **Кто источник.** Раз недоверенный ввод в той же траектории блокирует запись, внешнему атакующему через инъекцию сюда не пройти. Остаются ошибка модели, ошибка пользователя и инсайдер, который заранее открыл папку наружу. Это меняет сложность эксплуатации и риск: ниже, чем звучит в постановке. README формулирует находку под этот, более узкий зазор.
4. **Готовое решение берём.** Воспроизведение (`appa replay` + `.appa`) берём как есть. Исправленный контракт строится средствами самого формата: сужение по аргументу папки (если он есть) или `attention` на запись. Свой код только линтер.

| Нужно | Берём | Решение |
|---|---|---|
| Воспроизведение одной командой | `appa replay` v0.34.0 | ADOPT |
| Исправленный контракт | формат `appa.toml`: сужение по аргументу, `attention` | ADOPT, пишет автор |
| Проверка любых контрактов на «запись без ревью» | своего готового не найдено | BUILD: линтер `checker/`, перевести на настоящий `appa.toml` |
