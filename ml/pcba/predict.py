"""Инференс модели описания PCBA: фото -> JSON по схеме pcba/schema.py.

Бэкенды:
  * hf   — transformers + ByteDance/Sa2VA-InternVL3-14B (+ опц. LoRA-адаптер, +опц. steering-вектор трека C);
  * mlx  — квантованная модель на Apple Silicon через mlx-vlm (см. pcba/run_m5pro.py);
  * mock — без модели: либо «эхо» ground-truth из --gt-echo (для отладки downstream-пайплайна),
           либо пустое описание. Полезно в CI и для проверки compare/pipeline без GPU.

CLI:
    python3 -m pcba.predict --images data/sample_coco/annotations.json --image-root data/sample_coco \
        --backend mock --gt-echo data/manifest/test.jsonl --out data/eval/preds.jsonl
    python3 -m pcba.predict --images path/to/dir --backend hf \
        --model ByteDance/Sa2VA-InternVL3-14B --lora work_dirs/.../merged --out preds.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Iterable, Optional

from .schema import SCHEMA_VERSION, SYSTEM_PROMPT, describe_prompt, validate_output


# --------------------------------------------------------------------------- #
# Извлечение JSON из текстового ответа модели
# --------------------------------------------------------------------------- #

def extract_first_json(text: str) -> Optional[dict]:
    """Найти первый сбалансированный JSON-объект в тексте (терпит ```-обёртки и болтовню вокруг)."""
    if not text:
        return None
    s = text.strip()
    # снять markdown-обёртку
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                chunk = s[start:i + 1]
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    start = -1
                    continue
    return None


def normalize_output(obj: Optional[dict], image_id: str, w: int, h: int, board_side: str = "unknown") -> dict:
    """Привести/починить ответ модели к схеме (мягко): проставить недостающие поля, отбросить мусор."""
    base = {
        "schema_version": SCHEMA_VERSION,
        "image_id": image_id,
        "image_size": {"w": int(w), "h": int(h)},
        "board_side": board_side or "unknown",
        "components": [],
        "notes": "",
    }
    if not isinstance(obj, dict):
        base["notes"] = "model output was not valid JSON"
        return base
    size_in = obj.get("image_size")
    if isinstance(size_in, dict) and size_in.get("w") and size_in.get("h"):
        base["image_size"] = {"w": int(size_in["w"]), "h": int(size_in["h"])}
    base["board_side"] = obj.get("board_side") or base["board_side"]
    base["notes"] = obj.get("notes", "") or ""
    comps_in = obj.get("components") or []
    comps_out = []
    for k, c in enumerate(comps_in if isinstance(comps_in, list) else []):
        if not isinstance(c, dict):
            continue
        comps_out.append({
            "id": str(c.get("id") or f"c-{k+1:04d}"),
            "class": c.get("class", "unknown"),
            "subclass": c.get("subclass"),
            "bbox": list(c.get("bbox") or [0, 0, 0, 0])[:4] + [0, 0, 0, 0][:max(0, 4 - len(c.get("bbox") or []))],
            "polygon": c.get("polygon") or [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
            "confidence": float(c.get("confidence", 0.5)) if isinstance(c.get("confidence", 0.5), (int, float)) else 0.5,
            "attributes": c.get("attributes") or {"state": None, "orientation_deg": None},
        })
    base["components"] = comps_out
    return base


# --------------------------------------------------------------------------- #
# Бэкенды
# --------------------------------------------------------------------------- #

class MockBackend:
    """Без модели. Если задан gt_echo — отдаёт ground-truth описание для image_id; иначе пустое."""

    def __init__(self, gt_echo: Optional[str] = None):
        self.by_image: dict = {}
        if gt_echo:
            with open(gt_echo, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if "conversations" in rec:
                        if rec.get("meta", {}).get("kind") != "describe":
                            continue
                        gpt = next((c["value"] for c in rec["conversations"] if c["from"] == "gpt"), None)
                        if not gpt:
                            continue
                        obj = json.loads(gpt)
                        key = str(rec.get("meta", {}).get("image_id"))
                        # также индекс по basename изображения
                        self.by_image[key] = obj
                        self.by_image[os.path.basename(rec.get("image", ""))] = obj
                    else:
                        self.by_image[str(rec.get("image_id"))] = rec

    def describe(self, image_path: str, image_id: str, w: int, h: int, board_side: str) -> dict:
        for key in (str(image_id), os.path.basename(image_path)):
            if key in self.by_image:
                return normalize_output(self.by_image[key], image_id, w, h, board_side)
        return normalize_output({"components": []}, image_id, w, h, board_side)


class HFBackend:
    """transformers + Sa2VA. Точные имена методов берутся из model card ByteDance/Sa2VA на момент запуска."""

    def __init__(self, model_id: str, lora_dir: Optional[str] = None, steering: Optional[str] = None,
                 steer_scale: float = 2.0, dtype: str = "bfloat16", device: str = "cuda"):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(
            model_id, torch_dtype=getattr(torch, dtype), trust_remote_code=True, low_cpu_mem_usage=True,
        ).eval().to(device)
        if lora_dir:
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, lora_dir).merge_and_unload()
        self._steer_handles = []
        if steering:
            from repe.apply_steering import install_steering  # ml/ на sys.path при запуске `python -m`
            with open(steering, "r", encoding="utf-8") as f:
                spec = json.load(f)
            self._steer_handles = install_steering(self.model, spec, scale=steer_scale)

    def describe(self, image_path: str, image_id: str, w: int, h: int, board_side: str) -> dict:
        from PIL import Image
        image = Image.open(image_path).convert("RGB")
        prompt = f"<image>{describe_prompt()}"
        # Sa2VA HF API (см. model card): predict_forward возвращает text (+ маски при наличии <seg>).
        result = self.model.predict_forward(image=image, text=prompt, tokenizer=self.tokenizer)
        text = result["prediction"] if isinstance(result, dict) and "prediction" in result else str(result)
        obj = extract_first_json(text)
        out = normalize_output(obj, image_id, w, h, board_side)
        # при наличии масок от SAM2 — переписать polygon'ы (нормализованные); опускаем детали API.
        return out


def make_backend(args) -> object:
    if args.backend == "mock":
        return MockBackend(gt_echo=args.gt_echo)
    if args.backend == "hf":
        return HFBackend(args.model, lora_dir=args.lora, steering=args.steering, steer_scale=args.steer_scale)
    if args.backend == "mlx":
        from .run_m5pro import MLXBackend  # type: ignore
        return MLXBackend(args.model)
    raise ValueError(f"unknown backend {args.backend!r}")


# --------------------------------------------------------------------------- #
# Перечисление входных изображений
# --------------------------------------------------------------------------- #

def iter_images(images_arg: str, image_root: str) -> Iterable[tuple[str, str, int, int, str]]:
    """Вернуть (image_path, image_id, w, h, board_side). Принимает COCO json или директорию с изображениями."""
    if images_arg.endswith(".json"):
        with open(images_arg, "r", encoding="utf-8") as f:
            coco = json.load(f)
        for im in coco.get("images", []):
            yield (os.path.join(image_root, im["file_name"]), str(im["id"]),
                   int(im.get("width") or 0), int(im.get("height") or 0), im.get("board_side", "unknown"))
    else:
        exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        for name in sorted(os.listdir(images_arg)):
            if os.path.splitext(name)[1].lower() in exts:
                w = h = 0
                try:
                    from PIL import Image
                    with Image.open(os.path.join(images_arg, name)) as im:
                        w, h = im.size
                except Exception:
                    pass
                yield (os.path.join(images_arg, name), os.path.splitext(name)[0], w, h, "unknown")


def main() -> None:
    ap = argparse.ArgumentParser(description="PCBA description inference")
    ap.add_argument("--images", required=True, help="COCO annotations.json или директория с изображениями")
    ap.add_argument("--image-root", default="", help="корень для file_name из COCO")
    ap.add_argument("--out", required=True, help="выходной JSONL (по объекту схемы на изображение)")
    ap.add_argument("--backend", choices=["hf", "mlx", "mock"], default="mock")
    ap.add_argument("--model", default="ByteDance/Sa2VA-InternVL3-14B")
    ap.add_argument("--lora", default=None, help="директория с LoRA-адаптером (merge перед инференсом)")
    ap.add_argument("--steering", default=None, help="steering.json трека C (RepE)")
    ap.add_argument("--steer-scale", type=float, default=2.0)
    ap.add_argument("--gt-echo", default=None, help="(mock) JSONL с GT-описаниями для эха")
    ap.add_argument("--limit", type=int, default=0, help="ограничить число изображений (0 = все)")
    args = ap.parse_args()

    backend = make_backend(args)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    n = 0
    n_invalid = 0
    t0 = time.time()
    with open(args.out, "w", encoding="utf-8") as fout:
        for (path, image_id, w, h, side) in iter_images(args.images, args.image_root):
            out = backend.describe(path, image_id, w, h, side)
            errs = validate_output(out)
            if errs:
                n_invalid += 1
                out.setdefault("notes", "")
                out["notes"] = (out["notes"] + f" | schema warnings: {errs[:3]}").strip(" |")
            fout.write(json.dumps(out, ensure_ascii=False) + "\n")
            n += 1
            if args.limit and n >= args.limit:
                break
    dt = time.time() - t0
    print(f"backend={args.backend} images={n} invalid_schema={n_invalid} elapsed={dt:.2f}s -> {args.out}")


if __name__ == "__main__":
    main()
