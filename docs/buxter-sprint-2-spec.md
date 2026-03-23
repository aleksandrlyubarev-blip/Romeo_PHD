# Buxter Sprint 2 — Техническое задание

## 1. Основание для старта Sprint 2

### Self-review Sprint 1
По итогам self-review Sprint 1 выявлены следующие выводы:
- orchestration contract и export handoff уже оформлены достаточно, чтобы двигаться в сторону исполняемого CAD-слоя;
- текущий foundation preset полезен как planning layer, но ещё не даёт executable CAD pipeline;
- следующий инкремент должен добавить first executable CAD path без прыжка сразу в полный SolidWorks RPA scope.

## 2. Цель Sprint 2

Спринт 2 переводит Buxter из planning/foundation стадии в **executable CAD execution stage**:
- подготовить исполняемый FreeCAD-oriented pipeline;
- ввести export-ready interoperability stage;
- сделать release gate для первого исполняемого CAD handoff.

## 3. Scope Sprint 2

### Входит
- execution-oriented preset `Buxter Sprint 2 CAD Execution`;
- FreeCAD execution node вместо одного лишь planning node;
- geometry validation и interoperability export как обязательные quality gates;
- execution review gate перед переходом к Sprint 3 automation scope.

### Не входит
- production-grade AutoCAD automation;
- полный SolidWorks GUI/RPA execution;
- enterprise safety envelope для unattended automation.

## 4. Backlog Sprint 2

- **BXT-201**: добавить Sprint 2 preset в template catalog.
- **BXT-202**: сделать Sprint 2 активным пресетом по умолчанию.
- **BXT-203**: обновить Dashboard, чтобы Sprint 1 считался completed, а Sprint 2 — active.
- **BXT-204**: задокументировать review findings Sprint 1 и criteria входа в Sprint 3.

## 5. Acceptance criteria

Спринт 2 считается завершённым, если:
- в IDE по умолчанию загружается `Buxter Sprint 2 CAD Execution`;
- dashboard явно показывает Sprint 1 как completed и Sprint 2 как active;
- preset содержит executable FreeCAD stage, geometry gate, interoperability export и execution review gate;
- кодовая база отражает переход от planning layer к first executable CAD layer.
