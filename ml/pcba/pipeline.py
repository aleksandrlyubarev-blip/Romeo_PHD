"""End-to-end: фото -> описание (VLM) -> сравнение с эталоном -> вердикт + evidence-запись.

Соответствует §2.2 и §10 ТЗ и формату evidence-лога из питч-дека RoboQC
(immutable record на каждую инспекцию).

CLI (mock-бэкенд, без модели):
    python3 -m pcba.pipeline --image data/sample_coco/images/board_0001.png \
        --golden data/golden/smoke_board.json --backend mock \
        --gt-echo data/manifest/train.jsonl --image-id 1 --out report.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import time
from typing import Optional

from .compare import compare, ComparePolicy
from .golden import GoldenBoard
from .predict import make_backend, normalize_output
from .schema import validate_output


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def run_one(image_path: str, golden: GoldenBoard, backend, image_id: Optional[str] = None,
            w: int = 0, h: int = 0, board_side: str = "unknown",
            policy: Optional[ComparePolicy] = None) -> dict:
    image_id = image_id or os.path.splitext(os.path.basename(image_path))[0]
    if (not w or not h):
        try:
            from PIL import Image
            with Image.open(image_path) as im:
                w, h = im.size
        except Exception:
            pass
    t0 = time.time()
    desc = backend.describe(image_path, image_id, w, h, board_side)
    t_infer = time.time() - t0
    schema_warnings = validate_output(desc)
    t1 = time.time()
    cmp = compare(desc, golden, policy or ComparePolicy())
    t_compare = time.time() - t1

    return {
        "evidence_id": f"{image_id}-{int(t0)}",
        "timestamp": _now_iso(),
        "image": {"path": image_path, "image_id": image_id, "w": w, "h": h, "board_side": board_side},
        "model": {"schema_version": desc.get("schema_version"), "n_components": len(desc.get("components", [])),
                  "schema_warnings": schema_warnings},
        "board_type": golden.board_type,
        "verdict": cmp.verdict,
        "defects": [d.__dict__ for d in cmp.defects],
        "n_slots": cmp.n_slots,
        "matched_slots": len(cmp.matched_slot_ids),
        "timing_ms": {"inference": round(t_infer * 1000, 1), "compare": round(t_compare * 1000, 1)},
        "description": desc,            # полное описание сохраняем в evidence-запись
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="PCBA inspection pipeline (describe -> compare -> verdict)")
    ap.add_argument("--image", help="путь к изображению (для одиночного прогона)")
    ap.add_argument("--images", help="COCO annotations.json или директория (для батча)")
    ap.add_argument("--image-root", default="")
    ap.add_argument("--image-id", default=None)
    ap.add_argument("--golden", required=True, help="JSON эталона (pcba.golden build)")
    ap.add_argument("--out", required=True, help="report.json (одиночный) или reports.jsonl (батч)")
    ap.add_argument("--backend", choices=["hf", "mlx", "mock"], default="mock")
    ap.add_argument("--model", default="ByteDance/Sa2VA-InternVL3-14B")
    ap.add_argument("--lora", default=None)
    ap.add_argument("--steering", default=None)
    ap.add_argument("--steer-scale", type=float, default=2.0)
    ap.add_argument("--gt-echo", default=None, help="(mock) JSONL с GT-описаниями")
    args = ap.parse_args()
    if not args.image and not args.images:
        ap.error("нужен --image или --images")

    with open(args.golden, "r", encoding="utf-8") as f:
        golden = GoldenBoard.from_json(json.load(f))
    backend = make_backend(args)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    if args.image:
        rep = run_one(args.image, golden, backend, image_id=args.image_id)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
        print(f"verdict={rep['verdict']} defects={len(rep['defects'])} -> {args.out}")
        raise SystemExit(0 if rep["verdict"] == "OK" else 2)

    # батч
    from .predict import iter_images
    n_ok = n_nok = 0
    with open(args.out, "w", encoding="utf-8") as fout:
        for (path, image_id, w, h, side) in iter_images(args.images, args.image_root):
            rep = run_one(path, golden, backend, image_id=image_id, w=w, h=h, board_side=side)
            fout.write(json.dumps(rep, ensure_ascii=False) + "\n")
            if rep["verdict"] == "OK":
                n_ok += 1
            else:
                n_nok += 1
    print(f"batch: OK={n_ok} NOK={n_nok} -> {args.out}")


if __name__ == "__main__":
    main()
