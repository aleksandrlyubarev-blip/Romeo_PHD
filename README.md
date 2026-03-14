# RomeoPHD v6.0

Платформа агентной разработки с Human-in-the-Loop оркестрацией.

## Структура проекта

```
romeophi_v6/
├── src/
│   ├── compiler/
│   │   ├── llm_worker.py        # LLM-адаптер с безопасной AST-инъекцией
│   │   └── human_loop.py        # HITL-оркестратор на LangGraph
│   ├── devops/
│   │   ├── ai_telemetry.py      # Логгер цепочек рассуждений агентов
│   │   └── terraform_main.tf    # IaC для локального K8s (Kind)
│   └── web_ui/
│       └── src/app/page.tsx     # Next.js IDE: Monaco + React Flow
├── tests/
│   ├── test_parser.py           # Тесты парсера + алгоритм Кана
│   └── test_solver.py           # Тесты ConstraintPropagator
├── .github/workflows/
│   └── intent_pipeline.yml      # CI/CD с Self-Healing
├── Dockerfile                   # Multi-stage Python backend
├── docker-compose.yml           # Полный стек: compiler + web_ui + postgres
└── requirements.txt
```

## Быстрый старт

```bash
# 1. Установить зависимости Python
pip install -r requirements.txt

# 2. Запустить тесты
pytest tests/ -v

# 3. Запустить полный стек
cp .env.example .env  # добавить OPENROUTER_API_KEY
docker compose up --build

# Фронтенд: http://localhost:3000
# Compiler API: http://localhost:8000
```

## Переменные окружения

| Переменная         | Описание                        |
|--------------------|---------------------------------|
| OPENROUTER_API_KEY | API-ключ для LLM Worker         |
| DATABASE_URL       | PostgreSQL для LangGraph HITL   |
| LOG_LEVEL          | Уровень логирования (INFO/DEBUG)|

## TODO для MVP

- [ ] `src/compiler/api.py` — FastAPI шлюз (/start, /get_state, /resume)
- [ ] `src/compiler/executor.py` — точка входа для self-healing CI
- [ ] `src/compiler/parser.py` — реальный парсер YAML → граф
- [ ] `src/compiler/solver.py` — реальный ConstraintPropagator
- [ ] `src/web_ui/src/app/Dockerfile` — образ для Next.js
- [ ] WebSocket для live-обновлений статусов узлов React Flow
- [ ] PostgresSaver вместо MemorySaver в human_loop.py

