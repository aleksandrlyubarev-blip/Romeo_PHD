"""Train/val/test split + карта датасета для Sa2VA conversation JSONL.

Сплит детерминированный (по хэшу image_id с фиксированным seed), чтобы все сэмплы
одного изображения (describe + refer) попадали в одну часть — исключает утечку.

Использование:
    python3 -m pcba.make_manifest --in data/sa2va/all.jsonl --out-dir data/manifest \
        --val 0.15 --test 0.15 --seed 13
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter


def _bucket(image_id, seed: int) -> float:
    h = hashlib.sha256(f"{seed}:{image_id}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--val", type=float, default=0.15)
    ap.add_argument("--test", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    assert 0 <= args.val + args.test < 1.0, "val+test must be < 1.0"

    os.makedirs(args.out_dir, exist_ok=True)
    samples = []
    with open(args.inp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))

    test_thr = args.test
    val_thr = args.test + args.val
    splits = {"train": [], "val": [], "test": []}
    for s in samples:
        b = _bucket(s.get("meta", {}).get("image_id", s.get("image")), args.seed)
        split = "test" if b < test_thr else ("val" if b < val_thr else "train")
        splits[split].append(s)

    for name, items in splits.items():
        path = os.path.join(args.out_dir, f"{name}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for s in items:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # карта датасета
    def stats(items):
        kinds = Counter(s.get("meta", {}).get("kind") for s in items)
        cls = Counter()
        imgs = set()
        for s in items:
            imgs.add(s.get("meta", {}).get("image_id", s.get("image")))
            gpt = next((c["value"] for c in s["conversations"] if c["from"] == "gpt"), "{}")
            try:
                for c in json.loads(gpt).get("components", []):
                    cls[c["class"]] += 1
            except Exception:
                pass
        return {"samples": len(items), "images": len(imgs), "by_kind": dict(kinds), "components_by_class": dict(cls)}

    card = {
        "source_jsonl": os.path.abspath(args.inp),
        "seed": args.seed,
        "ratios": {"train": round(1 - val_thr, 4), "val": args.val, "test": args.test},
        "splits": {name: stats(items) for name, items in splits.items()},
    }
    with open(os.path.join(args.out_dir, "dataset_card.json"), "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=2)
    print("split sizes:", {k: len(v) for k, v in splits.items()})
    print(f"wrote {args.out_dir}/{{train,val,test}}.jsonl and dataset_card.json")


if __name__ == "__main__":
    main()
