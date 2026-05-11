#!/usr/bin/env bash
# Подготовка датасета end-to-end (на синтетическом сэмпле — для проверки пайплайна).
# Для реальных данных: подменить шаг (1) на свой COCO-датасет (или выход «Бригады»,
# приведённый к COCO) и оставить шаги (2)-(4) как есть.
#
# Запуск:  cd ml && bash scripts/prepare_dataset.sh [N_IMAGES]
set -euo pipefail
cd "$(dirname "$0")/.."          # -> ml/

N="${1:-8}"
DATA="${PCBA_DATA_DIR_ROOT:-data}"
COCO_DIR="$DATA/sample_coco"
SA2VA_JSONL="$DATA/sa2va/all.jsonl"
CONTRASTIVE_JSONL="$DATA/contrastive/pairs.jsonl"
MANIFEST_DIR="$DATA/manifest"

echo "[1/4] generate synthetic COCO sample ($N images) -> $COCO_DIR"
python3 -m pcba.make_sample_dataset --out "$COCO_DIR" --n "$N" --seed 42

echo "[2/4] COCO -> Sa2VA conversation JSONL -> $SA2VA_JSONL"
python3 -m pcba.coco_to_sa2va --coco "$COCO_DIR/annotations.json" \
  --images-prefix images --out "$SA2VA_JSONL" --refer-per-image 1 --seed 0

echo "[3/4] build contrastive pairs (track C) -> $CONTRASTIVE_JSONL"
python3 -m pcba.build_contrastive --in "$SA2VA_JSONL" --out "$CONTRASTIVE_JSONL"

echo "[4/4] train/val/test split + dataset card -> $MANIFEST_DIR"
python3 -m pcba.make_manifest --in "$SA2VA_JSONL" --out-dir "$MANIFEST_DIR" --val 0.15 --test 0.15 --seed 13

echo
echo "done. tree:"
find "$DATA" -maxdepth 3 -type f | sort
echo
echo "dataset card:"
cat "$MANIFEST_DIR/dataset_card.json"
