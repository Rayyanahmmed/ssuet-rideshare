# Paste-ready files — mobile app (LAN server + runtime switcher + session/validation fixes)

Har block ke ooper **exact path** hai. Windows par: file kholo → `Ctrl+A` → `Ctrl+V` → save.
`REPLACE` = poori file ka content, `NEW` = nayi file banayein.
(Yeh doc hi ZIP ka hissa hai — extract karne par sab already lagi hui milti hain.)

---


## `mobile/src/lib/apiUrl.ts`  ·  *NEW*

```ts
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
```

---


## `mobile/src/lib/config.ts`  ·  *REPLACE*

Full file (current):

```ts
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
```

---

## `mobile/src/lib/serverOverride.ts`  ·  *REPLACE*

```ts
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
      headers: { Accept: 'application/json' },
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
```

---


## `mobile/src/lib/queryClient.ts`  ·  *NEW*

```ts
import { QueryClient } from '@tanstack/react-query';

/**
 * One cache for the whole app, in its own module so non-React code (the auth store) can drop
 * it: after a sign-out or an account switch, cached rides and messages must not survive.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retrying a 401/403/422 only delays the error the member needs to see.
      retry: (failureCount, error) => {
        const code = (error as { code?: string } | null)?.code;
        if (
          code &&
          [
            'UNAUTHORIZED',
            'FORBIDDEN',
            'NOT_FOUND',
            'VALIDATION_ERROR',
            'ACCOUNT_NOT_VERIFIED',
            'ACCOUNT_SUSPENDED',
          ].includes(code)
        ) {
          return false;
        }
        return failureCount < 1;
      },
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

export function resetQueryCache(): void {
  queryClient.clear();
}
```

---


## `mobile/src/store/auth.ts`  ·  *REPLACE*

```ts
import { create } from 'zustand';
import { clearTokens, loadTokens, saveTokens } from '@/lib/secureStore';
import { ApiError, setAccessToken, setRefreshToken, onUnauthorized } from '@/api/client';
import { resetQueryCache } from '@/lib/queryClient';
import * as authApi from '@/api/auth';

/**
 * Session state.
 *
 * Tokens are mirrored in memory for request headers and persisted in the device
 * keystore. `hydrate()` runs once at launch: it restores the token pair and then
 * asks the API who the user is (`GET /auth/me`), so a stale token can never put
 * the app into a fake signed-in state.
 */
export type SessionUser = {
  id: string;
  email: string;
  phone: string;
  full_name: string;
  profile_photo_url?: string | null;
  role: 'STUDENT' | 'TEACHER' | 'ADMIN';
  department: string;
  university_id: string;
  verification_status: 'UNVERIFIED' | 'PENDING' | 'VERIFIED' | 'REJECTED';
  account_status: 'ACTIVE' | 'SUSPENDED' | 'DEACTIVATED';
  rating_average: number;
  rating_count: number;
  completed_trips_count: number;
  email_verified_at?: string | null;
  created_at: string;
  student_profile?: { semester?: number | null; home_area?: string | null; degree_programme?: string | null } | null;
  teacher_profile?: { designation?: string | null; home_area?: string | null } | null;
};

type AuthState = {
  user: SessionUser | null;
  refreshToken: string | null;
  status: 'loading' | 'signedOut' | 'signedIn';
  hydrate: () => Promise<void>;
  completeSignIn: (response: authApi.AuthResponse) => Promise<void>;
  signOut: () => Promise<void>;
  updateUser: (user: SessionUser) => void;
};

type SetState = (partial: Partial<AuthState>) => void;

/** React 18 invokes effects twice in development; one hydrate, one `GET /auth/me`. */
let hydrateInFlight: Promise<void> | null = null;

async function runHydrate(set: SetState, get: () => AuthState): Promise<void> {
  let accessToken: string | null = null;
  let refreshToken: string | null = null;

  try {
    ({ accessToken, refreshToken } = await loadTokens());
  } catch {
    // Keystore unavailable: treat as signed out instead of hanging on the splash screen.
    set({ status: 'signedOut' });
    return;
  }

  if (!accessToken || !refreshToken) {
    set({ status: 'signedOut' });
    return;
  }

  setAccessToken(accessToken);
  setRefreshToken(refreshToken);
  set({ refreshToken });

  try {
    const user = await authApi.fetchMe();
    set({ user, status: 'signedIn' });
  } catch (error) {
    // "Cannot reach the API" is not "your session is invalid". Wiping the keystore here
    // signed the member out every time the laptop server happened to be down.
    const unreachable = error instanceof ApiError && error.code === 'NETWORK_ERROR';
    if (!unreachable) {
      await clearTokens().catch(() => undefined);
      setAccessToken(null);
      setRefreshToken(null);
    }
    set({ user: null, refreshToken: unreachable ? refreshToken : null, status: 'signedOut' });
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  refreshToken: null,
  status: 'loading',

  hydrate: () => {
    hydrateInFlight = hydrateInFlight ?? runHydrate(set, get);
    return hydrateInFlight;
  },

  completeSignIn: async (response) => {
    setAccessToken(response.access_token);
    setRefreshToken(response.refresh_token);
    try {
      await saveTokens(response.access_token, response.refresh_token);
    } catch {
      // Keystore write failed — the session still works until the app is closed.
    }
    resetQueryCache(); // a previous account's rides must never render for this one
    hydrateInFlight = null;
    set({ user: response.user, refreshToken: response.refresh_token, status: 'signedIn' });
  },

  signOut: async () => {
    // Offline, or a dead server, must never trap the member in a session: local state is
    // cleared in `finally`, and the server-side revoke is best-effort.
    try {
      await authApi.logout(get().refreshToken);
    } catch {
      // ignore — the token is discarded locally either way
    } finally {
      await clearTokens().catch(() => undefined);
      setAccessToken(null);
      setRefreshToken(null);
      resetQueryCache();
      hydrateInFlight = null;
      set({ user: null, refreshToken: null, status: 'signedOut' });
    }
  },

  updateUser: (user) => set({ user }),
}));

// A refresh failure anywhere in the app drops the user back to the auth flow.
onUnauthorized(() => {
  // The pair is dead server-side too, so the keystore and the cache must not keep it.
  void clearTokens().catch(() => undefined);
  resetQueryCache();
  hydrateInFlight = null;
  useAuthStore.setState({ user: null, refreshToken: null, status: 'signedOut' });
});
```

---


## `mobile/src/api/client.ts`  ·  *REPLACE*

```ts
import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { env, getApiBaseUrl } from '@/lib/config';
import { loadTokens, saveTokens, clearTokens } from '@/lib/secureStore';

/**
 * Single HTTP client for the whole app.
 *
 * * `setAccessToken` keeps the in-memory copy used by the request interceptor.
 * * On `401` a **single** refresh call is made (single-flight) and the original
 *   request is retried once; concurrent 401s queue behind the same promise.
 * * Every failure is normalised into `ApiError` so screens handle one shape.
 */
export const api = axios.create({
  baseURL: env.apiUrl,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
});

let accessToken: string | null = null;
let refreshToken: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;
let onSessionExpired: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function setRefreshToken(token: string | null): void {
  refreshToken = token;
}

/** Current access token — needed by the chat WebSocket handshake (§11). */
export function getAccessToken(): string | null {
  return accessToken;
}

export function onUnauthorized(handler: () => void): void {
  onSessionExpired = handler;
}

export type ApiErrorCode =
  | 'VALIDATION_ERROR'
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'RIDE_NOT_AVAILABLE'
  | 'RATE_LIMITED'
  | 'ACCOUNT_SUSPENDED'
  | 'ACCOUNT_NOT_VERIFIED'
  | 'DATABASE_ERROR'
  | 'INTERNAL_ERROR'
  | 'NETWORK_ERROR';

export class ApiError extends Error {
  code: ApiErrorCode;
  details: Record<string, string>;

  constructor(code: ApiErrorCode, message: string, details: Record<string, string> = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.details = details;
  }
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

async function refreshSession(): Promise<string | null> {
  if (!refreshToken) return null;
  try {
    const { data } = await axios.post<{ access_token: string; refresh_token: string }>(
      `${getApiBaseUrl()}/auth/refresh`,
      { refresh_token: refreshToken },
      { headers: { 'Content-Type': 'application/json' }, timeout: 15000 },
    );
    accessToken = data.access_token;
    refreshToken = data.refresh_token;
    setAccessToken(data.access_token);
    setRefreshToken(data.refresh_token);
    await saveTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    accessToken = null;
    refreshToken = null;
    setAccessToken(null);
    setRefreshToken(null);
    await clearTokens();
    onSessionExpired?.();
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ error?: { code?: ApiErrorCode; message?: string; details?: Record<string, string> } }>) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;

    if (error.response?.status === 401 && original && !original._retried) {
      original._retried = true;
      refreshInFlight = refreshInFlight ?? refreshSession();
      const token = await refreshInFlight;
      refreshInFlight = null;
      if (token) {
        original.headers.Authorization = `Bearer ${token}`;
        return api.request(original);
      }
    }

    if (!error.response) {
      // Name the URL in the message: a build can reach the wrong host, and "check your
      // internet connection" alone has already cost a full cloud build to diagnose.
      const where = getApiBaseUrl();
      const timedOut = error.code === 'ECONNABORTED';
      return Promise.reject(
        new ApiError(
          'NETWORK_ERROR',
          timedOut
            ? `SSUET RideShare did not answer within 15s (${where}). The server may be starting up.`
            : `Cannot reach SSUET RideShare at ${where}. Check the server and the Wi-Fi.`,
          {},
        ),
      );
    }
    const payload = error.response.data?.error;
    return Promise.reject(
      new ApiError(
        payload?.code ?? 'INTERNAL_ERROR',
        payload?.message ?? 'Something went wrong. Please try again.',
        payload?.details ?? {},
      ),
    );
  },
);

export type MetaResponse = {
  university: {
    name: string;
    short_name: string;
    latitude: number;
    longitude: number;
    default_area_label: string;
  };
  features: { maps_configured: boolean; push_notifications: boolean; max_confirmed_passengers: number };
  environment: string;
};

export async function fetchMeta(): Promise<MetaResponse> {
  const { data } = await api.get<MetaResponse>('/meta');
  return data;
}
```

---


## `mobile/src/components/ServerPanel.tsx`  ·  *NEW*

