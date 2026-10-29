#!/usr/bin/env bash
# 1) Линтер контракта на настоящем контракте OpenAPPA v0.34.0 (= v0.37.0 и main на 2026-10-29,
#    тот же sha256; снимок в results/) и на исправленной модели replay/fixed.
#    Нужен Python 3.11+ (tomllib) или пакет tomli (на стенде: pip3 install --user tomli).
# 2) appa replay: решение монитора на тех же правилах (replay/), если установлен appa.
set -euo pipefail
cd "$(dirname "$0")"
PINNED=dc3d120de8f06ee17f594db0cca078c7c87699fd36c434188e9c52c6f0e8c117
GOT=$(shasum -a 256 results/google-workspace-appa-v0.34.0.toml | cut -d' ' -f1)
[ "$GOT" = "$PINNED" ] || { echo "снимок контракта изменён: $GOT" >&2; exit 1; }
echo "sha256 снимка: $GOT (закреплён)"
(cd checker && python3 -m unittest -v test_check)
echo "--- поставляемый контракт v0.34.0 ---"
python3 checker/check_contract.py checker/inventory.json results/google-workspace-appa-v0.34.0.toml || true
echo "--- исправленная модель (черновик варианта «б») ---"
python3 checker/check_contract.py checker/inventory.json --allow replay/fixed/allowlist.json replay/fixed/contract.toml

APPA="${APPA:-$(command -v appa || echo "$HOME/.local/bin/appa")}"
if [ -x "$APPA" ]; then
  echo "--- appa replay: $("$APPA" --version) ---"
  {
    echo "# gap (правила поставляемого контракта):"
    "$APPA" replay --config replay/gap/contract.toml -v replay/gap
    echo "# fixed (черновик исправления, вариант «б»):"
    "$APPA" replay --config replay/fixed/contract.toml -v replay/fixed
    for probe in replay/probes/*/; do
      echo "# проба: $(basename "$probe")"
      "$APPA" replay --config "$probe/contract.toml" -v "$probe"
    done
  } 2>&1 | tee results/appa-replay.txt
  # 3) Почему deny: replay печатает причину только на провале, поэтому каждое
  #    `expect deny` переворачивается во временной копии сценария.
  echo "--- причины отказов -> results/deny-reasons.txt ---"
  {
    for model in gap fixed probes/bool-selector probes/no-audience-source; do
      tmp=$(mktemp -d)
      for f in replay/$model/*.appa; do
        grep -q 'expect deny' "$f" && sed 's/expect deny/expect allow/' "$f" > "$tmp/$(basename "$f")"
      done
      echo "# $model"
      "$APPA" replay --config replay/$model/contract.toml "$tmp" 2>&1 \
        | sed "s#$tmp#replay/$model#" | grep -E '^replay/|^ +- |^ +\[appa\] [^B]' || true
      rm -rf "$tmp"
    done
  } | tee results/deny-reasons.txt
else
  echo "--- appa не установлен, replay пропущен (см. replay/README.md) ---"
fi
