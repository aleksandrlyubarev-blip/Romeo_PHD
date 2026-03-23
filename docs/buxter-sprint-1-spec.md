# Buxter Sprint 1 — Техническое задание

## 1. Цель спринта

Спринт 1 закладывает **операционное ядро Buxter MVP**: deterministic orchestration, intake инженерных требований, план параметрического моделирования в FreeCAD и формирование контракта на downstream interoperability.

## 2. Границы Sprint 1

### Входит в спринт
- формализация входных требований и ограничений;
- генерация плана FreeCAD-моделирования;
- первичная геометрическая/топологическая проверка как quality gate;
- формирование export/interoperability contract;
- release gate с журналом рисков и handoff для Sprint 2.

### Не входит в спринт
- полноценное GUI-управление SolidWorks;
- production-grade RPA execution;
- финальная AutoCAD/SolidWorks end-to-end автоматизация.

## 3. Архитектурные результаты

Спринт 1 должен оставить после себя следующие кодовые артефакты:
1. **Sprint 1 pipeline preset** в IDE.
2. **Переиспользуемый Buxter catalog module** с шаблонами и sprint metadata.
3. **Dashboard visibility** для Sprint 1 scope и ближайших deliverables.
4. **Документацию sprint scope** для последующего Sprint 2 planning.

## 4. User stories

### US-1: Архитектор workflow
Как инженер-архитектор, я хочу загрузить готовый Buxter Sprint 1 preset, чтобы быстро стартовать orchestration foundation без ручной сборки YAML.

### US-2: CAD lead
Как CAD lead, я хочу видеть Sprint 1 deliverables и quality gates, чтобы понимать, какие части сквозного процесса уже реализуются, а какие остаются на следующие спринты.

### US-3: Orchestrator owner
Как владелец оркестратора, я хочу иметь явный release gate и export contract node, чтобы downstream интеграции строились на предсказуемом handoff.

## 5. Backlog Sprint 1

- **BXT-101**: добавить sprint-specific template catalog для Buxter.
- **BXT-102**: сделать Sprint 1 preset шаблоном по умолчанию в IDE.
- **BXT-103**: показать Sprint 1 scope/roadmap на Dashboard.
- **BXT-104**: задокументировать deliverables, acceptance criteria и handoff в отдельном документе.

## 6. Acceptance criteria

Спринт 1 считается завершённым, если:
- в IDE можно загрузить `Buxter Sprint 1 Foundation` без ручного редактирования YAML;
- Dashboard показывает Sprint 1 scope и ожидаемые deliverables;
- Sprint 1 документирует quality gates и handoff к Sprint 2;
- кодовая база содержит переиспользуемые Buxter definitions, а не дублирование строк по UI.

## 7. Handoff к Sprint 2

На выходе Sprint 1 должны быть готовы:
- стабильный orchestration contract;
- quality gate перед downstream CAD execution;
- список рисков для AutoCAD/SolidWorks automation;
- стартовая точка для внедрения реального FreeCAD/interop executor layer.
