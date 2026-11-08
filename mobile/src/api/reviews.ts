import { api } from '@/api/client';
import type { Direction } from '@/api/rides';

/** Typed access to `/api/v1/reviews` — trust between members (§14). */

export type ReviewAuthor = {
  id: string;
  full_name: string;
  profile_photo_url: string | null;
  role: 'STUDENT' | 'TEACHER' | 'ADMIN';
  department: string;
};

export type Review = {
  id: string;
  trip_id: string;
  rating: number;
  comment: string | null;
  direction: Direction | null;
  pickup_area: string | null;
  destination_area: string | null;
  author: ReviewAuthor;
  subject_id: string;
  created_at: string;
};

export type ReviewPage = {
  items: Review[];
  total: number;
  page: number;
  limit: number;
  pages: number;
  average: number;
  /** Always contains all five keys, e.g. `{"5": 4, "4": 1, …}`. */
  breakdown: Record<string, number>;
};

export type PendingReview = {
  trip_id: string;
  counterpart: ReviewAuthor;
  direction: Direction | null;
  pickup_area: string | null;
  destination_area: string | null;
  departure_at: string | null;
  completed_at: string | null;
  my_role: 'DRIVER' | 'PASSENGER';
};

export type PendingReviewList = { items: PendingReview[]; count: number };

export async function listPendingReviews(): Promise<PendingReviewList> {
  const { data } = await api.get<PendingReviewList>('/reviews/pending');
  return data;
}

export async function submitReview(
  tripId: string,
  body: { rating: number; comment?: string },
): Promise<Review> {
  const { data } = await api.post<Review>(`/reviews/trips/${tripId}`, body);
  return data;
}

export async function listMyReceivedReviews(page = 1, limit = 20): Promise<ReviewPage> {
  const { data } = await api.get<ReviewPage>('/reviews/me/received', { params: { page, limit } });
  return data;
}

export async function listUserReviews(userId: string, page = 1, limit = 20): Promise<ReviewPage> {
  const { data } = await api.get<ReviewPage>(`/reviews/users/${userId}`, { params: { page, limit } });
  return data;
}
