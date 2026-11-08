/**
 * Browser build: expo-secure-store has no browser implementation, so tokens use localStorage.
 * This is the same trade-off every web app makes: keep the session out of the bundle and out
 * of URLs, and clear it on sign-out. The native build keeps using the platform keystore.
 */
const ACCESS_KEY = 'ssuet.access_token';
const REFRESH_KEY = 'ssuet.refresh_token';

export type TokenBundle = { accessToken: string | null; refreshToken: string | null };

function storage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null; // private mode / storage disabled
  }
}

export async function saveTokens(accessToken: string, refreshToken: string): Promise<void> {
  storage()?.setItem(ACCESS_KEY, accessToken);
  storage()?.setItem(REFRESH_KEY, refreshToken);
}

export async function loadTokens(): Promise<TokenBundle> {
  return {
    accessToken: storage()?.getItem(ACCESS_KEY) ?? null,
    refreshToken: storage()?.getItem(REFRESH_KEY) ?? null,
  };
}

export async function clearTokens(): Promise<void> {
  storage()?.removeItem(ACCESS_KEY);
  storage()?.removeItem(REFRESH_KEY);
}
