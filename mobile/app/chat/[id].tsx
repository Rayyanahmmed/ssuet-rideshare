import { goBackOr } from '@/lib/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import * as Location from 'expo-location';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  chatSocketUrl,
  getConversation,
  listMessages,
  markConversationRead,
  sendMessage,
  type Message,
  type SocketFrame,
} from '@/api/chat';
import { ApiError } from '@/api/client';
import { Avatar, Banner } from '@/components/ui';
import { formatTime, relativeDay } from '@/lib/format';
import { colors, radius, spacing, typography } from '@/theme';

type ConnectionState = 'connecting' | 'live' | 'fallback' | 'denied';

/** How long a "typing…" hint stays on screen after the last keystroke frame. */
const TYPING_TIMEOUT_MS = 4000;

/** Google Maps link inside a shared-location message (independent of the in-app map key). */
function extractMapLink(body: string): string | null {
  const match = body.match(/https:\/\/maps\.google\.com\/\?q=-?\d+\.\d+,-?\d+\.\d+/);
  return match ? match[0] : null;
}

export default function ChatScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [messages, setMessages] = useState<Message[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [myId, setMyId] = useState<string | null>(null);
  const [counterpartOnline, setCounterpartOnline] = useState(false);
  const [counterpartTyping, setCounterpartTyping] = useState(false);
  const [sharing, setSharing] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempt = useRef(0);

  const conversationQuery = useQuery({
    queryKey: ['conversation', id],
    queryFn: () => getConversation(id),
    enabled: Boolean(id),
  });
  const counterpart = conversationQuery.data?.counterpart;

  const mergeMessage = useCallback((incoming: Message) => {
    setMessages((previous) => {
      const withoutOptimistic = previous.filter(
        (item) =>
          !(
            item.id.startsWith('local-') &&
            item.body === incoming.body &&
            item.sender_id === incoming.sender_id
          ),
      );
      if (withoutOptimistic.some((item) => item.id === incoming.id)) return withoutOptimistic;
      return [...withoutOptimistic, incoming].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      );
    });
  }, []);

  const pushReadReceipt = useCallback(() => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'read' }));
    } else {
      void markConversationRead(id).catch(() => undefined);
    }
    void queryClient.invalidateQueries({ queryKey: ['notifications'] });
    void queryClient.invalidateQueries({ queryKey: ['conversations'] });
  }, [id, queryClient]);

  // ------------------------------------------------------------ initial load
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const page = await listMessages(id, undefined, 30);
        if (cancelled) return;
        setMessages([...page.items].reverse());
        setCursor(page.next_cursor);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not load this conversation.');
        }
      } finally {
        if (!cancelled) setInitialLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // --------------------------------------------------------------- socket
  useEffect(() => {
    if (!id) return;
    let closedByUs = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const handleFrame = (frame: SocketFrame) => {
      switch (frame.type) {
        case 'ready':
          setMyId(frame.user_id);
          setConnection('live');
          setError(null);
          setCounterpartOnline(
            frame.online.some((userId) => userId !== frame.user_id),
          );
          break;
        case 'message':
          mergeMessage(frame.message);
          if (!frame.message.is_mine) {
            pushReadReceipt();
            setCounterpartTyping(false);
          }
          break;
        case 'typing':
          setCounterpartTyping(frame.is_typing);
          if (typingTimer.current) clearTimeout(typingTimer.current);
          if (frame.is_typing) {
            typingTimer.current = setTimeout(() => setCounterpartTyping(false), TYPING_TIMEOUT_MS);
          }
          break;
        case 'read':
          setMessages((previous) =>
            previous.map((item) =>
              item.is_mine && !item.read_at ? { ...item, read_at: frame.read_at } : item,
            ),
          );
          break;
        case 'presence':
          setCounterpartOnline(frame.online.some((userId) => userId !== myId));
          break;
        case 'error':
          setError(frame.message);
          break;
        default:
          break;
      }
    };

    const connect = () => {
      const socket = new WebSocket(chatSocketUrl(id));
      socketRef.current = socket;

      socket.onopen = () => {
        reconnectAttempt.current = 0;
      };
      socket.onmessage = (event) => {
        try {
          handleFrame(JSON.parse(String(event.data)) as SocketFrame);
        } catch {
          // ignore malformed frames
        }
      };
      socket.onerror = () => {
        setConnection((current) => (current === 'live' ? current : 'fallback'));
      };
      socket.onclose = (event) => {
        setCounterpartOnline(false);
        if (closedByUs) return;
        if (event.code === 1008) {
          // authentication / access refused — retrying will not help
          setConnection('denied');
          return;
        }
        setConnection('fallback');
        const delay = Math.min(15000, 1000 * 2 ** reconnectAttempt.current);
        reconnectAttempt.current += 1;
        retryTimer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      closedByUs = true;
      if (retryTimer) clearTimeout(retryTimer);
      if (typingTimer.current) clearTimeout(typingTimer.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
    // `myId` is intentionally excluded: presence frames are re-evaluated on each message.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, mergeMessage, pushReadReceipt]);

  // mark everything read when the screen opens
  useEffect(() => {
    if (!initialLoading) pushReadReceipt();
  }, [initialLoading, pushReadReceipt]);

  const send = async (override?: string) => {
    const text = (override ?? draft).trim();
    if (!text) return;

    const optimistic: Message = {
      id: `local-${Date.now()}`,
      conversation_id: id,
      sender_id: myId ?? '',
      body: text,
      read_at: null,
      created_at: new Date().toISOString(),
      is_mine: true,
    };
    setMessages((previous) => [...previous, optimistic]);
    if (override === undefined) setDraft('');
    setError(null);

    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'message', body: text }));
      return;
    }

    try {
      const saved = await sendMessage(id, text);
      setMessages((previous) =>
        previous.map((item) => (item.id === optimistic.id ? saved : item)),
      );
    } catch (err) {
      setMessages((previous) => previous.filter((item) => item.id !== optimistic.id));
      if (override === undefined) setDraft(text);
      setError(err instanceof ApiError ? err.message : 'Your message could not be sent.');
    }
  };

  /** WhatsApp-style: send the current GPS position as a Google Maps link. No map API key needed. */
  const shareLocation = async () => {
    if (sharing) return;
    setSharing(true);
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== 'granted') {
        Alert.alert(
          'Location permission needed',
          'Allow location access in Settings, or type your pickup point in the message box.',
        );
        return;
      }
      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      const { latitude, longitude } = position.coords;
      await send(
        `📍 Mera current location: https://maps.google.com/?q=${latitude.toFixed(6)},${longitude.toFixed(6)}`,
      );
    } catch {
      Alert.alert(
        'Location not available',
        'Turn on GPS and try again, or type your pickup point in the message box.',
      );
    } finally {
      setSharing(false);
    }
  };

  const loadOlder = async () => {
    if (!cursor || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const page = await listMessages(id, cursor, 30);
      setMessages((previous) => [...[...page.items].reverse(), ...previous]);
      setCursor(page.next_cursor);
    } catch {
      // silent: the user can scroll again
    } finally {
      setLoadingOlder(false);
    }
  };

  const onTyping = (value: string) => {
    setDraft(value);
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'typing', is_typing: value.length > 0 }));
    }
  };

  const reversed = useMemo(() => [...messages].reverse(), [messages]);
  const lastMine = useMemo(() => [...messages].reverse().find((item) => item.is_mine), [messages]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => goBackOr(router)} style={styles.back}>
          <Ionicons name="arrow-back" size={20} color={colors.navy} />
        </Pressable>
        <Avatar
          name={counterpart?.full_name ?? 'Chat'}
          size={38}
          photoUrl={counterpart?.profile_photo_url}
        />
        <View style={{ flex: 1 }}>
          <Text style={styles.name} numberOfLines={1}>
            {counterpart?.full_name ?? 'Trip chat'}
          </Text>
          <Text style={styles.status} numberOfLines={1}>
            {counterpartTyping
              ? 'typing…'
              : counterpartOnline
                ? 'online'
                : connection === 'live'
                  ? 'offline'
                  : connection === 'denied'
                    ? 'live chat unavailable'
                    : connection === 'connecting'
                      ? 'connecting…'
                      : 'connecting — messages still send'}
          </Text>
        </View>
        <Pressable
          onPress={() => router.push(`/trip/${conversationQuery.data?.trip_id ?? ''}`)}
          style={styles.back}
          accessibilityLabel="Open trip"
        >
          <Ionicons name="navigate-outline" size={18} color={colors.navy} />
        </Pressable>
      </View>

      {error ? (
        <View style={styles.bannerWrap}>
          <Banner tone="danger" message={error} />
        </View>
      ) : null}
      {connection === 'fallback' ? (
        <View style={styles.bannerWrap}>
          <Banner
            tone="info"
            message="Live updates are reconnecting. Messages you send are still delivered."
          />
        </View>
      ) : null}

      {initialLoading ? (
        <View style={styles.centre}>
          <ActivityIndicator color={colors.green} />
          <Text style={styles.muted}>Loading messages…</Text>
        </View>
      ) : (
        <FlatList
          data={reversed}
          inverted
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          onEndReached={loadOlder}
          onEndReachedThreshold={0.4}
          ListFooterComponent={
            loadingOlder ? (
              <ActivityIndicator color={colors.green} style={{ marginVertical: spacing.md }} />
            ) : null
          }
          ListEmptyComponent={
            <View style={styles.empty}>
              <Ionicons name="chatbubbles-outline" size={34} color={colors.textMuted} />
              <Text style={styles.emptyTitle}>Say salam 👋</Text>
              <Text style={styles.muted}>
                Agree on the exact meeting point and time. Only you and{' '}
                {counterpart?.full_name.split(' ')[0] ?? 'your partner'} can read this chat.
              </Text>
            </View>
          }
          renderItem={({ item }) => (
            <View style={[styles.bubbleRow, item.is_mine ? styles.rowMine : styles.rowTheirs]}>
              <View style={[styles.bubble, item.is_mine ? styles.bubbleMine : styles.bubbleTheirs]}>
                <Text style={[styles.bubbleText, item.is_mine && styles.bubbleTextMine]}>{item.body}</Text>
                {extractMapLink(item.body) ? (
                  <Pressable
                    onPress={() => void Linking.openURL(extractMapLink(item.body) as string)}
                    style={styles.mapLinkButton}
                    accessibilityLabel="Open location in Google Maps"
                  >
                    <Ionicons
                      name="map-outline"
                      size={14}
                      color={item.is_mine ? colors.textInverse : colors.navy}
                    />
                    <Text style={[styles.mapLinkText, item.is_mine && styles.bubbleTextMine]}>
                      Open in Google Maps
                    </Text>
                  </Pressable>
                ) : null}
                <View style={styles.meta}>
                  <Text style={[styles.metaText, item.is_mine && styles.metaTextMine]}>
                    {formatTime(item.created_at)}
                  </Text>
                  {item.is_mine && item.id === lastMine?.id ? (
                    <Text style={[styles.metaText, item.is_mine && styles.metaTextMine]}>
                      {item.read_at ? ' · Read' : ' · Sent'}
                    </Text>
                  ) : null}
                </View>
              </View>
            </View>
          )}
        />
      )}

      {counterpartTyping ? (
        <View style={styles.typingRow}>
          <Text style={styles.typingText}>
            {counterpart?.full_name.split(' ')[0] ?? 'They'} is typing…
          </Text>
        </View>
      ) : null}

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.composer}>
          <Pressable
            onPress={() => void shareLocation()}
            disabled={sharing}
            style={styles.attach}
            accessibilityLabel="Send current location"
          >
            {sharing ? (
              <ActivityIndicator color={colors.navy} size="small" />
            ) : (
              <Ionicons name="location-outline" size={22} color={colors.navy} />
            )}
          </Pressable>
          <TextInput
            style={styles.input}
            placeholder="Write a message…"
            placeholderTextColor={colors.textMuted}
            value={draft}
            onChangeText={onTyping}
            multiline
            maxLength={2000}
          />
          <Pressable
            onPress={() => void send()}
            disabled={!draft.trim()}
            style={[styles.send, !draft.trim() && styles.sendDisabled]}
            accessibilityLabel="Send message"
          >
            <Ionicons name="send" size={18} color={colors.textInverse} />
          </Pressable>
        </View>
        <Text style={styles.disclaimer}>
          {conversationQuery.data?.departure_at
            ? `${relativeDay(conversationQuery.data.departure_at)} · ${conversationQuery.data.pickup_area} → ${conversationQuery.data.destination_area}. `
            : ''}
          Keep personal contact details inside the app until you meet.
        </Text>
      </KeyboardAvoidingView>
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
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surface,
  },
  back: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  name: { color: colors.text, ...typography.bodyStrong },
  status: { color: colors.textMuted, ...typography.caption },
  bannerWrap: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  centre: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.sm },
  muted: { color: colors.textMuted, ...typography.caption, textAlign: 'center' },
  listContent: { padding: spacing.lg, gap: spacing.sm },
  empty: { alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.xxl, paddingHorizontal: spacing.lg },
  emptyTitle: { color: colors.text, ...typography.h2 },
  bubbleRow: { flexDirection: 'row' },
  rowMine: { justifyContent: 'flex-end' },
  rowTheirs: { justifyContent: 'flex-start' },
  bubble: {
    maxWidth: '82%',
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: 2,
  },
  bubbleMine: { backgroundColor: colors.navy, borderBottomRightRadius: 4 },
  bubbleTheirs: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderBottomLeftRadius: 4 },
  bubbleText: { color: colors.text, ...typography.body },
  bubbleTextMine: { color: colors.textInverse },
  meta: { flexDirection: 'row', alignSelf: 'flex-end' },
  metaText: { color: colors.textMuted, fontSize: 10 },
  metaTextMine: { color: 'rgba(255,255,255,0.65)' },
  typingRow: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xs },
  typingText: { color: colors.textMuted, ...typography.caption, fontStyle: 'italic' },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  input: {
    flex: 1,
    maxHeight: 120,
    minHeight: 44,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.background,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    color: colors.text,
    ...typography.body,
  },
  send: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.green,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendDisabled: { backgroundColor: colors.border },
  attach: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  mapLinkButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 4,
    paddingVertical: 4,
  },
  mapLinkText: { color: colors.navy, fontSize: 12, fontWeight: '600', textDecorationLine: 'underline' },
  disclaimer: {
    color: colors.textMuted,
    fontSize: 10,
    textAlign: 'center',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
});
