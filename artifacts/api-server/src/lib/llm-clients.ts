import { anthropic } from "@workspace/integrations-anthropic-ai";
import { isRateLimitError } from "@workspace/integrations-anthropic-ai/batch";
import { generateWithRetry as generateGoogleWithRetry } from "@workspace/integrations-google-ai";
import { generateWithRetry as generatePerplexityWithRetry } from "@workspace/integrations-perplexity-ai";
import { MODELS, type ModelRoute, type Provider } from "./model-routing";

/** Единый результат вызова любого провайдера — независимо от формата ответа. */
export interface LLMCompletion {
  text: string | null;
  model: string;
  refused: boolean;
}

/** Провайдер-агностичный интерфейс. Один узел пайплайна — один вызов `complete`. */
export interface LLMClient {
  complete(route: ModelRoute, systemPrompt: string, userMessage: string): Promise<LLMCompletion>;
}

/**
 * Anthropic-клиент. Для architect-яруса (Fable 5) при policy-отказе
 * классификаторов (stop_reason: "refusal") запрос повторяется на Opus 4.8 —
 * иначе ложное срабатывание на безобидной смежной теме валит весь пайплайн.
 */
class AnthropicClient implements LLMClient {
  async complete(route: ModelRoute, systemPrompt: string, userMessage: string): Promise<LLMCompletion> {
    const opts = route.anthropic;

    const request = (model: string) =>
      anthropic.messages.create({
        model,
        max_tokens: route.maxTokens,
        // System-промпт узла одинаков между вызовами пайплайна (меняется только
        // userMessage) — передаём его блоком с cache_control, чтобы Anthropic
        // кэшировал префикс и не тарифицировал его повторно на каждом узле.
        system: [{ type: "text", text: systemPrompt, cache_control: { type: "ephemeral" } }],
        messages: [{ role: "user", content: userMessage }],
        // Fable 5: thinking всегда включён, параметр не передаётся вовсе.
        // Haiku 4.5: adaptive thinking недоступен.
        ...(opts?.sendAdaptiveThinking ? { thinking: { type: "adaptive" as const } } : {}),
        // Haiku 4.5 не принимает effort — отправляем только там, где поддержано.
        ...(opts?.effort ? { output_config: { effort: opts.effort } } : {}),
      });

    let message: Awaited<ReturnType<typeof request>>;
    try {
      message = await request(route.model);
    } catch (error) {
      // Worker-переполнение (env WORKER_OVERFLOW_PROVIDER=google): если на
      // worker-маршруте (Haiku 4.5) исчерпаны ретраи SDK (maxRetries: 5, см.
      // integrations-anthropic-ai/src/client.ts) и тир Anthropic упёрся в
      // rate-limit, легально разгружаем запрос на Gemini Flash вместо
      // накопления очереди/повторной подмены ключей (запрещено CLAUDE.md).
      // Один узкий чек, один повтор — не усложняем.
      if (
        route.tier === "worker" &&
        process.env.WORKER_OVERFLOW_PROVIDER === "google" &&
        isRateLimitError(error)
      ) {
        const overflowRoute: ModelRoute = {
          ...route,
          provider: MODELS.workerOverflow.provider,
          model: MODELS.workerOverflow.model,
        };
        return getClientForProvider("google").complete(overflowRoute, systemPrompt, userMessage);
      }
      throw error;
    }

    let servedBy = route.model;

    if (message.stop_reason === "refusal" && opts?.useRefusalFallback) {
      message = await request(MODELS.architectFallback.model);
      servedBy = MODELS.architectFallback.model;
    }

    if (message.stop_reason === "refusal") {
      return { text: null, model: servedBy, refused: true };
    }

    // При включённом thinking первый блок может быть thinking-блоком —
    // ищем текстовый блок, а не берём content[0].
    const textBlock = message.content.find((b) => b.type === "text");
    return {
      text: textBlock?.type === "text" ? textBlock.text : null,
      model: servedBy,
      refused: false,
    };
  }
}

