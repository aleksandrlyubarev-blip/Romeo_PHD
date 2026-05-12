#!/usr/bin/env bash
# Трек A (§5.1 ТЗ): обучение YOLOv11-seg на PCBA-датасете. Требует `ultralytics`.
# SAM2-уточнение масок применяется на инференсе отдельно (промпт = bbox от YOLO).
#
#   pip install ultralytics
#   cd ml
#   python3 -m baseline.coco_to_yolo --coco <coco.json> --image-root <images> --out data/yolo
#   DATA=data/yolo/data.yaml MODEL=yolo11s-seg.pt EPOCHS=100 IMGSZ=1280 bash baseline/train_yolo.sh
set -euo pipefail
cd "$(dirname "$0")/.."          # -> ml/

DATA="${DATA:-data/yolo/data.yaml}"
MODEL="${MODEL:-yolo11s-seg.pt}"     # s/m/l/x — баланс точности и скорости на edge/M5 Pro
EPOCHS="${EPOCHS:-100}"
IMGSZ="${IMGSZ:-1280}"               # мелкие компоненты -> высокое разрешение
BATCH="${BATCH:-8}"
PROJECT="${PROJECT:-work_dirs/yolo_pcba}"
NAME="${NAME:-yolo11_seg}"

if ! command -v yolo >/dev/null 2>&1 && ! python3 -c "import ultralytics" >/dev/null 2>&1; then
  echo "ERROR: ultralytics не установлен (pip install ultralytics)." >&2
  exit 1
fi

echo "data=$DATA model=$MODEL epochs=$EPOCHS imgsz=$IMGSZ batch=$BATCH"
yolo segment train data="$DATA" model="$MODEL" epochs="$EPOCHS" imgsz="$IMGSZ" batch="$BATCH" \
  project="$PROJECT" name="$NAME" patience=20 seed=42

echo
echo "validate:  yolo segment val   data=$DATA model=$PROJECT/$NAME/weights/best.pt imgsz=$IMGSZ"
echo "export:    yolo export model=$PROJECT/$NAME/weights/best.pt format=coreml imgsz=$IMGSZ  # для M5 Pro"
echo "ONNX:      yolo export model=$PROJECT/$NAME/weights/best.pt format=onnx imgsz=$IMGSZ"
echo "Дальше: предсказания YOLO -> bbox -> SAM2 (уточнение масок) -> привести к схеме pcba/schema.py -> pcba.compare."
