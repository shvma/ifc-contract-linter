# Снимок PR archestra-ai/OpenAPPA#750

- PR: https://github.com/archestra-ai/OpenAPPA/pull/750, «fix(google-workspace): check Drive writes against who reads their target», автор vadim0x60, открыт 2026-10-29, на 2026-10-30 не слит (`results/pin-check-2026-10-30.txt`).
- Коммит головы: `2a9397baf5305145bb10eb67fa92f2a3135b450b`, каталог `marketplace/batteries/google-workspace/`.
- Файлы взяты через `gh api repos/archestra-ai/OpenAPPA/contents/<путь>?ref=2a9397b` 2026-10-30, без правок:

| Файл | sha256 |
|---|---|
| `appa.toml` | `826227e121d16d850d19011fb5277e57b96a11b3b106a4c507b90a17ef11e0e0` |
| `drive-readers.py` | `443b078e452a7cc1f8cab4a6af287f458aed4cd138ff3b897d78a99aa61e104e` |
| `audience-source.py` | `b4aa6fce6490a1f3719bf62e0db8402ab646f56791320e212c3ff5fbc38a3cd1` |

`replay/drive-readers-fixture.py` сверяет sha256 двух скриптов перед загрузкой. Лицензия — исходного проекта (`../OPENAPPA-LICENSE.md`).
