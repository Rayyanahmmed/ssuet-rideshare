import { goBackOr } from '@/lib/navigation';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { listConversations, type Conversation } from '@/api/chat';
import { ApiError } from '@/api/client';
import { Avatar, Badge, Button, Card, EmptyState } from '@/components/ui';
import { relativeDay } from '@/lib/format';
import { colors, radius, spacing, typography } from '@/theme';

/** Every trip I share with someone — the entry point to private chat (§11). */
export default function ChatsScreen() {
  const router = useRouter();
  const query = useQuery({
    queryKey: ['conversations'],
    queryFn: listConversations,
    refetchInterval: 30_000,
  });

  const conversations: Conversation[] = query.data?.items ?? [];
  const unreadTotal = query.data?.unread_total ?? 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => goBackOr(router)} style={styles.back}>
          <Ionicons name="arrow-back" size={20} color={colors.navy} />
        </Pressable>
        <Text style={styles.title}>Messages</Text>
        {unreadTotal > 0 ? <Badge label={`${unreadTotal} new`} tone="info" icon="mail-unread-outline" /> : null}
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={query.isFetching} onRefresh={() => void query.refetch()} tintColor={colors.green} />
        }
      >
        {query.isLoading ? (
          <Text style={styles.muted}>Loading conversations…</Text>
        ) : query.isError ? (
          <Card>
            <EmptyState
              icon="cloud-offline-outline"
              title="Couldn't load messages"
              message={query.error instanceof ApiError ? query.error.message : 'Check your connection.'}
              action={<Button label="Retry" onPress={() => void query.refetch()} />}
            />
          </Card>
        ) : conversations.length === 0 ? (
          <Card>
            <EmptyState
              icon="chatbubbles-outline"
              title="No conversations yet"
              message="When a driver accepts your request — or you accept a passenger — a private chat opens here automatically."
              action={<Button label="Explore rides" onPress={() => router.push('/(tabs)/explore')} />}
            />
          </Card>
        ) : (
          conversations.map((conversation) => (
            <Pressable
              key={conversation.id}
              onPress={() => router.push(`/chat/${conversation.id}`)}
              style={({ pressed }) => [
                styles.row,
                conversation.unread_count > 0 && styles.rowUnread,
                pressed && styles.pressed,
              ]}
            >
              <Avatar
                name={conversation.counterpart.full_name}
                size={44}
                photoUrl={conversation.counterpart.profile_photo_url}
              />
              <View style={{ flex: 1, gap: 2 }}>
                <View style={styles.nameRow}>
                  <Text style={styles.name} numberOfLines={1}>
                    {conversation.counterpart.full_name}
                  </Text>
                  {conversation.last_message_at ? (
                    <Text style={styles.time}>{relativeDay(conversation.last_message_at)}</Text>
                  ) : null}
                </View>
                <Text style={styles.preview} numberOfLines={1}>
                  {conversation.last_message_preview
                    ? `${conversation.last_message_is_mine ? 'You: ' : ''}${conversation.last_message_preview}`
                    : 'Trip chat opened — agree on your meeting point.'}
                </Text>
                <Text style={styles.route} numberOfLines={1}>
                  {conversation.pickup_area} → {conversation.destination_area}
                </Text>
              </View>
              {conversation.unread_count > 0 ? (
                <View style={styles.unread}>
                  <Text style={styles.unreadText}>{conversation.unread_count}</Text>
                </View>
              ) : conversation.counterpart.is_online ? (
                <View style={styles.online} />
              ) : null}
            </Pressable>
          ))
        )}
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
  content: { padding: spacing.lg, gap: spacing.sm, paddingBottom: spacing.xxl },
  muted: { color: colors.textMuted, ...typography.caption },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.md,
  },
  rowUnread: { borderColor: colors.green, backgroundColor: colors.greenTint },
  pressed: { opacity: 0.85 },
  nameRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  name: { color: colors.text, ...typography.bodyStrong, flex: 1 },
  time: { color: colors.textMuted, fontSize: 10 },
  preview: { color: colors.textMuted, ...typography.caption },
  route: { color: colors.textMuted, fontSize: 10 },
  unread: {
    minWidth: 20,
    height: 20,
    borderRadius: 10,
    paddingHorizontal: 5,
    backgroundColor: colors.green,
    alignItems: 'center',
    justifyContent: 'center',
  },
  unreadText: { color: colors.textInverse, fontSize: 10, fontWeight: '700' },
  online: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.green },
});
