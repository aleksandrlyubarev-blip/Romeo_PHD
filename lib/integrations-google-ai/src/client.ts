import { GoogleGenAI } from "@google/genai";
import pRetry, { AbortError } from "p-retry";

/**
 * В отличие от `lib/integrations-anthropic-ai/src/client.ts`, здесь клиент
 * НЕ создаётся на верхнем уровне модуля и не падает на импорте: этот пакет
 * подключается через `getClientForProvider("google")` в api-server, а тот
 * файл (`llm-clients.ts`) импортируется всегда, даже когда ни один маршрут
 * ещё не использует Google. Если бросить на импорте — сервер не соберётся
 * без ключа Gemini, даже когда провайдер не задействован ни одним узлом.
 * Поэтому `GoogleGenAI` создаётся лениво, при первом реальном вызове.
 */
let googleAI: GoogleGenAI | undefined;

export function getGoogleAI(): GoogleGenAI {
  if (!googleAI) {
    const apiKey = process.env.AI_INTEGRATIONS_GEMINI_API_KEY;
    if (!apiKey) {
      throw new Error(
        "AI_INTEGRATIONS_GEMINI_API_KEY must be set. Did you forget to provision the Google AI integration?",
      );
    }
    googleAI = new GoogleGenAI({ apiKey });
  }
  return googleAI;
}

function isRetryableGoogleError(error: unknown): boolean {
  const status = (error as { status?: number } | null)?.status;
  if (typeof status === "number") {
    return status === 429 || status === 503;
  }
  const message = error instanceof Error ? error.message : String(error);
  return message.includes("429") || message.includes("503") || /rate.?limit|quota|unavailable/i.test(message);
}

/**
 * SDK `@google/genai` не ретраит запросы сам (в отличие от Anthropic SDK,
 * см. `lib/integrations-anthropic-ai/src/client.ts`) — оборачиваем вызов
 * `models.generateContent` в `p-retry` с backoff на 429 (rate limit) и 503
 * (service unavailable). Прочие ошибки (400, safety-block и т.д.) ретраить
 * бессмысленно — они не исчезнут при повторе, поэтому пробрасываются сразу
 * через `AbortError`.
 */
export async function generateWithRetry(
  params: Parameters<GoogleGenAI["models"]["generateContent"]>[0],
): ReturnType<GoogleGenAI["models"]["generateContent"]> {
  return pRetry(
    async () => {
      try {
        return await getGoogleAI().models.generateContent(params);
      } catch (error) {
        if (isRetryableGoogleError(error)) {
          throw error;
        }
        throw new AbortError(error instanceof Error ? error : new Error(String(error)));
      }
    },
    { retries: 5, minTimeout: 2000, maxTimeout: 60000, factor: 2 },
  );
}
