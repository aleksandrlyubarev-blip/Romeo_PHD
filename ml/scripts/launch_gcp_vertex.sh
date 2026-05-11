#!/usr/bin/env bash
# Submit Vertex AI Custom Training Job для LoRA-файнтюна Sa2VA-InternVL3-14B.
# Образ собирается из ml/Dockerfile и пушится в Artifact Registry.
#
# Предпосылки:
#   gcloud auth login && gcloud config set project "$PROJECT_ID"
#   датасет загружен в GCS: gsutil -m cp -r ml/data ${BUCKET}/pcba/data
#   образ собран и запушен (см. ml/Dockerfile)
#
# Запуск:
#   PROJECT_ID=my-proj REGION=us-central1 BUCKET=gs://my-bucket \
#   IMAGE_URI=us-central1-docker.pkg.dev/my-proj/ml/sa2va-pcba:latest \
#   MACHINE=a2-ultragpu-1g ACCELERATOR=NVIDIA_A100_80GB ACCEL_COUNT=1 \
#     bash scripts/launch_gcp_vertex.sh
#
# Для H100: MACHINE=a3-highgpu-8g ACCELERATOR=NVIDIA_H100_80GB ACCEL_COUNT=8 (и NPROC_PER_NODE=8 + zero3).
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
: "${REGION:=us-central1}"
: "${BUCKET:?set BUCKET (gs://...)}"
: "${IMAGE_URI:?set IMAGE_URI (Artifact Registry)}"
: "${MACHINE:=a2-ultragpu-1g}"
: "${ACCELERATOR:=NVIDIA_A100_80GB}"
: "${ACCEL_COUNT:=1}"
: "${NPROC_PER_NODE:=1}"
: "${DEEPSPEED:=deepspeed_zero2}"
JOB_NAME="${JOB_NAME:-sa2va-pcba-lora-$(date +%Y%m%d-%H%M%S)}"

DATA_GCS="${BUCKET%/}/pcba/data"
OUT_GCS="${BUCKET%/}/pcba/work_dirs/${JOB_NAME}"

# Команда, выполняемая в контейнере: тянем датасет из GCS, запускаем обучение, складываем чекпойнты обратно.
read -r -d '' CMD <<EOF || true
set -euo pipefail
mkdir -p /workspace/run/data /workspace/run/work_dirs
gsutil -m rsync -r ${DATA_GCS} /workspace/run/data
cd /workspace/ml
PCBA_DATA_DIR=/workspace/run/data/manifest \
PCBA_IMAGE_ROOT=/workspace/run/data/sample_coco \
PCBA_OUTPUT_DIR=/workspace/run/work_dirs/${JOB_NAME} \
SA2VA_BASE_MODEL=ByteDance/Sa2VA-InternVL3-14B \
NPROC_PER_NODE=${NPROC_PER_NODE} DEEPSPEED=${DEEPSPEED} \
  bash scripts/train_lora_local.sh
gsutil -m rsync -r /workspace/run/work_dirs/${JOB_NAME} ${OUT_GCS}
EOF

echo "submitting Vertex AI custom job: $JOB_NAME"
echo "  image      : $IMAGE_URI"
echo "  machine    : $MACHINE x ${ACCEL_COUNT} ${ACCELERATOR}"
echo "  data (GCS) : $DATA_GCS"
echo "  out  (GCS) : $OUT_GCS"

gcloud ai custom-jobs create \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --display-name="$JOB_NAME" \
  --worker-pool-spec="machine-type=${MACHINE},accelerator-type=${ACCELERATOR},accelerator-count=${ACCEL_COUNT},replica-count=1,container-image-uri=${IMAGE_URI}" \
  --args="-c,${CMD}"

echo "done. Tail logs:  gcloud ai custom-jobs stream-logs --region=$REGION <JOB_ID>"
