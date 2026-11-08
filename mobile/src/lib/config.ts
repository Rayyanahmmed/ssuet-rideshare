import Constants from 'expo-constants';
import { isLoopback, resolveApiBaseUrl, stripTrailingSlashes } from '@/lib/apiUrl';

/**
 * Typed access to `extra` from app.config.ts (fail-soft in release builds, §20, §13).
 */
type Extra = {
  apiUrl?: string;
  allowServerOverride?: boolean;
};

const extra = (Constants.expoConfig?.extra ?? {}) as Extra;

/**
 * `expo start` reports the machine serving the bundle (`192.168.100.32:8081`), which is the
 * same laptop that runs the API — so a dev build follows the PC's IP automatically instead
 * of falling back to an address no phone can reach.
 */
const hostUri = Constants.expoConfig?.hostUri ?? null;

const buildApiUrl = extra.apiUrl?.trim() || undefined;
const resolvedApiUrl = stripTrailingSlashes(resolveApiBaseUrl({ buildUrl: buildApiUrl, hostUri }));

export const env = {
  /** Build-time default, already normalised: build URL → dev-server host → localhost. */
  apiUrl: resolvedApiUrl,
  /** True when the resolved default only works on the machine itself. */
  apiUrlIsLoopback: isLoopback(resolvedApiUrl),
  /**
   * Testing builds only (`EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE=1`): the sign-in and sign-up
   * screens expose a field that changes the API base URL at runtime, so a QA build can be
   * pointed at a laptop on the LAN — or at a new server — without rebuilding the APK.
   */
  allowServerOverride: Boolean(extra.allowServerOverride),
  isDev: __DEV__,
} as const;

/**
 * The URL actually in use. Starts as the build-time value and may be replaced at runtime
 * by the stored override (`src/lib/serverOverride.ts`). Everything that needs the host —
 * the axios instance, the chat WebSocket — reads this, never `env.apiUrl` directly.
 */
let currentApiUrl: string = env.apiUrl;

export function getApiBaseUrl(): string {
  return currentApiUrl;
}

export function setApiBaseUrlRuntime(url: string): void {
  currentApiUrl = stripTrailingSlashes(url);
}

if (__DEV__ && env.apiUrlIsLoopback) {
  console.warn(
    `[config] API base URL is ${env.apiUrl} — reachable only from this machine. ` +
      'On a physical phone, start the API with --host 0.0.0.0 and set the LAN IP ' +
      '(mobile/.env or the "Server (testing build)" panel).',
  );
}
