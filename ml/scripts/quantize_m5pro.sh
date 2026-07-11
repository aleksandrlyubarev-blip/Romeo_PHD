#!/usr/bin/env bash
# Квантизация merged-чекпойнта Sa2VA-InternVL3-14B под Apple M5 Pro (§9 ТЗ).
# Запускается НА Mac (Apple Silicon). Два пути: MLX (рекомендуется) и/или llama.cpp GGUF.
# SAM2-голова квантуется/экспортируется отдельно (Core ML) — здесь не покрывается.
#
#   bash ml/scripts/quantize_m5pro.sh /path/to/merged_hf  out_dir  [mlx|gguf|both]
set -euo pipefail

SRC="${1:?путь к merged HF-чекпойнту (xtuner convert merge ...)}"
OUT="${2:?выходная директория}"
WHAT="${3:-both}"
QBITS="${QBITS:-4}"                 # 4 (база) или 8 (high-quality)
GGUF_QUANT="${GGUF_QUANT:-Q4_K_M}"
mkdir -p "$OUT"

if [ "$WHAT" = "mlx" ] || [ "$WHAT" = "both" ]; then
  echo "== MLX: конвертация в ${QBITS}-bit -> $OUT/mlx =="
  # mlx-vlm для мультимодальных моделей; для текстовой части подошёл бы mlx_lm.convert.
  python3 -m pip install -U mlx mlx-vlm >/dev/null
  python3 -m mlx_vlm.convert --hf-path "$SRC" --mlx-path "$OUT/mlx" -q --q-bits "$QBITS"
  echo "MLX-модель: $OUT/mlx  (~$(( QBITS * 14 / 8 ))GB порядка для 14B; уточнить замером)"
fi

if [ "$WHAT" = "gguf" ] || [ "$WHAT" = "both" ]; then
  echo "== llama.cpp: конвертация в GGUF + квантизация $GGUF_QUANT -> $OUT/gguf =="
  if [ ! -d "$OUT/llama.cpp" ]; then
    git clone --depth 1 https://github.com/ggml-org/llama.cpp "$OUT/llama.cpp"
    make -C "$OUT/llama.cpp" -j
  fi
  python3 "$OUT/llama.cpp/convert_hf_to_gguf.py" "$SRC" --outfile "$OUT/gguf/model-f16.gguf" --outtype f16
  "$OUT/llama.cpp/llama-quantize" "$OUT/gguf/model-f16.gguf" "$OUT/gguf/model-${GGUF_QUANT}.gguf" "$GGUF_QUANT"
  echo "GGUF-модель: $OUT/gguf/model-${GGUF_QUANT}.gguf"
  echo "Примечание: поддержка vision-проектора InternVL в llama.cpp/GGUF зависит от версии — проверить mmproj."
fi

cat <<'EOF'

Дальше:
  * замерить на M5 Pro: время на 1 изображение (end-to-end), токенов/с, пиковую unified memory,
    деградацию метрик vs FP16 (см. §9.2 ТЗ) — числа фиксировать вместе с конфигом запуска;
  * инференс: python3 -m pcba.run_m5pro --model <out>/mlx --image <img> --golden <golden.json>
  * SAM2 для уточнения масок — отдельно через Core ML / ONNX Runtime (Metal/ANE).
EOF
