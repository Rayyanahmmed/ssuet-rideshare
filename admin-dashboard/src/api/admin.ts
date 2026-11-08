import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

/**
 * Typed admin API layer (§16).
 *
 * Every screen reads from these hooks — there is no mock data and no derived
 * arithmetic in the browser: figures come from `/api/v1/admin/*`, which computes
 * them with SQL against the live tables.
 */

export type Page<T> = { items: T[]; total: number; page: number; limit: number; pages: number };
export type TrendPoint = { day: string; count: number };

export type DashboardStats = {
  total_users: number;
  verified_users: number;
  pending_verifications: number;
  pending_vehicles: number;
  suspended_accounts: number;
  published_rides: number;
  open_rides: number;
  active_trips: number;
  completed_trips: number;
  open_reports: number;
  rides_today: number;
  trips_today: number;
};

export type Dashboard = {
  stats: DashboardStats;
  users_per_day: TrendPoint[];
  rides_per_day: TrendPoint[];
  trips_per_day: TrendPoint[];
  rides_by_status: Record<string, number>;
  trips_by_status: Record<string, number>;
  generated_at: string;
};

export type Analytics = {
  days: number;
  completion_rate: number;
  cancellation_rate: number;
  average_rating: number;
  fuel_split: Record<string, number>;
  vehicle_split: Record<string, number>;
  direction_split: Record<string, number>;
  top_pickup_areas: { area: string; count: number }[];
  top_destinations: { area: string; count: number }[];
  users_per_day: TrendPoint[];
  rides_per_day: TrendPoint[];
};

export type AdminUser = {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  role: 'STUDENT' | 'TEACHER' | 'ADMIN';
  department: string;
  university_id: string;
  verification_status: 'UNVERIFIED' | 'PENDING' | 'VERIFIED' | 'REJECTED';
  account_status: 'ACTIVE' | 'SUSPENDED' | 'DEACTIVATED';
  rating_average: number;
  rating_count: number;
  completed_trips_count: number;
  vehicles_count: number;
  profile_photo_url: string | null;
  created_at: string;
  last_login_at: string | null;
};

export type AdminVehicle = {
  id: string;
  owner_id: string;
  owner_name: string;
  vehicle_type: 'CAR' | 'BIKE';
  make_and_model: string;
  color: string;
  registration_number: string;
  passenger_capacity: number;
  vehicle_photo_url: string | null;
  photo_asset_id: string | null;
  registration_asset_id: string | null;
  status: 'PENDING' | 'VERIFIED' | 'REJECTED';
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
};

export type AdminRide = {
  id: string;
  driver_id: string;
  driver_name: string;
  direction: 'HOME_TO_UNIVERSITY' | 'UNIVERSITY_TO_HOME';
  pickup_area: string;
  destination_area: string;
  departure_at: string;
  status: 'OPEN' | 'MATCHED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED' | 'EXPIRED';
  seats_remaining: number;
  fuel_preference: 'FREE' | 'SHARE_FUEL';
  matched_passenger_name: string | null;
  requests_count: number;
  created_at: string;
};

