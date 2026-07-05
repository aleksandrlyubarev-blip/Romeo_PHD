# Self-Harness PoC — цикл самоулучшения обвязки для RoboQC

Рабочий прототип трёхстадийного цикла из *Self-Harness: Harnesses That
Improve Themselves* (arXiv:2606.09498) на синтетическом QC-окружении
(инспекция печатных плат). Дизайн-документ: `docs/self-harness-roboqc.md`.

## Запуск

```bash
python3 self_harness_poc.py            # seed 42, 1200 задач, до 6 раундов
python3 self_harness_poc.py --seed 7 --tasks 2000
```

Только stdlib, детерминирован по seed. Результаты пишутся в
`results/summary.json` (полный лог раундов) и `results/rounds.csv`
(вердикты по каждой правке).

## Что демонстрирует эталонный прогон (seed 42)

- **Weakness Mining** кластеризует ошибки по сигнатуре
  `(причина верификатора, механизм агента, контекст)` и находит все
  9 recurring-паттернов: дрейф формата вывода, пропуски под бликом,
  непокрытые few-shot типы дефектов, бесконечные циклы переинспекции,
  false positives на коннекторах и галлюцинации.
- **Harness Proposal** выдаёт минимальные правки (ровно одна editable
  surface на правку), каждая привязана к mined weakness, плюс два
  «дистрактора» для проверки валидатора.
- **Proposal Validation** (paired evaluation на held-in/held-out,
  non-regression rule) принимает все 8 таргетных правок и отклоняет оба
  дистрактора: `paranoid_reject_everything` — регрессия по false positives,
  `add_generic_caution_instruction` — нулевой эффект.
- Цикл **сам останавливается**, когда остаётся только нередуцируемый
  остаток классификатора (`residual_classifier_miss`).

| pass rate | held-in | held-out |
|---|---|---|
| baseline | 56.3% | 53.3% |
| после цикла | 92.7% | 91.5% |

«Агент» — стохастический симулятор с failure modes, управляемыми surfaces
обвязки: прототип показывает механику контура, а не способности конкретной
LLM. LLM-proposer подключается вместо каталога правок (`propose_edits`)
без изменения остального контура.
