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
        # --- downstream good/bad: заполняется когда есть diff образца к эталону ---
        # "defect_recall": ...,        # доля пойманных дефектов (по DEFECT_TYPES)
        # "false_call_rate": ...,      # ложные NOK / общее число хороших образцов
        # "escape_rate": ...,          # пропущенные NOK / общее число дефектных образцов
        # "end_to_end_accuracy": ...,  # accuracy вердикта OK/NOK
        "todo": "defect-level метрики добавляются после реализации downstream-сравнения с эталоном (§10 ТЗ)",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True, help="JSONL предсказаний (объекты схемы или Sa2VA-сэмплы)")
    ap.add_argument("--gt", required=True, help="JSONL ground truth (то же)")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--polygon", action="store_true", help="матчить по полигонам (требует shapely)")
    args = ap.parse_args()
    res = evaluate(args.pred, args.gt, args.iou, args.polygon)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
