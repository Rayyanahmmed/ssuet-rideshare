import { api, getAccessToken } from '@/api/client';

/** Typed access to `/api/v1/chat` — REST fallback plus the socket URL (§11). */

export type ChatParticipant = {
  id: string;
  full_name: string;
  profile_photo_url: string | null;
  department: string;
  verification_status: string;
  is_online: boolean;
};

export type Conversation = {
  id: string;
  trip_id: string;
  trip_status: string;
  direction: 'HOME_TO_UNIVERSITY' | 'UNIVERSITY_TO_HOME' | null;
  pickup_area: string | null;
  destination_area: string | null;
  departure_at: string | null;
  counterpart: ChatParticipant;
  last_message_at: string | null;
  last_message_preview: string | null;
  last_message_is_mine: boolean;
  unread_count: number;
};

export type ConversationList = { items: Conversation[]; count: number; unread_total: number };

export type Message = {
  id: string;
  conversation_id: string;
  sender_id: string;
  body: string;
  read_at: string | null;
  created_at: string;
  is_mine: boolean;
};

export type MessageList = { items: Message[]; next_cursor: string | null; count: number };

export async function listConversations(): Promise<ConversationList> {
  const { data } = await api.get<ConversationList>('/chat/conversations');
  return data;
}

export async function getConversation(id: string): Promise<Conversation> {
  const { data } = await api.get<Conversation>(`/chat/conversations/${id}`);
  return data;
}

export async function listMessages(
  conversationId: string,
  cursor?: string,
  limit = 30,
): Promise<MessageList> {
  const { data } = await api.get<MessageList>(`/chat/conversations/${conversationId}/messages`, {
    params: { limit, ...(cursor ? { cursor } : {}) },
  });
  return data;
}

export async function sendMessage(conversationId: string, body: string): Promise<Message> {
  const { data } = await api.post<Message>(`/chat/conversations/${conversationId}/messages`, { body });
  return data;
}

export async function markConversationRead(
  conversationId: string,
): Promise<{ messages_marked_read: number }> {
  const { data } = await api.post(`/chat/conversations/${conversationId}/read`);
  return data;
}

// ------------------------------------------------------------------ socket

export type SocketFrame =
  | { type: 'ready'; conversation_id: string; user_id: string; online: string[]; counterpart: { id: string; full_name: string } }
  | { type: 'message'; message: Message }
  | { type: 'typing'; user_id: string; is_typing: boolean }
  | { type: 'read'; user_id: string; read_at: string; messages_marked_read: number }
  | { type: 'presence'; online: string[] }
  | { type: 'error'; code: string; message: string }
  | { type: 'pong' };

/**
 * `http(s)` → `ws(s)` and keep the `/api/v1` prefix, so the socket lives beside
 * the REST API on every environment (LAN IP, tunnel, production host).
 */
export function chatSocketUrl(conversationId: string): string {
  const base = api.defaults.baseURL ?? '';
  const socketBase = base.replace(/^http/i, 'ws').replace(/\/$/, '');
  const token = getAccessToken() ?? '';
  return `${socketBase}/chat/ws/${conversationId}?token=${encodeURIComponent(token)}`;
}