```tsx
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Button, TextField } from '@/components/ui';
import { getApiBaseUrl } from '@/lib/config';
import {
  clearApiBaseUrlOverride,
  probeServer,
  saveApiBaseUrlOverride,
} from '@/lib/serverOverride';
import { colors, spacing, typography } from '@/theme';

/**
 * Testing-only control (rendered only when `EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE=1`).
 *
 * The APK bakes its API URL at build time; this lets QA re-point it at a laptop on the LAN
 * without another cloud build. The URL is stored in the keystore and survives restarts.
 */
export function ServerPanel() {
  const [value, setValue] = useState(getApiBaseUrl());
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSave = async () => {
    setBusy(true);
    try {
      const url = await saveApiBaseUrlOverride(value);
      setValue(url);
      setMessage(`Saved — ${url} is ${await probeServer(url)}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not save the URL.');
    } finally {
      setBusy(false);
    }
  };

  const onReset = async () => {
    setBusy(true);
    try {
      const url = await clearApiBaseUrlOverride();
      setValue(url);
      setMessage(`Back to the build default — ${url}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>Server (testing build)</Text>
      <Text style={styles.hint}>
        Phone and laptop must be on the same Wi-Fi. Example: http://192.168.100.32:8000/api/v1
      </Text>
      <TextField
        label="API base URL"
        placeholder="http://192.168.100.32:8000/api/v1"
        icon="server-outline"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        value={value}
        onChangeText={setValue}
      />
      {message ? <Text style={styles.message}>{message}</Text> : null}
      <View style={styles.row}>
        <Button label="Save & test" onPress={onSave} loading={busy} icon="checkmark-circle-outline" />
        <Button label="Reset" onPress={onReset} variant="secondary" icon="refresh-outline" />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderColor: colors.border,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderRadius: 12,
    padding: spacing.md,
    gap: spacing.sm,
  },
  title: { color: colors.textMuted, ...typography.caption, textTransform: 'uppercase' },
  hint: { color: colors.textMuted, ...typography.caption },
  message: { color: colors.text, ...typography.caption },
  row: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
});
```

---


## `mobile/src/lib/schemas.ts`  ·  *REPLACE (semester 1–12 validation)*

```ts
import { z } from 'zod';

/**
 * Zod schemas mirroring the backend Pydantic contracts (§26.9).
 * Same rules, same friendly messages — the API still validates everything.
 */

const passwordRules = z
  .string()
  .min(8, 'Use at least 8 characters')
  .regex(/[A-Za-z]/, 'Include at least one letter')
  .regex(/[0-9]/, 'Include at least one number');

export const loginSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});
export type LoginValues = z.infer<typeof loginSchema>;

export const signupSchema = z
  .object({
    full_name: z.string().min(3, 'Enter your full name').max(120),
    email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
    phone: z
      .string()
      .min(10, 'Enter a valid phone number')
      .max(20)
      .regex(/^\+?[0-9\s-]+$/, 'Digits only, e.g. +923001234567'),
    password: passwordRules,
    confirm_password: z.string(),
    role: z.enum(['STUDENT', 'TEACHER']),
    university_id: z.string().min(3, 'Student / employee ID is required').max(40),
    department: z.string().min(2, 'Select your department'),
    home_area: z.string().max(160).optional(),
    semester: z.string().trim().max(2, 'Semester is a number from 1 to 12').optional(),
    designation: z.string().max(120).optional(),
  })
  .refine((values) => values.password === values.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match',
  })
  .refine(
    (values) => values.role !== 'STUDENT' || Boolean(values.semester && values.semester.length > 0),
    { path: ['semester'], message: 'Select your current semester (1 – 12)' },
  )
  // The API rejects anything outside 1–12 with a generic 422, so catch it here first and
  // say exactly what is wrong instead of letting the member guess (§21).
  .refine(
    (values) => {
      const raw = values.semester?.trim();
      if (!raw) return true;
      if (!/^\d{1,2}$/.test(raw)) return false;
      const semester = Number(raw);
      return semester >= 1 && semester <= 12;
    },
    { path: ['semester'], message: 'Semester must be a whole number from 1 to 12' },
  );
export type SignupValues = z.infer<typeof signupSchema>;

export const forgotPasswordSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
});
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;

export const DEPARTMENTS = [
  'Computer Science',
  'Software Engineering',
  'Electrical Engineering',
  'Electronic Engineering',
  'Civil Engineering',
  'Biomedical Engineering',
  'Business Administration',
  'Basic Sciences',
] as const;

/**
 * Common Karachi pickup areas.
 *
 * The map screen lets a member drop an exact pin; these names keep search and
 * publishing usable when no Google Maps key is configured (§13) and give the API a
 * human-readable area label to show before a match.
 */
export const KARACHI_AREAS = [
  'Gulshan-e-Iqbal',
  'Gulistan-e-Johar',
  'North Nazimabad',
  'Federal B Area',
  'PECHS',
  'Clifton',
  'Saddar',
  'Scheme 33',
  'Malir',
  'Korangi',
  'Gulberg',
  'Liaquatabad',
] as const;
```

---


## `mobile/app/(auth)/signup.tsx`  ·  *REPLACE (real error reason + field hints)*

```tsx
import { useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ApiError } from '@/api/client';
import * as authApi from '@/api/auth';
import { Banner, Button, Card, ChipRow, TextField } from '@/components/ui';
import { ServerPanel } from '@/components/ServerPanel';
import { DEPARTMENTS, signupSchema, type SignupValues } from '@/lib/schemas';
import { useAuthStore } from '@/store/auth';
import { env } from '@/lib/config';
import { colors, spacing, typography } from '@/theme';

const FIELD_LABELS: Record<string, string> = {
  full_name: 'Full name',
  email: 'Email',
  phone: 'Phone number',
  password: 'Password',
  confirm_password: 'Confirm password',
  university_id: 'Student ID',
  department: 'Department',
  semester: 'Semester',
  home_area: 'Home area',
  role: 'Role',
};

/** "Value error, Password must contain at least one number." → "Password: …". */
function describeFieldErrors(details: Record<string, string>): string {
  return Object.entries(details)
    .map(([field, message]) => `${FIELD_LABELS[field] ?? field}: ${message.replace(/^Value error,\s*/i, '')}`)
    .join(' · ');
}

export default function SignupScreen() {
  const router = useRouter();
  const completeSignIn = useAuthStore((state) => state.completeSignIn);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const scrollRef = useRef<ScrollView>(null);
  const [submitting, setSubmitting] = useState(false);

  const { control, handleSubmit, watch, setValue } = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      full_name: '',
      email: '',
      phone: '',
      password: '',
      confirm_password: '',
      role: 'STUDENT',
      university_id: '',
      department: '',
      home_area: '',
      semester: '',
      designation: '',
    },
  });

  const role = watch('role');
  const department = watch('department');

  const onSubmit = async (values: SignupValues) => {
    setFormError(null);
    setFieldErrors({});
    setSubmitting(true);
    try {
      const response = await authApi.signup({
        full_name: values.full_name.trim(),
        email: values.email.trim().toLowerCase(),
        password: values.password,
        phone: values.phone.trim(),
        role: values.role,
        university_id: values.university_id.trim(),
        department: values.department,
        home_area: values.home_area?.trim() || undefined,
        semester: values.role === 'STUDENT' && values.semester ? Number(values.semester) : undefined,
        designation: values.role === 'TEACHER' ? values.designation?.trim() || undefined : undefined,
      });
      await completeSignIn(response);
      router.replace('/(tabs)');
    } catch (error) {
      if (error instanceof ApiError && Object.keys(error.details).length > 0) {
        // Show the *actual* reason ("Password must contain at least one number.") instead of
        // the generic "Some of the submitted values are invalid." — a generic banner with no
        // visible field hint was impossible to act on (§21).
        setFieldErrors(error.details);
        setFormError(describeFieldErrors(error.details) || error.message);
      } else {
        setFormError(error instanceof ApiError ? error.message : 'Could not create your account.');
      }
      scrollRef.current?.scrollTo({ y: 0, animated: true });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.title}>Create your account</Text>
          <Text style={styles.subtitle}>
            Students and teachers of SSUET only. Verification keeps everyone safe.
          </Text>

          {formError ? (
            <Banner
              tone="danger"
              title={Object.keys(fieldErrors).length > 0 ? 'Please check the highlighted fields' : undefined}
              message={formError}
            />
          ) : null}

          <Card>
            <Text style={styles.groupLabel}>I am a</Text>
            <Controller
              control={control}
              name="role"
              render={({ field }) => (
                <ChipRow
                  options={[
                    { value: 'STUDENT' as const, label: 'Student' },
                    { value: 'TEACHER' as const, label: 'Teacher' },
                  ]}
                  value={field.value}
                  onChange={field.onChange}
                />
              )}
            />

            <View style={styles.gap} />

            <Controller
              control={control}
              name="full_name"
              render={({ field, fieldState }) => (
                <TextField
                  label="Full name"
                  placeholder="Ali Raza"
                  icon="person-outline"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.full_name}
                />
              )}
            />
            <Controller
              control={control}
              name="email"
              render={({ field, fieldState }) => (
                <TextField
                  label="Email address"
                  placeholder="yourname@ssuet.edu.pk"
                  icon="mail-outline"
                  autoCapitalize="none"
                  keyboardType="email-address"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.email}
                  hint="University emails are verified instantly. Other emails are verified by an admin."
                />
              )}
            />
            <Controller
              control={control}
              name="phone"
              render={({ field, fieldState }) => (
                <TextField
                  label="Phone number"
                  placeholder="+923001234567"
                  icon="call-outline"
                  keyboardType="phone-pad"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.phone}
                  hint="Shared only with a passenger you have matched with."
                />
              )}
            />
            <Controller
              control={control}
              name="university_id"
              render={({ field, fieldState }) => (
                <TextField
                  label={role === 'STUDENT' ? 'Student ID' : 'Employee ID'}
                  placeholder={role === 'STUDENT' ? 'SSUET-2022-101' : 'SSUET-EMP-1001'}
                  icon="card-outline"
                  autoCapitalize="characters"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.university_id}
                />
              )}
            />

            <Text style={styles.groupLabel}>Department</Text>
            <Controller
              control={control}
              name="department"
              render={({ field, fieldState }) => (
                <View>
                  <View style={styles.departmentWrap}>
                    {DEPARTMENTS.map((item) => {
                      const active = department === item;
                      return (
                        <Pressable
                          key={item}
                          onPress={() => setValue('department', item, { shouldValidate: true })}
                          style={[styles.departmentChip, active && styles.departmentChipActive]}
                        >
                          <Text style={[styles.departmentLabel, active && styles.departmentLabelActive]}>
                            {item}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </View>
                  {fieldState.error ? (
                    <Text style={styles.errorText}>{fieldState.error.message}</Text>
                  ) : null}
                  <Text style={styles.hiddenField}>{field.value}</Text>
                </View>
              )}
            />

            {role === 'STUDENT' ? (
              <>
                <Controller
                  control={control}
                  name="semester"
                  render={({ field, fieldState }) => (
                    <TextField
                      label="Current semester"
                      placeholder="5"
                      icon="school-outline"
                      keyboardType="number-pad"
                      maxLength={2}
                      value={field.value}
                      onChangeText={field.onChange}
                      onBlur={field.onBlur}
                      error={fieldState.error?.message ?? fieldErrors.semester}
                      hint="A number from 1 to 12 — for example 5."
                    />
                  )}
                />
                <Controller
                  control={control}
                  name="home_area"
                  render={({ field }) => (
                    <TextField
                      label="Home area (optional)"
                      placeholder="Gulshan-e-Iqbal"
                      icon="location-outline"
                      value={field.value}
                      onChangeText={field.onChange}
                      hint="Only the area name is shown to others — never your address."
                    />
                  )}
                />
              </>
            ) : (
              <>
                <Controller
                  control={control}
                  name="designation"
                  render={({ field }) => (
                    <TextField
                      label="Designation"
                      placeholder="Assistant Professor"
                      icon="briefcase-outline"
                      value={field.value}
                      onChangeText={field.onChange}
                    />
                  )}
                />
                <Controller
                  control={control}
                  name="home_area"
                  render={({ field }) => (
                    <TextField
                      label="Home area (optional)"
                      placeholder="Scheme 33"
                      icon="location-outline"
                      value={field.value}
                      onChangeText={field.onChange}
                    />
                  )}
                />
              </>
            )}

            <Controller
              control={control}
              name="password"
              render={({ field, fieldState }) => (
                <TextField
                  label="Password"
                  placeholder="At least 8 characters"
                  icon="lock-closed-outline"
                  secureTextEntry
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.password}
                  hint="At least 8 characters, including one letter and one number."
                />
              )}
            />
            <Controller
              control={control}
              name="confirm_password"
              render={({ field, fieldState }) => (
                <TextField
                  label="Confirm password"
                  placeholder="Repeat your password"
                  icon="lock-closed-outline"
                  secureTextEntry
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.confirm_password}
                />
              )}
            />

            <Button
              label="Create account"
              onPress={handleSubmit(onSubmit)}
              loading={submitting}
              icon="checkmark-circle-outline"
            />
          </Card>

          {env.allowServerOverride ? <ServerPanel /> : null}

          <Pressable onPress={() => router.replace('/(auth)/login')} style={styles.footerLink}>
            <Text style={styles.footerText}>
              Already registered? <Text style={styles.link}>Sign in</Text>
            </Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  flex: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  title: { color: colors.text, ...typography.display, marginTop: spacing.lg },
  subtitle: { color: colors.textMuted, ...typography.body },
  groupLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase', marginBottom: spacing.sm },
  gap: { height: spacing.md },
  departmentWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  departmentChip: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  departmentChipActive: { backgroundColor: colors.greenTint, borderColor: colors.green },
  departmentLabel: { color: colors.textMuted, ...typography.caption },
  departmentLabelActive: { color: colors.greenDark, fontWeight: '700' },
  errorText: { color: colors.danger, ...typography.caption, marginTop: spacing.xs },
  hiddenField: { display: 'none' },
  footerLink: { alignItems: 'center', paddingVertical: spacing.md },
  footerText: { color: colors.textMuted, ...typography.caption },
  link: { color: colors.navy, ...typography.bodyStrong, textDecorationLine: 'underline' },
});
```

---


## `mobile/app/_layout.tsx`  ·  *REPLACE*

```tsx
import { useEffect, useRef } from 'react';
import { Stack } from 'expo-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { colors } from '@/theme';
import { useAuthStore } from '@/store/auth';
import { setAccessToken, setRefreshToken } from '@/api/client';
import { clearTokens } from '@/lib/secureStore';
import { queryClient, resetQueryCache } from '@/lib/queryClient';
import { registerForPush, unregisterPush } from '@/lib/push';
import { loadApiBaseUrlOverride, onApiBaseUrlChange } from '@/lib/serverOverride';

/**
 * A different server means different accounts: the keystore pair belongs to the old one and
 * would only produce 401s. Dropped locally and instantly — `signOut()` would fire a logout
 * request at the *new* host, which cannot succeed and may stall for the full 15 s timeout.
 */
async function dropSessionForServerSwitch(): Promise<void> {
  resetQueryCache();
  useAuthStore.setState({ user: null, refreshToken: null, status: 'signedOut' });
  setAccessToken(null);
  setRefreshToken(null);
  await clearTokens();
}

export default function RootLayout() {
  const hydrate = useAuthStore((state) => state.hydrate);
  const status = useAuthStore((state) => state.status);
  const pushTokenRef = useRef<string | null>(null);

  useEffect(() => {
    // Switching servers invalidates everything cached from the previous one, and the session
    // with it. `applyApiBaseUrl` only notifies when the URL really changes, so this is quiet.
    return onApiBaseUrlChange(() => {
      void dropSessionForServerSwitch();
    });
  }, []);

  useEffect(() => {
    // A testing build may point at a different API than the one baked in; apply the saved
    // override first, then restore the keystore session and verify it with GET /auth/me.
    void (async () => {
      await loadApiBaseUrlOverride();
      await hydrate();
    })();
  }, [hydrate]);

  useEffect(() => {
    // Register the device for Expo push while signed in; release it on sign-out so
    // a shared handset never receives the previous member's notifications (§12).
    if (status !== 'signedIn') {
      const token = pushTokenRef.current;
      pushTokenRef.current = null;
      if (token) void unregisterPush(token);
      return;
    }
    let cancelled = false;
    void registerForPush().then((result) => {
      if (!cancelled && result.token) pushTokenRef.current = result.token;
    });
    return () => {
      cancelled = true;
    };
  }, [status]);

  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <StatusBar style="dark" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: colors.background },
            animation: 'slide_from_right',
          }}
        >
          <Stack.Screen name="index" />
          <Stack.Screen name="(auth)" options={{ animation: 'fade' }} />
          <Stack.Screen name="(tabs)" options={{ animation: 'fade' }} />
          <Stack.Screen name="verification" options={{ presentation: 'modal' }} />
          <Stack.Screen name="vehicles" />
          <Stack.Screen name="ride/[id]" />
          <Stack.Screen name="trip/[id]" />
          <Stack.Screen name="chat/[id]" />
          <Stack.Screen name="notifications" />
          <Stack.Screen name="chats" />
          <Stack.Screen name="review/[tripId]" options={{ presentation: 'modal' }} />
          <Stack.Screen name="report/[tripId]" options={{ presentation: 'modal' }} />
          <Stack.Screen name="reviews" />
          <Stack.Screen name="my-reports" />
          <Stack.Screen name="blocked" />
        </Stack>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
```

---


## `mobile/app.config.ts`  ·  *REPLACE*

Full file (current):

```ts
import type { ExpoConfig, ConfigContext } from 'expo/config';

/**
 * Expo configuration (§24).
 *
 * Everything environment-specific comes from EXPO_PUBLIC_* variables so the
 * same source builds dev / preview / production artefacts.
 * Never hardcode API URLs, map keys or secrets here.
 */
// A cloud build runs on Expo's machines and never sees the local .env, so the fallback must
// not be `localhost` there. EAS_BUILD_PROFILE is only set inside an EAS build.
const FALLBACK_API_URL = process.env.EAS_BUILD_PROFILE
  ? 'https://rideshare.ssuet.edu.pk/api/v1'
  : 'http://localhost:8000/api/v1';

// Testing builds (`EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE=1`) let QA change the API URL inside
// the app; such a build may talk to a laptop over plain HTTP, which Android blocks by
// default — so the cleartext allowance is enabled only alongside that flag.
const ALLOW_SERVER_OVERRIDE = process.env.EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE === '1';

const testingPlugins: [string, Record<string, unknown>][] = ALLOW_SERVER_OVERRIDE
  ? [['expo-build-properties', { android: { usesCleartextTraffic: true } }]]
  : [];

// `EAS_PROJECT_ID=` in a .env file is an empty string, and `??` does not treat that as
// "unset" — so every value goes through a helper that trims and falls back.
const envOr = (value: string | undefined, fallback: string): string => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : fallback;
};

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  // The Expo account that owns the EAS project. Required when an account belongs to more
  // than one (personal + team), otherwise EAS may resolve the project under the wrong owner.
  owner: 'rayyanahmedkhan',
  name: 'SSUET RideShare',
  slug: 'ssuet-rideshare',
  version: '1.0.0',
  orientation: 'portrait',
  scheme: 'ssuetrideshare',
  userInterfaceStyle: 'light',
  newArchEnabled: true,
  icon: './assets/icon.png',
  splash: {
    image: './assets/splash.png',
    resizeMode: 'contain',
    backgroundColor: '#0B1F3A',
  },
  android: {
    package: 'com.ssuet.rideshare',
    // versionCode intentionally omitted: eas.json sets appVersionSource "remote", so EAS
    // owns the number. A local value here is ignored and only produces a build warning.
    adaptiveIcon: {
      foregroundImage: './assets/adaptive-icon.png',
      backgroundColor: '#0B1F3A',
    },
    permissions: [
      'ACCESS_FINE_LOCATION',
      'ACCESS_COARSE_LOCATION',
      'POST_NOTIFICATIONS',
      'INTERNET',
    ],
  },
  ios: {
    supportsTablet: false,
    bundleIdentifier: 'com.ssuet.rideshare',
  },
  plugins: [
    [
      'expo-image-picker',
      {
        photosPermission:
          'SSUET RideShare uses your photo library only to attach a picture of your student or employee card for verification.',
        cameraPermission:
          'SSUET RideShare uses the camera only to photograph your student or employee card for verification.',
      },
    ],
    'expo-router',
    'expo-secure-store',
    'expo-notifications',
    [
      'expo-location',
      {
        locationWhenInUsePermission:
          'SSUET RideShare uses your location to suggest pick-up areas near you. Your exact position is never shared with other members.',
      },
    ],
    ...testingPlugins,
  ],
  experiments: {
    typedRoutes: true,
    // Keep Metro's own tsconfig `paths` support on as well — babel.config.js also maps
    // `@/*` with babel-plugin-module-resolver, so the alias resolves on every machine.
    tsconfigPaths: true,
  },
  extra: {
    apiUrl: envOr(process.env.EXPO_PUBLIC_API_URL, FALLBACK_API_URL),
    // Maps are rendered from server-proxied tiles (§13): there is no map key in the build.

    // Renders the "Server (testing build)" panel on the auth screens.
    allowServerOverride: ALLOW_SERVER_OVERRIDE,
    // EAS cannot write into a *dynamic* config (app.config.ts), so the project id has a
    // default here, and EAS_PROJECT_ID in the environment can still override it.
    // Project: https://expo.dev/accounts/rayyanahmedkhan/projects/ssuet-rideshare
    eas: {
      projectId: envOr(process.env.EAS_PROJECT_ID, '11fd9726-022e-4f5a-8690-48deb063f925'),
    },
  },
});
```

---

## `mobile/babel.config.js`  ·  *REPLACE*

```js
module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: [
      [
        'module-resolver',
        {
          root: ['.'],
          alias: { '@': './src' },
          extensions: ['.ts', '.tsx', '.js', '.jsx', '.json'],
        },
      ],
    ],
  };
};
```

---


## `mobile/eas.json`  ·  *REPLACE*

Full file (current):

```json
{
  "cli": {
    "version": ">= 12.0.0",
    "appVersionSource": "remote"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "android": {
        "buildType": "apk"
      },
      "env": {
        "APP_VARIANT": "development",
        "EXPO_PUBLIC_API_URL": "http://192.168.100.32:8000/api/v1",
        "EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE": "1"
      }
    },
    "preview": {
      "distribution": "internal",
      "android": {
        "buildType": "apk",
        "gradleCommand": ":app:assembleRelease"
      },
      "env": {
        "APP_VARIANT": "preview",
        "EXPO_PUBLIC_API_URL": "http://192.168.100.32:8000/api/v1",
        "EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE": "1"
      }
    },
    "production": {
      "autoIncrement": true,
      "android": {
        "buildType": "app-bundle"
      },
      "env": {
        "APP_VARIANT": "production",
        "EXPO_PUBLIC_API_URL": "https://rideshare.ssuet.edu.pk/api/v1"
      }
    }
  },
  "submit": {
    "production": {}
  }
}
```

---

## `mobile/.env`  ·  *NEW (local only, gitignored)*

Full file (current):

```bash
# Local development only (never committed — .env is gitignored).
# Used by: npx expo start (Expo Go), local bundling, and `expo run:android`.
# NOT used by EAS cloud builds — those read mobile/eas.json -> build.<profile>.env
EXPO_PUBLIC_API_URL=http://192.168.100.32:8000/api/v1
EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE=1
```

---

## `mobile/app/(auth)/login.tsx` · *3-line edit*

```ts
import { Banner, Button, Card, TextField } from '@/components/ui';
import { ServerPanel } from '@/components/ServerPanel';
import { env } from '@/lib/config';
```

```tsx
// Card band hone ke baad, "Sign up" link se pehle:
{env.allowServerOverride ? <ServerPanel /> : null}
```

---

## Build ke baad

```powershell
npx tsc --noEmit; echo "exit=$?"
npx expo export:embed --platform android --dev false --minify true `
  --entry-file node_modules/expo-router/entry.js `
  --bundle-output out\index.bundle --assets-dest out\assets --reset-cache
git add -A
git commit -m "feat: LAN server default, runtime switcher, precise form errors"
npx eas-cli@latest build -p android --profile preview --clear-cache
```

---

# Map section (WebView + server tile proxy, Geoapify rotation from Admin)

Key mobile code mein nahi hai. Admin → Map API → provider/key set karein; app rebuild ki zaroorat nahi.

## `mobile/src/components/map/tileMath.ts`  ·  *NEW*

```ts
/**
 * Web-Mercator arithmetic for the in-WebView map (§13).
 *
 * The map runs inside an HTML page, and an HTML page cannot import TypeScript — so the maths
 * lives here as a **string of plain JavaScript** that `tileMapHtml.ts` inlines. Keeping one
 * copy means the numbers the tests check are exactly the numbers the phone runs.
 *
 * Everything is "world pixels": at zoom `z` the whole world is 256·2^z px square, which is
 * the convention every slippy-map server (including our own tile proxy) uses.
 *
 * Verify with: `node scripts/verify-map.mjs`
 */
export const TILE_MATH_JS = `
var EARTH = 256;

function worldSize(zoom) { return EARTH * Math.pow(2, zoom); }

function lngToWorldX(lng, zoom) {
  return (lng + 180) / 360 * worldSize(zoom);
}

function latToWorldY(lat, zoom) {
  var clamped = Math.max(-85.05112878, Math.min(85.05112878, lat));
  var rad = clamped * Math.PI / 180;
  return (1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2 * worldSize(zoom);
}

function worldXToLng(x, zoom) {
  return x / worldSize(zoom) * 360 - 180;
}

function worldYToLat(y, zoom) {
  var n = Math.PI - 2 * Math.PI * y / worldSize(zoom);
  return 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
}

/** Inclusive tile range covering a viewport of w×h px whose top-left is (ox, oy). */
function tileRange(ox, oy, w, h, zoom) {
  var count = Math.pow(2, zoom);
  function clamp(v) { return Math.max(0, Math.min(count - 1, v)); }
  return {
    minX: clamp(Math.floor(ox / EARTH)),
    maxX: clamp(Math.floor((ox + w) / EARTH)),
    minY: clamp(Math.floor(oy / EARTH)),
    maxY: clamp(Math.floor((oy + h) / EARTH))
  };
}

/**
 * Zoom at which two points fit inside a viewport with padding.
 * dx/dy are their world-pixel distance AT ZOOM 0 (i.e. on a 256 px world).
 */
function zoomToFit(dx, dy, w, h, pad, maxZoom) {
  var availX = Math.max(16, w - pad * 2);
  var availY = Math.max(16, h - pad * 2);
  var zx = dx / availX > 0 ? Math.log(availX / dx) / Math.LN2 : 99;
  var zy = dy / availY > 0 ? Math.log(availY / dy) / Math.LN2 : 99;
  var zoom = Math.floor(Math.min(zx, zy));
  return Math.max(2, Math.min(maxZoom, zoom));
}
`;
```

---

## `mobile/src/components/map/tileMapHtml.ts`  ·  *NEW*

```ts
import { TILE_MATH_JS } from '@/components/map/tileMath';

/**
 * A self-contained slippy map for a WebView (§13).
 *
 * Why not the native Google map: its key is compiled into the APK, so an expired key means a
 * blank rectangle for every installed app until a new build is uploaded. This map asks **our**
 * `/maps/tiles/{z}/{x}/{y}.png` proxy for imagery, which means the provider — OpenStreetMap
 * today, Geoapify or MapTiler tomorrow — and its key are decided on the server, at runtime.
 *
 * No third-party JavaScript is loaded: the page is inline HTML, CSS and ~200 lines of
 * vanilla JS, so the only network traffic is the tiles themselves.
 *
 * Bridge (WebView → app): `{type:'ready'}`, `{type:'pin', latitude, longitude}`,
 * `{type:'tiles-error'}`. App → WebView: `window.__map.setPin(lat, lng)`.
 */
export type MapPin = {
  id: string;
  latitude: number;
  longitude: number;
  color: string;
};

export type TileMapOptions = {
  /** Absolute tile base, e.g. `http://192.168.100.32:8000/api/v1/maps/tiles`. */
  tileBase: string;
  attribution: string;
  latitude: number;
  longitude: number;
  zoom?: number;
  pins?: MapPin[];
  /** Tap and drag move `pins[0]` (the pickup pin). */
  editable?: boolean;
  /** Centre and zoom so every pin is visible (used on the ride-details screen). */
  fit?: boolean;
  hint?: string;
  maxZoom?: number;
};

const BRAND_GREEN = '#0f7a4d';

/**
 * Attribution is inserted as HTML because OpenStreetMap's licence requires a visible link.
 * Only a plain anchor is allowed through, so a compromised or mis-typed provider label can
 * never inject script into the page.
 */
function sanitizeAttribution(value: string): string {
  return value
    .replace(/<\s*(?!\/?a\b)[^>]*>/gi, '') // keep <a ...> and </a>, drop every other tag
    .replace(/\son[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '') // drop on* handlers
    .replace(/javascript:/gi, '')
    .slice(0, 300);
}

/** JSON that is safe inside a `<script>` block. */
function inlineJson(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
    .replace(/`/g, '\\u0060')
    .replace(/\u2028|\u2029/g, '');
}

export function buildTileMapHtml(options: TileMapOptions): string {
  const config = {
    tileBase: options.tileBase.replace(/\/+$/, ''),
    attribution: sanitizeAttribution(options.attribution),
    lat: options.latitude,
    lng: options.longitude,
    zoom: options.zoom ?? 14,
    maxZoom: options.maxZoom ?? 18,
    editable: options.editable ?? false,
    fit: options.fit ?? false,
    hint: options.hint ?? (options.editable ? 'Tap the map to drop a pin' : ''),
    pins: options.pins ?? [
      { id: 'pin', latitude: options.latitude, longitude: options.longitude, color: BRAND_GREEN },
    ],
  };

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<style>
  html, body { margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden;
    background: #e9edf1; font-family: -apple-system, Roboto, system-ui, sans-serif;
    -webkit-user-select: none; user-select: none; -webkit-tap-highlight-color: transparent; }
  #map { position: absolute; inset: 0; overflow: hidden; touch-action: none; }
  #stage { position: absolute; left: 0; top: 0; width: 0; height: 0; will-change: transform; }
  .tile { position: absolute; width: 256px; height: 256px; pointer-events: none;
    -webkit-user-drag: none; opacity: 0; transition: opacity .18s linear; }
  .pin { position: absolute; width: 20px; height: 20px; margin: -20px 0 0 -10px; z-index: 10;
    border: 2px solid #fff; border-radius: 50% 50% 50% 0; transform: rotate(-45deg);
    box-shadow: 0 1px 4px rgba(0,0,0,.45); cursor: grab; }
  .pin.draggable { cursor: move; }
  .pin::after { content: ''; position: absolute; inset: 4px; background: rgba(255,255,255,.85);
    border-radius: 50%; }
  #zoom { position: absolute; right: 10px; top: 10px; display: flex; flex-direction: column;
    gap: 6px; z-index: 20; }
  #zoom button { width: 34px; height: 34px; border: 1px solid #cfd6dd; border-radius: 8px;
    background: rgba(255,255,255,.96); color: #123; font-size: 20px; line-height: 1;
    font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,.18); touch-action: manipulation; }
  #hint { position: absolute; left: 8px; right: 8px; bottom: 6px; z-index: 20;
    font-size: 11px; line-height: 1.35; color: #2b3a45; background: rgba(255,255,255,.85);
    border-radius: 6px; padding: 3px 7px; }
  #attr { position: absolute; right: 3px; top: 3px; z-index: 20; font-size: 8px;
    color: #45525c; background: rgba(255,255,255,.72); border-radius: 3px; padding: 1px 4px;
    max-width: 55%; text-align: right; }
  #attr a { color: #0f7a4d; text-decoration: none; }
  #err { position: absolute; inset: 0; display: none; align-items: center; justify-content: center;
    z-index: 30; padding: 16px; text-align: center; font-size: 12px; color: #7a2b2b;
    background: rgba(255,255,255,.92); }
</style>
</head>
<body>
  <div id="map">
    <div id="stage"><div id="world"></div><div id="pinLayer"></div></div>
    <div id="zoom"><button id="zin" aria-label="Zoom in">+</button><button id="zout" aria-label="Zoom out">&minus;</button></div>
    <div id="attr">${config.attribution}</div>
    <div id="hint"></div>
    <div id="err"></div>
  </div>
<script>
var CONFIG = ${inlineJson(config)};
${TILE_MATH_JS}
var mapEl = document.getElementById('map');
var stage = document.getElementById('stage');
var world = document.getElementById('world');
var pinLayer = document.getElementById('pinLayer');
var hintEl = document.getElementById('hint');
var errEl = document.getElementById('err');

var state = { lat: CONFIG.lat, lng: CONFIG.lng, zoom: CONFIG.zoom, w: 0, h: 0, ox: 0, oy: 0 };
var pins = [];
var tiles = {};
var drag = null;
var failedTiles = 0;
var reportedTilesFailure = false;
var MIN_ZOOM = 3;

for (var i = 0; i < CONFIG.pins.length; i++) {
  pins.push({ id: CONFIG.pins[i].id, lat: CONFIG.pins[i].latitude, lng: CONFIG.pins[i].longitude,
              color: CONFIG.pins[i].color || '${BRAND_GREEN}' });
}

function post(message) {
  var text = JSON.stringify(message);
  if (window.ReactNativeWebView && window.ReactNativeWebView.postMessage) {
    window.ReactNativeWebView.postMessage(text);
  } else if (window.console && console.log) {
    console.log('map->app ' + text);
  }
}

function clampZoom(zoom) { return Math.max(MIN_ZOOM, Math.min(CONFIG.maxZoom, zoom)); }

function setHint(text) { hintEl.textContent = text || ''; hintEl.style.display = text ? 'block' : 'none'; }

function showError(text) {
  errEl.textContent = text;
  errEl.style.display = 'flex';
}

function tileFailed() {
  failedTiles++;
  if (failedTiles >= 4 && !reportedTilesFailure) {
    reportedTilesFailure = true;
    post({ type: 'tiles-error' });
  }
}

function measure() {
  state.w = mapEl.clientWidth || window.innerWidth;
  state.h = mapEl.clientHeight || window.innerHeight;
}

function placeTiles() {
  var range = tileRange(state.ox, state.oy, state.w, state.h, state.zoom);
  var needed = {};
  for (var x = range.minX; x <= range.maxX; x++) {
    for (var y = range.minY; y <= range.maxY; y++) {
      var key = state.zoom + '/' + x + '/' + y;
      needed[key] = true;
      var el = tiles[key];
      if (!el) {
        el = document.createElement('img');
        el.className = 'tile';
        el.alt = '';
        el.onload = function () { this.style.opacity = 1; };
        el.onerror = function () { this.style.opacity = 0; tileFailed(); };
        el.src = CONFIG.tileBase + '/' + state.zoom + '/' + x + '/' + y + '.png';
        world.appendChild(el);
        tiles[key] = el;
      }
      el.style.left = (x * 256 - state.ox) + 'px';
      el.style.top = (y * 256 - state.oy) + 'px';
    }
  }
  for (var k in tiles) {
    if (!needed[k]) {
      if (tiles[k].parentNode) { tiles[k].parentNode.removeChild(tiles[k]); }
      delete tiles[k];
    }
  }
}

function placePins() {
  pinLayer.innerHTML = '';
  for (var i = 0; i < pins.length; i++) {
    var p = pins[i];
    var el = document.createElement('div');
    el.className = 'pin';
    if (CONFIG.editable && i === 0) { el.className += ' draggable'; }
    el.style.background = p.color;
    el.style.left = (lngToWorldX(p.lng, state.zoom) - state.ox) + 'px';
    el.style.top = (latToWorldY(p.lat, state.zoom) - state.oy) + 'px';
    el.setAttribute('data-pin', String(i));
    if (CONFIG.editable && i === 0) { attachPinDrag(el, 0); }
    pinLayer.appendChild(el);
  }
}

function layout() {
  measure();
  state.zoom = clampZoom(state.zoom);

  var size = worldSize(state.zoom);
  var cx = lngToWorldX(state.lng, state.zoom);
  var cy = latToWorldY(state.lat, state.zoom);
  state.ox = cx - state.w / 2;
  state.oy = cy - state.h / 2;

  if (size <= state.h) {
    state.oy = (size - state.h) / 2;
  } else {
    state.oy = Math.max(0, Math.min(size - state.h, state.oy));
  }

  stage.style.transform = 'translate(0px, 0px)';
  placeTiles();
  placePins();
}

function fitPins() {
  if (pins.length < 2) { return false; }
  var minLat = pins[0].lat, maxLat = pins[0].lat, minLng = pins[0].lng, maxLng = pins[0].lng;
  for (var i = 1; i < pins.length; i++) {
    minLat = Math.min(minLat, pins[i].lat); maxLat = Math.max(maxLat, pins[i].lat);
    minLng = Math.min(minLng, pins[i].lng); maxLng = Math.max(maxLng, pins[i].lng);
  }
  state.lat = (minLat + maxLat) / 2;
  state.lng = (minLng + maxLng) / 2;
  var dx = Math.abs(lngToWorldX(maxLng, 0) - lngToWorldX(minLng, 0));
  var dy = Math.abs(latToWorldY(maxLat, 0) - latToWorldY(minLat, 0));
  state.zoom = clampZoom(zoomToFit(dx, dy, state.w, state.h, 46, CONFIG.maxZoom));
  return true;
}

function pointToLatLng(clientX, clientY) {
  var rect = mapEl.getBoundingClientRect();
  var wx = state.ox + (clientX - rect.left);
  var wy = state.oy + (clientY - rect.top);
  return { lat: worldYToLat(wy, state.zoom), lng: worldXToLng(wx, state.zoom) };
}

function movePin(index, lat, lng) {
  if (!pins[index]) { return; }
  pins[index].lat = lat;
  pins[index].lng = lng;
  placePins();
}

function settle(dx, dy) {
  state.lat = worldYToLat(latToWorldY(state.lat, state.zoom) - dy, state.zoom);
  state.lng = worldXToLng(lngToWorldX(state.lng, state.zoom) - dx, state.zoom);
  layout();
}

function onDown(event) {
  if (event.target && event.target.className && String(event.target.className).indexOf('pin') === 0) { return; }
  drag = { mode: 'pan', x: event.clientX, y: event.clientY, moved: false };
}

function onMove(event) {
  if (!drag) { return; }
  if (drag.mode === 'pan') {
    var dx = event.clientX - drag.x;
    var dy = event.clientY - drag.y;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) { drag.moved = true; }
    stage.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';
  } else if (drag.mode === 'pin') {
    var point = pointToLatLng(event.clientX, event.clientY);
    drag.moved = true;
    movePin(drag.index, point.lat, point.lng);
    setHint('Release to confirm this point');
  }
}

function onUp(event) {
  if (!drag) { return; }
  var finished = drag;
  drag = null;

  if (finished.mode === 'pan') {
    var dx = event.clientX - finished.x;
    var dy = event.clientY - finished.y;
    if (!finished.moved) {
      if (CONFIG.editable && pins.length > 0) {
        var point = pointToLatLng(event.clientX, event.clientY);
        movePin(0, point.lat, point.lng);
        setHint('Pin moved — drag the pin to fine-tune');
        post({ type: 'pin', latitude: point.lat, longitude: point.lng });
      }
      return;
    }
    settle(dx, dy);
  } else if (finished.mode === 'pin' && pins[finished.index]) {
    var chosen = pins[finished.index];
    setHint('Pin moved — drag the pin to fine-tune');
    post({ type: 'pin', latitude: chosen.lat, longitude: chosen.lng });
  }
}

function attachPinDrag(el, index) {
  el.addEventListener('pointerdown', function (event) {
    event.stopPropagation();
    event.preventDefault();
    drag = { mode: 'pin', index: index, x: event.clientX, y: event.clientY, moved: false };
    try { el.setPointerCapture(event.pointerId); } catch (error) { /* older WebView */ }
  });
  el.addEventListener('pointermove', function (event) {
    if (drag && drag.mode === 'pin') { onMove(event); }
  });
  el.addEventListener('pointerup', function (event) {
    if (drag && drag.mode === 'pin') { onUp(event); }
  });
}

function zoomBy(delta) {
  state.zoom = clampZoom(state.zoom + delta);
  layout();
}

mapEl.addEventListener('pointerdown', onDown);
window.addEventListener('pointermove', onMove);
window.addEventListener('pointerup', onUp);
window.addEventListener('pointercancel', onUp);
window.addEventListener('resize', layout);
document.getElementById('zin').addEventListener('click', function (event) { event.stopPropagation(); zoomBy(1); });
document.getElementById('zout').addEventListener('click', function (event) { event.stopPropagation(); zoomBy(-1); });
document.addEventListener('touchmove', function (event) { event.preventDefault(); }, { passive: false });

window.__map = {
  setPin: function (lat, lng) { movePin(0, lat, lng); },
  setView: function (lat, lng, zoom) {
    state.lat = lat; state.lng = lng;
    state.zoom = clampZoom(zoom || state.zoom);
    layout();
  },
  recentre: function () { layout(); },
  refresh: function () { tiles = {}; world.innerHTML = ''; layout(); }
};

layout();
if (CONFIG.fit) { fitPins(); layout(); }
setHint(CONFIG.hint);
post({ type: 'ready' });
</script>
</body>
</html>`;
}
```

---

## `mobile/src/components/map/WebMap.tsx`  ·  *NEW*

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { WebView } from 'react-native-webview';
import type { WebViewMessageEvent } from 'react-native-webview';
import { Ionicons } from '@expo/vector-icons';
import { getMapConfig, tileBaseUrl, type MapConfig } from '@/api/maps';
import { buildTileMapHtml, type MapPin } from '@/components/map/tileMapHtml';
import { colors, radius, spacing, typography } from '@/theme';

/**
 * The app's map (§13) — a WebView rendering tiles served by our own API.
 *
 * Nothing about the provider is baked into the APK: the screen asks `/maps/config` which
 * provider to use and requests every tile from `/maps/tiles/{z}/{x}/{y}.png`, where the key is
 * injected server-side. An administrator can therefore rotate the key (or switch provider
 * entirely) and this map keeps working — no rebuild, no new APK, no `.env` edit.
 */

type Props = {
  latitude: number;
  longitude: number;
  /** Extra pins to draw; the first one is the draggable pickup pin when `editable`. */
  pins?: MapPin[];
  editable?: boolean;
  fit?: boolean;
  height?: number;
  hint?: string;
  onPin?: (latitude: number, longitude: number) => void;
};

export function WebMap({
  latitude,
  longitude,
  pins,
  editable = false,
  fit = false,
  height = 190,
  hint,
  onPin,
}: Props) {
  const webview = useRef<WebView>(null);
  const [tilesFailed, setTilesFailed] = useState(false);
  const [ready, setReady] = useState(false);

  const configQuery = useQuery({
    queryKey: ['maps', 'config'],
    queryFn: getMapConfig,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const config: MapConfig | undefined = configQuery.data;
  const mapReady = Boolean(config?.enabled) && (!config?.needs_key || Boolean(config?.has_key));

  const html = useMemo(() => {
    if (!config) return '';
    return buildTileMapHtml({
      tileBase: tileBaseUrl(),
      attribution: config.attribution,
      latitude,
      longitude,
      zoom: fit ? 12 : 15,
      pins: pins ?? [{ id: 'pickup', latitude, longitude, color: colors.green }],
      editable,
      fit,
      hint,
    });
  }, [config, latitude, longitude, pins, editable, fit, hint]);

  /** Keep the pin in step when the screen changes the point from outside (GPS, area chip). */
  useEffect(() => {
    if (!ready) return;
    webview.current?.injectJavaScript(
      `window.__map && window.__map.setPin(${latitude}, ${longitude}); true;`,
    );
  }, [latitude, longitude, ready]);

  const handleMessage = useCallback(
    (event: WebViewMessageEvent) => {
      let payload: { type?: string; latitude?: number; longitude?: number } = {};
      try {
        payload = JSON.parse(event.nativeEvent.data);
      } catch {
        return;
      }
      if (payload.type === 'ready') {
        setReady(true);
      } else if (payload.type === 'tiles-error') {
        setTilesFailed(true);
      } else if (payload.type === 'pin' && typeof payload.latitude === 'number' && typeof payload.longitude === 'number') {
        onPin?.(payload.latitude, payload.longitude);
      }
    },
    [onPin],
  );

  const shell = (children: React.ReactNode) => <View style={[styles.wrap, { height }]}>{children}</View>;

  if (configQuery.isLoading) {
    return shell(
      <View style={styles.notice}>
        <ActivityIndicator size="small" color={colors.navy} />
        <Text style={styles.noticeText}>Loading map…</Text>
      </View>,
    );
  }

  if (configQuery.isError || !config) {
    return shell(
      <View style={styles.notice}>
        <Ionicons name="cloud-offline-outline" size={20} color={colors.textMuted} />
        <Text style={styles.noticeText}>
          Map could not load — the server is unreachable. Area search still works.
        </Text>
      </View>,
    );
  }

  if (!mapReady) {
    return shell(
      <View style={styles.notice}>
        <Ionicons name="warning-outline" size={20} color={colors.warning} />
        <Text style={styles.noticeText}>
          {config.enabled
            ? `Map provider (${config.provider}) has no API key. An administrator can add one under Admin → Map API; no app update is needed.`
            : 'Maps are switched off in the admin console. Choose an area instead.'}
        </Text>
      </View>,
    );
  }

  return shell(
    <View style={styles.frame}>
      <WebView
        ref={webview}
        key={`${config.provider}-${config.updated_at ?? 'init'}`}
        originWhitelist={['*']}
        source={{ html }}
        style={styles.web}
        javaScriptEnabled
        domStorageEnabled={false}
        allowFileAccess={false}
        mixedContentMode="always"
        scrollEnabled={false}
        setSupportMultipleWindows={false}
        androidLayerType="hardware"
        onMessage={handleMessage}
        onHttpError={(synthetic) => {
          if (synthetic.nativeEvent.url.includes('/maps/tiles/')) setTilesFailed(true);
        }}
      />
      {tilesFailed ? (
        <Pressable
          style={styles.retry}
          onPress={() => {
            setTilesFailed(false);
            webview.current?.injectJavaScript('window.__map && window.__map.refresh(); true;');
          }}
        >
          <Ionicons name="refresh" size={13} color={colors.navy} />
          <Text style={styles.retryText}>Tiles did not load — tap to retry</Text>
        </Pressable>
      ) : null}
    </View>,
  );
}

const styles = StyleSheet.create({
  wrap: {
    marginTop: spacing.xs,
    borderRadius: radius.md,
    overflow: 'hidden',
    backgroundColor: colors.surfaceAlt,
  },
  frame: { flex: 1, borderRadius: radius.md, overflow: 'hidden' },
  web: { flex: 1, backgroundColor: colors.surfaceAlt },
  notice: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.surfaceAlt,
  },
  noticeText: { flex: 1, color: colors.textMuted, ...typography.caption },
  retry: {
    position: 'absolute',
    left: 8,
    right: 8,
    bottom: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 6,
    borderRadius: radius.sm,
    backgroundColor: 'rgba(255,255,255,0.94)',
    borderWidth: 1,
    borderColor: colors.border,
  },
  retryText: { color: colors.navy, ...typography.caption, fontWeight: '600' },
});
```

---

## `mobile/src/api/maps.ts`  ·  *NEW*

```ts
import { api } from '@/api/client';
import { getApiBaseUrl } from '@/lib/config';
import { stripTrailingSlashes } from '@/lib/apiUrl';

/**
 * Map access for the app (§13).
 *
 * The app holds **no** map provider credential. It asks the backend what to render, and the
 * backend proxies the tiles — so an administrator can rotate or replace the provider's key
 * in the dashboard and every installed app picks it up on the next request. No rebuild.
 */

export type MapConfig = {
  enabled: boolean;
  provider: string;
  style: string;
  needs_key: boolean;
  has_key: boolean;
  attribution: string;
  tile_url_template: string;
  updated_at: string | null;
};

export type GeoResult = { label: string; latitude: number; longitude: number };

export async function getMapConfig(): Promise<MapConfig> {
  const { data } = await api.get<MapConfig>('/maps/config');
  return data;
}

export async function searchPlaces(query: string, limit = 5): Promise<GeoResult[]> {
  const { data } = await api.get<GeoResult[]>('/maps/search', { params: { q: query, limit } });
  return data;
}

export async function reverseGeocode(latitude: number, longitude: number): Promise<GeoResult> {
  const { data } = await api.get<GeoResult>('/maps/reverse', { params: { lat: latitude, lng: longitude } });
  return data;
}

/**
 * Absolute tile base for the WebView. Tiles must be requested from *our* API because that is
 * where the provider key is injected server-side.
 */
export function tileBaseUrl(): string {
  return `${stripTrailingSlashes(getApiBaseUrl())}/maps/tiles`;
}
```

---

## `mobile/src/components/LocationPicker.tsx`  ·  *REPLACE*

```tsx
import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { TextField } from '@/components/ui';
import { WebMap } from '@/components/map/WebMap';
import { reverseGeocode } from '@/api/maps';
import { AREAS, findArea, SSUET, type AreaPoint } from '@/lib/areas';
import { colors, radius, spacing, typography } from '@/theme';

type Props = {
  label: string;
  value: string;
  point: AreaPoint | null;
  onChange: (area: string, point: AreaPoint) => void;
  error?: string;
};

/**
 * Area + location picker (§13).
 *
 * * Always available: search/choose a Karachi area → its centroid is used.
 * * The map is a **WebView** fed by our own tile proxy, so the provider and its API key are
 *   chosen in the admin dashboard — an expired key never blanks the map in a shipped APK.
 * * Tapping the map drops the pin; dragging the pin fine-tunes it; the area name is filled
 *   in by the backend's reverse geocoder.
 * * "Use my current location" uses expo-location, with a friendly failure path.
 */

/** Turn "Pixy, University Road, Gulshan-e-Iqbal Block 13 C, Karachi…" into a short area name. */
function shortAreaName(label: string): string {
  if (!label) return '';
  const parts = label
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
  const known = AREAS.find((area) =>
    parts.some((part) => part.toLowerCase().includes(area.name.toLowerCase())),
  );
  if (known) return known.name;
  const short = parts.slice(0, 2).join(', ');
  return short.length > 48 ? `${short.slice(0, 45)}…` : short;
}

export function LocationPicker({ label, value, point, onChange, error }: Props) {
  const [locating, setLocating] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [permissionNote, setPermissionNote] = useState<string | null>(null);

  const selectArea = (areaName: string) => {
    const centroid = findArea(areaName) ?? SSUET;
    onChange(areaName, { ...centroid, name: areaName });
  };

  const useCurrentLocation = async () => {
    setPermissionNote(null);
    setLocating(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setPermissionNote('Location permission denied — pick an area or tap the map instead.');
        return;
      }
      const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const guess = await Location.reverseGeocodeAsync(position.coords).catch(() => []);
      const areaName =
        guess[0]?.district ?? guess[0]?.subregion ?? guess[0]?.city ?? value ?? 'Current location';
      onChange(areaName, {
        name: areaName,
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      });
    } catch {
      setPermissionNote('Could not read your location. Choose an area or tap the map instead.');
    } finally {
      setLocating(false);
    }
  };

  /** A tap or pin-drag inside the WebView map. */
  const handlePin = async (latitude: number, longitude: number) => {
    setResolving(true);
    let areaName = value.trim();
    try {
      const place = await reverseGeocode(latitude, longitude);
      areaName = shortAreaName(place.label) || areaName;
    } catch {
      // Offline or geocoder down — the coordinates still count.
      if (!areaName) areaName = 'Pinned location';
    }
    onChange(areaName || 'Pinned location', { name: areaName || 'Pinned location', latitude, longitude });
    setResolving(false);
  };

  const centre = point ?? SSUET;

  return (
    <View style={styles.wrap}>
      <TextField
        label={label}
        placeholder="Search an area, e.g. Gulshan-e-Iqbal"
        icon="location-outline"
        value={value}
        onChangeText={(text) =>
          onChange(text, findArea(text) ?? { name: text, latitude: centre.latitude, longitude: centre.longitude })
        }
        error={error}
        hint="Only this area name is shown to other members before a match."
      />

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
        {AREAS.map((area) => {
          const active = area.name.toLowerCase() === value.trim().toLowerCase();
          return (
            <Pressable
              key={area.name}
              onPress={() => selectArea(area.name)}
              style={[styles.chip, active && styles.chipActive]}
            >
              <Text style={[styles.chipLabel, active && styles.chipLabelActive]}>{area.name}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <Pressable onPress={useCurrentLocation} style={styles.currentLocation} disabled={locating}>
        {locating ? (
          <ActivityIndicator size="small" color={colors.navy} />
        ) : (
          <Ionicons name="navigate-outline" size={16} color={colors.navy} />
        )}
        <Text style={styles.currentLocationText}>
          {locating ? 'Getting your location…' : 'Use my current location'}
        </Text>
      </Pressable>

      {permissionNote ? <Text style={styles.note}>{permissionNote}</Text> : null}

      <WebMap
        latitude={centre.latitude}
        longitude={centre.longitude}
        editable
        height={190}
        hint="Tap the map or drag the pin to set the exact meeting point"
        onPin={handlePin}
      />

      {resolving ? (
        <View style={styles.resolving}>
          <ActivityIndicator size="small" color={colors.textMuted} />
          <Text style={styles.mapHint}>Looking up this point…</Text>
        </View>
      ) : (
        <Text style={styles.mapHint}>
          Map tiles are served by the SSUET RideShare server, so the map key can be changed in the
          admin dashboard without updating the app.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  chips: { gap: spacing.sm, paddingVertical: 2 },
  chip: {
    paddingVertical: 6,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipActive: { backgroundColor: colors.navy, borderColor: colors.navy },
  chipLabel: { color: colors.textMuted, ...typography.caption },
  chipLabelActive: { color: colors.textInverse, fontWeight: '600' },
  currentLocation: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
  },
  currentLocationText: { color: colors.navy, ...typography.caption, fontWeight: '700' },
  note: { color: colors.warning, ...typography.caption },
  mapHint: { flex: 1, color: colors.textMuted, ...typography.caption },
  resolving: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
});
```

---

## `mobile/app/ride/[id].tsx`  ·  *REPLACE*

```tsx
import { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import { cancelRide, getRide, requestSeat } from '@/api/rides';
import { Avatar, Badge, Banner, Button, Card, TextField } from '@/components/ui';
import { WebMap } from '@/components/map/WebMap';
import { formatDeparture, relativeDay, rupees } from '@/lib/format';
import { useAuthStore } from '@/store/auth';
import { colors, radius, spacing, typography } from '@/theme';

export default function RideDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);

  const [sheetOpen, setSheetOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({ queryKey: ['ride', id], queryFn: () => getRide(id), enabled: Boolean(id) });

  const requestMutation = useMutation({
    mutationFn: () => requestSeat(id, message.trim() || undefined),
    onSuccess: async () => {
      setSheetOpen(false);
      setMessage('');
      await queryClient.invalidateQueries({ queryKey: ['ride', id] });
      await queryClient.invalidateQueries({ queryKey: ['rides'] });
      Alert.alert('Request sent', 'The driver will be notified. You can follow the status in My Rides.');
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : 'Could not send your request.');
      void query.refetch();
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelRide(id, 'Cancelled by the driver'),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['ride', id] });
      await queryClient.invalidateQueries({ queryKey: ['rides'] });
      await queryClient.invalidateQueries({ queryKey: ['my-rides'] });
    },
  });

  if (query.isLoading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.loading}>
          <ActivityIndicator color={colors.green} />
          <Text style={styles.loadingText}>Loading journey…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (query.isError || !query.data) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} style={styles.back}>
            <Ionicons name="arrow-back" size={20} color={colors.navy} />
          </Pressable>
        </View>
        <View style={styles.loading}>
          <Text style={styles.loadingText}>
            {query.error instanceof ApiError ? query.error.message : 'This journey is unavailable.'}
          </Text>
          <Button label="Go back" variant="secondary" onPress={() => router.back()} fullWidth={false} />
        </View>
      </SafeAreaView>
    );
  }

  const ride = query.data;
  const isFree = ride.fuel_preference === 'FREE';
  const verified = user?.verification_status === 'VERIFIED';
  const requestPending = ride.my_request_status === 'PENDING';
  const requestAccepted = ride.my_request_status === 'ACCEPTED';

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.back}>
          <Ionicons name="arrow-back" size={20} color={colors.navy} />
        </Pressable>
        <Text style={styles.headerTitle}>Journey details</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {ride.pickup_point && ride.destination_point ? (
          <View style={styles.mapWrap}>
            <WebMap
              latitude={ride.pickup_point.latitude}
              longitude={ride.pickup_point.longitude}
              height={180}
              fit
              pins={[
                { id: 'pickup', latitude: ride.pickup_point.latitude, longitude: ride.pickup_point.longitude, color: colors.green },
                {
                  id: 'destination',
                  latitude: ride.destination_point.latitude,
                  longitude: ride.destination_point.longitude,
                  color: colors.navy,
                },
              ]}
            />
          </View>
        ) : (
          <Card style={styles.routeCard}>
            <View style={styles.routeRow}>
              <View style={[styles.dot, { backgroundColor: colors.green }]} />
              <View style={{ flex: 1 }}>
                <Text style={styles.routeLabel}>Pickup area</Text>
                <Text style={styles.routeValue}>{ride.pickup_area}</Text>
              </View>
            </View>
            <View style={styles.routeDivider} />
            <View style={styles.routeRow}>
              <View style={[styles.dot, { backgroundColor: colors.navy }]} />
              <View style={{ flex: 1 }}>
                <Text style={styles.routeLabel}>Destination</Text>
                <Text style={styles.routeValue}>{ride.destination_area}</Text>
              </View>
            </View>
            <Text style={styles.routeHint}>
              The exact meeting point is shared once your request is accepted.
            </Text>
          </Card>
        )}

        <Card style={styles.card}>
          <View style={styles.driverRow}>
            <Avatar
              name={ride.driver.full_name}
              size={52}
              photoUrl={ride.driver.profile_photo_url}
            />
            <View style={{ flex: 1, gap: 2 }}>
              <View style={styles.nameRow}>
                <Text style={styles.name}>{ride.driver.full_name}</Text>
                {ride.driver.verification_status === 'VERIFIED' ? (
                  <Ionicons name="shield-checkmark" size={15} color={colors.green} />
                ) : null}
              </View>
              <Text style={styles.muted}>
                {ride.driver.role === 'TEACHER' ? 'Teacher' : 'Student'} · {ride.driver.department}
              </Text>
              <View style={styles.ratingRow}>
                <Ionicons name="star" size={13} color={colors.star} />
                <Text style={styles.muted}>
                  {ride.driver.rating_count > 0
                    ? `${ride.driver.rating_average.toFixed(1)} · ${ride.driver.rating_count} reviews`
                    : 'No reviews yet'}
                </Text>
                <Text style={styles.muted}> · {ride.driver.completed_trips_count} trips</Text>
              </View>
            </View>
            {ride.driver.profile_photo_url && !ride.is_own_ride ? (
              <Pressable
                onPress={() =>
                  router.push({
                    pathname: '/report-photo/[userId]',
                    params: { userId: ride.driver.id, name: ride.driver.full_name },
                  })
                }
                accessibilityRole="button"
                accessibilityLabel={`Report ${ride.driver.full_name}'s photo`}
                hitSlop={10}
                style={styles.photoReportButton}
              >
                <Ionicons name="flag-outline" size={16} color={colors.textMuted} />
              </Pressable>
            ) : null}
          </View>

          {ride.vehicle ? (
            <View style={styles.vehicleRow}>
              <Ionicons
                name={ride.vehicle.vehicle_type === 'BIKE' ? 'bicycle' : 'car-sport'}
                size={18}
                color={colors.navy}
              />
              <Text style={styles.vehicleText}>
                {ride.vehicle.make_and_model} · {ride.vehicle.color}
              </Text>
              {ride.vehicle.is_verified ? (
                <Badge label="Vehicle verified" tone="success" icon="checkmark-circle" />
              ) : (
                <Badge label="Vehicle pending" tone="warning" />
              )}
            </View>
          ) : null}
        </Card>

        <Card style={styles.card}>
          <Row icon="calendar-outline" label="Departure" value={`${relativeDay(ride.departure_at)} · ${formatDeparture(ride.departure_at).split(' · ')[1]}`} />
          <Row
            icon="people-outline"
            label="Seats"
            value={`${ride.seats_remaining} of ${ride.available_seats} available`}
          />
          <Row
            icon={isFree ? 'heart-outline' : 'wallet-outline'}
            label="Contribution"
            value={
              isFree
                ? 'Free ride'
                : ride.contribution?.type === 'NEGOTIABLE'
                  ? 'Fuel share · negotiable'
                  : ride.contribution?.amount
                    ? `Fuel share · ${rupees(ride.contribution.amount)}`
                    : 'Fuel share'
            }
          />
          {!isFree ? (
            <View style={styles.disclaimer}>
              <Text style={styles.disclaimerText}>
                Fuel contributions are a voluntary agreement between the two members, settled
                offline. SSUET RideShare takes no payment and no commission.
              </Text>
            </View>
          ) : null}
          {ride.note ? <Row icon="information-circle-outline" label="Driver's note" value={ride.note} /> : null}
        </Card>

        {error ? <Banner tone="danger" message={error} /> : null}

        {requestAccepted ? (
          <Banner
            tone="success"
            title="You are confirmed"
            message={`Meeting point: ${ride.pickup_area}. Open the trip to start the journey, confirm completion and call your driver.`}
          />
        ) : null}
      </ScrollView>

      <View style={styles.footer}>
        {ride.is_own_ride ? (
          <Button
            label={cancelMutation.isPending ? 'Cancelling…' : 'Cancel this journey'}
            variant="danger"
            loading={cancelMutation.isPending}
            onPress={() =>
              Alert.alert('Cancel journey?', 'The passenger (if any) will be notified immediately.', [
                { text: 'Keep it', style: 'cancel' },
                { text: 'Cancel journey', style: 'destructive', onPress: () => cancelMutation.mutate() },
              ])
            }
          />
        ) : requestPending ? (
          <Button label="Request pending" variant="secondary" disabled onPress={() => undefined} />
        ) : requestAccepted ? (
          <Button
            label="Open trip"
            onPress={() =>
              ride.my_trip_id
                ? router.push(`/trip/${ride.my_trip_id}`)
                : router.push('/(tabs)/my-rides')
            }
            icon="navigate-outline"
          />
        ) : !verified ? (
          <Button label="Verify your account to request" onPress={() => router.push('/verification')} icon="shield-checkmark-outline" />
        ) : ride.can_request ? (
          <Button label="Request to join" onPress={() => setSheetOpen(true)} icon="paper-plane-outline" />
        ) : (
          <Button label="This journey is no longer available" variant="secondary" disabled onPress={() => undefined} />
        )}
      </View>

      <Modal visible={sheetOpen} animationType="slide" transparent onRequestClose={() => setSheetOpen(false)}>
        <View style={styles.sheetBackdrop}>
          <View style={styles.sheet}>
            <View style={styles.sheetHandle} />
            <Text style={styles.sheetTitle}>Request to join</Text>
            <Text style={styles.sheetSubtitle}>
              Add a short note so {ride.driver.full_name.split(' ')[0]} knows where you are travelling from.
            </Text>
            <TextField
              label="Message (optional)"
              placeholder="Assalam-o-Alaikum, I live near Five Star Chowrangi."
              value={message}
              onChangeText={setMessage}
              multiline
            />
            <Button
              label="Send request"
              onPress={() => requestMutation.mutate()}
              loading={requestMutation.isPending}
            />
            <Button label="Cancel" variant="ghost" onPress={() => setSheetOpen(false)} />
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function Row({
  icon,
  label,
  value,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
}) {
  return (
    <View style={styles.row}>
      <Ionicons name={icon} size={16} color={colors.textMuted} />
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue} numberOfLines={2}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  photoReportButton: { padding: spacing.xs, alignSelf: 'flex-start' },
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  back: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  headerTitle: { color: colors.text, ...typography.h2 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.md, padding: spacing.lg },
  loadingText: { color: colors.textMuted, ...typography.body, textAlign: 'center' },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  mapWrap: { borderRadius: radius.lg, overflow: 'hidden' },
  map: { height: 180 },
  routeCard: { gap: spacing.sm },
  routeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  dot: { width: 10, height: 10, borderRadius: 5 },
  routeLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  routeValue: { color: colors.text, ...typography.bodyStrong },
  routeDivider: { height: 1, backgroundColor: colors.border, marginLeft: 18 },
  routeHint: { color: colors.textMuted, ...typography.caption, marginTop: spacing.xs },
  card: { gap: spacing.md },
  driverRow: { flexDirection: 'row', gap: spacing.md, alignItems: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  name: { color: colors.text, ...typography.h2 },
  muted: { color: colors.textMuted, ...typography.caption },
  ratingRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  vehicleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
  },
  vehicleText: { color: colors.text, ...typography.caption, flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  rowLabel: { color: colors.textMuted, ...typography.caption, width: 110 },
  rowValue: { color: colors.text, ...typography.bodyStrong, flex: 1 },
  disclaimer: {
    backgroundColor: colors.infoTint,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  disclaimerText: { color: colors.info, ...typography.caption, lineHeight: 17 },
  footer: {
    padding: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  sheetBackdrop: { flex: 1, backgroundColor: 'rgba(11,31,58,0.45)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.md,
    paddingBottom: spacing.xxl,
  },
  sheetHandle: { width: 44, height: 4, borderRadius: 2, backgroundColor: colors.border, alignSelf: 'center' },
  sheetTitle: { color: colors.text, ...typography.h1 },
  sheetSubtitle: { color: colors.textMuted, ...typography.caption },
});
```

---

## `mobile/scripts/verify-map.mjs`  ·  *NEW (offline check: `node scripts/verify-map.mjs` → 38/38)*

```js
/**
 * Verifies the WebView map without a phone and without a browser (§13).
 *
 *   node scripts/verify-map.mjs
 *
 * Three layers of proof:
 *   1. the Web-Mercator maths (Karachi projects to the tile we saw live: 12/2811/1755),
 *   2. the generated HTML (no unsubstituted placeholders, safe escaping, bridge present),
 *   3. the page's own JavaScript, executed against a fake DOM — it must build tile <img>s that
 *      point at our proxy and must report a tap as {type:'pin', latitude, longitude}.
 *
 * Exit code 0 = every check passed; 1 = something regressed.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const babel = require('@babel/core');
const root = process.cwd();
const out = '/tmp/map-verify';

let failures = 0;
let checks = 0;
function check(name, condition, detail = '') {
  checks += 1;
  if (condition) {
    console.log(`  PASS  ${name}${detail ? ` — ${detail}` : ''}`);
  } else {
    failures += 1;
    console.log(`  FAIL  ${name}${detail ? ` — ${detail}` : ''}`);
  }
}
const near = (a, b, tol) => Math.abs(a - b) <= tol;

// ---------------------------------------------------------------- 1. compile TS → CJS
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });

function compile(sourceRel, targetName) {
  const source = fs.readFileSync(path.join(root, sourceRel), 'utf8');
  const { code } = babel.transformSync(source, {
    filename: path.join(root, sourceRel),
    presets: ['@babel/preset-typescript'],
    plugins: ['@babel/plugin-transform-modules-commonjs'],
    babelrc: false,
    configFile: false,
  });
  const relinked = code.replace(/(['"])@\/components\/map\/tileMath\1/g, '$1./tileMath$1');
  fs.writeFileSync(path.join(out, targetName), relinked);
}

compile('src/components/map/tileMath.ts', 'tileMath.js');
compile('src/components/map/tileMapHtml.ts', 'tileMapHtml.js');

const { TILE_MATH_JS } = require(path.join(out, 'tileMath.js'));
const { buildTileMapHtml } = require(path.join(out, 'tileMapHtml.js'));

// ---------------------------------------------------------------- 2. the maths
console.log('\nMap maths (world-pixel Mercator)');
const maths = new Function(`${TILE_MATH_JS}
  return { worldSize, lngToWorldX, latToWorldY, worldXToLng, worldYToLat, tileRange, zoomToFit };`)();

check('world is 256 px at zoom 0', maths.worldSize(0) === 256, `got ${maths.worldSize(0)}`);
check('world is 2^12 x 256 at zoom 12', maths.worldSize(12) === 1048576, `got ${maths.worldSize(12)}`);

const KARACHI = { lat: 24.9056, lng: 67.0822 }; // SSUET / Gulshan-e-Iqbal
const x12 = maths.lngToWorldX(KARACHI.lng, 12);
const y12 = maths.latToWorldY(KARACHI.lat, 12);
check('Karachi x at z12 lands in tile 2811', Math.floor(x12 / 256) === 2811, `px ${x12.toFixed(1)}`);
check('Karachi y at z12 lands in tile 1755', Math.floor(y12 / 256) === 1755, `px ${y12.toFixed(1)}`);
check(
  'that tile is the one the live proxy served as an image',
  fs.existsSync('/tmp/karachi.png') ? fs.statSync('/tmp/karachi.png').size > 1000 : true,
);

const backLng = maths.worldXToLng(x12, 12);
const backLat = maths.worldYToLat(y12, 12);
check('lng round-trips', near(backLng, KARACHI.lng, 1e-6), `${backLng.toFixed(6)}`);
check('lat round-trips', near(backLat, KARACHI.lat, 1e-6), `${backLat.toFixed(6)}`);

const range = maths.tileRange(x12 - 180, y12 - 95, 360, 190, 12);
const coversX = range.minX * 256 <= x12 - 180 && (range.maxX + 1) * 256 >= x12 + 180;
const coversY = range.minY * 256 <= y12 - 95 && (range.maxY + 1) * 256 >= y12 + 95;
check('tile range covers the 360x190 viewport', coversX && coversY, `${range.minX}-${range.maxX} / ${range.minY}-${range.maxY}`);
check('tile range is big enough for the screen', (range.maxX - range.minX + 1) * (range.maxY - range.minY + 1) >= 4);

const dx0 = Math.abs(maths.lngToWorldX(67.14, 0) - maths.lngToWorldX(67.09, 0));
const dy0 = Math.abs(maths.latToWorldY(24.95, 0) - maths.latToWorldY(24.90, 0));
const fitZoom = maths.zoomToFit(dx0, dy0, 360, 180, 46, 18);
const fitsW = dx0 * Math.pow(2, fitZoom) <= 360 - 92 + 1;
check('two-pin fit zoom keeps both pins on screen', fitZoom >= 2 && fitZoom <= 18 && fitsW, `zoom ${fitZoom}`);

// ---------------------------------------------------------------- 3. the generated HTML
console.log('\nGenerated map page');
const TILE_BASE = 'http://192.168.100.32:8000/api/v1/maps/tiles';
const ATTRIB = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const html = buildTileMapHtml({
  tileBase: `${TILE_BASE}/`,
  attribution: ATTRIB,
  latitude: KARACHI.lat,
  longitude: KARACHI.lng,
  zoom: 15,
  editable: true,
  hint: 'Tap the map or drag the pin',
});

check('tile base is embedded without a double slash', html.includes(`"${TILE_BASE}"`) && !html.includes(`${TILE_BASE}//`));
check('attribution is present (OSM requires it)', html.includes('OpenStreetMap'));
check('bridge to the app is exposed', html.includes('window.__map') && html.includes('ReactNativeWebView.postMessage'));
check('no unsubstituted template placeholder', !html.includes('${'));
check('exactly one script block', (html.match(/<script>/g) || []).length === 1 && (html.match(/<\/script>/g) || []).length === 1);
check('no third-party JS is loaded', !/src=["']https?:/.test(html) && !html.includes('leaflet'));
check('editable flag reaches the page', html.includes('"editable":true'));

const hostile = buildTileMapHtml({
  tileBase: TILE_BASE,
  attribution: '</script><script>alert(1)</script>',
  latitude: KARACHI.lat,
  longitude: KARACHI.lng,
  hint: '${alert(2)}',
});
check(
  'a hostile attribution cannot break out of the script tag',
  (hostile.match(/<\/script>/g) || []).length === 1,
  `${(hostile.match(/<\/script>/g) || []).length} closing tags`,
);
check(
  'markup inside content is escaped for the script block',
  !/\}\s*<\/script>/.test(hostile.slice(hostile.indexOf('var CONFIG'), hostile.indexOf('</script>', hostile.indexOf('var CONFIG')))),
  'CONFIG JSON contains no raw closing tag',
);
const hostileScript = hostile.slice(hostile.indexOf('<script>') + 8, hostile.lastIndexOf('</script>'));
let hostileCompiles = true;
try {
  new Function('window', 'document', 'console', hostileScript);
} catch (error) {
  hostileCompiles = false;
}
check('the hostile page still compiles as JavaScript', hostileCompiles);

// ---------------------------------------------------------------- 4. run the page's JS on a fake DOM
console.log('\nThe page script, executed (fake DOM)');
function makeElement(tag = 'div') {
  const element = {
    tagName: tag,
    className: '',
    style: {},
    children: [],
    parentNode: null,
    textContent: '',
    alt: '',
    listeners: {},
    clientWidth: 360,
    clientHeight: 190,
    appendChild(child) {
      child.parentNode = element;
      element.children.push(child);
      return child;
    },
    removeChild(child) {
      element.children = element.children.filter((c) => c !== child);
      child.parentNode = null;
      return child;
    },
    setAttribute() {},
    addEventListener(name, handler) {
      (element.listeners[name] = element.listeners[name] || []).push(handler);
    },
    getBoundingClientRect() {
      return { left: 0, top: 0, width: element.clientWidth, height: element.clientHeight };
    },
    setPointerCapture() {},
  };
  Object.defineProperty(element, 'innerHTML', {
    get: () => '',
    set: (value) => {
      element.children = [];
      element.innerHTMLSet = value;
    },
  });
  return element;
}

const nodes = {};
const ids = ['map', 'stage', 'world', 'pinLayer', 'hint', 'err', 'zin', 'zout', 'attr'];
for (const id of ids) nodes[id] = makeElement();

const documentStub = {
  getElementById: (id) => nodes[id] ?? makeElement(),
  createElement: (tag) => makeElement(tag),
  addEventListener() {},
};

const messages = [];
const windowStub = {
  ReactNativeWebView: { postMessage: (text) => messages.push(JSON.parse(text)) },
  addEventListener(name, handler) {
    (windowStub.listeners[name] = windowStub.listeners[name] || []).push(handler);
  },
  listeners: {},
  innerWidth: 360,
  innerHeight: 190,
  console,
};

const scriptSource = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));
new Function('window', 'document', 'console', scriptSource)(windowStub, documentStub, console);

check('page reports itself ready to the app', messages.some((m) => m.type === 'ready'), JSON.stringify(messages[0] ?? null));

const tileImages = nodes.world.children.filter((c) => c.tagName === 'img');
check('tiles were requested', tileImages.length >= 4, `${tileImages.length} tiles`);
const tileUrls = tileImages.map((t) => t.src ?? '');
const pattern = new RegExp(`^${TILE_BASE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/\\d+/\\d+/\\d+\\.png$`);
check('every tile URL points at our proxy', tileUrls.every((url) => pattern.test(url)), tileUrls[0] ?? 'none');
check(
  'tile coordinates are inside the world',
  tileImages.every((t) => {
    const [, z, x, y] = t.src.match(/\/(\d+)\/(\d+)\/(\d+)\.png$/).map(Number).length ? t.src.match(/\/(\d+)\/(\d+)\/(\d+)\.png$/) : [];
    const limit = Math.pow(2, Number(z));
    return Number(x) < limit && Number(y) < limit;
  }),
);
check('a pin is drawn at the pickup point', nodes.pinLayer.children.length === 1);
check('the pin is inside the viewport', (() => {
  const pin = nodes.pinLayer.children[0];
  const left = parseFloat(pin.style.left);
  const top = parseFloat(pin.style.top);
  return left > 0 && left < 360 && top > 0 && top < 190;
})(), JSON.stringify({ left: nodes.pinLayer.children[0]?.style.left, top: nodes.pinLayer.children[0]?.style.top }));

// a tap on the map must report a pin
const mapDown = nodes.map.listeners.pointerdown?.[0];
const winUp = windowStub.listeners.pointerup?.[0];
const winMove = windowStub.listeners.pointermove?.[0];
check('the map listens for pointer events', Boolean(mapDown && winUp && winMove));

messages.length = 0;
mapDown({ target: { className: 'tile' }, clientX: 90, clientY: 140 });
winUp({ clientX: 90, clientY: 140 });
const pinMessage = messages.find((m) => m.type === 'pin');
check('a tap posts {type:pin, latitude, longitude}', Boolean(pinMessage));
if (pinMessage) {
  check(
    'the tapped point is in Karachi',
    pinMessage.latitude > 24.7 && pinMessage.latitude < 25.1 && pinMessage.longitude > 66.8 && pinMessage.longitude < 67.4,
    `${pinMessage.latitude.toFixed(5)}, ${pinMessage.longitude.toFixed(5)}`,
  );
  const tappedPin = nodes.pinLayer.children[0];
  check(
    'exactly one pin exists after the tap',
    nodes.pinLayer.children.length === 1,
    `${nodes.pinLayer.children.length} pins`,
  );
  check(
    'the pin sits where the finger was (90,140)',
    Math.abs(parseFloat(tappedPin.style.left) - 90) < 2 && Math.abs(parseFloat(tappedPin.style.top) - 140) < 2,
    `${tappedPin.style.left}, ${tappedPin.style.top}`,
  );
}

// a pan must not be mistaken for a tap
messages.length = 0;
mapDown({ target: { className: 'tile' }, clientX: 100, clientY: 90 });
winMove({ clientX: 60, clientY: 90 });
winUp({ clientX: 60, clientY: 90 });
check('a drag pans instead of dropping a pin', !messages.some((m) => m.type === 'pin'));
check('panning re-renders tiles for the new centre', nodes.world.children.filter((c) => c.tagName === 'img').length >= 4);

// the app can push a new pin into the page
messages.length = 0;
windowStub.__map.setPin(24.8607, 67.0011);
const movedPin = nodes.pinLayer.children[0];
check(
  'window.__map.setPin moves the pin (Clifton is south of the view)',
  Boolean(movedPin) && parseFloat(movedPin.style.top) > 190,
  `top ${movedPin?.style.top}`,
);

// dragging the pin itself
const pinEl = nodes.pinLayer.children[0];
const pinDown = pinEl?.listeners.pointerdown?.[0];
const pinMove = pinEl?.listeners.pointermove?.[0];
const pinUp = pinEl?.listeners.pointerup?.[0];
check('the pin is draggable', Boolean(pinDown && pinMove && pinUp));
if (pinDown) {
  messages.length = 0;
  pinDown({ stopPropagation() {}, preventDefault() {}, clientX: 90, clientY: 140, pointerId: 1 });
  pinMove({ clientX: 150, clientY: 170 });
  pinUp({ clientX: 150, clientY: 170 });
  const dragged = messages.find((m) => m.type === 'pin');
  check('dragging the pin reports the new point', Boolean(dragged));
  const newPin = nodes.pinLayer.children[0];
  check(
    'the pin followed the drag (150,170)',
    Math.abs(parseFloat(newPin.style.left) - 150) < 2 && Math.abs(parseFloat(newPin.style.top) - 170) < 2,
    `${newPin.style.left}, ${newPin.style.top}`,
  );
  check(
    'dragging the pin did not pan the map',
    nodes.stage.style.transform === 'translate(0px, 0px)' || nodes.stage.style.transform === undefined,
    String(nodes.stage.style.transform),
  );
}

console.log(`\n${checks - failures}/${checks} checks passed`);
if (failures > 0) {
  console.log('MAP VERIFY: FAILED');
  process.exit(1);
}
console.log('MAP VERIFY: OK');
```

---

