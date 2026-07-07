# План доработок: Gemini Pro, Perplexity (Comet) и computer use

Продолжение аудита `docs/audit-2026-07-frontier-readiness.md`. Цель — фабрика
использует подписки на американские фронтир-модели трёх вендоров и получает
«руки» для работы с браузером/компьютером.

## Важное про подписки и ToS (читать до реализации)

- **Подписка ≠ API.** Консьюмерские подписки (Google AI Pro, Perplexity
  Pro/Max с браузером Comet) дают доступ к приложениям, а не к программному
  API. Автоматизировать консьюмерский UI headless-ботом ради обхода оплаты
  API — то же нарушение ToS, что и запрещённая в `CLAUDE.md` ротация ключей.
  В фабрику подключаем только официальные API:
  - **Gemini API** (ключ из Google AI Studio; есть бесплатный tier, платный
    billing по токенам);
  - **Perplexity Sonar API** (`api.perplexity.ai`, OpenAI-совместимый;
    подписка Pro включает ежемесячные API-кредиты).
- **Comet** — агентный браузер без публичного API. Его место — интерактивная
  работа человека (ручной ресёрч, разбор статей). Автономный веб-сёрфинг
  внутри фабрики делаем собственным computer-use контуром (Этап 4), а не
  автоматизацией Comet.
- Model ID на момент написания: `gemini-3-pro-preview` (флагман),
  `gemini-2.5-flash` (дешёвый ярус), `sonar-pro`, `sonar-reasoning-pro`,
  `sonar-deep-research`. Перед реализацией сверить с актуальными доками
  вендоров — ID меняются быстро.

## Целевая матрица моделей

| Роль | Модель | Провайдер | Когда используется |
|---|---|---|---|
| architect | `claude-fable-5` | anthropic | проектирование, физика RWDM, ревью (без изменений) |
| architect-fallback | `claude-opus-4-8` | anthropic | refusal-fallback (без изменений) |
| **architect-crosscheck** | `gemini-3-pro-preview` | google | независимое второе мнение по физике/спекам; 1M контекст для сверки больших документов |
| manager | `claude-sonnet-5` | anthropic | оркестровка, синтез (без изменений) |
| worker | `claude-haiku-4-5` | anthropic | логи, парсинг, классификация (без изменений) |
| **worker-alt** | `gemini-2.5-flash` | google | перелив worker-нагрузки при исчерпании лимитов Anthropic; мультимодальные скриншот-задачи |
| **researcher** | `sonar-pro` / `sonar-deep-research` | perplexity | узлы с веб-поиском и цитатами: литература по RWDM, свежие arXiv, сравнение с существующими бенчмарками |
| **browser-operator** | `claude-haiku-4-5` → скриншоты, `claude-sonnet-5` → действия | anthropic | computer-use контур (Этап 4) |

Правило маршрутизации не меняется: интеллект > вкус > стоимость, при сомнении
— ярус выше. Новые роли ортогональны ярусам: crosscheck и researcher — это
*дополнительные* узлы в пайплайне, а не замена architect.

## Этап 0 — пререквизиты (P0 из аудита, блокируют всё остальное)

1. HITL-фикс: апдейты по `consultation.nodeId`, использование `nodeId` из
   `ResumePipelineBody` (`routes/pipeline/index.ts:349-360, 208-270`).
2. Серверная валидация пустого/заглушечного `output` в
   `pipeline-executor.ts:160-179` — иначе новые провайдеры унаследуют дыру.
3. Удалить мёртвый дубль `lib/integrations/anthropic_ai_integrations/` и
   вычистить `build.ts` allowlist — чтобы новые интеграции не путались со
   скаффолд-мусором.

## Этап 1 — провайдер-абстракция

Точка привязки одна: `callModelWithRoute` (`pipeline-executor.ts:47-81`).

