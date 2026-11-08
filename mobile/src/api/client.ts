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
