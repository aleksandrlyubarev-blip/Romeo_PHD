"""Сравнение образца с эталоном и вердикт good/bad (§10 ТЗ).

Вход: описание образца (объект схемы pcba/schema.py — то, что вернула VLM) + эталон
(pcba/golden.py). Выход: diff (список отклонений с типом дефекта, локализацией и
уверенностью) и вердикт OK/NOK.

Логика матчинга: жадно по близости центроидов среди компонентов того же класса
(в пределах увеличенного допуска слота). Для каждого слота эталона:
  * нет кандидата                     -> defect "missing"
  * матч, но класс другой             -> defect "wrong_part"  (учитывается отдельно при cross-class матче)
  * матч, смещение центроида > pos_tol -> defect "misaligned"
  * матч, |ориентация - ожидаемой| > ori_tol -> defect "wrong_orientation"
  * матч, состояние != ожидаемому     -> defect соответствующего типа (unlatched/unseated/...) либо "wrong_part"
Компоненты образца, не привязанные ни к одному слоту -> defect "extra_part".

Пороги в ComparePolicy переопределяемы (на линии под конкретное изделие).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Optional

from .golden import GoldenBoard, GoldenSlot
from .taxonomy import COMPONENT_STATE_VALUES


def _norm_bbox(bbox_px: list[float], w: int, h: int) -> list[float]:
    x, y, bw, bh = bbox_px
    return [x / w, y / h, bw / w, bh / h]


def _centroid(bbox_norm: list[float]) -> tuple[float, float]:
    x, y, w, h = bbox_norm
    return (x + w / 2.0, y + h / 2.0)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _ori_delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


# Какое состояние считается «дефектным» и какой тип дефекта ему присвоить.
_STATE_DEFECT = {
    ("present", "missing"): "missing",
    ("mated", "unmated"): "unseated",
    ("latched", "unlatched"): "unlatched",
    ("seated", "unseated"): "unseated",
}


@dataclass
class ComparePolicy:
    cross_class_match_dist: float = 0.04   # для поиска "wrong_part" допускаем матч с другим классом
    extra_part_min_conf: float = 0.5       # лишний компонент с уверенностью ниже — игнор (шум)
    # Какие типы дефектов считаются «критичными» (любой критичный -> NOK).
    critical_defects: tuple[str, ...] = (
        "missing", "wrong_part", "wrong_orientation", "extra_part", "unlatched", "unseated", "damaged",
    )
    # Некритичные дефекты дают NOK только если их больше порога.
    minor_defects_nok_threshold: int = 3


@dataclass
class Defect:
    type: str
    slot_id: Optional[str]
    component_id: Optional[str]
    cls: Optional[str]
    bbox_norm: Optional[list[float]]
    detail: str = ""
    confidence: float = 1.0


@dataclass
class CompareResult:
    board_type: str
    verdict: str                       # "OK" | "NOK"
    n_slots: int = 0
    n_components: int = 0
    defects: list[Defect] = field(default_factory=list)
    matched_slot_ids: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "board_type": self.board_type,
            "verdict": self.verdict,
            "n_slots": self.n_slots,
            "n_components": self.n_components,
            "defects": [d.__dict__ for d in self.defects],
            "matched_slot_ids": self.matched_slot_ids,
        }


def _sample_components_norm(sample: dict) -> list[dict]:
    size = sample.get("image_size", {})
    w = int(size.get("w") or 1)
    h = int(size.get("h") or 1)
    out = []
    for c in sample.get("components", []):
        cc = dict(c)
        cc["_bbox_norm"] = c.get("bbox_norm") or _norm_bbox(c["bbox"], w, h)
        cc["_centroid"] = _centroid(cc["_bbox_norm"])
        out.append(cc)
    return out


def compare(sample: dict, golden: GoldenBoard, policy: Optional[ComparePolicy] = None) -> CompareResult:
    policy = policy or ComparePolicy()
    comps = _sample_components_norm(sample)
    used = [False] * len(comps)
    defects: list[Defect] = []
    matched_slot_ids: list[str] = []

    for slot in golden.slots:
        scx = _centroid(slot.bbox_norm)
        # 1) кандидаты того же класса в пределах допуска
        same_cls = [(i, _dist(c["_centroid"], scx)) for i, c in enumerate(comps)
                    if not used[i] and c["class"] == slot.cls]
        same_cls = [(i, d) for i, d in same_cls if d <= max(slot.pos_tol * 3.0, policy.cross_class_match_dist)]
        same_cls.sort(key=lambda t: t[1])

        if same_cls:
            i, d = same_cls[0]
            used[i] = True
            matched_slot_ids.append(slot.slot_id)
            c = comps[i]
            conf = float(c.get("confidence", 1.0))
            # misaligned?
            if d > slot.pos_tol:
                defects.append(Defect("misaligned", slot.slot_id, c.get("id"), slot.cls, c["_bbox_norm"],
                                      detail=f"centroid offset {d:.3f} > tol {slot.pos_tol:.3f}", confidence=conf))
            # wrong_orientation?
            od = _ori_delta((c.get("attributes") or {}).get("orientation_deg"), slot.expected_orientation_deg)
            if od is not None and od > slot.ori_tol:
                defects.append(Defect("wrong_orientation", slot.slot_id, c.get("id"), slot.cls, c["_bbox_norm"],
                                      detail=f"orientation delta {od:.0f}deg > tol {slot.ori_tol:.0f}", confidence=conf))
            # state mismatch?
            if slot.expected_state is not None:
                got = (c.get("attributes") or {}).get("state")
                if got is not None and got != slot.expected_state:
                    dtype = _STATE_DEFECT.get((slot.expected_state, got), "wrong_part")
                    defects.append(Defect(dtype, slot.slot_id, c.get("id"), slot.cls, c["_bbox_norm"],
                                          detail=f"state {got!r} != expected {slot.expected_state!r}", confidence=conf))
            # subclass mismatch -> wrong_part (мягко)
            if slot.subclass and c.get("subclass") and c["subclass"] != slot.subclass:
                defects.append(Defect("wrong_part", slot.slot_id, c.get("id"), slot.cls, c["_bbox_norm"],
                                      detail=f"subclass {c['subclass']!r} != expected {slot.subclass!r}", confidence=conf))
            continue

        # 2) кандидат другого класса рядом -> wrong_part
        other = [(i, _dist(c["_centroid"], scx)) for i, c in enumerate(comps)
                 if not used[i] and _dist(c["_centroid"], scx) <= policy.cross_class_match_dist]
        other.sort(key=lambda t: t[1])
        if other:
            i, d = other[0]
            used[i] = True
            matched_slot_ids.append(slot.slot_id)
            c = comps[i]
            defects.append(Defect("wrong_part", slot.slot_id, c.get("id"), slot.cls, c["_bbox_norm"],
                                  detail=f"got class {c['class']!r}, expected {slot.cls!r}",
                                  confidence=float(c.get("confidence", 1.0))))
            continue

        # 3) ничего нет -> missing
        defects.append(Defect("missing", slot.slot_id, None, slot.cls, slot.bbox_norm, detail="no matching component"))

    # 4) лишние компоненты
    for i, c in enumerate(comps):
        if used[i]:
            continue
        if float(c.get("confidence", 1.0)) < policy.extra_part_min_conf:
            continue
        defects.append(Defect("extra_part", None, c.get("id"), c["class"], c["_bbox_norm"],
                              detail="not present in golden reference", confidence=float(c.get("confidence", 1.0))))

    # вердикт
    n_critical = sum(1 for d in defects if d.type in policy.critical_defects)
    n_minor = len(defects) - n_critical
    verdict = "NOK" if (n_critical > 0 or n_minor >= policy.minor_defects_nok_threshold) else "OK"

    return CompareResult(
        board_type=golden.board_type, verdict=verdict,
        n_slots=len(golden.slots), n_components=len(comps),
        defects=defects, matched_slot_ids=matched_slot_ids,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True, help="JSON эталона (из pcba.golden build)")
    ap.add_argument("--sample", required=True, help="JSON описания образца (объект схемы pcba/schema.py)")
    args = ap.parse_args()
    with open(args.golden, "r", encoding="utf-8") as f:
        golden = GoldenBoard.from_json(json.load(f))
    with open(args.sample, "r", encoding="utf-8") as f:
        sample = json.load(f)
    res = compare(sample, golden)
    print(json.dumps(res.to_json(), ensure_ascii=False, indent=2))
    raise SystemExit(0 if res.verdict == "OK" else 2)


if __name__ == "__main__":
    main()
