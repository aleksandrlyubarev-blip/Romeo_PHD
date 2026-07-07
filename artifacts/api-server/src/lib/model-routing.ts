/**
 * Model routing for the multi-agent factory (Fable 5 setup).
 *
 * Три яруса агентов — маршрутизация по типу узла пайплайна:
 *
 * | Ярус       | Модель            | Роль                                     | Интеллект | Вкус | Стоимость ($/1M in/out) |
 * |------------|-------------------|------------------------------------------|-----------|------|--------------------------|
 * | architect  | claude-fable-5    | Проектирование, физика, ревью, спеки     | max       | max  | 10 / 50                  |
 * | manager    | claude-sonnet-5   | Оркестровка, валидация, синтез           | high      | high | 3 / 15                   |
 * | worker     | claude-haiku-4-5  | Грязная работа: логи, парсинг, извлечение | ok        | low  | 1 / 5                    |
 *
 * Плюс кросс-провайдерные роли (Этап 1 плана `docs/plan-gemini-perplexity-computer-use.md`;
 * сами маршруты на типы узлов подключаются на Этапах 2-3 — здесь пока только
 * провайдер-агностичная структура и заготовки под них):
 *
 * | Роль          | Модель                   | Провайдер  | Назначение                                             |
 * |---------------|--------------------------|------------|---------------------------------------------------------|
 * | crosscheck    | gemini-3-pro-preview     | google     | независимое второе мнение по физике/спекам, 1M контекст  |
 * | workerOverflow| gemini-2.5-flash         | google     | перелив worker-нагрузки при исчерпании лимитов Anthropic |
 * | researcher    | sonar-pro                | perplexity | узлы с веб-поиском и цитатами                            |
 * | deepResearcher| sonar-deep-research      | perplexity | дорогой глубокий ресёрч — точечно, аналог xhigh-effort   |
 *
 * Правило маршрутизации: интеллект важнее вкуса, вкус важнее стоимости.
 * При сомнении узел уходит на ярус выше (default = manager), никогда — ниже.
 *
 * Reasoning effort назначается по типу задачи, а не глобально:
 * выкрученный на максимум effort на рутинных узлах даёт переусложнённый
 * вывод и циклы саморефлексии, а платит за это каждый токен.
 */

export type AgentTier = "architect" | "manager" | "worker";

/** Провайдер, обслуживающий маршрут. Диспетчер — `getClientForProvider` в `llm-clients.ts`. */
export type Provider = "anthropic" | "google" | "perplexity";

// SDK 0.78 типизирует effort без "xhigh"; при апгрейде SDK можно добавить.
export type EffortLevel = "low" | "medium" | "high" | "max";

export interface ModelRoute {
  tier: AgentTier;
  provider: Provider;
  model: string;
  maxTokens: number;
  /** Anthropic-специфичные параметры запроса — используются только когда `provider === "anthropic"`. */
  anthropic?: {
    /**
     * `output_config.effort`. Не поддерживается на Haiku 4.5 — для worker
     * остаётся undefined и параметр не отправляется вовсе (иначе 400).
     */
    effort?: EffortLevel;
    /**
     * Адаптивное мышление. На Fable 5 thinking всегда включён и параметр
     * НЕ отправляется (явный disabled/enabled — это 400); на Sonnet 5
     * adaptive включается явно; на Haiku 4.5 недоступен.
     */
    sendAdaptiveThinking: boolean;
    /**
     * Fallback на Opus 4.8 при policy-отказе классификаторов Fable 5
     * (stop_reason: "refusal"): запрос повторяется на fallback-модели
     * клиентской стороной. Только для architect-яруса.
     */
    useRefusalFallback: boolean;
  };
  /** Заготовка под Gemini (Этап 2) — thinking-бюджет для thinking-моделей Gemini. */
  google?: { thinkingBudget?: number };
  /** Заготовка под Perplexity Sonar (Этап 3) — режим поиска. */
  perplexity?: { searchMode?: "web" | "academic" };
}

export const MODELS = {
  architect: { provider: "anthropic", model: "claude-fable-5" },
  architectFallback: { provider: "anthropic", model: "claude-opus-4-8" },
  manager: { provider: "anthropic", model: "claude-sonnet-5" },
  worker: { provider: "anthropic", model: "claude-haiku-4-5" },
  // Gemini/Perplexity ID меняются быстро — сверить актуальный ID перед включением.
  crosscheck: { provider: "google", model: "gemini-3-pro-preview" },
  workerOverflow: { provider: "google", model: "gemini-2.5-flash" },
  researcher: { provider: "perplexity", model: "sonar-pro" },
  deepResearcher: { provider: "perplexity", model: "sonar-deep-research" },
} as const satisfies Record<string, { provider: Provider; model: string }>;

/** Типы узлов, требующие максимального интеллекта и вкуса. */
const ARCHITECT_TYPE_PATTERNS = [
  /^physics_/, // доменный эксперт по диссертации — ошибка здесь дороже всего
  /design/,
  /architect/,
  /spec/,
  /review/,
  /theory/,
];

/** Типы узлов «грязной работы» — высокий объём, нулевые требования к вкусу. */
const WORKER_TYPE_PATTERNS = [
  /extract/,
  /parse/,
  /^log/,
  /logs?$/,
  /classif/,
  /screenshot/,
  /scrape/,
  /transcri/,
  /format/,
];