1. `model-routing.ts`:
   - `export type Provider = "anthropic" | "google" | "perplexity"`;
   - в `ModelRoute` добавить `provider: Provider`; Anthropic-специфику
     (`effort`, `sendAdaptiveThinking`, `useRefusalFallback`) переместить в
     `anthropicOptions?: {...}`, добавить `googleOptions?: { thinkingBudget?... }`,
     `perplexityOptions?: { searchMode?... }`;
   - `MODELS` → таблица `{ model, provider }` вместо плоских строк.
2. Новый `lib/llm-router` (или файл в api-server): интерфейс

   ```ts
   interface LLMClient {
     complete(route: ModelRoute, system: string, user: string):
       Promise<{ text: string | null; model: string; refused: boolean }>;
   }
   ```

   Реестр `Record<Provider, LLMClient>`; `callModelWithRoute` становится
   диспетчером: выбор клиента по `route.provider`, refusal-fallback остаётся
   провайдер-специфичной логикой anthropic-клиента.
3. Телеметрия: в `node_executed` добавить поле `provider` рядом с `model` —
   иначе метрика durationMs перестанет разделять вендоров.
4. `pnpm run typecheck` зелёный; поведение существующих Anthropic-маршрутов
   бит-в-бит прежнее (регрессионная проверка на одном пайплайне).

## Этап 2 — Gemini Pro (`lib/integrations-google-ai`)

1. Новый workspace-пакет по образцу `lib/integrations-anthropic-ai`:
   - SDK `@google/genai`; env `AI_INTEGRATIONS_GEMINI_API_KEY` (падение при
     отсутствии, как в `client.ts:3-13` у Anthropic);
   - ретраи: у SDK нет автоматических — обернуть в уже используемый
     `p-retry` с backoff на 429/503.
2. Реализация `LLMClient`: маппинг `system` → `systemInstruction`,
   `maxTokens` → `maxOutputTokens`; thinking-модели Gemini возвращают
   thought-блоки — фильтровать так же, как thinking-блоки Anthropic
   (`pipeline-executor.ts:78-80`); safety-block трактовать как `refused`.
3. Маршрутизация:
   - новый паттерн узлов `/^crosscheck_|second_opinion/` → route
     `{ provider: "google", model: "gemini-3-pro-preview" }`;
   - опциональный env-флаг `WORKER_OVERFLOW_PROVIDER=google`: при
     исчерпании ретраев на 429 worker-узел повторяется на
     `gemini-2.5-flash` (легальная разгрузка лимитов вместо ротации ключей).
4. Критерий приёмки: пайплайн с узлом `crosscheck_physics` получает ответ от
   Gemini, `node_executed` содержит `provider: "google"`, durationMs пишется.

## Этап 3 — Perplexity Sonar (`lib/integrations-perplexity-ai`)

1. Пакет по тому же шаблону; API OpenAI-совместимый — достаточно `fetch` или
   `openai`-SDK с `baseURL: "https://api.perplexity.ai"`; env
   `AI_INTEGRATIONS_PERPLEXITY_API_KEY`.
2. Особенность ответа: `citations`/`search_results` — сохранять их в payload
   телеметрии и прокидывать в `output` узла (формат: текст + нумерованный
   список источников). Правило обязательного негативного ответа действует:
   «по запросу X релевантных публикаций не найдено» — валидный результат.
3. Маршрутизация: паттерны `/research|literature|websearch|arxiv/` → route
   `{ provider: "perplexity", model: "sonar-pro" }`; для узлов
   `deep_research_*` — `sonar-deep-research` (дороже, дольше — только
   точечно, аналог правила про xhigh-effort).
4. Место Comet: зафиксировать в доке фабрики, что Comet — инструмент
   оператора-человека (ручная проверка источников из citations, разбор
   пейволл-статей по подписке). Результаты человек вносит через существующий
   HITL-механизм consultations — новая инфраструктура не нужна.
5. Критерий приёмки: узел `research_rwdm_literature` возвращает ответ с ≥1
   цитатой на реальный источник; ссылки кликабельны из UI.

## Этап 4 — Computer use (браузер как инструмент фабрики)

Сейчас executor умеет только LLM-вызовы; «скриншоты» в роли Haiku — заглушка.

