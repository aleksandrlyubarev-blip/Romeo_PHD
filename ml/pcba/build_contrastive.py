"""Контрастные пары для трека C (RepE/SAE/steering) из Sa2VA conversation JSONL.

Для каждого `describe`-сэмпла строим пару:
  * positive: тот же вопрос -> структурный JSON-ответ (целевое поведение «PCB AOI expert»);
  * negative: тот же вопрос -> «размытый» ответ без структуры/координат.

Эти пары используются для:
  * снятия активаций модели на positive/negative и вычисления разностного направления (RepE);
  * обучения/анализа SAE и отбора признаков «точная техническая сегментация».

Формат выхода (JSONL), по строке на пару:
  {"image": "...", "prompt": "<image>\n<вопрос>", "system": "...",
   "positive": "<JSON>", "negative": "<текст>",
   "meta": {"image_id": ..., "n_components": ...}}

Использование:
    python3 -m pcba.build_contrastive --in data/sa2va/all.jsonl --out data/contrastive/pairs.jsonl
"""
from __future__ import annotations

import argparse
import json
import os

from .schema import vague_answer_for


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Sa2VA conversation JSONL (из coco_to_sa2va.py)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only-describe", action="store_true", default=True,
                    help="брать только describe-сэмплы (по умолчанию да)")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    n = 0
    with open(args.inp, "r", encoding="utf-8") as fin, open(args.out, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            if args.only_describe and s.get("meta", {}).get("kind") != "describe":
                continue
            convs = {c["from"]: c["value"] for c in s["conversations"]}
            system = convs.get("system", "")
            human = convs.get("human", "")
            positive = convs.get("gpt", "")
            try:
                comps = json.loads(positive).get("components", [])
            except Exception:
                comps = []
            negative = vague_answer_for(comps)
            fout.write(json.dumps({
                "image": s["image"],
                "system": system,
                "prompt": human,
                "positive": positive,
                "negative": negative,
                "meta": {"image_id": s.get("meta", {}).get("image_id"), "n_components": len(comps)},
            }, ensure_ascii=False) + "\n")
            n += 1
    print(f"wrote {n} contrastive pairs -> {args.out}")


if __name__ == "__main__":
    main()
