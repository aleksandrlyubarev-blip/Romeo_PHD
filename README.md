# RomeoPHD v6.0 — GitHub Codespaces

## Запуск за 3 шага

### Шаг 1 — Добавить API-ключ в GitHub Secrets

Перед созданием Codespace добавьте ключ один раз (он сохранится для всех ваших codespaces):

1. **github.com** → ваш аватар → **Settings**
2. **Codespaces** → **Secrets** → **New secret**
3. Name: `ANTHROPIC_API_KEY`  
   Value: ваш ключ с [console.anthropic.com](https://console.anthropic.com)
4. В поле **Repository access** → выберите этот репозиторий → **Add secret**

### Шаг 2 — Открыть Codespace

1. На странице репозитория → зелёная кнопка **Code**
2. Вкладка **Codespaces** → **Create codespace on main**
3. Подождать ~3 минуты пока запустится setup (прогресс виден в терминале)

### Шаг 3 — Запустить проект

После того как setup завершится, в терминале Codespace:

```bash
pnpm run dev
```

Codespaces автоматически откроет браузер с фронтендом на порту **5173**.  
API работает на порту **3001**.

---

## Структура проекта

```
Romeo-Agent-System/
├── artifacts/
│   ├── api-server/          # Express 5 API (порт 3001)
│   │   └── src/
│   │       ├── lib/pipeline-parser.ts   # Kahn's Algorithm + YAML parser
│   │       ├── lib/pipeline-executor.ts # LLM workers + HITL
│   │       └── routes/pipeline/         # REST endpoints
│   └── romeo-phd/           # React + Vite UI (порт 5173)
│       └── src/pages/
│           ├── ide.tsx          # Monaco Editor + React Flow
│           ├── consultations.tsx # HITL approval queue
│           ├── telemetry.tsx    # Live agent logs
│           └── dashboard.tsx    # Mission Control
├── lib/
│   ├── db/                  # Drizzle ORM + PostgreSQL schema
│   ├── api-zod/             # Zod schemas (auto-generated)
│   ├── api-client-react/    # React Query hooks (auto-generated)
│   └── api-spec/            # OpenAPI 3.1 spec
└── .devcontainer/
    ├── devcontainer.json    # Codespace конфигурация
    ├── setup.sh             # Авто-установка PostgreSQL + deps
    └── patch.mjs            # Исправление критических багов
```

## API endpoints

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/healthz` | Health check |
| GET | `/api/pipelines` | Список пайплайнов |
| POST | `/api/pipelines` | Создать пайплайн из YAML |
| GET | `/api/pipelines/:id` | Пайплайн + узлы |
| POST | `/api/pipelines/:id/execute` | Запустить (SSE) |
| POST | `/api/pipelines/:id/resume` | Возобновить после HITL-паузы |
| POST | `/api/consultations/:id/respond` | Ответ оператора |
| GET | `/api/telemetry` | Логи телеметрии |

## Если что-то пошло не так

```bash
# Перезапустить PostgreSQL
sudo service postgresql start

# Сбросить и пересоздать БД
pnpm --filter @workspace/db run push --accept-data-loss

# Проверить типы
pnpm run typecheck

# Посмотреть логи API
pnpm --filter @workspace/api-server run dev
```
