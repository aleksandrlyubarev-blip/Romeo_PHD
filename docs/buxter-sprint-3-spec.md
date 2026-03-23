# Buxter Sprint 3 — Техническое задание

## 1. Основание для старта Sprint 3

### Self-review Sprint 2
По итогам self-review Sprint 2 выявлены следующие выводы:
- execution-oriented FreeCAD/interoperability layer уже описан как исполняемый контур;
- текущий Sprint 2 handoff достаточно зрелый, чтобы переходить к automation layer, но ещё не тянуть за собой весь production-grade full MAS;
- следующий инкремент должен добавить guarded GUI/RPA automation и rollback-first review loop.

## 2. Цель Sprint 3

Спринт 3 переводит Buxter в **automation stage**:
- добавить guarded AutoCAD/SolidWorks automation path;
- формализовать automation safety gates;
- подготовить production review handoff для full MAS rollout.

## 3. Scope Sprint 3

### Входит
- preset `Buxter Sprint 3 Automation Layer`;
- guarded CAD automation workflow с automation gate и rollback loop;
- production review decision на выходе спринта.

### Не входит
- полностью безнадзорный production rollout;
- enterprise approval workflows и governance automation;
- финальная промышленная эксплуатация full MAS.

## 4. Backlog Sprint 3

- **BXT-301**: добавить Sprint 3 preset в catalog.
- **BXT-302**: сделать Sprint 3 активным пресетом по умолчанию.
- **BXT-303**: перевести dashboard delivery status на Sprint 3 active.
- **BXT-304**: задокументировать Sprint 2 review findings и handoff в full MAS production track.

## 5. Acceptance criteria

Спринт 3 считается завершённым, если:
- IDE по умолчанию загружает `Buxter Sprint 3 Automation Layer`;
- dashboard показывает Sprint 2 как completed и Sprint 3 как active;
- шаблон включает automation stage, rollback stage и production review gate;
- UI показывает automation-specific tooling, quality gates и handoff для текущего спринта.
