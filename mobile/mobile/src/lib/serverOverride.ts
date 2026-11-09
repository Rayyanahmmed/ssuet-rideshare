import * as SecureStore from 'expo-secure-store';
import { api } from '@/api/client';
import { env, getApiBaseUrl, setApiBaseUrlRuntime } from '@/lib/config';
import { normalizeBaseUrl } from '@/lib/apiUrl';

/**
 * Runtime override of the API base URL (testing builds only).
 *
 * A release APK bakes `EXPO_PUBLIC_API_URL` at build time, which makes every demo depend on
 * a new 10-minute cloud build — painful when the server is a laptop on a changing Wi-Fi IP.
 * This module stores one string in the keystore and re-points the HTTP client (the chat
 * WebSocket derives its URL from `api.defaults.baseURL`, so it follows automatically).
 *
 * The build-time value stays the fallback: clearing the override restores it.
 */
const KEY = 'ssuet.api_base_url';

type ApiBaseUrlListener = (url: string) => void;

/**
 * Screens cache server data (react-query). After a switch, everything cached belongs to the
 * previous server, so subscribers are told to drop it. Kept as a listener set instead of a
 * direct import to avoid a config → react-query → api cycle.
 */
const listeners = new Set<ApiBaseUrlListener>();

export function onApiBaseUrlChange(listener: ApiBaseUrlListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Points the HTTP client at `rawUrl`; returns the normalised URL actually applied. */
export function applyApiBaseUrl(rawUrl: string): string {
  const url = normalizeBaseUrl(rawUrl) || env.apiUrl;
  if (url === getApiBaseUrl()) return url; // nothing changes — don't clear anyone's cache

  api.defaults.baseURL = url;
  setApiBaseUrlRuntime(url);

  for (const listener of listeners) {
    try {
      listener(url);
    } catch {
      // a misbehaving subscriber must never break the switch itself
    }
  }
  return url;
}

/** Called once at start-up, before the session is verified against the API. */
export async function loadApiBaseUrlOverride(): Promise<string | null> {
  try {
    const saved = await SecureStore.getItemAsync(KEY);
    if (!saved) return null;
    const url = normalizeBaseUrl(saved); // older builds may have stored a trailing slash
    if (!url) return null;
    return applyApiBaseUrl(url);
  } catch {
    // keystore unavailable — keep the build-time URL
    return null;
  }
}

export async function saveApiBaseUrlOverride(raw: string): Promise<string> {
  // Apply first: the switch has to work for this session even if the keystore refuses to persist.
  const url = applyApiBaseUrl(raw);
  try {
    await SecureStore.setItemAsync(KEY, url);
  } catch {
    // persistence failed — the URL still applies until the app is restarted
  }
  return url;
}

export async function clearApiBaseUrlOverride(): Promise<string> {
  const url = applyApiBaseUrl(env.apiUrl);
  try {
    await SecureStore.deleteItemAsync(KEY);
  } catch {
    // removal failed — the next launch re-applies it, which the member can undo again
  }
  return url;
}

/** One-off reachability probe used by the settings panel (`GET {api}/health`). */
export async function probeServer(rawUrl: string): Promise<string> {
  const url = normalizeBaseUrl(rawUrl);
  if (!url) return 'no URL given';

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6000);
  try {
    const response = await fetch(`${url}/health`, {
      signal: controller.signal,
      headers: { Accept: 'application/json', 'ngrok-skip-browser-warning': '1' },
    });
    return response.ok ? 'reachable' : `HTTP ${response.status}`;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') return 'timed out after 6s';
    return error instanceof Error ? error.message : 'unreachable';
  } finally {
    clearTimeout(timer);
  }
}

export { getApiBaseUrl, normalizeBaseUrl };
