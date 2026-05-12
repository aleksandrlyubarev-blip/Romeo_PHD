"""Посчитать steering-вектор «PCB AOI expert» из снятых активаций (трек C, шаг 2).

Метод по умолчанию — diff-of-means: v_layer = mean_pos - mean_neg, нормируется до единичной
нормы; «сила слоя» = ||mean_pos - mean_neg|| / (||mean_pos|| + ||mean_neg|| + eps).
Отбираем top-k слоёв по силе, сохраняем steering.json:
    {"model": ..., "scale": 2.0, "vectors": [{"layer": "llm.27", "dim": 5120, "vector": [...], "strength": 0.13}, ...]}

Альтернатива (SAE): вместо diff-of-means обучить/взять Sparse Autoencoder на этих активациях
(SAELens + multimodal-расширение, sae-for-vlm), найти признак(и), коррелирующие со структурным
ответом, и использовать декодер-направление признака как steering-вектор. Точка расширения —
функция `sae_directions()` ниже (заглушка).

CLI:
    python3 -m repe.fit_steering --acts work_dirs/repe/acts.npz --topk 3 --scale 2.0 \
        --out work_dirs/repe/steering.json
"""
from __future__ import annotations

import argparse
import json


def diff_of_means(mean_pos, mean_neg):
    import numpy as np
    v = mean_pos.astype("float64") - mean_neg.astype("float64")
    nrm = float(np.linalg.norm(v))
    strength = nrm / (float(np.linalg.norm(mean_pos)) + float(np.linalg.norm(mean_neg)) + 1e-8)
    unit = (v / nrm) if nrm > 0 else v
    return unit, strength


def sae_directions(acts_npz_path: str):
    """Заглушка для SAE-варианта (SAELens / sae-for-vlm). Вернуть [(layer_label, unit_vector, strength), ...]."""
    raise NotImplementedError("SAE-путь подключается здесь: обучить/загрузить SAE на активациях и выбрать признаки")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--acts", required=True, help=".npz из repe.extract_activations")
    ap.add_argument("--method", choices=["diff_of_means", "sae"], default="diff_of_means")
    ap.add_argument("--topk", type=int, default=3, help="сколько слоёв оставить (по силе направления)")
    ap.add_argument("--scale", type=float, default=2.0, help="дефолтный масштаб инъекции (1.0–4.0)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import numpy as np
    data = np.load(args.acts, allow_pickle=True)
    meta = json.loads(str(data["meta"])) if "meta" in data else {}
    layers = meta.get("layers") or sorted({k.split("__", 1)[1] for k in data.files if k.startswith("mean_pos__")})

    if args.method == "sae":
        triples = sae_directions(args.acts)
    else:
        triples = []
        for label in layers:
            mp = data[f"mean_pos__{label}"]
            mn = data[f"mean_neg__{label}"]
            unit, strength = diff_of_means(mp, mn)
            triples.append((label, unit, strength))

    triples.sort(key=lambda t: t[2], reverse=True)
    chosen = triples[: args.topk]
    spec = {
        "model": meta.get("model"),
        "method": args.method,
        "scale": args.scale,
        "vectors": [
            {"layer": label, "dim": int(vec.shape[0]), "strength": round(float(s), 5), "vector": [round(float(x), 6) for x in vec]}
            for (label, vec, s) in chosen
        ],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(spec, f)
    print("chosen layers:", [(l, round(s, 4)) for (l, _, s) in chosen])
    print(f"steering spec ({len(chosen)} layers, scale={args.scale}) -> {args.out}")


if __name__ == "__main__":
    main()
