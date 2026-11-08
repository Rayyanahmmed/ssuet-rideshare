import { Platform } from 'react-native';
import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import { registerDeviceToken, unregisterDeviceToken } from '@/api/notifications';

/**
 * Expo push registration (§12).
 *
 * The backend never asks for permission and never holds a raw token for longer
 * than it is valid: the app registers on sign-in and unregisters on sign-out, and
 * the server deactivates tokens Expo reports as `DeviceNotRegistered`.
 *
 * Everything here degrades silently — a member who declines notifications simply
 * keeps the in-app bell, which always works.
 */

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: true,
  }),
});

export type PushRegistration = { token: string | null; reason?: string };

export async function registerForPush(): Promise<PushRegistration> {
  if (Platform.OS === 'web') return { token: null, reason: 'Push is not available on web.' };

  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== 'granted') {
    const requested = await Notifications.requestPermissionsAsync();
    status = requested.status;
  }
  if (status !== 'granted') return { token: null, reason: 'Notification permission was not granted.' };

  const projectId =
    (Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined)?.eas?.projectId ??
    Constants.easConfig?.projectId;

  if (!projectId) {
    // Without an EAS project id Expo cannot mint a token; in-app notifications
    // still work, so this is a warning rather than an error.
    return { token: null, reason: 'EAS project id is not configured.' };
  }

  try {
    const { data } = await Notifications.getExpoPushTokenAsync({ projectId });
    await registerDeviceToken(data, Platform.OS === 'ios' ? 'ios' : 'android');
    return { token: data };
  } catch (error) {
    return { token: null, reason: error instanceof Error ? error.message : 'Push registration failed.' };
  }
}

export async function unregisterPush(token: string | null): Promise<void> {
  if (!token) return;
  try {
    await unregisterDeviceToken(token);
  } catch {
    // best effort: the backend also deactivates tokens Expo rejects
  }
}
