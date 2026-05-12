"""Метрики качества модели описания PCBA (§10 ТЗ) — скелет.

Считает по предсказаниям модели (JSON по схеме pcba/schema.py) против ground truth:
  * сегментация/классификация: per-class precision/recall/F1 при IoU>=thr, mean IoU;
    (полноценный mAP@[.5:.95] — через pycocotools на COCO-форматированных предсказаниях);
  * downstream good/bad: при наличии diff'а образца к эталону — defect recall,
    false-call rate, end-to-end accuracy.

Зависимости: numpy, shapely (IoU полигонов), scipy (венгерский матчинг).
Здесь — чистый-Python fallback для bbox-IoU, чтобы файл импортировался без зависимостей;
полигональный путь требует shapely.

CLI:
    python3 -m eval.metrics --pred preds.jsonl --gt data/manifest/test.jsonl --iou 0.5
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict


# --- IoU ---

def bbox_iou(a: list[float], b: list[float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def polygon_iou(poly_a: list[list[float]], poly_b: list[list[float]]) -> float:
    """IoU полигонов (нормализованные координаты ок). Требует shapely; иначе кидает ImportError."""
    from shapely.geometry import Polygon  # type: ignore
    pa, pb = Polygon(poly_a), Polygon(poly_b)
    if not pa.is_valid:
        pa = pa.buffer(0)
    if not pb.is_valid:
        pb = pb.buffer(0)
    if pa.is_empty or pb.is_empty:
        return 0.0
    inter = pa.intersection(pb).area
    union = pa.union(pb).area
    return inter / union if union > 0 else 0.0


# --- матчинг предсказаний и GT (greedy по убыванию IoU; для строгого mAP — pycocotools) ---

def match_components(pred: list[dict], gt: list[dict], iou_thr: float, use_polygon: bool) -> dict:
    pairs = []
    for i, p in enumerate(pred):
        for j, g in enumerate(gt):
            try:
                iou = polygon_iou(p["polygon"], g["polygon"]) if use_polygon else bbox_iou(p["bbox"], g["bbox"])
            except ImportError:
                iou = bbox_iou(p["bbox"], g["bbox"])
            if iou >= iou_thr:
                pairs.append((iou, i, j))
    pairs.sort(reverse=True)
    used_p, used_g, matched = set(), set(), []
    for iou, i, j in pairs:
        if i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
        matched.append((i, j, iou))
    return {
        "matched": matched,
        "fp": [i for i in range(len(pred)) if i not in used_p],
        "fn": [j for j in range(len(gt)) if j not in used_g],
    }


def _parse_jsonl_components(path: str) -> dict:
    """image_id -> list[component]. Принимает как полный объект схемы, так и Sa2VA conversation-сэмплы."""
    out: dict = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "conversations" in rec:  # Sa2VA-формат: ответ в роли gpt
                gpt = next((c["value"] for c in rec["conversations"] if c["from"] == "gpt"), "{}")
                obj = json.loads(gpt)
                key = rec.get("meta", {}).get("image_id", rec.get("image"))
            else:
                obj = rec
                key = obj.get("image_id")
            out.setdefault(key, []).extend(obj.get("components", []))
    return out


def evaluate(pred_path: str, gt_path: str, iou_thr: float, use_polygon: bool) -> dict:
    preds = _parse_jsonl_components(pred_path)
    gts = _parse_jsonl_components(gt_path)

    tp = fp = fn = 0
    cls_tp: dict = defaultdict(int)
    cls_fp: dict = defaultdict(int)
    cls_fn: dict = defaultdict(int)
    iou_sum = 0.0
    n_matched = 0
    cls_correct_on_match = 0

    for key in set(preds) | set(gts):
        p, g = preds.get(key, []), gts.get(key, [])
        m = match_components(p, g, iou_thr, use_polygon)
        for i, j, iou in m["matched"]:
            iou_sum += iou
            n_matched += 1
            if p[i].get("class") == g[j].get("class"):
                cls_correct_on_match += 1
                cls_tp[g[j]["class"]] += 1
                tp += 1
            else:
                cls_fp[p[i].get("class", "unknown")] += 1
                cls_fn[g[j]["class"]] += 1
                fp += 1
                fn += 1
        for i in m["fp"]:
            cls_fp[p[i].get("class", "unknown")] += 1
            fp += 1
        for j in m["fn"]:
            cls_fn[g[j]["class"]] += 1
            fn += 1

    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    per_class = {}
    for c in set(cls_tp) | set(cls_fp) | set(cls_fn):
        ctp, cfp, cfn = cls_tp[c], cls_fp[c], cls_fn[c]
        cp = ctp / (ctp + cfp) if (ctp + cfp) else 0.0
        cr = ctp / (ctp + cfn) if (ctp + cfn) else 0.0
        per_class[c] = {"precision": round(cp, 4), "recall": round(cr, 4), "tp": ctp, "fp": cfp, "fn": cfn}

    return {
        "iou_threshold": iou_thr,
        "matching": "polygon" if use_polygon else "bbox",
        "overall": {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
                    "mean_iou_on_match": round(iou_sum / n_matched, 4) if n_matched else 0.0,
                    "class_acc_on_match": round(cls_correct_on_match / n_matched, 4) if n_matched else 0.0,
                    "tp": tp, "fp": fp, "fn": fn},
        "per_class": per_class,
    }


# --------------------------------------------------------------------------- #
# Downstream good/bad: метрики вердикта (§10 ТЗ)
# --------------------------------------------------------------------------- #

def _match_defects(pred_defects: list[dict], gt_defects: list[dict]) -> tuple[int, int, int]:
    """Жадный one-to-one матч предсказанных дефектов с GT по (type, class или id).

    Возвращает (matched, fp, fn) — где matched = TP по дефектам.
    """
    used_p = [False] * len(pred_defects)
    matched = 0
    for g in gt_defects:
        gtype = g.get("type")
        gid = g.get("ref_id")
        gcls = g.get("ref_class")
        for i, p in enumerate(pred_defects):
            if used_p[i]:
                continue
            if p.get("type") != gtype:
                continue
            if (gid is not None and (p.get("component_id") == gid)) or \
               (gcls is not None and (p.get("cls") == gcls)) or \
               (gid is None and gcls is None):
                used_p[i] = True
                matched += 1
                break
    fp = sum(1 for u in used_p if not u)
    fn = len(gt_defects) - matched
    return matched, fp, fn


def evaluate_verdicts(cases_path: str, golden_path: str, policy_overrides: dict | None = None) -> dict:
    """Прогнать compare() на симулированных/реальных кейсах и посчитать метрики вердикта.

    cases_path: JSONL со строками {"sample": <описание-схема>, "gt_defects": [...], "label": "OK"|"NOK"}
                (см. pcba/inject_defects.py — либо реальные размеченные образцы в том же виде).
    golden_path: JSON эталона (pcba.golden build).
    """
    # импорт здесь, чтобы eval.metrics оставался импортируемым без пакета pcba в окружениях анализа
    from pcba.golden import GoldenBoard
    from pcba.compare import compare, ComparePolicy

    with open(golden_path, "r", encoding="utf-8") as f:
        golden = GoldenBoard.from_json(json.load(f))
    policy = ComparePolicy(**(policy_overrides or {}))

    n = 0
    n_good = n_bad = 0
    e2e_correct = 0
    false_calls = 0          # label OK, verdict NOK
    escapes = 0              # label NOK, verdict OK
    d_tp = d_fp = d_fn = 0
    type_stat: dict = defaultdict(lambda: {"tp": 0, "fn": 0})

    with open(cases_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            sample = case["sample"]
            gt_defects = case.get("gt_defects", [])
            label = case.get("label") or ("NOK" if gt_defects else "OK")
            res = compare(sample, golden, policy)
            pred_defects = [d.__dict__ if hasattr(d, "__dict__") else d for d in res.defects]
            n += 1
            if label == "OK":
                n_good += 1
                if res.verdict == "NOK":
                    false_calls += 1
            else:
                n_bad += 1
                if res.verdict == "OK":
                    escapes += 1
            if res.verdict == label:
                e2e_correct += 1
            m, fp, fn = _match_defects(pred_defects, gt_defects)
            d_tp += m
            d_fp += fp
            d_fn += fn
            # per-type recall
            # (повторный лёгкий матч для статистики по типам)
            used = [False] * len(pred_defects)
            for g in gt_defects:
                hit = False
                for i, p in enumerate(pred_defects):
                    if used[i] or p.get("type") != g.get("type"):
                        continue
                    if (g.get("ref_id") and p.get("component_id") == g.get("ref_id")) or \
                       (g.get("ref_class") and p.get("cls") == g.get("ref_class")) or \
                       (not g.get("ref_id") and not g.get("ref_class")):
                        used[i] = True
                        hit = True
                        break
                type_stat[g.get("type")]["tp" if hit else "fn"] += 1

    defect_recall = d_tp / (d_tp + d_fn) if (d_tp + d_fn) else 0.0
    defect_precision = d_tp / (d_tp + d_fp) if (d_tp + d_fp) else 0.0
    return {
        "n_cases": n, "n_good": n_good, "n_bad": n_bad,
        "end_to_end_accuracy": round(e2e_correct / n, 4) if n else 0.0,
        "false_call_rate": round(false_calls / n_good, 4) if n_good else 0.0,
        "escape_rate": round(escapes / n_bad, 4) if n_bad else 0.0,
        "defect_recall": round(defect_recall, 4),
        "defect_precision": round(defect_precision, 4),
        "defect_tp": d_tp, "defect_fp": d_fp, "defect_fn": d_fn,
        "per_defect_type": {t: {"recall": round(v["tp"] / (v["tp"] + v["fn"]), 4) if (v["tp"] + v["fn"]) else 0.0,
                                "tp": v["tp"], "fn": v["fn"]} for t, v in type_stat.items()},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="PCBA model evaluation")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seg", help="метрики сегментации/классификации (pred vs gt)")
    s.add_argument("--pred", required=True, help="JSONL предсказаний (объекты схемы или Sa2VA-сэмплы)")
    s.add_argument("--gt", required=True, help="JSONL ground truth (то же)")
    s.add_argument("--iou", type=float, default=0.5)
    s.add_argument("--polygon", action="store_true", help="матчить по полигонам (требует shapely)")

    v = sub.add_parser("verdicts", help="метрики вердикта good/bad (compare() vs golden)")
    v.add_argument("--cases", required=True, help='JSONL: {"sample":..., "gt_defects":[...], "label":"OK|NOK"}')
    v.add_argument("--golden", required=True, help="JSON эталона (pcba.golden build)")

    args = ap.parse_args()
    if args.cmd == "seg":
        res = evaluate(args.pred, args.gt, args.iou, args.polygon)
    else:
        res = evaluate_verdicts(args.cases, args.golden)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
