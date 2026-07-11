"""Эталон платы («golden board») и его построение (§10 ТЗ).

Эталон — это нормализованное (координаты в [0,1]) ожидаемое описание конкретного
типа изделия: список «слотов» (посадочных мест) с ожидаемым классом, положением,
состоянием и допусками. Образец на линии сравнивается с эталоном (см. compare.py).

Источники эталона:
  * один заведомо хороший образец (быстрый старт);
  * агрегация нескольких хороших образцов: компоненты кластеризуются по близости
    центроидов + совпадению класса, по кластеру берётся медиана положения и
    мода класса/состояния; допуск = размах положений в кластере (с минимумом).

Можно также собрать эталон из BOM/CAD-данных — это вне scope этого модуля
(сюда подаётся уже список компонентов).

CLI:
    # из одного хорошего образца (Sa2VA describe-сэмпл или объект схемы)
    python3 -m pcba.golden build --board-type my_board_v1 --from data/manifest/train.jsonl \
        --image-id 1 --out data/golden/my_board_v1.json
    # агрегация нескольких хороших образцов одного типа
    python3 -m pcba.golden build --board-type my_board_v1 --from good_samples.jsonl --out ...
"""
from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass, field, asdict
from typing import Iterable, Optional

GOLDEN_SCHEMA_VERSION = "pcba-golden/1.0"

# Допуски по умолчанию (в долях диагонали изображения / в градусах).
DEFAULT_POS_TOL = 0.03      # сдвиг центроида сверх этого -> misaligned
DEFAULT_ORI_TOL = 20.0      # отклонение ориентации сверх этого -> wrong_orientation
MIN_POS_TOL = 0.015         # нижняя граница допуска при агрегации


def _norm_bbox(bbox_px: list[float], w: int, h: int) -> list[float]:
    x, y, bw, bh = bbox_px
    return [x / w, y / h, bw / w, bh / h]


def _centroid(bbox_norm: list[float]) -> tuple[float, float]:
    x, y, w, h = bbox_norm
    return (x + w / 2.0, y + h / 2.0)


@dataclass
class GoldenSlot:
    slot_id: str
    cls: str
    subclass: Optional[str]
    bbox_norm: list[float]              # [x,y,w,h] в [0,1]
    polygon_norm: list[list[float]]     # [[x,y],...] в [0,1]
    expected_state: Optional[str]       # из COMPONENT_STATE_VALUES, либо None
    expected_orientation_deg: Optional[float]
    pos_tol: float = DEFAULT_POS_TOL
    ori_tol: float = DEFAULT_ORI_TOL
    n_obs: int = 1                      # на скольких хороших образцах подтверждён слот


