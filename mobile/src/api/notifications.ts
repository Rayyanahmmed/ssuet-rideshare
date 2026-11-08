import { api } from '@/api/client';

/** Typed access to `/api/v1/notifications` (§12). */

export type AppNotification = {
  id: string;
  type: string;
  title: string;
  body: string;
  is_read: boolean;
  read_at: string | null;
  data: { screen?: string; trip_id?: string; conversation_id?: string } | null;
  created_at: string;
};

export type NotificationList = {
  items: AppNotification[];
  next_cursor: string | null;
  count: number;
  unread_count: number;
};

export async function listNotifications(cursor?: string, limit = 20): Promise<NotificationList> {
  const { data } = await api.get<NotificationList>('/notifications', {
    params: { limit, ...(cursor ? { cursor } : {}) },
  });
  return data;
}

export async function getUnreadCount(): Promise<number> {
  const { data } = await api.get<{ unread_count: number }>('/notifications/unread-count');
  return data.unread_count;
}

export async function markNotificationRead(id: string): Promise<AppNotification> {
  const { data } = await api.post<AppNotification>(`/notifications/${id}/read`);
  return data;
}

export async function markAllNotificationsRead(): Promise<number> {
  const { data } = await api.post<{ marked_read: number }>('/notifications/read-all');
  return data.marked_read;
}

export async function registerDeviceToken(token: string, platform: 'android' | 'ios'): Promise<void> {
  await api.post('/notifications/devices', { token, platform });
}

export async function unregisterDeviceToken(token: string): Promise<void> {
  await api.delete(`/notifications/devices/${encodeURIComponent(token)}`);
}
