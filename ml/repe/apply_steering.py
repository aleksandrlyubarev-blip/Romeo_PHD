"""Инъекция steering-вектора в residual stream на инференсе (трек C, шаг 3).

`install_steering(model, spec, scale)` вешает forward-hook'и на слои из spec и добавляет
`scale * unit_vector` к их выходу: activations[layer] += scale * v  (geodesic step из видео
«Beyond Markdown: Geometry of Model-Native Skills»). Возвращает список handle'ов
(вызвать `.remove()` для отключения) — также доступен контекст-менеджер `steering(...)`.

Используется из pcba/predict.py: `--steering steering.json --steer-scale 2.0`.
Несколько навыков переключаются разными spec-файлами (строгий AOI-инспектор / отладчик / репортёр).
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Optional


def _resolve_layer(model, label: str):
    """label вида 'llm.27' или 'vit.12' -> модуль (использует repe.layers)."""
    from repe.layers import llm_decoder_layers, vision_encoder_blocks
    where, idx = label.split(".")
    idx = int(idx)
    layers = llm_decoder_layers(model) if where == "llm" else vision_encoder_blocks(model)
    return layers[idx]


def install_steering(model, spec: dict, scale: Optional[float] = None):
    import torch
    eff_scale = float(scale if scale is not None else spec.get("scale", 1.0))
    handles = []
    for entry in spec.get("vectors", []):
        label = entry["layer"]
        mod = _resolve_layer(model, label)
        vec = torch.tensor(entry["vector"], dtype=torch.float32)

        def mk_hook(v):
            def hook(_m, _inp, out):
                if isinstance(out, tuple):
                    h0 = out[0]
                    h0 = h0 + eff_scale * v.to(h0.dtype).to(h0.device)
                    return (h0,) + tuple(out[1:])
                return out + eff_scale * v.to(out.dtype).to(out.device)
            return hook

        handles.append(mod.register_forward_hook(mk_hook(vec)))
    return handles


@contextmanager
def steering(model, spec_path: str, scale: Optional[float] = None):
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    handles = install_steering(model, spec, scale=scale)
    try:
        yield model
    finally:
        for h in handles:
            h.remove()
