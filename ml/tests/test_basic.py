"""Юнит-тесты без внешних зависимостей. Запуск:  cd ml && python3 -m tests.test_basic"""
from __future__ import annotations

import json
import random
import sys

from pcba import taxonomy, schema
from pcba.predict import extract_first_json, normalize_output
from pcba.coco_to_sa2va import build_samples
from pcba.golden import build_golden, GoldenBoard
from pcba.compare import compare
from eval.metrics import evaluate, evaluate_verdicts  # noqa: F401  (evaluate проверяем ниже)


def test_taxonomy():
    ids = [c.id for c in taxonomy.COMPONENT_CLASSES]
    assert len(ids) == len(set(ids)), "duplicate class ids"
    assert len(taxonomy.CLASS_NAMES) == len(taxonomy.COMPONENT_CLASSES)
    cats = taxonomy.coco_categories()
    assert all("id" in c and "name" in c for c in cats)
    assert "connector" in taxonomy.CLASS_BY_NAME and taxonomy.class_name(6) == "connector"


def test_schema_validate():
    good = {
        "schema_version": schema.SCHEMA_VERSION, "image_size": {"w": 10, "h": 10}, "board_side": "top",
        "components": [{"id": "c-1", "class": "connector", "bbox": [1, 1, 2, 2],
                        "polygon": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3]], "confidence": 0.9}],
    }
    assert schema.validate_output(good) == []
    bad = json.loads(json.dumps(good))
    bad["components"][0]["class"] = "not_a_class"
    assert schema.validate_output(bad), "bad class should fail"
    assert schema.validate_output(123) == ["root is not an object"]


def test_extract_json():
    assert extract_first_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_first_json('blah {"x": {"y": 2}} trailing') == {"x": {"y": 2}}
    assert extract_first_json("no json here") is None
    assert extract_first_json('text "with } brace" then {"ok": true}') == {"ok": True}
    n = normalize_output({"components": [{"class": "screw_fastener"}]}, "img1", 100, 50)
    assert n["schema_version"] == schema.SCHEMA_VERSION and n["image_size"] == {"w": 100, "h": 50}
    assert len(n["components"]) == 1 and n["components"][0]["class"] == "screw_fastener"


_TINY_COCO = {
    "images": [{"id": 1, "file_name": "b1.png", "width": 100, "height": 80, "board_side": "top"}],
    "annotations": [
        {"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 10, 20, 10], "area": 200, "iscrowd": 0,
         "segmentation": [[10, 10, 30, 10, 30, 20, 10, 20]], "attributes": {}},
        {"id": 2, "image_id": 1, "category_id": 6, "bbox": [50, 40, 30, 20], "area": 600, "iscrowd": 0,
         "segmentation": [[50, 40, 80, 40, 80, 60, 50, 60]], "attributes": {"state": "latched"}},
    ],
    "categories": taxonomy.coco_categories(),
}


def test_coco_to_sa2va():
    samples = build_samples(_TINY_COCO, images_prefix="images", refer_per_image=1, rng=random.Random(0))
    kinds = {s["meta"]["kind"] for s in samples}
    assert "describe" in kinds
    desc = next(s for s in samples if s["meta"]["kind"] == "describe")
    ans = json.loads(desc["conversations"][-1]["value"])
    assert len(ans["components"]) == 2
    for c in ans["components"]:
        for (x, y) in c["polygon"]:
            assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0, "polygon not normalized"
    assert len(desc["masks"]) == 2 and desc["masks"][0]["size"] == [80, 100]
    assert schema.validate_output(ans) == []


def _describe_obj_from_coco():
    samples = build_samples(_TINY_COCO, images_prefix="images", refer_per_image=0, rng=random.Random(0))
    desc = next(s for s in samples if s["meta"]["kind"] == "describe")
    return json.loads(desc["conversations"][-1]["value"])


def test_golden_and_compare():
    obj = _describe_obj_from_coco()
    golden = build_golden("board_v1", [{"image_size": obj["image_size"], "components": obj["components"]}])
    assert len(golden.slots) == 2
    # идентичное описание -> OK, без дефектов
    res = compare(obj, golden)
    assert res.verdict == "OK" and len(res.defects) == 0, res.to_json()
    # удалить компонент -> missing -> NOK
    obj_missing = json.loads(json.dumps(obj))
    obj_missing["components"].pop()
    r2 = compare(obj_missing, golden)
    assert r2.verdict == "NOK" and any(d.type == "missing" for d in r2.defects), r2.to_json()
    # лишний компонент -> extra_part
    obj_extra = json.loads(json.dumps(obj))
    extra = json.loads(json.dumps(obj["components"][0]))
    extra["id"] = "c-extra"
    extra["bbox"] = [0, 0, 5, 5]
    obj_extra["components"].append(extra)
    r3 = compare(obj_extra, golden)
    assert any(d.type == "extra_part" for d in r3.defects), r3.to_json()


def test_metrics_seg_identity(tmp_jsonl):
    obj = _describe_obj_from_coco()
    obj["image_id"] = "1"
    path = tmp_jsonl([obj])
    res = evaluate(path, path, iou_thr=0.5, use_polygon=False)
    assert res["overall"]["precision"] == 1.0 and res["overall"]["recall"] == 1.0, res


# --- крошечный «раннер» без pytest ---

def _run():
    import tempfile
    import os

    created = []

    def tmp_jsonl(objs):
        fd, p = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for o in objs:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
        created.append(p)
        return p

    tests = [
        ("taxonomy", lambda: test_taxonomy()),
        ("schema_validate", lambda: test_schema_validate()),
        ("extract_json", lambda: test_extract_json()),
        ("coco_to_sa2va", lambda: test_coco_to_sa2va()),
        ("golden_and_compare", lambda: test_golden_and_compare()),
        ("metrics_seg_identity", lambda: test_metrics_seg_identity(tmp_jsonl)),
    ]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  FAIL {name}: {type(e).__name__}: {e}")
    for p in created:
        try:
            os.remove(p)
        except OSError:
            pass
    if failures:
        print(f"{failures} test(s) failed")
        sys.exit(1)
    print("all tests passed")


if __name__ == "__main__":
    _run()
