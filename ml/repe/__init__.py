"""Трек C из ТЗ (docs/vlm-pcba-tz.md §5.3): model-native «навык» через RepE / SAE / steering-векторы.

Поток:
  1. extract_activations.py — прогнать VLM на контрастных парах (pcba/build_contrastive.py),
     снять активации residual stream на выбранных слоях для positive/negative.
  2. fit_steering.py — посчитать направление «PCB AOI expert» (diff-of-means или тонкий probe),
     отобрать слои/масштаб, сохранить steering.json.
  3. apply_steering.py — на инференсе добавлять scale * vector в выход выбранных слоёв
     (используется из pcba/predict.py через --steering).

Точные пути модулей внутри Sa2VA-InternVL3-14B (decoder-слои LLM, блоки vision-энкодера,
cross-attention) помечены плейсхолдерами и уточняются по коду модели на момент запуска.
SAE-вариант (SAELens + мультимодальное расширение, sae-for-vlm) подключается здесь же
как альтернатива diff-of-means — см. комментарии в fit_steering.py.
"""
