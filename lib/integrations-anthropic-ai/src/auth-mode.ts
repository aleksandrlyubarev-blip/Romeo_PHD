/**
 * Anthropic provider auth-mode toggle.
 *
 * Selects how Anthropic calls authenticate without forcing every call site to
 * branch on env vars. Other providers are unaffected.
 *
 * Modes (env var ANTHROPIC_AUTH_MODE):
 *   - "api_key" (default): standard AI_INTEGRATIONS_ANTHROPIC_API_KEY path.
 *   - "sdk":               plan auth via `claude login` cached credentials.
 *                          Hot-path wiring lands in Phase 1.3 of the
 *                          SDK-credit migration. Until then this throws on
 *                          `requireApiKeyMode()` so the toggle cannot silently
 *                          fall through.
 */

export type AuthMode = "api_key" | "sdk";

const VALID_MODES: readonly AuthMode[] = ["api_key", "sdk"];
const DEFAULT_MODE: AuthMode = "api_key";

export function getAuthMode(): AuthMode {
  const raw = (process.env.ANTHROPIC_AUTH_MODE ?? DEFAULT_MODE).trim().toLowerCase();
  if ((VALID_MODES as readonly string[]).includes(raw)) {
    return raw as AuthMode;
  }
  console.warn(
    `[anthropic-auth] Unknown ANTHROPIC_AUTH_MODE=${JSON.stringify(raw)}, falling back to ${JSON.stringify(DEFAULT_MODE)}`,
  );
  return DEFAULT_MODE;
}

export function isSdkMode(): boolean {
  return getAuthMode() === "sdk";
}

/**
 * Hot-path guard for code paths that still assume AI_INTEGRATIONS_ANTHROPIC_API_KEY.
 * Throws when the operator has flipped to sdk mode before Phase 1.3 wiring
 * is in place.
 */
export function requireApiKeyMode(component: string): void {
  if (isSdkMode()) {
    throw new Error(
      `${component}: ANTHROPIC_AUTH_MODE=sdk requested, but plan-auth wiring ` +
        "is not yet implemented (Phase 1.3 of the SDK-credit migration). " +
        "Unset ANTHROPIC_AUTH_MODE or set it to 'api_key' to use the current path.",
    );
  }
}
