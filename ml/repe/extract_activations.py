"""Снять активации residual stream Sa2VA на контрастных парах (трек C, шаг 1).

Вход: JSONL контрастных пар из pcba/build_contrastive.py
      ({"image", "system", "prompt", "positive", "negative", ...}).
Для каждой пары делаем два forward-прохода (teacher forcing на positive- и на negative-ответе),
снимаем средние по токенам активации на выбранных слоях, копим суммы по полярности.
Выход: .npz с массивами mean_pos[layer], mean_neg[layer] (+ counts, meta).

Требует torch + transformers + установленный пакет Sa2VA. Запуск — в обучающем контейнере (ml/Dockerfile).

CLI:
    python3 -m repe.extract_activations --pairs data/contrastive/pairs.jsonl --image-root data/sample_coco \
        --model ByteDance/Sa2VA-InternVL3-14B --layers-llm -1 -8 -16 --layers-vit -1 \
        --out work_dirs/repe/acts.npz --max-pairs 200
"""
from __future__ import annotations

import argparse
import json
import os


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--image-root", default="")
    ap.add_argument("--model", default="ByteDance/Sa2VA-InternVL3-14B")
    ap.add_argument("--layers-llm", type=int, nargs="*", default=[-1, -8, -16])
    ap.add_argument("--layers-vit", type=int, nargs="*", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-pairs", type=int, default=0)
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer
    from PIL import Image
    from repe.layers import select_modules

    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    model = AutoModel.from_pretrained(args.model, torch_dtype=getattr(torch, args.dtype),
                                      trust_remote_code=True, low_cpu_mem_usage=True).eval().to(args.device)

    targets = []
    targets += select_modules(model, "llm", args.layers_llm)
    targets += select_modules(model, "vision", args.layers_vit)
    if not targets:
        raise SystemExit("нет валидных слоёв — проверьте --layers-* и repe/layers.py")

    # буферы активаций (последний прогон), накопители сумм по полярности
    last = {}
    sums = {label: {"pos": None, "neg": None} for label, _ in targets}
    counts = {label: {"pos": 0, "neg": 0} for label, _ in targets}
    handles = []

    def mk_hook(label):
        def hook(_m, _inp, out):
            t = out[0] if isinstance(out, tuple) else out          # [B, T, D]
            last[label] = t.detach().float().mean(dim=1).squeeze(0).cpu()  # среднее по токенам -> [D]
        return hook

    for label, mod in targets:
        handles.append(mod.register_forward_hook(mk_hook(label)))

    def run_once(image, system, prompt, answer):
        # teacher forcing: подаём prompt+answer, нас интересуют активации, а не лосс.
        # Точный вызов зависит от API Sa2VA; ниже — типовой для InternVL-обёрток.
        text = f"<image>{prompt}\n{answer}"
        with torch.no_grad():
            try:
                model.predict_forward(image=image, text=text, tokenizer=tok)  # type: ignore[attr-defined]
            except Exception:
                # fallback: ручная сборка inputs (зависит от processor модели) — заполнить под релиз
                raise
        return {label: last[label].clone() for label in last}

    n = 0
    with open(args.pairs, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            img_path = os.path.join(args.image_root, rec["image"]) if args.image_root else rec["image"]
            image = Image.open(img_path).convert("RGB")
            for polarity, ans in (("pos", rec["positive"]), ("neg", rec["negative"])):
                acts = run_once(image, rec.get("system", ""), rec["prompt"], ans)
                for label, v in acts.items():
                    if sums[label][polarity] is None:
                        sums[label][polarity] = v.clone()
                    else:
                        sums[label][polarity] += v
                    counts[label][polarity] += 1
            n += 1
            if args.max_pairs and n >= args.max_pairs:
                break

    for h in handles:
        h.remove()

    out_arrays = {}
    meta = {"model": args.model, "n_pairs": n, "layers": [l for l, _ in targets]}
    for label, _ in targets:
        cp, cn = counts[label]["pos"], counts[label]["neg"]
        out_arrays[f"mean_pos__{label}"] = (sums[label]["pos"] / max(cp, 1)).numpy()
        out_arrays[f"mean_neg__{label}"] = (sums[label]["neg"] / max(cn, 1)).numpy()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    np.savez(args.out, meta=json.dumps(meta), **out_arrays)
    print(f"saved activations for {len(targets)} layers from {n} pairs -> {args.out}")


if __name__ == "__main__":
    main()
