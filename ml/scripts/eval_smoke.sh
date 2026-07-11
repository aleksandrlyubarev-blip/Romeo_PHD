#!/usr/bin/env bash
# Smoke-тест downstream-логики: эталон -> симуляция дефектов -> compare -> метрики вердикта.
# Работает на синтетическом сэмпле (для проверки кода, не качества модели).
#
# Запуск:  cd ml && bash scripts/eval_smoke.sh
set -euo pipefail
cd "$(dirname "$0")/.."          # -> ml/

DATA="${PCBA_DATA_DIR_ROOT:-data}"

if [ ! -f "$DATA/manifest/train.jsonl" ]; then
  echo "[prep] dataset not found -> running prepare_dataset.sh"
  PCBA_DATA_DIR_ROOT="$DATA" bash scripts/prepare_dataset.sh 8 >/dev/null
fi

# image_id первого describe-сэмпла из train -> эталонная плата
GID="$(python3 - "$DATA/manifest/train.jsonl" <<'PY'
import json, sys
for line in open(sys.argv[1]):
    r = json.loads(line)
    if r.get("meta", {}).get("kind") == "describe":
        print(r["meta"]["image_id"]); break
PY
)"
echo "[golden] board image_id = $GID"
python3 -m pcba.golden build --board-type smoke_board \
  --from "$DATA/manifest/train.jsonl" --image-id "$GID" --out "$DATA/golden/smoke_board.json"

echo "[cases] simulating defective + good descriptions"
python3 -m pcba.inject_defects --from "$DATA/manifest/train.jsonl" --image-id "$GID" \
  --n-bad 8 --n-good 4 --seed 7 --out "$DATA/eval/cases.jsonl"

echo
echo "=== segmentation/classification metrics (test set vs itself — sanity) ==="
python3 -m eval.metrics seg --pred "$DATA/manifest/test.jsonl" --gt "$DATA/manifest/test.jsonl" --iou 0.5

echo
echo "=== verdict metrics (simulated cases vs golden) ==="
python3 -m eval.metrics verdicts --cases "$DATA/eval/cases.jsonl" --golden "$DATA/golden/smoke_board.json"
