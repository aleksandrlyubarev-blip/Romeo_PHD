"""JSON-схема ответа модели и промпт-шаблоны (§4 ТЗ).

Модель обязана возвращать строго валидный JSON по схеме `OUTPUT_SCHEMA`.
`validate_output()` — лёгкая проверка без внешних зависимостей (для CI/рантайма
можно подключить полноценный jsonschema).
"""
from __future__ import annotations

import json
from typing import Any

from .taxonomy import CLASS_NAMES, DEFECT_TYPES

SCHEMA_VERSION = "pcba-desc/1.0"

# JSON Schema (draft-2020-12) ответа модели.
OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "PCBA component description",
    "type": "object",
    "required": ["schema_version", "image_size", "components"],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "image_id": {"type": "string"},
        "image_size": {
            "type": "object",
            "required": ["w", "h"],
            "properties": {"w": {"type": "integer", "minimum": 1}, "h": {"type": "integer", "minimum": 1}},
            "additionalProperties": False,
        },
        "board_side": {"enum": ["top", "bottom", "unknown"]},
        "components": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "class", "bbox", "polygon", "confidence"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "class": {"enum": list(CLASS_NAMES)},
                    "subclass": {"type": ["string", "null"]},
                    # bbox в пикселях: [x, y, w, h]
                    "bbox": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
                    # полигон нормализован в [0,1]: [[x1,y1],[x2,y2],...]
                    "polygon": {
                        "type": "array",
                        "minItems": 3,
                        "items": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    },
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "attributes": {
                        "type": "object",
                        "properties": {
                            "state": {"type": ["string", "null"]},
                            "orientation_deg": {"type": ["number", "null"]},
                        },
                        "additionalProperties": True,
                    },
                    # Опционально: подсказка дефекта (только для треков с прямой детекцией).
                    "defect_hint": {"enum": [*DEFECT_TYPES, None]},
                },
            },
        },
        "notes": {"type": "string"},
    },
}


# --- промпт-шаблоны ---

SYSTEM_PROMPT = (
    "Ты — экспертная система визуального контроля качества электронной сборки (AOI). "
    "Тебе показывают фотографию печатной платы в сборе (PCBA). "
    "Найди все компоненты, аккуратно сегментируй каждый, классифицируй по таксономии "
    "и верни СТРОГО валидный JSON по заданной схеме без какого-либо текста вокруг."
)

# Полное описание платы.
USER_PROMPT_DESCRIBE = (
    "Опиши все компоненты на этой плате. Для каждого: класс из списка [{classes}], "
    "bbox в пикселях [x,y,w,h], полигон маски нормализованный в [0,1], уверенность 0..1, "
    "и атрибуты (state/orientation_deg) где применимо. "
    "Верни JSON ровно такого вида:\n{schema_hint}"
).format(
    classes=", ".join(CLASS_NAMES),
    schema_hint=json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "image_id": "<str>",
            "image_size": {"w": 0, "h": 0},
            "board_side": "top|bottom|unknown",
            "components": [
                {
                    "id": "c-0001",
                    "class": "connector",
                    "subclass": None,
                    "bbox": [0, 0, 0, 0],
                    "polygon": [[0.0, 0.0]],
                    "confidence": 0.0,
                    "attributes": {"state": None, "orientation_deg": None},
                }
            ],
            "notes": "",
        },
        ensure_ascii=False,
    ),
)

# Referring-запрос (подмножество классов) — используется и для аугментации обучающих данных.
USER_PROMPT_REFER = (
    "Сегментируй на этой плате только следующие компоненты: {targets}. "
    "Верни JSON того же формата, но в `components` оставь только запрошенные классы."
)

# «Размытый» (negative) запрос для контрастного датасета трека C — модель должна
# дать общее описание без структуры (используется только при генерации пар, не в обучении трека B).
USER_PROMPT_VAGUE = "Опиши вкратце, что изображено на фото."


def describe_prompt() -> str:
    return USER_PROMPT_DESCRIBE


def refer_prompt(target_classes: list[str]) -> str:
    return USER_PROMPT_REFER.format(targets=", ".join(target_classes))


def vague_answer_for(components: list[dict]) -> str:
    """Сгенерировать «размытый» ответ-негатив по списку компонентов (для контрастных пар)."""
    n = len(components)
    classes = sorted({c["class"] for c in components})
    head = ", ".join(classes[:3])
    return (
        f"На фотографии печатная плата, на ней примерно {n} разных деталей "
        f"(например {head} и другие). Точные позиции и типы не уточняются."
    )


def validate_output(obj: Any) -> list[str]:
    """Минимальная валидация ответа. Возвращает список ошибок (пустой = ок)."""
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["root is not an object"]
    if obj.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version != {SCHEMA_VERSION}")
    size = obj.get("image_size")
    if not (isinstance(size, dict) and isinstance(size.get("w"), int) and isinstance(size.get("h"), int)):
        errors.append("image_size invalid")
    comps = obj.get("components")
    if not isinstance(comps, list):
        return errors + ["components is not a list"]
    valid_classes = set(CLASS_NAMES)
    for i, c in enumerate(comps):
        if not isinstance(c, dict):
            errors.append(f"components[{i}] not an object")
            continue
        if c.get("class") not in valid_classes:
            errors.append(f"components[{i}].class invalid: {c.get('class')!r}")
        bbox = c.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4):
            errors.append(f"components[{i}].bbox invalid")
        poly = c.get("polygon")
        if not (isinstance(poly, list) and len(poly) >= 3 and all(isinstance(p, list) and len(p) == 2 for p in poly)):
            errors.append(f"components[{i}].polygon invalid")
        conf = c.get("confidence")
        if not (isinstance(conf, (int, float)) and 0.0 <= conf <= 1.0):
            errors.append(f"components[{i}].confidence invalid")
    return errors
