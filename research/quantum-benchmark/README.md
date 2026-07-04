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
