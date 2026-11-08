import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { useAdminAuth } from '@/store/auth';

/**
 * Admin API client.
 *
 * `VITE_API_BASE_URL` is empty by default: the Vite dev server proxies /api to
 * the FastAPI backend, so the browser only ever talks to one origin. In
 * production point it at the API domain (HTTPS only).
 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: { Accept: 'application/json' },
});

export type ApiErrorPayload = {
  error?: { code?: string; message?: string; details?: Record<string, string> };
};

export function describeError(error: unknown): string {
  const payload = (error as { response?: { data?: ApiErrorPayload } })?.response?.data?.error;
  if (payload?.message) return payload.message;
  if ((error as AxiosError)?.response) return 'The request was rejected by the API.';
  return 'Cannot reach the server. Check your internet connection and try again.';
}

export function errorCode(error: unknown): string | undefined {
  return (error as { response?: { data?: ApiErrorPayload } })?.response?.data?.error?.code;
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAdminAuth.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshInFlight: Promise<string | null> | null = null;

async function refresh(): Promise<string | null> {
  const { refreshToken } = useAdminAuth.getState();
  if (!refreshToken) return null;
  try {
    const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, { refresh_token: refreshToken });
    useAdminAuth.getState().setSession(data.user, data.access_token, data.refresh_token);
    return data.access_token as string;
  } catch {
    useAdminAuth.getState().signOut();
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    if (error.response?.status === 401 && original && !original._retried) {
      original._retried = true;
      refreshInFlight = refreshInFlight ?? refresh();
      const token = await refreshInFlight;
      refreshInFlight = null;
      if (token) {
        original.headers.Authorization = `Bearer ${token}`;
        return api.request(original);
      }
    }
    return Promise.reject(error);
  },
);
