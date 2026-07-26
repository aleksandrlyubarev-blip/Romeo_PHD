# RWDM-LiF quantum-computer benchmark — prototype

Прототип бенчмарка для квантовых компьютеров на основе переноса поляризации
⁸Li→⁶Li в LiF (случайные блуждания в неупорядоченной среде, RWDM).

Дизайн исследования: [`docs/quantum-benchmark-rwdm-lif.md`](../../docs/quantum-benchmark-rwdm-lif.md).

## Запуск

```bash
pip install numpy matplotlib
python3 rwdm_qbench_prototype.py   # ~1.5 мин на CPU
```

Результаты пишутся в `results/`:

- `fig_qbench_prototype.png` — Tier A (CTRW vs CTQW, локализация) и
  Tier B (точная многочастичная динамика vs master equation);
- `tier_a_p00.csv`, `tier_b_p00.csv` — усреднённые кривые `P00(τ)`;
- `summary.json` — параметры запуска и контрольные значения.

## Эталонные константы (golden values)

`rwdm_reference_constants.py` — исполняемая фикстура с константами из статей
2009/2014/2021 (разбор: [`docs/article-comparison-2009-2014-2021.md`](../../docs/article-comparison-2009-2014-2021.md)).
Каждая величина хранит значение, единицы, источник и допуск.

**Каноническая нормировка:** `β₀ = 1.122·β₀G = 12.15 с⁻¹` при c=10 % — основная;
`β₀G = 10.80` — legacy/гауссова оценка 2009, не смешивать с β₀.

Тесты (чистая stdlib, без numpy/pytest) покрывают: `β₀∝c²`, преобразование
`β₀G→β₀`, три значения `β₁/β₀`, обе таблицы, обе формы `G(β₀t)`, окно
`β₀t=30–108` (как benchmark/outlier, а не требование совпадения с `F(t)·G(t)`).

```bash
python3 rwdm_reference_constants.py          # печать сводки
python3 -m unittest test_rwdm_reference_constants -v   # 26 тестов, без зависимостей
```