export type AdminTrip = {
  id: string;
  ride_id: string;
  driver_id: string;
  driver_name: string;
  passenger_id: string;
  passenger_name: string;
  status: 'CONFIRMED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED' | 'NO_SHOW';
  pickup_area: string | null;
  destination_area: string | null;
  departure_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type AdminReport = {
  id: string;
  reporter_id: string;
  reporter_name: string;
  reported_user_id: string;
  reported_user_name: string;
  category: string;
  description: string;
  status: 'OPEN' | 'UNDER_REVIEW' | 'RESOLVED' | 'DISMISSED';
  /** Phase 15 — only present on photo reports. */
  photo_reason: string | null;
  reported_photo_url: string | null;
  ride_id: string | null;
  trip_id: string | null;
  resolution_note: string | null;
  resolved_at: string | null;
  created_at: string;
};

export type AdminVerification = {
  id: string;
  user_id: string;
  user_name: string;
  user_email: string;
  department: string;
  university_id: string;
  verification_type: string;
  status: string;
  submitted_value: string | null;
  document_url: string | null;
  document_asset_id: string | null;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
};

export type AdminUserDetail = {
  user: AdminUser;
  email_verified_at: string | null;
  verified_at: string | null;
  suspension_reason: string | null;
  home_area: string | null;
  semester: number | null;
  vehicles: AdminVehicle[];
  recent_rides: AdminRide[];
  verifications: AdminVerification[];
  trips_as_driver: number;
  trips_as_passenger: number;
  reports_against: number;
  reports_filed: number;
};

export type AdminReview = {
  id: string;
  trip_id: string;
  rating: number;
  comment: string | null;
  author_id: string;
  author_name: string;
  subject_id: string;
  subject_name: string;
  is_hidden: boolean;
  created_at: string;
  has_report: boolean;
};

export type AdminAction = {
  id: string;
  admin_id: string | null;
  admin_name: string | null;
  action_type: string;
  target_user_id: string | null;
  target_user_name: string | null;
  entity_type: string | null;
  entity_id: string | null;
  notes: string | null;
  created_at: string;
};

export type Settings = {
  environment: string;
  university_domains: string[];
  auto_verify_university_emails: boolean;
  maps_configured: boolean;
  smtp_configured: boolean;
  expo_push_enabled: boolean;
  rate_limit_enabled: boolean;
  admin_bootstrap_enabled: boolean;
  max_confirmed_passengers: number;
  ride_auto_expire_grace_minutes: number;
  maintenance_interval_minutes: number;
  api_version: string;
  features: Record<string, boolean>;
};

const clean = (params: Record<string, unknown>) =>
  Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  );

// ------------------------------------------------------------------ queries
export const useDashboard = () =>
  useQuery({
    queryKey: ['admin', 'dashboard'],
    queryFn: async () => (await api.get<Dashboard>('/admin/dashboard')).data,
    refetchInterval: 60_000,
  });

export const useAnalytics = (days = 30) =>
  useQuery({
    queryKey: ['admin', 'analytics', days],
    queryFn: async () => (await api.get<Analytics>('/admin/analytics', { params: { days } })).data,
  });

export const useSettings = () =>
  useQuery({
    queryKey: ['admin', 'settings'],
    queryFn: async () => (await api.get<Settings>('/admin/settings')).data,
  });

export const useAdminUsers = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ['admin', 'users', params],
    queryFn: async () => (await api.get<Page<AdminUser>>('/admin/users', { params: clean(params) })).data,
  });

export const useAdminUser = (id: string | null) =>
  useQuery({
    queryKey: ['admin', 'user', id],
    queryFn: async () => (await api.get<AdminUserDetail>(`/admin/users/${id}`)).data,
    enabled: Boolean(id),
  });

export const useVerifications = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ['admin', 'verifications', params],
    queryFn: async () =>
      (await api.get<Page<AdminVerification>>('/admin/verifications', { params: clean(params) })).data,
  });

export const useAdminVehicles = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ['admin', 'vehicles', params],
    queryFn: async () => (await api.get<Page<AdminVehicle>>('/admin/vehicles', { params: clean(params) })).data,
  });

export const useAdminRides = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ['admin', 'rides', params],
    queryFn: async () => (await api.get<Page<AdminRide>>('/admin/rides', { params: clean(params) })).data,
  });

export const useAdminTrips = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ['admin', 'trips', params],
    queryFn: async () => (await api.get<Page<AdminTrip>>('/admin/trips', { params: clean(params) })).data,
  });

export const useReports = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ['admin', 'reports', params],
    queryFn: async () => (await api.get<Page<AdminReport>>('/admin/reports', { params: clean(params) })).data,
  });

export const useAdminReviews = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ['admin', 'reviews', params],
    queryFn: async () => (await api.get<Page<AdminReview>>('/admin/reviews', { params: clean(params) })).data,
  });

