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
    sa2va_internvl3_14b_pcba_lora.py   # XTuner-конфиг LoRA-файнтюна Sa2VA-InternVL3-14B
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
  scripts/
    prepare_dataset.sh          # end-to-end: sample -> convert -> contrastive -> manifest
    eval_smoke.sh               # golden -> симуляция дефектов -> compare -> метрики вердикта
    train_lora_local.sh         # запуск xtuner-обучения локально / на одной ноде
    launch_gcp_vertex.sh        # submit Vertex AI Custom Job (A100/H100)
  eval/
    metrics.py                  # seg: precision/recall/IoU per-class; verdicts: defect recall / false-call / escape / e2e acc
```

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
