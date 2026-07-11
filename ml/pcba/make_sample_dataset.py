"""Сгенерировать крошечный синтетический COCO-датасет PCBA для проверки пайплайна.

Без внешних зависимостей: PNG пишется минимальным энкодером на stdlib (zlib).
Это НЕ замена реальным данным и не «Бригаде» — только smoke-test для шагов
coco_to_sa2va.py -> build_contrastive.py -> make_manifest.py.

Использование:
    python3 -m pcba.make_sample_dataset --out data/sample_coco --n 6
"""
from __future__ import annotations

import argparse
import json
import os
import random
import struct
import zlib

from .taxonomy import coco_categories, COMPONENT_CLASSES


# --- минимальный PNG-энкодер (RGB, 8 бит) ---

def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path: str, width: int, height: int, rgb_rows: list[list[tuple[int, int, int]]]) -> None:
    raw = bytearray()
    for row in rgb_rows:
        raw.append(0)  # filter type 0
        for (r, g, b) in row:
            raw += bytes((r & 255, g & 255, b & 255))
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # bit depth 8, color type 2 (RGB)
    idat = zlib.compress(bytes(raw), 9)
    with open(path, "wb") as f:
        f.write(sig + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b""))


# --- генерация одной "платы" ---

def _rect_polygon(x: int, y: int, w: int, h: int) -> list[float]:
    # COCO segmentation: [x1,y1,x2,y2,...] одной полигональной частью
    return [float(x), float(y), float(x + w), float(y), float(x + w), float(y + h), float(x), float(y + h)]


def gen_board(rng: random.Random, idx: int, width: int = 256, height: int = 192):
    board_color = (12, 70, 30)  # тёмно-зелёный текстолит
    pixels = [[board_color for _ in range(width)] for _ in range(height)]

    # выбрать классы компонентов, исключая служебные
    pickable = [c for c in COMPONENT_CLASSES if c.name not in ("pcb_bare_area", "unknown")]
    n_comp = rng.randint(4, 9)
    annos = []
    palette = {
        "smt_passive": (40, 40, 40), "smt_ic": (20, 20, 20), "mcu_controller": (10, 10, 10),
        "tht_component": (120, 80, 30), "press_fit": (180, 180, 180), "connector": (220, 220, 220),
        "screw_fastener": (160, 160, 170), "heatsink_mechanical": (190, 190, 195),
        "gold_pad_enig": (200, 170, 60), "test_point": (210, 180, 70), "silkscreen_marking": (240, 240, 240),
    }
    placed: list[tuple[int, int, int, int]] = []
    for _ in range(n_comp):
        cls = rng.choice(pickable)
        cw = rng.randint(10, 40)
        ch = rng.randint(8, 30)
        for _try in range(20):
            x = rng.randint(2, width - cw - 2)
            y = rng.randint(2, height - ch - 2)
            if all(not (x < px + pw and px < x + cw and y < py + ph and py < y + ch) for (px, py, pw, ph) in placed):
                break
        else:
            continue
        placed.append((x, y, cw, ch))
        color = palette.get(cls.name, (100, 100, 100))
        for yy in range(y, y + ch):
            for xx in range(x, x + cw):
                pixels[yy][xx] = color
        attrs = {}
        if "present" in cls.attributes:
            attrs["state"] = "present"
        if "latched" in cls.attributes:
            attrs["state"] = rng.choice(["latched", "unlatched"])
        if "orientation_deg" in cls.attributes:
            attrs["orientation_deg"] = rng.choice([0, 90, 180, 270])
        annos.append({
            "category_id": cls.id,
            "bbox": [x, y, cw, ch],
            "area": cw * ch,
            "iscrowd": 0,
            "segmentation": [_rect_polygon(x, y, cw, ch)],
            "attributes": attrs,
        })
    file_name = f"board_{idx:04d}.png"
    return file_name, width, height, pixels, annos


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sample_coco")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    img_dir = os.path.join(args.out, "images")
    os.makedirs(img_dir, exist_ok=True)

    images, annotations = [], []
    ann_id = 1
    for i in range(args.n):
        file_name, w, h, pixels, annos = gen_board(rng, i)
        write_png(os.path.join(img_dir, file_name), w, h, pixels)
        image_id = i + 1
        images.append({"id": image_id, "file_name": file_name, "width": w, "height": h, "board_side": "top"})
        for a in annos:
            a["id"] = ann_id
            a["image_id"] = image_id
            annotations.append(a)
            ann_id += 1

    coco = {
        "info": {"description": "Synthetic PCBA sample (smoke-test only)", "version": "0.1"},
        "licenses": [],
        "images": images,
        "annotations": annotations,
        "categories": coco_categories(),
    }
    out_json = os.path.join(args.out, "annotations.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(coco, f, ensure_ascii=False, indent=2)
    print(f"wrote {len(images)} images -> {img_dir}")
    print(f"wrote {len(annotations)} annotations -> {out_json}")


if __name__ == "__main__":
    main()
