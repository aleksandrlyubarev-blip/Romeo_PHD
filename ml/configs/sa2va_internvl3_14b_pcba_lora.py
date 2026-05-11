# XTuner-конфиг LoRA-файнтюна Sa2VA-InternVL3-14B на датасете описания PCBA.
#
# Запуск (см. ml/scripts/train_lora_local.sh):
#   xtuner train ml/configs/sa2va_internvl3_14b_pcba_lora.py --deepspeed deepspeed_zero2
#
# Это стартовая конфигурация (трек B из docs/vlm-pcba-tz.md). Гиперпараметры
# подбираются на PoC (Этап 0). Любые цифры throughput фиксируются вместе с конфигом
# (модель, precision, batch, длины, железо) — как в RomeoFlexVision/docs/brigada-architecture.md.
#
# ВАЖНО: точные имена классов/полей XTuner и dataset-обёртки Sa2VA берутся из
# актуального репозитория ByteDance/Sa2VA на момент запуска; здесь они помечены
# плейсхолдерами `sa2va.*` там, где API может отличаться между релизами.

import os

# --------------------------------------------------------------------------- #
# Пути (переопределяются через переменные окружения в launch-скриптах)
# --------------------------------------------------------------------------- #
BASE_MODEL = os.environ.get("SA2VA_BASE_MODEL", "ByteDance/Sa2VA-InternVL3-14B")
DATA_DIR = os.environ.get("PCBA_DATA_DIR", "data/manifest")        # содержит train.jsonl / val.jsonl
IMAGE_ROOT = os.environ.get("PCBA_IMAGE_ROOT", "data/sample_coco") # 'image' в JSONL = относительно этого корня
OUTPUT_DIR = os.environ.get("PCBA_OUTPUT_DIR", "work_dirs/sa2va_internvl3_14b_pcba_lora")
TRAIN_JSONL = os.path.join(DATA_DIR, "train.jsonl")
VAL_JSONL = os.path.join(DATA_DIR, "val.jsonl")

# --------------------------------------------------------------------------- #
# Гиперпараметры
# --------------------------------------------------------------------------- #
max_length = 8192               # длинные JSON-ответы с полигонами
batch_size_per_device = 1       # 14B + изображения: на A100 80GB держим 1, добираем grad accum
accumulative_counts = 16        # эффективный batch = 1 * 16 * num_gpus
dataloader_num_workers = 4
max_epochs = 3
optim_lr = 2e-4                 # типичный LR для LoRA
optim_wd = 0.0
warmup_ratio = 0.03
save_steps = 200
save_total_limit = 3
log_interval = 10
seed = 42

# QLoRA: 4-bit базовая модель + LoRA-адаптеры (помещается в 1×A100 80GB).
# Для полного LoRA в bf16 на multi-GPU поставить load_in_4bit=False и поднять число GPU.
load_in_4bit = True
lora_r = 32
lora_alpha = 64
lora_dropout = 0.05
# Целевые модули — линейные слои языковой части InternVL3 (q/k/v/o/gate/up/down);
# vision-энкодер и SAM2-голову по умолчанию НЕ трогаем (freeze) на старте.
lora_target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
freeze_vision_encoder = True
freeze_sam2 = False             # лёгкое дообучение головы сегментации под мелкие PCBA-компоненты
freeze_llm = True               # сам LLM заморожен, учим только LoRA-адаптеры

