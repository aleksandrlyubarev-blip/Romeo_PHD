"""Симулятор дефектов на УРОВНЕ ОПИСАНИЯ — для юнит-/smoke-тестов comparator'а и метрик.

ВАЖНО: это НЕ генератор дефектных изображений. Image-level synthetic defect generation —
задача пайплайна «Бригада» (RomeoFlexVision/docs/brigada-architecture.md). Здесь мы берём
хорошее описание платы и мутируем его так, как примерно выглядел бы вывод VLM на дефектной
плате, чтобы проверить downstream-логику (compare.py) и метрики (eval/metrics.py) без модели.

Каждый дефектный вариант сохраняется вместе с ground-truth списком дефектов:
    {"sample": <описание-схема>, "gt_defects": [{"type": ..., "ref": <slot-or-id-hint>}], "label": "OK"|"NOK"}

CLI:
    python3 -m pcba.inject_defects --from data/manifest/test.jsonl --image-id 7 \
        --n-bad 5 --n-good 3 --seed 1 --out data/eval/cases.jsonl
"""
from __future__ import annotations

import argparse
import copy
import json
import random
from typing import Optional

from .schema import SCHEMA_VERSION


def _load_describe(path: str, image_id=None) -> Optional[dict]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "conversations" in rec:
                if rec.get("meta", {}).get("kind") != "describe":
                    continue
                rid = rec.get("meta", {}).get("image_id")
                if image_id is not None and str(rid) != str(image_id):
                    continue
                gpt = next((c["value"] for c in rec["conversations"] if c["from"] == "gpt"), None)
                if gpt:
                    obj = json.loads(gpt)
                    obj.setdefault("image_id", rec.get("image"))
                    return obj
            else:
                if image_id is not None and str(rec.get("image_id")) != str(image_id):
                    continue
                return rec
    return None


_STATE_FLIP = {"latched": "unlatched", "unlatched": "latched", "present": "missing",
               "mated": "unmated", "seated": "unseated"}


def _mutate(sample: dict, rng: random.Random) -> tuple[dict, list[dict]]:
    s = copy.deepcopy(sample)
    comps = s.get("components", [])
    if not comps:
        return s, []
    gt: list[dict] = []
    n_defects = rng.randint(1, min(3, len(comps)))
    idxs = rng.sample(range(len(comps)), n_defects)
    # применяем от большего индекса к меньшему, чтобы удаление не сбивало индексы
    for i in sorted(idxs, reverse=True):
        c = comps[i]
        kind = rng.choice(["missing", "wrong_part", "wrong_orientation", "misaligned", "state", "extra"])
        if kind == "missing":
            gt.append({"type": "missing", "ref_class": c["class"], "ref_id": c.get("id")})
            comps.pop(i)
        elif kind == "wrong_part":
            others = [x for x in {"smt_passive", "smt_ic", "connector", "test_point", "screw_fastener"} if x != c["class"]]
            c["class"] = rng.choice(others)
            gt.append({"type": "wrong_part", "ref_class": c["class"], "ref_id": c.get("id")})
        elif kind == "wrong_orientation":
            attrs = c.setdefault("attributes", {})
            base = attrs.get("orientation_deg") or 0
            attrs["orientation_deg"] = (base + rng.choice([90, 180, 270])) % 360
            gt.append({"type": "wrong_orientation", "ref_class": c["class"], "ref_id": c.get("id")})
        elif kind == "misaligned":
            bb = c["bbox"]
            # сдвиг достаточно велик, чтобы превысить допуск слота, но не настолько,
            # чтобы компонент «оторвался» от слота при матчинге (стал missing+extra).
            shift = rng.choice([-1, 1]) * rng.uniform(7.0, 11.0)
            c["bbox"] = [bb[0] + shift, bb[1], bb[2], bb[3]]
            gt.append({"type": "misaligned", "ref_class": c["class"], "ref_id": c.get("id")})
        elif kind == "state":
            attrs = c.setdefault("attributes", {})
            st = attrs.get("state")
            if st in _STATE_FLIP:
                attrs["state"] = _STATE_FLIP[st]
                dtype = "missing" if st == "present" else ("unlatched" if st == "latched" else "unseated")
                gt.append({"type": dtype, "ref_class": c["class"], "ref_id": c.get("id")})
            else:  # нет состояния — деградируем в misaligned, чтобы дефект всё же был
                bb = c["bbox"]
                c["bbox"] = [bb[0] + rng.uniform(7.0, 11.0), bb[1], bb[2], bb[3]]
                gt.append({"type": "misaligned", "ref_class": c["class"], "ref_id": c.get("id")})
        elif kind == "extra":
            base = copy.deepcopy(rng.choice(comps))
            base["id"] = f"c-extra-{rng.randint(1000,9999)}"
            bb = base["bbox"]
            base["bbox"] = [min(bb[0] + bb[2] + 4, max(0, s.get('image_size', {}).get('w', 100) - bb[2])), bb[1], bb[2], bb[3]]
            base["confidence"] = round(rng.uniform(0.6, 0.95), 2)
            comps.append(base)
            gt.append({"type": "extra_part", "ref_class": base["class"], "ref_id": base["id"]})
    s["schema_version"] = SCHEMA_VERSION
    return s, gt


def _jitter_good(sample: dict, rng: random.Random) -> dict:
    """Лёгкий шум на хорошем образце (в пределах допуска) — не должен давать NOK."""
    s = copy.deepcopy(sample)
    for c in s.get("components", []):
        bb = c["bbox"]
        c["bbox"] = [bb[0] + rng.uniform(-1.5, 1.5), bb[1] + rng.uniform(-1.5, 1.5), bb[2], bb[3]]
        c["confidence"] = round(rng.uniform(0.85, 1.0), 3)
    s["schema_version"] = SCHEMA_VERSION
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--image-id", default=None)
    ap.add_argument("--n-bad", type=int, default=5)
    ap.add_argument("--n-good", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    base = _load_describe(args.src, image_id=args.image_id)
    if base is None:
        raise SystemExit("no describe sample found")
    rng = random.Random(args.seed)
    import os
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for _ in range(args.n_good):
            f.write(json.dumps({"sample": _jitter_good(base, rng), "gt_defects": [], "label": "OK"}, ensure_ascii=False) + "\n")
        for _ in range(args.n_bad):
            mut, gt = _mutate(base, rng)
            label = "NOK" if gt else "OK"
            f.write(json.dumps({"sample": mut, "gt_defects": gt, "label": label}, ensure_ascii=False) + "\n")
    print(f"wrote {args.n_good} good + {args.n_bad} bad simulated cases -> {args.out}")


if __name__ == "__main__":
    main()
