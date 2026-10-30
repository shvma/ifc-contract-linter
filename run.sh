#!/usr/bin/env bash
# Полная проверка одной командой. Код выхода 0 — всё совпало с ожиданиями.
# 1) Линтер контракта: поставляемый контракт OpenAPPA v0.34.0 (= v0.37.0 и main на 2026-10-30,
#    тот же sha256; снимок в results/), черновик исправления replay/fixed, контракт PR #750
#    и чужая батарея slack v0.37.0. Нужен Python 3.11+ (tomllib) или пакет tomli.
# 2) appa replay: решение монитора на тех же правилах (replay/). Нужен appa 0.34.0.
#    Модель PR #750 исполняет настоящий drive-readers.py из PR: ему нужен Python 3.10+.
# Без appa или Python 3.10+ шаги 1 отрабатывают, затем выход с кодом 2: проверка неполная.
set -euo pipefail
cd "$(dirname "$0")"
PINNED=dc3d120de8f06ee17f594db0cca078c7c87699fd36c434188e9c52c6f0e8c117
GOT=$(shasum -a 256 results/google-workspace-appa-v0.34.0.toml | cut -d' ' -f1)
[ "$GOT" = "$PINNED" ] || { echo "снимок контракта изменён: $GOT" >&2; exit 1; }
echo "sha256 снимка: $GOT (закреплён)"
(cd checker && python3 -m unittest -v test_check)

lint() {  # lint <ожидаемый код> <аргументы линтера...>
  local want=$1; shift
  set +e
  python3 checker/check_contract.py "$@"
  local got=$?
  set -e
  [ "$got" -eq "$want" ] || { echo "линтер: ждали код $want, получили $got ($*)" >&2; exit 1; }
}
{
  echo "--- поставляемый контракт v0.34.0 (ждём пробелы) ---"
  lint 1 checker/inventory.json results/google-workspace-appa-v0.34.0.toml
  echo "--- черновик исправления, вариант «б» (ждём чисто) ---"
  lint 0 checker/inventory.json --allow replay/fixed/allowlist.json replay/fixed/contract.toml
  echo "--- PR #750 @2a9397b (ждём: пробелов нет, аннотатор к проверке трассами) ---"
  lint 0 checker/inventory.json results/upstream-pr750-2a9397b/appa.toml
} | tee results/linter-run.txt
echo "--- чужая батарея: slack v0.37.0, черновой инвентарь (ждём пробелы) ---"
lint 1 checker/inventory-slack.json results/slack-appa-v0.37.0.toml | tee results/linter-slack-v0.37.0.txt

APPA="${APPA:-$(command -v appa || echo "$HOME/.local/bin/appa")}"
[ -x "$APPA" ] || { echo "нет appa: линтер прошёл, replay не запускался; проверка неполная (README, «Как воспроизвести»)" >&2; exit 2; }

# Python 3.10+ для drive-readers.py (оператор match). PY310 задаёт явно.
PY310="${PY310:-}"
if [ -z "$PY310" ]; then
  for c in python3.13 python3.12 python3.11 python3.10 python3 "$HOME"/.local/share/uv/python/cpython-3.1*/bin/python3; do
    p=$(command -v "$c" 2>/dev/null || true)
    [ -n "$p" ] && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null && { PY310=$p; break; }
  done
fi
[ -n "$PY310" ] || { echo "нет Python 3.10+: модель PR #750 не запускается; задайте PY310; проверка неполная" >&2; exit 2; }
PYBIN=$(mktemp -d)
trap 'rm -rf "$PYBIN"' EXIT
ln -s "$PY310" "$PYBIN/python3"

replay() {  # replay <модель> <пути...>; модель pr750 видит python3 >= 3.10
  local model=$1; shift
  if [ "$model" = pr750 ]; then
    PATH="$PYBIN:$PATH" "$APPA" replay --config "replay/$model/contract.toml" "$@"
  else
    "$APPA" replay --config "replay/$model/contract.toml" "$@"
  fi
}

echo "--- appa replay: $("$APPA" --version), python для PR #750: $("$PY310" --version) ---"
rm -f results/pr750-annotations.jsonl
export DRIVE_READERS_LOG="$PWD/results/pr750-annotations.jsonl"
{
  echo "# gap (правила поставляемого контракта):"
  replay gap -v replay/gap
  echo "# fixed (черновик исправления, вариант «б»; пробы критика — critic-*):"
  replay fixed -v replay/fixed
  echo "# pr750 (PR archestra-ai/OpenAPPA#750 @2a9397b, аннотатор на фикстуре):"
  replay pr750 -v replay/pr750
  for probe in replay/probes/bool-selector replay/probes/no-audience-source; do
    echo "# проба: $(basename "$probe")"
    "$APPA" replay --config "$probe/contract.toml" -v "$probe"
  done
} 2>&1 | grep -v 'WARN' | tee results/appa-replay.txt
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "replay: есть провалы, см. results/appa-replay.txt" >&2; exit 1; }
# replay гоняет трассы параллельно: порядок строк лога случайный, сортируем.
LC_ALL=C sort -o results/pr750-annotations.jsonl results/pr750-annotations.jsonl

# Проба: id, которого Drive не знает, против PR #750. Ждём «could not run»: аннотатор падает на 404.
echo "# проба: pr750-unknown-id (ждём could not run)" | tee -a results/appa-replay.txt
set +e
out=$(PATH="$PYBIN:$PATH" "$APPA" replay --config replay/pr750/contract.toml replay/probes/pr750-unknown-id 2>&1 | grep -v 'WARN')
set -e
echo "$out" | tee -a results/appa-replay.txt
echo "$out" | grep -q '1 could not run' || { echo "проба pr750-unknown-id: ждали could not run" >&2; exit 1; }

# 3) Почему deny: replay печатает причину только на провале, поэтому каждое
#    `expect deny` переворачивается во временной копии сценария.
echo "--- причины отказов -> results/deny-reasons.txt ---"
{
  for model in gap fixed pr750 probes/bool-selector probes/no-audience-source; do
    tmp=$(mktemp -d)
    for f in replay/$model/*.appa; do
      grep -q 'expect deny' "$f" && sed 's/expect deny/expect allow/' "$f" > "$tmp/$(basename "$f")"
    done
    echo "# $model"
    if [ "$model" = pr750 ]; then
      DRIVE_READERS_LOG=/dev/null PATH="$PYBIN:$PATH" "$APPA" replay --config replay/$model/contract.toml "$tmp" 2>&1
    else
      "$APPA" replay --config replay/$model/contract.toml "$tmp" 2>&1
    fi | sed "s#$tmp#replay/$model#" | grep -E '^replay/|^ +- |^ +\[appa\] [^B]' || true
    rm -rf "$tmp"
  done
} | tee results/deny-reasons.txt
echo "полная проверка пройдена"
