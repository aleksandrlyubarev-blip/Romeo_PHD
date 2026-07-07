import { anthropic } from "@workspace/integrations-anthropic-ai";
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

    let message = await request(route.model);
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
 * Заглушка для провайдеров, интеграция которых ещё не подключена
 * (Google — Этап 2, Perplexity — Этап 3 плана `docs/plan-gemini-perplexity-computer-use.md`).
 * Бросает понятную ошибку вместо молчаливого падения на несуществующем клиенте.
 */
class NotImplementedClient implements LLMClient {
  constructor(private readonly providerName: string, private readonly stage: string) {}

  async complete(): Promise<LLMCompletion> {
    throw new Error(`провайдер ${this.providerName} будет подключён на ${this.stage}`);
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
      if (!googleClient) googleClient = new NotImplementedClient("google", "Этапе 2");
      return googleClient;
    case "perplexity":
      if (!perplexityClient) perplexityClient = new NotImplementedClient("perplexity", "Этапе 3");
      return perplexityClient;
  }
}
