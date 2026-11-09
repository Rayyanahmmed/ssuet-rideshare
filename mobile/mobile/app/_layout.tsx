import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import { Stack, useRouter, useSegments } from 'expo-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { colors } from '@/theme';
import { NotificationToaster } from '@/components/NotificationToaster';
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

/**
 * Signed-out users may only be on the launch screen or inside (auth). Any other route,
 * including one opened from a deep link or a notification, goes to Welcome. Protected
 * screens would otherwise render and fire 401 requests.
 */
function AuthGuard() {
  const status = useAuthStore((state) => state.status);
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (status !== 'signedOut') return; // 'loading' waits for the keystore check
    const first = segments[0] as string | undefined;
    const onLaunchOrAuth = !first || first === 'index' || first === '(auth)';
    if (!onLaunchOrAuth) router.replace('/(auth)/welcome');
  }, [status, segments, router]);

  return null;
}

/**
 * Web only: mobile browsers make `100vh` taller than the visible screen, which pushed the
 * bottom tab labels below the fold. `100dvh` follows the real visible height.
 */
function useWebFullHeight() {
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    const style = document.createElement('style');
    style.id = 'ssuet-full-height';
    style.textContent =
      'html, body { height: 100%; overflow: hidden; } ' +
      '#root { position: fixed; top: 0; left: 0; right: 0; bottom: 0; height: 100dvh !important; }';
    document.head.appendChild(style);
    return () => style.remove();
  }, []);
}

export default function RootLayout() {
  useWebFullHeight();
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
        <AuthGuard />
        <NotificationToaster />
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
