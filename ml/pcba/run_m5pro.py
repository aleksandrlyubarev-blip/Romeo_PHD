"""Локальный инференс на Apple M5 Pro через mlx-vlm (§9 ТЗ).

Бэкенд для pcba/predict.py и pcba/pipeline.py. Требует apple-silicon + `mlx`, `mlx-vlm`
и заранее сконвертированную квантованную модель (см. ml/scripts/quantize_m5pro.sh).

CLI (одиночный прогон с вердиктом):
    python3 -m pcba.run_m5pro --model out/mlx --image board.png --golden golden.json
Или как бэкенд массового инференса:
    python3 -m pcba.predict --backend mlx --model out/mlx --images <dir> --out preds.jsonl
"""
from __future__ import annotations

import argparse
import json
import os

from .predict import extract_first_json, normalize_output
from .schema import describe_prompt


class MLXBackend:
    def __init__(self, mlx_model_path: str, max_tokens: int = 4096, temperature: float = 0.0):
        from mlx_vlm import load
        from mlx_vlm.utils import load_config
        self.model, self.processor = load(mlx_model_path)
        self.config = load_config(mlx_model_path)
        self.max_tokens = max_tokens
        self.temperature = temperature

    def describe(self, image_path: str, image_id: str, w: int, h: int, board_side: str) -> dict:
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template
        if not w or not h:
            try:
                from PIL import Image
                with Image.open(image_path) as im:
                    w, h = im.size
            except Exception:
                pass
        prompt = apply_chat_template(self.processor, self.config, describe_prompt(), num_images=1)
        text = generate(self.model, self.processor, prompt, image=[image_path],
                        max_tokens=self.max_tokens, temperature=self.temperature, verbose=False)
        if isinstance(text, tuple):  # некоторые версии возвращают (text, usage)
            text = text[0]
        return normalize_output(extract_first_json(text), image_id, w, h, board_side)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="директория MLX-модели (quantize_m5pro.sh)")
    ap.add_argument("--image", required=True)
    ap.add_argument("--golden", default=None, help="если задан — сразу вердикт через pcba.compare")
    ap.add_argument("--out", default=None, help="куда записать описание/отчёт (по умолчанию stdout)")
    ap.add_argument("--max-tokens", type=int, default=4096)
    args = ap.parse_args()

    backend = MLXBackend(args.model, max_tokens=args.max_tokens)
    image_id = os.path.splitext(os.path.basename(args.image))[0]
    desc = backend.describe(args.image, image_id, 0, 0, "unknown")

    if args.golden:
        from .golden import GoldenBoard
        from .compare import compare
        with open(args.golden, "r", encoding="utf-8") as f:
            golden = GoldenBoard.from_json(json.load(f))
        res = compare(desc, golden)
        report = {"image_id": image_id, "verdict": res.verdict, "defects": [d.__dict__ for d in res.defects],
                  "description": desc}
        payload = report
        rc = 0 if res.verdict == "OK" else 2
    else:
        payload = desc
        rc = 0

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"-> {args.out}")
    else:
        print(text)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
