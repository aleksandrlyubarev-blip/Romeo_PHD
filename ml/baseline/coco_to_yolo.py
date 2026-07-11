"""COCO instance-segmentation -> YOLOv11-seg датасет (трек A baseline, §5.1 ТЗ).

Пишет структуру Ultralytics:
    <out>/
      images/{train,val}/*.png
      labels/{train,val}/*.txt          # строки: "<cls_idx> x1 y1 x2 y2 ..."  (полигон, норм. в [0,1])
      data.yaml                          # path / train / val / names

Сплит детерминированный по хэшу image_id (тот же принцип, что в pcba/make_manifest.py),
чтобы трек A и треки B/C делили данные одинаково. Изображения по умолчанию копируются
(--symlink — делать симлинки вместо копии).

Использование:
    python3 -m baseline.coco_to_yolo --coco data/sample_coco/annotations.json \
        --image-root data/sample_coco/images --out data/yolo --val 0.2 --seed 13
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import defaultdict

from pcba.taxonomy import CLASS_NAMES, CLASS_BY_ID


def _bucket(image_id, seed: int) -> float:
    h = hashlib.sha256(f"{seed}:{image_id}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _seg_xy(segmentation) -> list[tuple[float, float]]:
    if not segmentation:
        return []
    part = segmentation[0] if isinstance(segmentation[0], list) else segmentation
    return [(float(part[i]), float(part[i + 1])) for i in range(0, len(part) - 1, 2)]


def _class_index(category_id: int) -> int:
    c = CLASS_BY_ID.get(category_id)
    if c is None:
        return CLASS_NAMES.index("unknown")
    return CLASS_NAMES.index(c.name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coco", required=True)
    ap.add_argument("--image-root", required=True, help="директория с изображениями (file_name из COCO)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--val", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--symlink", action="store_true", help="симлинки вместо копирования изображений")
    args = ap.parse_args()

    with open(args.coco, "r", encoding="utf-8") as f:
        coco = json.load(f)
    anns_by_img: dict[int, list[dict]] = defaultdict(list)
    for a in coco["annotations"]:
        anns_by_img[a["image_id"]].append(a)

    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        os.makedirs(os.path.join(args.out, sub), exist_ok=True)

    n = {"train": 0, "val": 0}
    for im in coco["images"]:
        split = "val" if _bucket(im["id"], args.seed) < args.val else "train"
        w, h = float(im["width"]), float(im["height"])
        src = os.path.join(args.image_root, im["file_name"])
        dst_img = os.path.join(args.out, "images", split, im["file_name"])
        if os.path.exists(src):
            if args.symlink:
                if os.path.lexists(dst_img):
                    os.remove(dst_img)
                os.symlink(os.path.abspath(src), dst_img)
            else:
                shutil.copy2(src, dst_img)
        label_path = os.path.join(args.out, "labels", split, os.path.splitext(im["file_name"])[0] + ".txt")
        with open(label_path, "w", encoding="utf-8") as lf:
            for a in anns_by_img.get(im["id"], []):
                xy = _seg_xy(a.get("segmentation"))
                if len(xy) < 3:
                    continue
                idx = _class_index(a["category_id"])
                coords = " ".join(f"{x / w:.6f} {y / h:.6f}" for (x, y) in xy)
                lf.write(f"{idx} {coords}\n")
        n[split] += 1

    names = {i: name for i, name in enumerate(CLASS_NAMES)}
    data_yaml = os.path.join(args.out, "data.yaml")
    with open(data_yaml, "w", encoding="utf-8") as f:
        f.write(f"path: {os.path.abspath(args.out)}\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        f.write(f"nc: {len(CLASS_NAMES)}\n")
        f.write("names:\n")
        for i, name in names.items():
            f.write(f"  {i}: {name}\n")
    print(f"YOLO dataset: train={n['train']} val={n['val']} images -> {args.out}")
    print(f"data.yaml -> {data_yaml}")


if __name__ == "__main__":
    main()
