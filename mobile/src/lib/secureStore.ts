import * as SecureStore from 'expo-secure-store';

/**
 * Tokens live in the platform keystore (Android Keystore / iOS Keychain), never
 * in AsyncStorage and never in plain files (§22).
 */
const ACCESS_KEY = 'ssuet.access_token';
const REFRESH_KEY = 'ssuet.refresh_token';

export type TokenBundle = { accessToken: string | null; refreshToken: string | null };

export async function saveTokens(accessToken: string, refreshToken: string): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_KEY, accessToken),
    SecureStore.setItemAsync(REFRESH_KEY, refreshToken),
  ]);
}

export async function loadTokens(): Promise<TokenBundle> {
  const [accessToken, refreshToken] = await Promise.all([
    SecureStore.getItemAsync(ACCESS_KEY),
    SecureStore.getItemAsync(REFRESH_KEY),
  ]);
  return { accessToken, refreshToken };
}

export async function clearTokens(): Promise<void> {
  await Promise.all([SecureStore.deleteItemAsync(ACCESS_KEY), SecureStore.deleteItemAsync(REFRESH_KEY)]);
}
