# Buxter — Fusion 360 Integration

## 1. Назначение

Расширяет **FreeCAD Modeling Agent** из [Buxter MAS](./buxter-mas-architecture.md) вторым бэкендом — **Autodesk Fusion 360**. Для высокоуровневых ролей (Orchestrator, Validator, Interoperability, RPA) это прозрачно: они выбирают бэкенд по флагу в pipeline-ноде.

Репо: [`aleksandrlyubarev-blip/buxter`](https://github.com/aleksandrlyubarev-blip/buxter) (ветка `claude/fusion-360-integration-R3sTD`).

## 2. Почему два бэкенда

| Аспект                | FreeCAD                                | Fusion 360                                 |
|-----------------------|----------------------------------------|--------------------------------------------|
| Лицензия               | LGPL, бесплатно                       | коммерческая подписка                     |
| Headless              | да (`freecadcmd`)                       | нет — GUI-процесс                          |
| CI                    | подходит                              | только рабочая станция или MCP-режим        |
| Sketch и Timeline    | ручная сборка через Part API           | полный parametric timeline с history    |
| Экспорт                | STL, STEP                              | STL, STEP, IGES, OBJ, native `.f3d`         |
| RPA-интеграция       | ограничена                              | тесная связвка с SolidWorks или ИНвентор |

Поэтому FreeCAD остаётся основным бэкендом для батчевых прогонов, а Fusion 360 включается, когда нужна осознаваемая operator-ом модель с timeline или ready-to-ship `.f3d` для коллег.

## 3. Режимы исполнения

### 3.1 `dryrun` (default)

Buxter генерирует Python-скрипт и пишет его в `out/_gen_fusion.py`. Ничего не запускается. Operator потом выполняет скрипт вручную в Fusion: **Utilities → Add-Ins → Scripts → +**, выбрать файл, **Run**.

Когда использовать:
- pipeline в CI/headless;
- HITL-пауза для review скрипта до выполнения;
- демо/семплы для LinkedIn или обучающих материалов.

### 3.2 `subprocess`

Buxter вызывает Fusion 360 через `FUSION_CMD -ExecuteScript=path/to/_gen_fusion.py`. Работает только на рабочей станции с фоновым GUI: Fusion при первом запуске просит логин и требует active session. Непригоден для Codespaces/Replit/Docker.

Когда использовать:
- инженер работает локально с установленным Fusion;
- нужна быстрая итерация `draw → inspect → retry` без ручного запуска.

### 3.3 `mcp`

Скрипт исполняется внутри Claude Desktop через Fusion 360 MCP-коннектор. Buxter отвечает только за генерацию промпта и логирование результата. Этот режим отмечен в типах (`FusionExecMode`), но локально в `fusion_runner.py` пока не реализован — connector живёт в Claude Desktop, не в Buxter CLI.

## 4. Контракт pipeline-ноды

Новый тип ноды: `buxter.fusion-360`. Конфиг (см. `lib/integrations/fusion_360_integrations/src/types.ts`):

```yaml
nodes:
  - id: model
    type: buxter.fusion-360
    description: "корпус для платы Pi 5 95×65×30, M3 отверстия по углам"
    execMode: dryrun
    exportFormats: [stl, step, f3d]
    approvalRequired: true
```

При `approvalRequired: true` pipeline-executor ставит HITL-паузу с ID сгенерированного скрипта в поле consultation и продолжается только после ack от operator-а.

## 5. Environment

| Переменная                  | Назначение                                                               |
|------------------------------|------------------------------------------------------------------------|
| `ANTHROPIC_API_KEY`          | API-ключ Claude (общий с FreeCAD-бэкендом).                              |
| `BUXTER_BACKEND`             | `freecad` (default) или `fusion`.                                       |
| `FUSION_CMD`                 | Абсолютный путь до Fusion 360. Нужен только в `subprocess`-режиме.        |
| `FUSION_EXEC_MODE`           | `dryrun` (default) или `subprocess`.                                    |
| `FUSION_EMIT_F3D`            | `true`/`false` — дополнительно экспортировать native `.f3d`.            |
| `BUXTER_OUTPUT_DIR`          | Директория артефактов.                                                  |
| `BUXTER_FUSION_BASE_URL`     | URL HTTP-обёртки Buxter, к которой ходит `BuxterFusionClient`.            |
| `BUXTER_FUSION_TOKEN`        | Bearer-токен для HTTP-обёртки (опционально).                          |

## 6. Артефакты

```
out/
  _gen_fusion.py     # сгенерированный скрипт (всегда)
  out.stl            # в режиме subprocess или после ручного запуска
  out.step           # B-Rep для интероперабельности
  out.f3d            # native Fusion archive (при FUSION_EMIT_F3D=true)
  run.log            # лог выполнения или dryrun-запись
```

## 7. Ограничения

- Fusion 360 не является headless — `subprocess` не подходит для CI/Codespaces.
- API Fusion реже выходит в публичных release notes; ломающие изменения ловим через retry и ревизии промпта.
- MCP-режим живёт в Claude Desktop и не подключён к pipeline-executor; он зафиксирован в типах как future contract.
- Native `.f3d` не является neutral CAD-форматом — для Interoperability Agent используется STEP.

## 8. Roadmap

1. HTTP-обёртка Buxter (`BUXTER_FUSION_BASE_URL`) с endpoint-ами `/api/fusion/draw` и `/api/fusion/retry`.
2. pipeline-executor: обработчик `buxter.fusion-360` и SSE-события `script_emitted`/`approval_required`/`completed`.
3. Validator integration: STL → `trimesh` watertight + min-wall → вердикт в telemetry.
4. Snapshot тесты на system prompts (`FUSION_SYSTEM_PROMPT`) в buxter в Репо.
