# ml/ — обучение VLM для описания PCBA (Sa2VA-InternVL3-14B)

Код подготовки данных и обучения для модели описания печатных плат (PCBA) из ТЗ
[`docs/vlm-pcba-tz.md`](../docs/vlm-pcba-tz.md). Базовая модель — **`ByteDance/Sa2VA-InternVL3-14B`**
(InternVL3-14B backbone + интегрированный SAM2, dense referring segmentation «из коробки»).

> Это трек B из ТЗ (VLM + LoRA-файнтюн). Контрастный датасет, который генерирует
> `pcba/build_contrastive.py`, переиспользуется треком C (RepE/SAE/steering).

## Структура

```
ml/
  requirements.txt              # python-зависимости подготовки данных + обучения
  Dockerfile                    # обучающий контейнер для GCP (CUDA + xtuner + sa2va)
  configs/
    sa2va_internvl3_14b_pcba_lora.py   # XTuner-конфиг LoRA-файнтюна Sa2VA-InternVL3-14B (трек B)
  pcba/
    taxonomy.py                 # классы компонентов и типы дефектов (см. §4, §7 ТЗ)
    schema.py                   # JSON-схема ответа модели + промпт-шаблоны
    make_sample_dataset.py      # генерирует крошечный синтетический COCO-датасет (без зависимостей)
    coco_to_sa2va.py            # COCO instance-seg -> Sa2VA conversation JSONL (GCG-формат)
    build_contrastive.py        # из Sa2VA JSONL -> контрастные пары (good vs blurry) для трека C
    make_manifest.py            # train/val/test split + манифест датасета
    golden.py                   # эталон платы («golden board») из одного/нескольких хороших образцов
    compare.py                  # сравнение образца с эталоном -> diff дефектов + вердикт OK/NOK (§10 ТЗ)
    inject_defects.py           # симулятор дефектов на уровне ОПИСАНИЯ — для тестов compare/метрик
    predict.py                  # инференс описания: бэкенды hf / mlx / mock; извлечение+валидация JSON
    pipeline.py                 # end-to-end: фото -> описание -> compare -> вердикт + evidence-запись
    run_m5pro.py                # инференс на Apple M5 Pro через mlx-vlm (§9 ТЗ)
  baseline/                     # трек A (§5.1 ТЗ): YOLOv11-seg + SAM2 как baseline
    coco_to_yolo.py             # COCO instance-seg -> YOLO-seg датасет + data.yaml
    train_yolo.sh               # обучение YOLOv11-seg (ultralytics)
  repe/                         # трек C (§5.3 ТЗ): model-native steering (RepE / SAE)
    layers.py                   # адресация residual-stream слоёв Sa2VA (плейсхолдеры под релиз)
    extract_activations.py      # снять активации на контрастных парах
    fit_steering.py             # diff-of-means / SAE -> steering.json (слои + векторы + масштаб)
    apply_steering.py           # forward-hook инъекции вектора на инференсе (используется из predict.py)
  scripts/
    prepare_dataset.sh          # end-to-end: sample -> convert -> contrastive -> manifest
    eval_smoke.sh               # golden -> симуляция дефектов -> compare -> метрики вердикта
    run_tests.sh                # юнит-тесты + интеграционная проверка всего пайплайна (без модели)
    train_lora_local.sh         # запуск xtuner-обучения локально / на одной ноде
    launch_gcp_vertex.sh        # submit Vertex AI Custom Job (A100/H100)
    quantize_m5pro.sh           # квантизация merged-чекпойнта под M5 Pro (MLX / llama.cpp GGUF)
  eval/
    metrics.py                  # seg: precision/recall/IoU per-class; verdicts: defect recall / false-call / escape / e2e acc
  tests/
    test_basic.py               # юнит-тесты без зависимостей (python3 -m tests.test_basic)
```

Соответствие трекам ТЗ (§5): **A** — `baseline/` (YOLOv11-seg + SAM2); **B** — `configs/` + `scripts/train_lora_local.sh` (Sa2VA-InternVL3-14B + LoRA/QLoRA); **C** — `repe/` (steering-векторы поверх той же модели, без изменения весов). Все три кормятся из общего датасета (`pcba/coco_to_sa2va.py`, `pcba/build_contrastive.py`); сравниваются единым `eval/metrics.py` и downstream-логикой `pcba/compare.py`.

## Быстрый старт (подготовка данных)

```bash
cd ml
python3 -m pip install -r requirements.txt        # для самой подготовки данных хватает stdlib; зависимости нужны для обучения
bash scripts/prepare_dataset.sh                   # создаст data/ с сэмплом и всеми производными
```

После прогона появится:

```
ml/data/
  sample_coco/                  # синтетический COCO (images/ + annotations.json)
  sa2va/all.jsonl               # conversation-формат для Sa2VA
  contrastive/pairs.jsonl       # контрастные пары для RepE/SAE
  manifest/{train,val,test}.jsonl
  manifest/dataset_card.json
```

Реальные данные кладутся в том же COCO-формате (instance segmentation, полигоны),
после чего шаги `coco_to_sa2va.py -> build_contrastive.py -> make_manifest.py`
повторяются на них. Синтетику генерирует пайплайн «Бригада»
(`RomeoFlexVision/docs/brigada-architecture.md`) — её выход также приводится к COCO.

## Обучение

Локально / на одной GPU-ноде:

```bash
bash scripts/train_lora_local.sh
```

В GCP (Vertex AI Custom Job, A100 80GB или H100 80GB):

```bash
PROJECT_ID=... REGION=us-central1 BUCKET=gs://... IMAGE_URI=... \
  bash scripts/launch_gcp_vertex.sh
```

