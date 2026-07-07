import Anthropic from "@anthropic-ai/sdk";

if (!process.env.AI_INTEGRATIONS_ANTHROPIC_BASE_URL) {
  throw new Error(
    "AI_INTEGRATIONS_ANTHROPIC_BASE_URL must be set. Did you forget to provision the Anthropic AI integration?",
  );
}

if (!process.env.AI_INTEGRATIONS_ANTHROPIC_API_KEY) {
  throw new Error(
    "AI_INTEGRATIONS_ANTHROPIC_API_KEY must be set. Did you forget to provision the Anthropic AI integration?",
  );
}

export const anthropic = new Anthropic({
  apiKey: process.env.AI_INTEGRATIONS_ANTHROPIC_API_KEY,
  baseURL: process.env.AI_INTEGRATIONS_ANTHROPIC_BASE_URL,
  // Балансировка нагрузки честным способом: SDK сам повторяет 429/529/5xx
  // с экспоненциальным backoff и уважает заголовок retry-after.
  // Подмена API-ключей «на лету» для обхода лимитов нарушает ToS Anthropic —
  // при упоре в лимиты правильные рычаги: retry+backoff (здесь), очередь задач,
  // Batches API (−50% стоимости) и запрос повышения тира.
  maxRetries: 5,
  // Architect-узлы на Fable 5 при high effort могут работать минутами.
  timeout: 15 * 60 * 1000,
});