# --------------------------------------------------------------------------- #
# Сборка конфига в стиле XTuner (mmengine Runner).
# Имена `sa2va.*` — обёртки модели/датасета из репозитория Sa2VA; при несовпадении
# имён в конкретном релизе поправить здесь по README Sa2VA (раздел training).
# --------------------------------------------------------------------------- #
try:
    # Эти импорты доступны только внутри обучающего контейнера (см. ml/Dockerfile).
    from mmengine.config import read_base  # noqa: F401
    from torch.optim import AdamW
    from transformers import AutoTokenizer
    import sa2va  # репозиторий ByteDance/Sa2VA, установленный как пакет

    tokenizer = dict(type=AutoTokenizer.from_pretrained, pretrained_model_name_or_path=BASE_MODEL, trust_remote_code=True)

    model = dict(
        type=sa2va.Sa2VAModel,                       # обёртка InternVL3 + SAM2
        model_path=BASE_MODEL,
        freeze_llm=freeze_llm,
        freeze_visual_encoder=freeze_vision_encoder,
        freeze_grounding_encoder=freeze_sam2,
        quantization_config=dict(load_in_4bit=load_in_4bit, bnb_4bit_compute_dtype="bfloat16",
                                 bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True) if load_in_4bit else None,
        lora=dict(type="LoraConfig", r=lora_r, lora_alpha=lora_alpha, lora_dropout=lora_dropout,
                  bias="none", task_type="CAUSAL_LM", target_modules=lora_target_modules),
    )

    # Датасет: conversation JSONL из ml/pcba/coco_to_sa2va.py (поля image / conversations / masks).
    train_dataset = dict(
        type=sa2va.PcbaConversationDataset if hasattr(sa2va, "PcbaConversationDataset") else sa2va.GCGDataset,
        data_path=TRAIN_JSONL,
        image_folder=IMAGE_ROOT,
        tokenizer=tokenizer,
        max_length=max_length,
        with_mask=True,                              # подключить SAM2-маски как GT
    )
    val_dataset = dict(**{**train_dataset, "data_path": VAL_JSONL})

    train_dataloader = dict(
        batch_size=batch_size_per_device, num_workers=dataloader_num_workers,
        dataset=train_dataset, sampler=dict(type="DefaultSampler", shuffle=True),
        collate_fn=dict(type=sa2va.sa2va_collate_fn if hasattr(sa2va, "sa2va_collate_fn") else "default_collate"),
    )

    optim_wrapper = dict(
        type="AmpOptimWrapper",
        optimizer=dict(type=AdamW, lr=optim_lr, weight_decay=optim_wd),
        accumulative_counts=accumulative_counts, dtype="bfloat16", clip_grad=dict(max_norm=1.0),
    )
    param_scheduler = [
        dict(type="LinearLR", start_factor=1e-3, by_epoch=True, begin=0, end=warmup_ratio * max_epochs),
        dict(type="CosineAnnealingLR", by_epoch=True, begin=warmup_ratio * max_epochs, end=max_epochs),
    ]
    train_cfg = dict(by_epoch=True, max_epochs=max_epochs)

    default_hooks = dict(
        logger=dict(type="LoggerHook", interval=log_interval),
        checkpoint=dict(type="CheckpointHook", by_epoch=False, interval=save_steps, max_keep_ckpts=save_total_limit),
    )
    # W&B/Vertex Experiments — опционально (выставить переменные окружения).
    visualizer = dict(type="Visualizer", vis_backends=[dict(type="WandbVisBackend")] if os.environ.get("WANDB_PROJECT") else [dict(type="LocalVisBackend")])

    work_dir = OUTPUT_DIR
    randomness = dict(seed=seed, deterministic=False)
    env_cfg = dict(cudnn_benchmark=True)
    launcher = "pytorch"

except ImportError:
    # Вне обучающего контейнера импорты недоступны — экспортируем только параметры,
    # чтобы конфиг можно было импортировать инструментами проверки/линтерами.
    HYPERPARAMS = dict(
        base_model=BASE_MODEL, max_length=max_length, batch_size_per_device=batch_size_per_device,
        accumulative_counts=accumulative_counts, max_epochs=max_epochs, optim_lr=optim_lr,
        load_in_4bit=load_in_4bit, lora_r=lora_r, lora_alpha=lora_alpha,
        lora_target_modules=lora_target_modules, freeze_vision_encoder=freeze_vision_encoder,
        freeze_sam2=freeze_sam2, freeze_llm=freeze_llm, seed=seed,
        train_jsonl=TRAIN_JSONL, val_jsonl=VAL_JSONL, image_root=IMAGE_ROOT, output_dir=OUTPUT_DIR,
    )
    if __name__ == "__main__":
        import json as _json
        print(_json.dumps(HYPERPARAMS, ensure_ascii=False, indent=2))