export const useAdminActions = (page = 1) =>
  useQuery({
    queryKey: ['admin', 'actions', page],
    queryFn: async () => (await api.get<Page<AdminAction>>('/admin/admin-actions', { params: { page } })).data,
  });

// ---------------------------------------------------------------- mutations
function useAdminMutation<TVariables>(options: {
  mutationFn: (variables: TVariables) => Promise<unknown>;
  invalidate: string[];
}) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: options.mutationFn,
    onSuccess: async () => {
      await Promise.all([
        ...options.invalidate.map((key) => queryClient.invalidateQueries({ queryKey: ['admin', key] })),
        queryClient.invalidateQueries({ queryKey: ['admin', 'dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['admin', 'actions'] }),
      ]);
    },
  });
}

export const useVerifyUser = () =>
  useAdminMutation<{ id: string; note?: string }>({
    mutationFn: ({ id, note }) => api.post(`/admin/users/${id}/verify`, { note }),
    invalidate: ['users', 'verifications', 'user'],
  });

export const useRejectUser = () =>
  useAdminMutation<{ id: string; reason: string }>({
    mutationFn: ({ id, reason }) => api.post(`/admin/users/${id}/reject`, { reason }),
    invalidate: ['users', 'verifications', 'user'],
  });

export const useSuspendUser = () =>
  useAdminMutation<{ id: string; reason: string }>({
    mutationFn: ({ id, reason }) => api.post(`/admin/users/${id}/suspend`, { reason }),
    invalidate: ['users', 'rides', 'user'],
  });

export const useReactivateUser = () =>
  useAdminMutation<{ id: string }>({
    mutationFn: ({ id }) => api.post(`/admin/users/${id}/reactivate`, {}),
    invalidate: ['users', 'user'],
  });

export type PasswordResetCode = {
  code: string;
  expires_at: string;
  expires_in_minutes: number;
};

/** Fallback when email is not set up: a one-time code the admin passes to the member. */
export const useIssuePasswordResetCode = () =>
  useAdminMutation<{ id: string }>({
    mutationFn: ({ id }) =>
      api.post<PasswordResetCode>(`/admin/users/${id}/password-reset-code`, {}).then((r) => r.data),
    invalidate: [],
  });

export const useVerifyVehicle = () =>
  useAdminMutation<{ id: string; note?: string }>({
    mutationFn: ({ id, note }) => api.post(`/admin/vehicles/${id}/verify`, { note }),
    invalidate: ['vehicles', 'user'],
  });

export const useRejectVehicle = () =>
  useAdminMutation<{ id: string; reason: string }>({
    mutationFn: ({ id, reason }) => api.post(`/admin/vehicles/${id}/reject`, { reason }),
    invalidate: ['vehicles', 'user'],
  });

export const useCancelRide = () =>
  useAdminMutation<{ id: string; reason?: string }>({
    mutationFn: ({ id, reason }) => api.post(`/admin/rides/${id}/cancel`, { reason }),
    invalidate: ['rides', 'trips', 'user'],
  });

export const useHideReview = () =>
  useAdminMutation<{ id: string; reason: string }>({
    mutationFn: ({ id, reason }) => api.post(`/admin/reviews/${id}/hide`, { reason }),
    invalidate: ['reviews', 'users', 'analytics'],
  });

export const useUnhideReview = () =>
  useAdminMutation<{ id: string; note?: string }>({
    mutationFn: ({ id, note }) => api.post(`/admin/reviews/${id}/unhide`, { note }),
    invalidate: ['reviews', 'users', 'analytics'],
  });

export const useUpdateReport = () =>
  useAdminMutation<{ id: string; status: string; resolution_note?: string; remove_photo?: boolean }>({
    mutationFn: ({ id, ...body }) => api.patch(`/admin/reports/${id}`, body),
    invalidate: ['reports'],
  });
