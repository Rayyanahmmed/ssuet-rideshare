/**
 * Pure URL helpers — deliberately free of Expo imports so they can be unit-tested with
 * plain node (`npx tsc src/lib/apiUrl.ts --outDir /tmp/x --module commonjs`), and reused by
 * both the config layer and the testing-only server switcher.
 */

export const API_SUFFIX = '/api/v1';
export const API_PORT = 8000;

/** `http://host:8000/api/v1/` → `http://host:8000/api/v1` (axios would otherwise build `//auth`). */
export function stripTrailingSlashes(url: string): string {
  return url.replace(/\/+$/, '');
}

/** Accepts `192.168.100.32:8000`, `192.168.100.32:8000/api/v1` or a full URL. */
export function normalizeBaseUrl(raw: string): string {
  let url = raw.trim();
  if (!url) return '';
  if (!/^https?:\/\//i.test(url)) url = `http://${url}`;
  url = stripTrailingSlashes(url);
  if (!/\/api\/v\d+$/i.test(url)) url = `${url}${API_SUFFIX}`;
  return url;
}

/** True for addresses that only resolve on the machine itself, never on a phone. */
export function isLoopback(url: string): boolean {
  return /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(:\d+)?/i.test(url);
}

/**
 * The Expo dev server reports the host the bundle was served from
 * (`hostUri` = `192.168.100.32:8081`) — that is the same laptop that runs the API.
 */
export function hostFromUri(hostUri?: string | null): string | null {
  if (!hostUri) return null;
  const withoutScheme = hostUri.trim().replace(/^https?:\/\//i, '');
  const host = withoutScheme.split('/')[0]?.split(':')[0] ?? '';
  if (!host || host === 'localhost' || host === '127.0.0.1') return null;
  return host;
}

/**
 * Resolution order: the URL baked at build time → the host this bundle came from →
 * localhost (web / emulator only).
 */
export function resolveApiBaseUrl(options: {
  buildUrl?: string;
  hostUri?: string | null;
  port?: number;
} = {}): string {
  const { buildUrl, hostUri, port = API_PORT } = options;
  const fromBuild = buildUrl?.trim();
  if (fromBuild) return stripTrailingSlashes(fromBuild);
  const host = hostFromUri(hostUri);
  if (host) return `http://${host}:${port}${API_SUFFIX}`;
  return `http://localhost:${port}${API_SUFFIX}`;
}