/**
 * Кросс-провайдерные роли (Этап 2/3 плана) — ортогональны трём Anthropic-ярусам,
 * поэтому проверяются ДО ярусной логики в `resolveRouteForNodeType`, а не как
 * очередной паттерн внутри ARCHITECT/WORKER списков.
 *
 * Порядок проверки важен: crosscheck → deep_research → research → ярусы.
 *
 * Ловушка с `research_report`: в пресете physics-engineer-rwdm
 * (`artifacts/romeo-phd/src/lib/buxter.ts`) узел с id "research_report" имеет
 * type "physics_report" (не "research_report") — он и так уходит на architect
 * через `/^physics_/` и в паттерн ниже не попадает. Но паттерн `RESEARCH_TYPE_PATTERN`
 * всё равно анкорим к началу строки с negative lookahead на "_report" (а не
 * голым `/research/`), чтобы будущий узел с type, буквально совпадающим с id
 * "research_report", не перехватился на manager+Perplexity вместо architect.
 */
const CROSSCHECK_TYPE_PATTERN = /^crosscheck_|second_opinion/;
const DEEP_RESEARCH_TYPE_PATTERN = /^deep_research_/;
const RESEARCH_TYPE_PATTERN = /^research_(?!report)|literature|websearch|arxiv/;

export function resolveTierForNodeType(nodeType: string): AgentTier {
  const t = nodeType.toLowerCase();
  if (ARCHITECT_TYPE_PATTERNS.some((re) => re.test(t))) return "architect";
  if (WORKER_TYPE_PATTERNS.some((re) => re.test(t))) return "worker";
  // При сомнении — на ярус выше, а не ниже: менеджер достаточно умён,
  // чтобы понять характер ошибки и решить, нужен ли перезапуск.
  return "manager";
}

/**
 * Кросс-провайдерные роли проверяются раньше ярусной логики: crosscheck и
 * research/deep_research — это отдельные узлы пайплайна, а не замена
 * architect/manager/worker (см. комментарий у паттернов выше про порядок
 * проверки и ловушку с `research_report`).
 */
export function resolveRouteForNodeType(nodeType: string): ModelRoute {
  const t = nodeType.toLowerCase();

  if (CROSSCHECK_TYPE_PATTERN.test(t)) {
    return {
      tier: "architect",
      provider: MODELS.crosscheck.provider,
      model: MODELS.crosscheck.model,
      maxTokens: 32000,
      google: {},
    };
  }

  if (DEEP_RESEARCH_TYPE_PATTERN.test(t)) {
    return {
      tier: "manager",
      provider: MODELS.deepResearcher.provider,
      model: MODELS.deepResearcher.model,
      maxTokens: 16000,
      perplexity: { searchMode: "web" },
    };
  }

  if (RESEARCH_TYPE_PATTERN.test(t)) {
    return {
      tier: "manager",
      provider: MODELS.researcher.provider,
      model: MODELS.researcher.model,
      maxTokens: 16000,
      perplexity: { searchMode: "web" },
    };
  }

  const tier = resolveTierForNodeType(nodeType);
  switch (tier) {
    case "architect":
      return {
        tier,
        provider: MODELS.architect.provider,
        model: MODELS.architect.model,
        maxTokens: 32000,
        anthropic: {
          effort: "high", // xhigh/max — только точечно; high — рабочий максимум по умолчанию
          sendAdaptiveThinking: false, // Fable 5: thinking всегда включён, параметр не передаём
          useRefusalFallback: true,
        },
      };
    case "manager":
      return {
        tier,
        provider: MODELS.manager.provider,
        model: MODELS.manager.model,
        maxTokens: 16000,
        anthropic: {
          effort: "medium", // ≈ Sonnet 4.6 на high, но дешевле — базовый уровень для рутины
          sendAdaptiveThinking: true,
          useRefusalFallback: false,
        },
      };
    case "worker":
      return {
        tier,
        provider: MODELS.worker.provider,
        model: MODELS.worker.model,
        maxTokens: 8192,
        anthropic: {
          effort: undefined, // Haiku 4.5 не принимает effort — не отправляем
          sendAdaptiveThinking: false,
          useRefusalFallback: false,
        },
      };
  }
}

/**
 * Жёсткие правила промптинга для worker-яруса (Шаг 4 настройки):
 * базовые модели не понимают вежливых и сложных просьб — только прямые
 * алгоритмические инструкции.
 */
export const WORKER_TIER_RULES = `## Правила worker-агента (обязательны)
1. Выполняй ТОЛЬКО поставленную задачу. Не трогай ничего за её пределами.
2. Не рассуждай о задаче в output — только результат.
3. Формат ответа — строго JSON из системного промпта. Никакого текста вокруг.`;

/**
 * Железное правило негативного ответа — для ВСЕХ ярусов.
 * Молчание или пустой output система трактует как невыполненную задачу
 * и уходит в цикл перезапусков, сжигающий бюджет API.
 */
export const MANDATORY_NEGATIVE_RESULT_RULE = `## Обязательный явный результат
Если по задаче нечего сообщить (ошибок нет, совпадений нет, данные отсутствуют) —
ты ОБЯЗАН вернуть явный негативный ответ в поле "output",
например: "Проверен компонент X — ошибок не найдено" или "Совпадений по запросу нет".
Пустой output, "N/A" или молчание ЗАПРЕЩЕНЫ: система сочтёт задачу невыполненной.`;
