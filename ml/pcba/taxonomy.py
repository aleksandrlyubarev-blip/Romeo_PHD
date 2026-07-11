"""Таксономия компонентов PCBA и типы дефектов.

Соответствует §4 и §7 ТЗ (docs/vlm-pcba-tz.md). Список расширяемый: добавление
класса = новая запись здесь + переразметка/дообучение. `id` стабильны и не
переиспользуются при удалении классов.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ComponentClass:
    id: int
    name: str
    description: str
    # Атрибуты, которые имеют смысл для этого класса (см. ComponentState ниже).
    attributes: tuple[str, ...] = field(default_factory=tuple)


# Верхний уровень таксономии. Подтипы (корпуса 0402/0603, конкретные разъёмы и т.п.)
# хранятся в поле `subclass` аннотации, а не как отдельные классы — чтобы таксономия
# оставалась компактной и стабильной.
COMPONENT_CLASSES: tuple[ComponentClass, ...] = (
    ComponentClass(1, "smt_passive", "SMT-пассив: резистор/конденсатор/индуктивность", ("orientation_deg",)),
    ComponentClass(2, "smt_ic", "SMT-микросхема общего назначения / память / регулятор", ("orientation_deg",)),
    ComponentClass(3, "mcu_controller", "Микроконтроллер / контроллер / SoC", ("orientation_deg",)),
    ComponentClass(4, "tht_component", "Выводной (through-hole) компонент", ("orientation_deg",)),
    ComponentClass(5, "press_fit", "Press-fit разъём / контакт", ("seated",)),
    ComponentClass(6, "connector", "Разъём, в т.ч. кабельный", ("mated", "latched", "orientation_deg")),
    ComponentClass(7, "screw_fastener", "Винт / гайка / стойка / клипса", ("present",)),
    ComponentClass(8, "heatsink_mechanical", "Радиатор / экран / рамка / механический элемент", ()),
    ComponentClass(9, "gold_pad_enig", "Позолоченная / ENIG площадка, краевые контакты", ()),
    ComponentClass(10, "test_point", "Тест-пойнт", ()),
    ComponentClass(11, "silkscreen_marking", "Маркировка / шелкография / QR/DataMatrix / key-маркер", ()),
    ComponentClass(12, "pcb_bare_area", "Открытый участок платы / служебный класс", ()),
    ComponentClass(13, "unknown", "Не удалось классифицировать", ()),
)

CLASS_BY_ID: dict[int, ComponentClass] = {c.id: c for c in COMPONENT_CLASSES}
CLASS_BY_NAME: dict[str, ComponentClass] = {c.name: c for c in COMPONENT_CLASSES}
CLASS_NAMES: tuple[str, ...] = tuple(c.name for c in COMPONENT_CLASSES)


# Возможные значения атрибута `state` для downstream-сравнения good/bad.
COMPONENT_STATE_VALUES: dict[str, tuple[str, ...]] = {
    "present": ("present", "missing"),
    "mated": ("mated", "unmated"),
    "latched": ("latched", "unlatched"),
    "seated": ("seated", "unseated"),
}


# Типы дефектов для разметки дефектных образцов и для метрик (§7.3, §10 ТЗ).
DEFECT_TYPES: tuple[str, ...] = (
    "missing",            # компонент отсутствует относительно эталона/BOM
    "extra_part",         # лишний компонент
    "wrong_part",         # не тот компонент / класс / номинал
    "wrong_orientation",  # неверная ориентация (поворот/полярность)
    "misaligned",         # смещение / сдвиг с посадочного места
    "damaged",            # механическое повреждение (bent pins, скол)
    "contaminated",       # загрязнение / флюс / посторонние частицы
    "unlatched",          # разъём не защёлкнут
    "unseated",           # разъём/press-fit не до конца вставлен
)


def coco_categories() -> list[dict]:
    """Категории в формате COCO (`annotations.json["categories"]`)."""
    return [{"id": c.id, "name": c.name, "supercategory": "pcba_component"} for c in COMPONENT_CLASSES]


def class_name(class_id: int) -> str:
    c = CLASS_BY_ID.get(class_id)
    return c.name if c else "unknown"
