"""COCO instance-segmentation -> Sa2VA conversation JSONL (GCG-формат).

Sa2VA ожидает диалоговые сэмплы вида:
    {
      "image": "<относительный путь к изображению>",
      "conversations": [
        {"from": "system", "value": "<system prompt>"},
        {"from": "human",  "value": "<image>\n<вопрос>"},
        {"from": "gpt",    "value": "<JSON-ответ>"}
      ],
      # ground-truth маски для SAM2-головы (по одной на компонент, в порядке появления в JSON):
      "masks": [ {"size": [h, w], "polygon": [[x,y],...]} , ... ]
    }

Здесь мы:
  * генерируем два типа сэмплов на изображение — full describe и refer (подмножество классов);
  * полигоны в JSON-ответе нормализуем в [0,1] (разрешение-инвариантно);
  * `masks` оставляем в пикселях (нужны SAM2-голове как GT).

Использование:
    python3 -m pcba.coco_to_sa2va --coco data/sample_coco/annotations.json \
        --images-prefix images --out data/sa2va/all.jsonl --refer-per-image 1
"""
from __future__ import annotations

import argparse
import json
import os
import random
from collections import defaultdict

from .schema import SCHEMA_VERSION, SYSTEM_PROMPT, describe_prompt, refer_prompt
from .taxonomy import class_name


def _seg_to_xy_pairs(segmentation) -> list[list[float]]:
    """COCO polygon part -> [[x,y],...]. Берём первую часть полигона."""
    if not segmentation:
        return []
    part = segmentation[0] if isinstance(segmentation[0], list) else segmentation
    return [[float(part[i]), float(part[i + 1])] for i in range(0, len(part) - 1, 2)]


def _normalize_polygon(xy: list[list[float]], w: int, h: int) -> list[list[float]]:
    return [[round(x / w, 5), round(y / h, 5)] for (x, y) in xy]


def _component_record(idx: int, ann: dict, w: int, h: int) -> tuple[dict, dict]:
    cname = class_name(ann["category_id"])
    xy = _seg_to_xy_pairs(ann.get("segmentation"))
    bbox = [round(v, 2) for v in ann["bbox"]]
    attrs = dict(ann.get("attributes") or {})
    comp = {
        "id": f"c-{idx:04d}",
        "class": cname,
        "subclass": ann.get("subclass"),
        "bbox": bbox,
        "polygon": _normalize_polygon(xy, w, h) or [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
        "confidence": 1.0,  # ground truth
        "attributes": {"state": attrs.get("state"), "orientation_deg": attrs.get("orientation_deg")},
    }
    mask = {"size": [h, w], "polygon": xy}
    return comp, mask


def _answer_json(image_id: str, w: int, h: int, board_side: str, comps: list[dict]) -> str:
    obj = {
        "schema_version": SCHEMA_VERSION,
        "image_id": image_id,
        "image_size": {"w": w, "h": h},
        "board_side": board_side or "unknown",
        "components": comps,
        "notes": "",
    }
    return json.dumps(obj, ensure_ascii=False)


def build_samples(coco: dict, images_prefix: str, refer_per_image: int, rng: random.Random):
    anns_by_img: dict[int, list[dict]] = defaultdict(list)
    for a in coco["annotations"]:
        anns_by_img[a["image_id"]].append(a)
    img_by_id = {im["id"]: im for im in coco["images"]}

    samples = []
    for img_id, im in img_by_id.items():
        w, h = im["width"], im["height"]
        side = im.get("board_side", "unknown")
        img_path = os.path.join(images_prefix, im["file_name"]) if images_prefix else im["file_name"]
        anns = anns_by_img.get(img_id, [])

        # 1) full describe
        comps, masks = [], []
        for i, a in enumerate(anns):
            c, m = _component_record(i + 1, a, w, h)
            comps.append(c)
            masks.append(m)
        samples.append({
            "image": img_path,
            "conversations": [
                {"from": "system", "value": SYSTEM_PROMPT},
                {"from": "human", "value": "<image>\n" + describe_prompt()},
                {"from": "gpt", "value": _answer_json(im["file_name"], w, h, side, comps)},
            ],
            "masks": masks,
            "meta": {"image_id": img_id, "kind": "describe"},
        })

        # 2) refer (подмножество классов)
        present_classes = sorted({class_name(a["category_id"]) for a in anns})
        for _ in range(refer_per_image):
            if not present_classes:
                break
            k = rng.randint(1, max(1, min(3, len(present_classes))))
            targets = rng.sample(present_classes, k)
            sub = [(i, a) for i, a in enumerate(anns) if class_name(a["category_id"]) in targets]
            if not sub:
                continue
            r_comps, r_masks = [], []
            for j, (orig_i, a) in enumerate(sub):
                c, m = _component_record(j + 1, a, w, h)
                r_comps.append(c)
                r_masks.append(m)
            samples.append({
                "image": img_path,
                "conversations": [
                    {"from": "system", "value": SYSTEM_PROMPT},
                    {"from": "human", "value": "<image>\n" + refer_prompt(targets)},
                    {"from": "gpt", "value": _answer_json(im["file_name"], w, h, side, r_comps)},
                ],
                "masks": r_masks,
                "meta": {"image_id": img_id, "kind": "refer", "targets": targets},
            })
    return samples


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coco", required=True, help="path to COCO annotations.json")
    ap.add_argument("--images-prefix", default="images", help="prefix prepended to file_name in 'image' field")
    ap.add_argument("--out", required=True, help="output JSONL")
    ap.add_argument("--refer-per-image", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    with open(args.coco, "r", encoding="utf-8") as f:
        coco = json.load(f)
    rng = random.Random(args.seed)
    samples = build_samples(coco, args.images_prefix, args.refer_per_image, rng)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    n_describe = sum(1 for s in samples if s["meta"]["kind"] == "describe")
    n_refer = len(samples) - n_describe
    print(f"wrote {len(samples)} samples ({n_describe} describe + {n_refer} refer) -> {args.out}")


if __name__ == "__main__":
    main()