/**
 * Google Gemini-клиент (Этап 2 плана `docs/plan-gemini-perplexity-computer-use.md`).
 * Обслуживает две роли: architect-crosscheck (независимое второе мнение,
 * gemini-3-pro-preview) и worker-overflow (перелив worker-нагрузки при
 * исчерпании лимитов Anthropic, gemini-2.5-flash) — маршрут решает какая
 * модель и параметры используются, клиент от роли не зависит.
 */
class GoogleClient implements LLMClient {
  async complete(route: ModelRoute, systemPrompt: string, userMessage: string): Promise<LLMCompletion> {
    const response = await generateGoogleWithRetry({
      model: route.model,
      contents: userMessage,
      config: {
        systemInstruction: systemPrompt,
        maxOutputTokens: route.maxTokens,
        ...(route.google?.thinkingBudget
          ? { thinkingConfig: { thinkingBudget: route.google.thinkingBudget } }
          : {}),
      },
    });

    const candidate = response.candidates?.[0];

    // Safety-block — единообразно с refusal Anthropic: text: null, refused: true.
    // FinishReason — строковый enum SDK ("SAFETY" и т.д.); сравниваем строкой,
    // чтобы не тянуть @google/genai в api-server напрямую (типы и так
    // проверяются через ModelRoute/generateWithRetry из integrations-google-ai).
    const safetyBlocked =
      candidate?.finishReason === "SAFETY" || Boolean(response.promptFeedback?.blockReason);
    if (safetyBlocked) {
      return { text: null, model: route.model, refused: true };
    }

    // `response.text` — SDK-геттер, склеивающий текстовые part'ы первого
    // кандидата мимо thought-блоков. Если по какой-то причине геттер не дал
    // текста (например, ответ состоит только из non-text part'ов), собираем
    // текст вручную тем же правилом (исключая part.thought).
    let text = response.text ?? null;
    if (!text) {
      const parts = candidate?.content?.parts?.filter((part) => !part.thought && part.text) ?? [];
      text = parts.length > 0 ? parts.map((part) => part.text).join("") : null;
    }

    return { text: text ?? null, model: route.model, refused: false };
  }
}

/**
 * Perplexity Sonar-клиент (Этап 3 плана). Цитаты дописываются в конец text
 * блоком "Источники:", чтобы доехать до output узла без изменения интерфейса
 * LLMCompletion — у Sonar нет отдельного message-блока для ссылок, только
 * плоский текст ответа.
 */
class PerplexityClient implements LLMClient {
  async complete(route: ModelRoute, systemPrompt: string, userMessage: string): Promise<LLMCompletion> {
    const result = await generatePerplexityWithRetry({
      model: route.model,
      max_tokens: route.maxTokens,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userMessage },
      ],
      ...(route.perplexity?.searchMode === "academic" ? { search_mode: "academic" as const } : {}),
    });

    if (result.text === null) {
      return { text: null, model: route.model, refused: true };
    }

    // Пустой список цитат — не ошибка (MANDATORY_NEGATIVE_RESULT_RULE
    // допускает валидный негативный ответ "релевантных публикаций не найдено").
    const text =
      result.citations.length > 0
        ? `${result.text}\n\nИсточники:\n${result.citations.map((url, i) => `[${i + 1}] ${url}`).join("\n")}`
        : result.text;

    return { text, model: route.model, refused: false };
  }
}

// Ленивая инициализация: клиенты создаются по первому обращению, а не на
// импорте модуля. Иначе отсутствие env-ключей ещё не подключённых провайдеров
// (Google/Perplexity) уронит сервер сразу при старте, даже если ни один
// маршрут ими пока не пользуется.
let anthropicClient: LLMClient | undefined;
let googleClient: LLMClient | undefined;
let perplexityClient: LLMClient | undefined;

export function getClientForProvider(provider: Provider): LLMClient {
  switch (provider) {
    case "anthropic":
      if (!anthropicClient) anthropicClient = new AnthropicClient();
      return anthropicClient;
    case "google":
      if (!googleClient) googleClient = new GoogleClient();
      return googleClient;
    case "perplexity":
      if (!perplexityClient) perplexityClient = new PerplexityClient();
      return perplexityClient;
  }
}
