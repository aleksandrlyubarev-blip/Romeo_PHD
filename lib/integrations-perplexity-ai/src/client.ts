import pRetry, { AbortError } from "p-retry";

/**
 * Perplexity Sonar API — OpenAI-совместимый эндпоинт, официального SDK нет
 * (см. план `docs/plan-gemini-perplexity-computer-use.md`, Этап 3). Голый
 * `fetch` вместо самодельной обёртки поверх чужого протокола — здесь нечего
 * оборачивать, кроме самого HTTP-вызова.
 */
const PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions";

export interface PerplexityMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface PerplexityRequest {
  model: string;
  messages: PerplexityMessage[];
  max_tokens?: number;
  /** `academic` — поиск по академическим источникам вместо общего веба. */
  search_mode?: "web" | "academic";
}

export interface PerplexityResult {
  text: string | null;
  citations: string[];
}

/**
 * `sonar-deep-research` может отвечать по несколько минут (модель сама гоняет
 * цепочку веб-поисков перед ответом) — таймаут держим на 300с; остальные
 * модели (`sonar-pro` и т.д.) укладываются в обычные 120с.
 */
export function timeoutForModel(model: string): number {
  return model.includes("deep-research") ? 300_000 : 120_000;
}

function getApiKey(): string {
  const apiKey = process.env.AI_INTEGRATIONS_PERPLEXITY_API_KEY;
  if (!apiKey) {
    throw new Error(
      "AI_INTEGRATIONS_PERPLEXITY_API_KEY must be set. Did you forget to provision the Perplexity AI integration?",
    );
  }
  return apiKey;
}

function isRetryableStatus(status: number): boolean {
  return status === 429 || status >= 500;
}

/**
 * Тело ответа Perplexity — только используемые нами поля. `citations` —
 * плоский список URL; `search_results` — более подробная структура (может
 * присутствовать вместо/вместе с `citations` в зависимости от версии API) —
 * возвращаем оба, если найдены, дедуплицируя URL.
 */
interface PerplexityResponseBody {
  choices?: Array<{ message?: { content?: string | null } }>;
  citations?: string[];
  search_results?: Array<{ url?: string }>;
}

/**
 * Ключ читается лениво при первом вызове (не на импорте модуля) — по тем же
 * причинам, что и в `lib/integrations-google-ai/src/client.ts`: этот пакет
 * подключается через `getClientForProvider("perplexity")`, а `llm-clients.ts`
 * импортируется всегда, даже если ни один маршрут ещё не использует Perplexity.
 *
 * Ретраи — `p-retry` на 429/5xx (SDK нет, ретраить не на чем, кроме fetch).
 */
export async function generateWithRetry(request: PerplexityRequest): Promise<PerplexityResult> {
  const apiKey = getApiKey();
  const timeoutMs = timeoutForModel(request.model);

  const body = await pRetry(
    async () => {
      const response = await fetch(PERPLEXITY_API_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
        signal: AbortSignal.timeout(timeoutMs),
      });

      if (!response.ok) {
        const message = `Perplexity API вернул ${response.status}: ${await response.text().catch(() => "")}`;
        if (isRetryableStatus(response.status)) {
          throw new Error(message);
        }
        throw new AbortError(message);
      }

      return (await response.json()) as PerplexityResponseBody;
    },
    { retries: 5, minTimeout: 2000, maxTimeout: 60000, factor: 2 },
  );

  const text = body.choices?.[0]?.message?.content ?? null;
  const citations = new Set<string>();
  for (const url of body.citations ?? []) citations.add(url);
  for (const result of body.search_results ?? []) {
    if (result.url) citations.add(result.url);
  }

  return { text, citations: [...citations] };
}
