import { goBackOr } from '@/lib/navigation';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type AppNotification,
} from '@/api/notifications';
import { ApiError } from '@/api/client';
import { Badge, Button, Card, EmptyState } from '@/components/ui';
import { relativeDay } from '@/lib/format';
import { colors, radius, spacing, typography } from '@/theme';

const ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  RIDE_REQUEST_RECEIVED: 'mail-unread-outline',
  RIDE_REQUEST_ACCEPTED: 'checkmark-circle-outline',
  RIDE_REQUEST_REJECTED: 'close-circle-outline',
  RIDE_CANCELLED: 'car-outline',
  TRIP_STARTED: 'navigate-outline',
  TRIP_CANCELLED: 'alert-circle-outline',
  TRIP_NO_SHOW: 'person-remove-outline',
  TRIP_COMPLETED: 'ribbon-outline',
  TRIP_AWAITING_CONFIRMATION: 'help-circle-outline',
  NEW_MESSAGE: 'chatbubble-ellipses-outline',
  ACCOUNT_VERIFIED: 'shield-checkmark-outline',
  VEHICLE_VERIFIED: 'car-sport-outline',
  VEHICLE_REJECTED: 'warning-outline',
  SYSTEM: 'information-circle-outline',
};

export default function NotificationsScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [items, setItems] = useState<AppNotification[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const query = useQuery({ queryKey: ['notifications', 'first'], queryFn: () => listNotifications() });

  useEffect(() => {
    if (query.data) {
      setItems(query.data.items);
      setCursor(query.data.next_cursor);
    }
  }, [query.data]);

  const refresh = useCallback(async () => {
    await query.refetch();
    await queryClient.invalidateQueries({ queryKey: ['notifications', 'unread'] });
  }, [query, queryClient]);

  const open = async (notification: AppNotification) => {
    if (!notification.is_read) {
      setItems((previous) =>
        previous.map((item) => (item.id === notification.id ? { ...item, is_read: true } : item)),
      );
      void markNotificationRead(notification.id).catch(() => undefined);
      void queryClient.invalidateQueries({ queryKey: ['notifications', 'unread'] });
    }

    const target = notification.data ?? {};
    if (target.screen === 'chat' && target.conversation_id) {
      router.push(`/chat/${target.conversation_id}`);
    } else if (target.screen === 'trip' && target.trip_id) {
      router.push(`/trip/${target.trip_id}`);
    } else if (notification.type.startsWith('RIDE_REQUEST')) {
      router.push('/(tabs)/my-rides');
    } else {
      router.push('/(tabs)/explore');
    }
  };

  const loadMore = async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await listNotifications(cursor);
      setItems((previous) => [...previous, ...page.items]);
      setCursor(page.next_cursor);
    } catch {
      // ignore; the user can pull to refresh
    } finally {
      setLoadingMore(false);
    }
  };

  const unread = items.filter((item) => !item.is_read).length;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => goBackOr(router)} style={styles.back}>
          <Ionicons name="arrow-back" size={20} color={colors.navy} />
        </Pressable>
        <Text style={styles.title}>Notifications</Text>
        <Pressable
          onPress={async () => {
            await markAllNotificationsRead().catch(() => undefined);
            setItems((previous) => previous.map((item) => ({ ...item, is_read: true })));
            void queryClient.invalidateQueries({ queryKey: ['notifications', 'unread'] });
          }}
          disabled={unread === 0}
          style={styles.markAll}
        >
          <Text style={[styles.markAllText, unread === 0 && styles.markAllDisabled]}>Mark all</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={query.isFetching} onRefresh={refresh} tintColor={colors.green} />}
        onScrollEndDrag={({ nativeEvent }) => {
          const { contentOffset, contentSize, layoutMeasurement } = nativeEvent;
          if (contentOffset.y + layoutMeasurement.height > contentSize.height - 80) void loadMore();
        }}
      >
        {query.isLoading ? (
          <View style={styles.centre}>
            <ActivityIndicator color={colors.green} />
          </View>
        ) : query.isError ? (
          <Card>
            <EmptyState
              icon="cloud-offline-outline"
              title="Couldn't load notifications"
              message={query.error instanceof ApiError ? query.error.message : 'Check your connection.'}
              action={<Button label="Retry" onPress={() => void refresh()} />}
            />
          </Card>
        ) : items.length === 0 ? (
          <Card>
            <EmptyState
              icon="notifications-off-outline"
              title="Nothing yet"
              message="Requests, accepted seats, trip updates and messages will appear here."
            />
          </Card>
        ) : (
          items.map((item) => (
            <Pressable
              key={item.id}
              onPress={() => void open(item)}
              style={({ pressed }) => [styles.row, !item.is_read && styles.rowUnread, pressed && styles.pressed]}
            >
              <View style={[styles.iconWrap, !item.is_read && styles.iconWrapUnread]}>
                <Ionicons
                  name={ICONS[item.type] ?? 'information-circle-outline'}
                  size={18}
                  color={!item.is_read ? colors.greenDark : colors.textMuted}
                />
              </View>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={styles.rowTitle}>{item.title}</Text>
                <Text style={styles.rowBody}>{item.body}</Text>
                <Text style={styles.rowMeta}>{relativeDay(item.created_at)}</Text>
              </View>
              {!item.is_read ? <View style={styles.dot} /> : null}
            </Pressable>
          ))
        )}
        {loadingMore ? <ActivityIndicator color={colors.green} style={{ marginVertical: spacing.md }} /> : null}
        {items.length > 0 ? (
          <View style={styles.footerNote}>
            <Badge label={`${unread} unread`} tone={unread ? 'info' : 'neutral'} icon="mail-outline" />
            <Text style={styles.rowMeta}>
              Push delivery uses your registered device; the in-app list always works.
            </Text>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
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
  title: { color: colors.text, ...typography.h2, flex: 1 },
  markAll: { paddingHorizontal: spacing.sm, paddingVertical: 4 },
  markAllText: { color: colors.navy, ...typography.caption, fontWeight: '700' },
  markAllDisabled: { color: colors.textMuted },
  content: { padding: spacing.lg, gap: spacing.sm, paddingBottom: spacing.xxl },
  centre: { paddingVertical: spacing.xxl, alignItems: 'center' },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  rowUnread: { borderColor: colors.green, backgroundColor: colors.greenTint },
  pressed: { opacity: 0.85 },
  iconWrap: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.surfaceAlt,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconWrapUnread: { backgroundColor: colors.surface },
  rowTitle: { color: colors.text, ...typography.bodyStrong },
  rowBody: { color: colors.textMuted, ...typography.caption, lineHeight: 17 },
  rowMeta: { color: colors.textMuted, fontSize: 10 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.green, marginTop: 6 },
  footerNote: { alignItems: 'center', gap: spacing.xs, paddingTop: spacing.lg },
});
