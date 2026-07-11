#!/usr/bin/env bash
# Юнит-тесты + лёгкая интеграционная проверка всего пайплайна (без модели и без зависимостей).
#   cd ml && bash scripts/run_tests.sh
set -euo pipefail
cd "$(dirname "$0")/.."          # -> ml/

echo "== unit tests =="
python3 -m tests.test_basic

echo
echo "== integration: dataset prep (4 imgs) =="
rm -rf data
PCBA_DATA_DIR_ROOT=data bash scripts/prepare_dataset.sh 4 >/dev/null
test -f data/manifest/train.jsonl && echo "  ok  manifest created"

echo
echo "== integration: track A — COCO -> YOLO-seg =="
python3 -m baseline.coco_to_yolo --coco data/sample_coco/annotations.json \
  --image-root data/sample_coco/images --out data/yolo --val 0.25 --seed 13 --symlink >/dev/null
test -f data/yolo/data.yaml && ls data/yolo/labels/train/*.txt >/dev/null 2>&1 && echo "  ok  yolo dataset + data.yaml"

echo
echo "== integration: downstream — golden -> inject -> compare -> verdict metrics =="
GID="$(python3 - data/manifest/train.jsonl <<'PY'
import json, sys
for line in open(sys.argv[1]):
    r = json.loads(line)
    if r.get("meta", {}).get("kind") == "describe":
        print(r["meta"]["image_id"]); break
PY
)"
python3 -m pcba.golden build --board-type t --from data/manifest/train.jsonl --image-id "$GID" --out data/golden/t.json >/dev/null
python3 -m pcba.inject_defects --from data/manifest/train.jsonl --image-id "$GID" --n-bad 6 --n-good 3 --seed 5 --out data/eval/cases.jsonl >/dev/null
python3 -m eval.metrics verdicts --cases data/eval/cases.jsonl --golden data/golden/t.json | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['n_cases']==9; print('  ok  verdicts:', {k:d[k] for k in ('end_to_end_accuracy','false_call_rate','escape_rate','defect_recall')})"

echo
echo "== integration: pipeline (mock backend, GT-echo) =="
IMG="$(ls data/sample_coco/images | head -1)"
python3 -m pcba.pipeline --image "data/sample_coco/images/$IMG" --image-id "$GID" \
  --golden data/golden/t.json --backend mock --gt-echo data/manifest/train.jsonl --out data/eval/report.json >/dev/null || true
python3 -c "import json; r=json.load(open('data/eval/report.json')); assert r['verdict'] in ('OK','NOK'); print('  ok  pipeline report verdict=', r['verdict'], 'defects=', len(r['defects']))"

echo
echo "ALL CHECKS PASSED"