1. Новый тип исполнения узла `tool_browser_*` в `pipeline-executor.ts`:
   вместо `callModelWithRoute` — цикл Anthropic computer-use
   (`computer_20250124` tool + Playwright с headless Chromium), где модель
   (Sonnet 5) получает скриншоты и отдаёт действия.
2. Песочница (обязательно, до первого запуска):
   - allowlist доменов (env `BROWSER_ALLOWED_HOSTS`), по умолчанию только
     staging-URL фабрики и `arxiv.org`;
   - только чтение/навигация автономно; любое действие с побочным эффектом
     (submit-формы, покупки, логины) → консультация HITL (починенная в
     Этапе 0);
   - лимит шагов на узел (например, 30 скриншот-циклов) — защита от циклов,
     сжигающих бюджет.
3. Первые применения:
   - визуальная проверка UI `/telemetry` и `/consultations` на staging
     (скриншот → Haiku-классификация «рендерится/сломано»);
   - выкачивание PDF с arXiv по ссылкам из citations Sonar-узла для
     последующего разбора Gemini (1M контекст).
4. Критерий приёмки: пайплайн «открой staging, сними скриншот /consultations,
   классифицируй состояние» проходит без участия человека; попытка выйти на
   домен вне allowlist блокируется и логируется.

## Этап 5 — применение к RWDM-бенчмарку

Собирается из этапов 1-4 плюс tool-узел исполнения кода (P0.3 аудита):

1. Тип узла `tool_python_*`: запуск скрипта из `research/quantum-benchmark/`
   в песочнице, чтение `results/summary.json`, передача чисел следующему узлу.
2. Обновлённый пресет `physics-engineer-rwdm` (`buxter.ts:385-427`):

   ```
   problem_intake (manager)
   → theory_audit (architect: Fable 5)
   → crosscheck_theory (google: Gemini 3 Pro — независимый вывод формул)
   → research_rwdm_literature (perplexity: sonar-deep-research)
   → model_design (architect)
   → tool_python_run_qbench (исполнение прототипа, реальные числа)
   → validation_gate (manager: сверка чисел с гейтами §5 дизайн-дока;
       расхождение Fable/Gemini по формулам → консультация HITL)
   → research_report (architect)
   ```

3. Смысл кросс-провайдерности именно здесь: независимый вывод физических
   формул двумя моделями разных вендоров — самый дешёвый детектор
   галлюцинаций в предметной области, где ошибка дороже всего. Совпали —
   уверенность; разошлись — человек решает.

## Экономика (актуально при 14% лимита Fable)

- Fable 5 остаётся только на architect-узлах; кросс-чеки — Gemini,
  литература — Sonar, переполнение worker — Flash. Ни один из этих вызовов
  больше не тратит лимит Anthropic.
- Prompt caching (`cache_control` на system-блоке в anthropic-клиенте) и
  Batches API для оффлайн worker-партий — из P1 аудита, делаются попутно с
  Этапом 1, пока трогаем `callModelWithRoute`.

## Порядок работ

| # | Этап | Зависимости | Оценка объёма |
|---|---|---|---|
| 1 | Этап 0 (P0 аудита) | — | 3 точечных фикса + удаление мусора |
| 2 | Этап 1 абстракция | Этап 0 | 1 новый модуль, рефакторинг 2 файлов |
| 3 | Этап 2 Gemini | Этап 1 | 1 workspace-пакет + маршруты |
| 4 | Этап 3 Perplexity | Этап 1 | 1 workspace-пакет + маршруты |
| 5 | Этап 4 computer use | Этап 0 (HITL) | новый контур исполнения, самый объёмный |
| 6 | Этап 5 RWDM-пайплайн | Этапы 2-4 + tool_python | пресет + гейты §5 |

Этапы 2 и 3 независимы и делаются параллельно. Каждый этап — отдельный PR в
`main` (staging), с зелёным `pnpm run typecheck` и регрессионным прогоном
одного Anthropic-пайплайна как критерием мержа.
