import { api } from '@/api/client';

/** Typed access to `/api/v1/reports` — safety and complaints (§15). */

export type ReportCategory =
  | 'INAPPROPRIATE_BEHAVIOR'
  | 'FAKE_PROFILE'
  | 'MISLEADING_RIDE'
  | 'HARASSMENT'
  | 'SAFETY_CONCERN'
  | 'PROFILE_PHOTO'
  | 'OTHER';

export type ReportStatus = 'OPEN' | 'UNDER_REVIEW' | 'RESOLVED' | 'DISMISSED';

export type Report = {
  id: string;
  category: ReportCategory;
  description: string;
  status: ReportStatus;
  reported_user: {
    id: string;
    full_name: string;
    profile_photo_url: string | null;
    role: 'STUDENT' | 'TEACHER' | 'ADMIN';
    department: string;
  };
  trip_id: string | null;
  ride_id: string | null;
  resolution_note: string | null;
  resolved_at: string | null;
  created_at: string;
};

export type ReportPage = {
  items: Report[];
  total: number;
  page: number;
  limit: number;
  pages: number;
};

export const REPORT_CATEGORIES: { value: ReportCategory; label: string; hint: string }[] = [
  { value: 'HARASSMENT', label: 'Harassment', hint: 'Unwanted messages, pressure or intimidation' },
  { value: 'SAFETY_CONCERN', label: 'Safety concern', hint: 'Dangerous driving, vehicle condition, no show' },
  { value: 'INAPPROPRIATE_BEHAVIOR', label: 'Behaviour', hint: 'Rude, discriminatory or threatening conduct' },
  { value: 'MISLEADING_RIDE', label: 'Misleading ride', hint: 'Route, timing or fuel terms did not match' },
  { value: 'FAKE_PROFILE', label: 'Fake profile', hint: 'Identity or photograph looks wrong' },
  { value: 'OTHER', label: 'Something else', hint: 'Tell us in your own words' },
];

/** Why a profile photo was reported (Phase 15) — mirrors the server's enum. */
export type PhotoReportReason = 'OFFENSIVE' | 'NOT_A_REAL_PERSON' | 'IMPERSONATION' | 'OTHER';

export const PHOTO_REPORT_REASONS: { value: PhotoReportReason; label: string; hint: string }[] = [
  { value: 'OFFENSIVE', label: 'Offensive', hint: 'Explicit, violent or otherwise inappropriate' },
  { value: 'NOT_A_REAL_PERSON', label: 'Not a person', hint: 'A logo, a landscape or a cartoon' },
  { value: 'IMPERSONATION', label: 'Someone else', hint: 'A photo of another person used as their own' },
  { value: 'OTHER', label: 'Something else', hint: 'Tell us in your own words' },
];

/**
 * Report a member's profile photo.
 *
 * Addressed by member, not by asset id: the server pins whichever picture is current,
 * so a member cannot dodge a complaint by swapping the photo first.
 */
export async function reportProfilePhoto(
  userId: string,
  body: { reason: PhotoReportReason; description: string },
): Promise<Report> {
  const { data } = await api.post<Report>(`/users/${userId}/photo/report`, body);
  return data;
}

export async function fileReport(body: {
  category: ReportCategory;
  description: string;
  trip_id?: string;
  ride_id?: string;
  reported_user_id?: string;
}): Promise<Report> {
  const { data } = await api.post<Report>('/reports', body);
  return data;
}

export async function listMyReports(status?: ReportStatus): Promise<ReportPage> {
  const { data } = await api.get<ReportPage>('/reports', { params: status ? { status } : {} });
  return data;
}

export async function getMyReport(id: string): Promise<Report> {
  const { data } = await api.get<Report>(`/reports/${id}`);
  return data;
}