@dataclass
class GoldenBoard:
    board_type: str
    schema_version: str = GOLDEN_SCHEMA_VERSION
    n_reference_samples: int = 1
    slots: list[GoldenSlot] = field(default_factory=list)

    def to_json(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_json(d: dict) -> "GoldenBoard":
        slots = [GoldenSlot(**s) for s in d.get("slots", [])]
        return GoldenBoard(board_type=d["board_type"],
                           schema_version=d.get("schema_version", GOLDEN_SCHEMA_VERSION),
                           n_reference_samples=d.get("n_reference_samples", 1),
                           slots=slots)


# --- чтение «хороших» образцов ---

def _components_from_record(rec: dict) -> tuple[list[dict], int, int]:
    """Вернуть (components, w, h). Принимает объект схемы pcba/schema.py или Sa2VA-сэмпл."""
    if "conversations" in rec:
        gpt = next((c["value"] for c in rec["conversations"] if c["from"] == "gpt"), "{}")
        obj = json.loads(gpt)
    else:
        obj = rec
    size = obj.get("image_size", {})
    w = int(size.get("w") or 1)
    h = int(size.get("h") or 1)
    return obj.get("components", []), w, h


def _iter_good_samples(path: str, image_id=None, board_side: Optional[str] = None) -> Iterable[dict]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if image_id is not None:
                rid = rec.get("meta", {}).get("image_id", rec.get("image_id"))
                if str(rid) != str(image_id):
                    continue
            yield rec


# --- агрегация компонентов нескольких хороших образцов в слоты ---

def _aggregate(samples_components: list[list[dict]], pos_match: float = DEFAULT_POS_TOL * 1.5) -> list[GoldenSlot]:
    # вход: списки нормализованных компонентов с ключами cls/subclass/bbox_norm/polygon_norm/state/orientation_deg
    clusters: list[list[dict]] = []

    for comps in samples_components:
        for nc in comps:
            cx, cy = _centroid(nc["bbox_norm"])
            best = None
            best_d = 1e9
            for cl in clusters:
                ecx, ecy = _centroid(cl[0]["bbox_norm"])
                d = ((cx - ecx) ** 2 + (cy - ecy) ** 2) ** 0.5
                if d < best_d and cl[0]["cls"] == nc["cls"] and d <= pos_match:
                    best, best_d = cl, d
            if best is None:
                clusters.append([nc])
            else:
                best.append(nc)

    slots: list[GoldenSlot] = []
    for i, cl in enumerate(clusters):
        xs = [c["bbox_norm"][0] for c in cl]
        ys = [c["bbox_norm"][1] for c in cl]
        ws = [c["bbox_norm"][2] for c in cl]
        hs = [c["bbox_norm"][3] for c in cl]
        bbox = [statistics.median(xs), statistics.median(ys), statistics.median(ws), statistics.median(hs)]
        # допуск положения = размах центроидов в кластере, но не меньше MIN_POS_TOL
        cxs = [c["bbox_norm"][0] + c["bbox_norm"][2] / 2 for c in cl]
        cys = [c["bbox_norm"][1] + c["bbox_norm"][3] / 2 for c in cl]
        spread = max((max(cxs) - min(cxs)), (max(cys) - min(cys))) if len(cl) > 1 else 0.0
        pos_tol = max(MIN_POS_TOL, spread * 1.5)
        states = [c["state"] for c in cl if c["state"] is not None]
        oris = [c["orientation_deg"] for c in cl if c["orientation_deg"] is not None]
        subs = [c["subclass"] for c in cl if c["subclass"] is not None]
        slots.append(GoldenSlot(
            slot_id=f"s-{i+1:04d}",
            cls=cl[0]["cls"],
            subclass=statistics.mode(subs) if subs else None,
            bbox_norm=bbox,
            polygon_norm=cl[0]["polygon_norm"],
            expected_state=statistics.mode(states) if states else None,
            expected_orientation_deg=statistics.median(oris) if oris else None,
            pos_tol=round(pos_tol, 5),
            ori_tol=DEFAULT_ORI_TOL,
            n_obs=len(cl),
        ))
    return slots


def _norm_component(c: dict, w: int, h: int) -> dict:
    bn = c.get("bbox_norm") or _norm_bbox(c["bbox"], w, h)
    return {
        "cls": c["class"], "subclass": c.get("subclass"),
        "bbox_norm": bn, "polygon_norm": c.get("polygon", []),
        "state": (c.get("attributes") or {}).get("state"),
        "orientation_deg": (c.get("attributes") or {}).get("orientation_deg"),
    }


def build_golden(board_type: str, records: list[dict]) -> GoldenBoard:
    samples_components: list[list[dict]] = []
    for rec in records:
        comps, w, h = _components_from_record(rec)
        samples_components.append([_norm_component(c, w, h) for c in comps])
    slots = _aggregate(samples_components)
    return GoldenBoard(board_type=board_type, n_reference_samples=len(records), slots=slots)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="построить эталон из хороших образцов")
    b.add_argument("--board-type", required=True)
    b.add_argument("--from", dest="src", required=True, help="JSONL с хорошими образцами")
    b.add_argument("--image-id", default=None, help="взять только этот image_id (если в файле много изделий)")
    b.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.cmd == "build":
        records = list(_iter_good_samples(args.src, image_id=args.image_id))
        if not records:
            raise SystemExit("no matching good samples")
        # для одного образца обычно несколько сэмплов (describe+refer) — берём только describe
        records = [r for r in records if r.get("meta", {}).get("kind", "describe") == "describe"] or records
        golden = build_golden(args.board_type, records)
        import os
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(golden.to_json(), f, ensure_ascii=False, indent=2)
        print(f"golden '{args.board_type}': {len(golden.slots)} slots from {len(records)} sample(s) -> {args.out}")


if __name__ == "__main__":
    main()
