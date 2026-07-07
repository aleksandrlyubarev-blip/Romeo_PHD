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
 * Правило маршрутизации: интеллект важнее вкуса, вкус важнее стоимости.
 * При сомнении узел уходит на ярус выше (default = manager), никогда — ниже.
 *
 * Reasoning effort назначается по типу задачи, а не глобально:
 * выкрученный на максимум effort на рутинных узлах даёт переусложнённый
 * вывод и циклы саморефлексии, а платит за это каждый токен.
 */

export type AgentTier = "architect" | "manager" | "worker";

// SDK 0.78 типизирует effort без "xhigh"; при апгрейде SDK можно добавить.
export type EffortLevel = "low" | "medium" | "high" | "max";

export interface ModelRoute {
  tier: AgentTier;
  model: string;
  maxTokens: number;
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
}

export const MODELS = {
  architect: "claude-fable-5",
  architectFallback: "claude-opus-4-8",
  manager: "claude-sonnet-5",
  worker: "claude-haiku-4-5",
} as const;

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

export function resolveTierForNodeType(nodeType: string): AgentTier {
  const t = nodeType.toLowerCase();
  if (ARCHITECT_TYPE_PATTERNS.some((re) => re.test(t))) return "architect";
  if (WORKER_TYPE_PATTERNS.some((re) => re.test(t))) return "worker";
  // При сомнении — на ярус выше, а не ниже: менеджер достаточно умён,
  // чтобы понять характер ошибки и решить, нужен ли перезапуск.
  return "manager";
}

export function resolveRouteForNodeType(nodeType: string): ModelRoute {
  const tier = resolveTierForNodeType(nodeType);
  switch (tier) {
    case "architect":
      return {
        tier,
        model: MODELS.architect,
        maxTokens: 32000,
        effort: "high", // xhigh/max — только точечно; high — рабочий максимум по умолчанию
        sendAdaptiveThinking: false, // Fable 5: thinking всегда включён, параметр не передаём
        useRefusalFallback: true,
      };
    case "manager":
      return {
        tier,
        model: MODELS.manager,
        maxTokens: 16000,
        effort: "medium", // ≈ Sonnet 4.6 на high, но дешевле — базовый уровень для рутины
        sendAdaptiveThinking: true,
        useRefusalFallback: false,
      };
    case "worker":
      return {
        tier,
        model: MODELS.worker,
        maxTokens: 8192,
        effort: undefined, // Haiku 4.5 не принимает effort — не отправляем
        sendAdaptiveThinking: false,
        useRefusalFallback: false,
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
