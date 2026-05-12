"""Адресация слоёв residual stream внутри Sa2VA-InternVL3-14B (плейсхолдеры).

Эти функции — единственное место, которое нужно поправить под конкретный релиз модели.
Возвращают список (name, module) для слоёв, на выход которых вешаются hook'и
(снятие активаций в extract_activations.py, инъекция вектора в apply_steering.py).
"""
from __future__ import annotations

from typing import Iterable


def _try_paths(model, paths: Iterable[str]):
    for p in paths:
        obj = model
        ok = True
        for part in p.split("."):
            if part.endswith("]"):  # foo[3]
                name, idx = part[:-1].split("[")
                obj = getattr(obj, name, None)
                if obj is None:
                    ok = False
                    break
                obj = obj[int(idx)]
            else:
                obj = getattr(obj, part, None)
                if obj is None:
                    ok = False
                    break
        if ok and obj is not None:
            return obj
    return None


def llm_decoder_layers(model):
    """Список decoder-слоёв языковой части (InternVL3 / Qwen2.5-backbone)."""
    candidates = [
        "language_model.model.layers",          # многие InternVL/LLaVA-обёртки
        "model.language_model.model.layers",
        "llm.model.layers",
        "model.layers",
    ]
    layers = _try_paths(model, candidates)
    if layers is None:
        raise RuntimeError("не найден список decoder-слоёв LLM — поправьте repe/layers.py под релиз Sa2VA")
    return list(layers)


def vision_encoder_blocks(model):
    """Список блоков vision-энкодера (InternViT)."""
    candidates = [
        "vision_model.encoder.layers",
        "model.vision_model.encoder.layers",
        "vision_tower.vision_model.encoder.layers",
        "visual.blocks",
    ]
    blocks = _try_paths(model, candidates)
    return list(blocks) if blocks is not None else []


def select_modules(model, where: str, layer_idx: list[int]):
    """where in {'llm', 'vision'}; layer_idx — индексы слоёв. Возвращает [(label, module), ...]."""
    if where == "llm":
        layers = llm_decoder_layers(model)
        prefix = "llm"
    elif where == "vision":
        layers = vision_encoder_blocks(model)
        prefix = "vit"
        if not layers:
            return []
    else:
        raise ValueError(where)
    n = len(layers)
    out = []
    for i in layer_idx:
        j = i if i >= 0 else n + i
        if 0 <= j < n:
            out.append((f"{prefix}.{j}", layers[j]))
    return out
