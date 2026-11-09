import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter, usePathname } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import {
  listNotifications,
  markNotificationRead,
  type AppNotification,
} from '@/api/notifications';
import { useAuthStore } from '@/store/auth';
import { colors, radius, spacing, typography } from '@/theme';

/** How often the app checks for new notifications while it is open (web and APK). */
const POLL_MS = 15000;
/** How long the banner stays on screen before it hides itself. */
const SHOW_MS = 6000;

/**
 * In-app notification pop-up. Browsers cannot receive Expo push, and the APK only shows
 * push when the app is closed, so while the app is open we poll the notification feed and
 * show the newest unseen item as a banner. Tapping it opens the matching screen.
 *
 * The first load of a session only records what already exists, so old notifications never
 * pop up when the app opens.
 */
export function NotificationToaster() {
  const status = useAuthStore((state) => state.status);
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const insets = useSafeAreaInsets();
  const seen = useRef<Set<string> | null>(null);
  const [toast, setToast] = useState<AppNotification | null>(null);

  const feed = useQuery({
    queryKey: ['notifications', 'toaster'],
    queryFn: () => listNotifications(undefined, 10),
    enabled: status === 'signedIn',
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    staleTime: 0,
  });

  // Signed out: forget what was seen so the next sign-in starts clean.
  useEffect(() => {
    if (status !== 'signedIn') {
      seen.current = null;
      setToast(null);
    }
  }, [status]);

  useEffect(() => {
    const items = feed.data?.items;
    if (!items) return;
    if (seen.current === null) {
      seen.current = new Set(items.map((item) => item.id));
      return;
    }
    const known = seen.current;
    const fresh = items
      .filter((item) => !item.is_read && !known.has(item.id))
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
    items.forEach((item) => known.add(item.id));
    if (fresh.length === 0) return;

    // Skip the banner when the member is already reading that very conversation.
    const newest = fresh[0];
    if (!newest) return;
    const conversationId = newest.data?.conversation_id;
    if (conversationId && pathname.includes(conversationId)) return;

    setToast(newest);
    void queryClient.invalidateQueries({ queryKey: ['notifications'], exact: false });
  }, [feed.data, pathname, queryClient]);

  // Auto-hide after a few seconds.
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), SHOW_MS);
    return () => clearTimeout(timer);
  }, [toast]);

  if (!toast) return null;

  const open = () => {
    const current = toast;
    setToast(null);
    void markNotificationRead(current.id).catch(() => undefined);
    void queryClient.invalidateQueries({ queryKey: ['notifications'], exact: false });
    const target = current.data;
    if (target?.screen === 'chat' && target.conversation_id) {
      router.push(`/chat/${target.conversation_id}`);
    } else if (target?.screen === 'trip' && target.trip_id) {
      router.push(`/trip/${target.trip_id}`);
    } else {
      router.push('/notifications');
    }
  };

  return (
    <View pointerEvents="box-none" style={[styles.wrap, { top: insets.top + spacing.sm }]}>
      <Pressable
        accessibilityRole="alert"
        accessibilityLabel={`New notification: ${toast.title}`}
        onPress={open}
        style={styles.card}
      >
        <View style={styles.iconWrap}>
          <Ionicons name="notifications" size={18} color={colors.textInverse} />
        </View>
        <View style={styles.textWrap}>
          <Text style={styles.title} numberOfLines={1}>
            {toast.title}
          </Text>
          <Text style={styles.body} numberOfLines={2}>
            {toast.body}
          </Text>
        </View>
        <Pressable
          onPress={() => setToast(null)}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel="Dismiss notification"
        >
          <Ionicons name="close" size={18} color={colors.textMuted} />
        </Pressable>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: spacing.lg,
    right: spacing.lg,
    zIndex: 1000,
    elevation: 10,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: '#000',
    shadowOpacity: 0.15,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
  },
  iconWrap: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.green,
  },
  textWrap: { flex: 1, gap: 2 },
  title: { color: colors.text, ...typography.caption, fontWeight: '700' },
  body: { color: colors.textMuted, ...typography.caption },
});
