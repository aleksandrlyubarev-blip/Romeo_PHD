# Buxter MAS Architecture

## 1. Назначение

Buxter — это автономная мультиагентная CAD-система для сквозного проектирования: от инженерной концепции и параметрической 3D-модели до 2D-документации и финальной проверки в коммерческих CAD-интерфейсах.

## 2. Архитектурные роли

### 2.1 Orchestrator
- принимает задание;
- декомпозирует процесс на атомарные шаги;
- управляет состояниями, retry и rollback;
- публикует единый журнал действий и handoff-событий.

### 2.2 Modeling Agent
- работает через Python API выбранного CAD-ядра;
- создаёт параметрические 3D-модели;
- сохраняет редактируемые размеры, feature intent и производственные атрибуты;
- поддерживает два бэкенда:
  - **FreeCAD** (default, headless `freecadcmd`) — батч и CI;
  - **Autodesk Fusion 360** — timeline + native `.f3d`, см. [`buxter-fusion-360-integration.md`](./buxter-fusion-360-integration.md).

### 2.3 Geometry & Topology Validator
- проверяет целостность B-Rep/топологии;
- выявляет коллизии, невалидную геометрию и риски импорта;
- возвращает рекомендации для rollback или исправления.

### 2.4 Interoperability Agent
- экспортирует модель в STEP/DXF/DWG и другие нейтральные форматы;
- контролирует сохранение слоёв, размеров, допусков и аннотаций;
- формирует контракт передачи данных между CAD-средами.

### 2.5 SolidWorks RPA/CV Agent
- управляет GUI SolidWorks через CV/RPA;
- распознаёт элементы интерфейса и выполняет последовательности действий;
- фиксирует недетерминированные ошибки GUI и передаёт их оркестратору.

## 3. Сквозной workflow

1. **Scope orchestration** — Buxter формализует входные требования, критерии качества и rollback checkpoints.
2. **Modeling** — создаётся или модифицируется параметрическая 3D-модель (FreeCAD или Fusion 360).
3. **Geometry validation** — проверяются топология, коллизии и экспортная готовность.
4. **Interoperability export** — формируются нейтральные CAD-артефакты и правила обмена данными.
5. **AutoCAD documentation** — выпускаются 2D-чертежи и аннотированные DWG-доставки.
6. **SolidWorks GUI review** — выполняется автоматическая проверка сборки и сопряжений через GUI.
7. **Rollback/reporting** — при ошибках оркестратор инициирует откат и формирует итоговый отчёт.

## 4. Нефункциональные принципы

- **Надёжность:** rollback-first orchestration для сбоев импорта, геометрии и GUI.
- **Детерминированность:** шаги должны иметь воспроизводимые входы/выходы и явные контрольные точки.
- **Безопасность:** RPA-модуль изолируется, а все действия логируются.
- **Масштабируемость:** роли Buxter проектируются как отдельные агенты/воркеры.

## 5. Технологический каркас

- Основной язык: Python 3.11+.
- FreeCAD integration: Python API.
- Fusion 360 integration: Python API через скрипты/MCP, см. `lib/integrations/fusion_360_integrations`.
- CV/RPA: OpenCV/YOLO + PyAutoGUI/кастомный раннер.
- Возможный SolidWorks-side microservice: C#.
- Кандидаты orchestration layer: LangGraph, CrewAI, AutoGen, Semantic Kernel или custom MAS на FastAPI + Redis.

## 6. Что уже отражено в интерфейсе Romeo PHD

- На Dashboard Buxter показывается как blueprint multi-agent CAD stack.
- В IDE есть стартовый pipeline-шаблон `Buxter End-to-End CAD MAS`.
- Этот шаблон специально раскладывает процесс по ролям orchestration, modeling, validation, interoperability, AutoCAD, SolidWorks RPA и rollback.
- Тип ноды `buxter.fusion-360` выведён в `lib/integrations/fusion_360_integrations` и используется в Sprint 3 Automation Layer-шаблоне.
