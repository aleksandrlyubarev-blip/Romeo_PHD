import Anthropic from "@anthropic-ai/sdk";
import { requireApiKeyMode } from "./auth-mode";

// Phase 0 of the SDK-credit migration: this client still hard-requires the
// API key path. The `requireApiKeyMode` guard fails loudly if someone flips
// ANTHROPIC_AUTH_MODE=sdk before Phase 1.3 has rewired the client to use
// `claude login` cached credentials.
requireApiKeyMode("integrations-anthropic-ai/client");

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
});