Подробности по железу, бюджету и воспроизводимости — раздел 8 ТЗ.

После обучения смержить LoRA в fp16 и квантовать под M5 Pro:

```bash
xtuner convert pth_to_hf <config> <out>/last_checkpoint <out>/hf
xtuner convert merge ByteDance/Sa2VA-InternVL3-14B <out>/hf <out>/merged --max-shard-size 4GB
bash scripts/quantize_m5pro.sh <out>/merged <out>/m5pro both    # MLX 4-bit и/или GGUF Q4_K_M
```

## Трек A — YOLOv11-seg + SAM2 (baseline)

```bash
pip install ultralytics
python3 -m baseline.coco_to_yolo --coco <coco.json> --image-root <images> --out data/yolo --val 0.2
DATA=data/yolo/data.yaml MODEL=yolo11s-seg.pt EPOCHS=100 IMGSZ=1280 bash baseline/train_yolo.sh
# инференс: YOLO bbox -> SAM2 (уточнение масок) -> привести к схеме pcba/schema.py -> pcba.compare
```

## Трек C — model-native steering (RepE / SAE)

Веса базовой модели не меняются — навык «PCB AOI expert» внедряется вектором в residual stream
(идея из видео «Beyond Markdown: Geometry of Model-Native Skills»). Запускать в обучающем контейнере.

```bash
python3 -m repe.extract_activations --pairs data/contrastive/pairs.jsonl --image-root data/sample_coco \
  --model ByteDance/Sa2VA-InternVL3-14B --layers-llm -1 -8 -16 --out work_dirs/repe/acts.npz
python3 -m repe.fit_steering --acts work_dirs/repe/acts.npz --topk 3 --scale 2.0 --out work_dirs/repe/steering.json
# инференс со steering:
python3 -m pcba.predict --backend hf --model ByteDance/Sa2VA-InternVL3-14B \
  --steering work_dirs/repe/steering.json --steer-scale 2.0 --images <dir> --out preds.jsonl
```

`repe/layers.py` — единственное место, которое правится под конкретный релиз Sa2VA (пути к decoder-слоям LLM / блокам InternViT). SAE-вариант подключается в `repe/fit_steering.py::sae_directions`.

## Инференс и end-to-end пайплайн

```bash
# описание (mock — без модели, эхо GT; для отладки downstream):
python3 -m pcba.predict --images data/sample_coco/annotations.json --image-root data/sample_coco \
  --backend mock --gt-echo data/manifest/test.jsonl --out data/eval/preds.jsonl
python3 -m eval.metrics seg --pred data/eval/preds.jsonl --gt data/manifest/test.jsonl --iou 0.5

# полный конвейер: фото -> описание -> сравнение с эталоном -> вердикт + evidence-запись:
python3 -m pcba.pipeline --image data/sample_coco/images/board_0001.png --image-id 1 \
  --golden data/golden/my_board_v1.json --backend mock --gt-echo data/manifest/train.jsonl --out report.json
# на M5 Pro: --backend mlx --model <out>/m5pro/mlx   (или python3 -m pcba.run_m5pro ...)
```

## Тесты

```bash
bash scripts/run_tests.sh        # юнит-тесты + интеграция (dataset prep, COCO->YOLO, golden/compare, metrics, pipeline) — всё без модели
```

## Downstream: вердикт good/bad (§10 ТЗ)

Двухступенчатая схема: VLM выдаёт описание образца -> `compare.py` сопоставляет его
с эталоном (`golden.py`) и формирует diff дефектов + вердикт `OK/NOK`.

```bash
# 1) собрать эталон из хороших образцов (Sa2VA describe-сэмплы или объекты схемы)
python3 -m pcba.golden build --board-type my_board_v1 \
  --from data/manifest/train.jsonl --image-id 1 --out data/golden/my_board_v1.json

# 2) сравнить описание образца с эталоном
python3 -m pcba.compare --golden data/golden/my_board_v1.json --sample sample_description.json

# 3) метрики вердикта на наборе кейсов {"sample":..., "gt_defects":[...], "label":"OK|NOK"}
python3 -m eval.metrics verdicts --cases data/eval/cases.jsonl --golden data/golden/my_board_v1.json
# метрики сегментации/классификации:
python3 -m eval.metrics seg --pred preds.jsonl --gt data/manifest/test.jsonl --iou 0.5

# всё вместе на синтетическом сэмпле (smoke):
bash scripts/eval_smoke.sh
```

`inject_defects.py` мутирует ОПИСАНИЕ хорошей платы (имитация вывода VLM на дефектной)
для проверки `compare.py`/метрик без модели. Генерация дефектных ИЗОБРАЖЕНИЙ — задача
пайплайна «Бригада» (`RomeoFlexVision/docs/brigada-architecture.md`), не этого модуля.
Пороги вердикта (`ComparePolicy` в `compare.py`) и допуски слотов (`golden.py`)
настраиваются под конкретное изделие; целевые значения метрик — раздел 10 ТЗ.

## Замечания

- Числовые гиперпараметры в конфиге — стартовые, подбираются на PoC (Этап 0 ТЗ).
- Любые цифры throughput фиксируются вместе с конфигом (модель, precision, batch,
  длины последовательностей, железо) — как в `RomeoFlexVision/docs/brigada-architecture.md`.
- Полигоны в `coco_to_sa2va.py` сериализуются нормализованными в `[0,1]` (разрешение-инвариантно);
  для Sa2VA-режима с `<seg>`-токенами и SAM2-головой полигоны используются как ground-truth маски.
