#!/usr/bin/env bash
# LoRA/QLoRA-обучение Sa2VA-InternVL3-14B на одной GPU-ноде (локально или в контейнере).
# Требует установленных torch / xtuner / sa2va (см. ml/Dockerfile, ml/requirements.txt).
#
# Запуск:
#   cd ml
#   PCBA_DATA_DIR=data/manifest PCBA_IMAGE_ROOT=data/sample_coco \
#   PCBA_OUTPUT_DIR=work_dirs/sa2va_pcba_lora \
#     bash scripts/train_lora_local.sh
#
# Multi-GPU (один узел): NPROC_PER_NODE=8 bash scripts/train_lora_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."          # -> ml/

CONFIG="configs/sa2va_internvl3_14b_pcba_lora.py"
NPROC_PER_NODE="${NPROC_PER_NODE:-1}"
DEEPSPEED="${DEEPSPEED:-deepspeed_zero2}"   # zero2 для одной ноды; zero3 для большего числа GPU/узлов

export PCBA_DATA_DIR="${PCBA_DATA_DIR:-data/manifest}"
export PCBA_IMAGE_ROOT="${PCBA_IMAGE_ROOT:-data/sample_coco}"
export PCBA_OUTPUT_DIR="${PCBA_OUTPUT_DIR:-work_dirs/sa2va_internvl3_14b_pcba_lora}"
export SA2VA_BASE_MODEL="${SA2VA_BASE_MODEL:-ByteDance/Sa2VA-InternVL3-14B}"

echo "base model : $SA2VA_BASE_MODEL"
echo "data dir   : $PCBA_DATA_DIR"
echo "image root : $PCBA_IMAGE_ROOT"
echo "output dir : $PCBA_OUTPUT_DIR"
echo "gpus       : $NPROC_PER_NODE | deepspeed: $DEEPSPEED"

if ! command -v xtuner >/dev/null 2>&1; then
  echo "ERROR: 'xtuner' не найден. Установите зависимости: pip install -r requirements.txt и Sa2VA из исходников." >&2
  exit 1
fi

if [ "$NPROC_PER_NODE" -gt 1 ]; then
  NPROC_PER_NODE="$NPROC_PER_NODE" xtuner train "$CONFIG" --deepspeed "$DEEPSPEED" --launcher pytorch
else
  xtuner train "$CONFIG" --deepspeed "$DEEPSPEED"
fi

echo
echo "training finished. Merge LoRA in fp16 for inference / quantization (M5 Pro):"
echo "  xtuner convert pth_to_hf $CONFIG $PCBA_OUTPUT_DIR/last_checkpoint $PCBA_OUTPUT_DIR/hf"
echo "  xtuner convert merge $SA2VA_BASE_MODEL $PCBA_OUTPUT_DIR/hf $PCBA_OUTPUT_DIR/merged --max-shard-size 4GB"
echo "Дальше: квантизация merged-модели под Apple Silicon (MLX / llama.cpp) — см. §9 ТЗ."
