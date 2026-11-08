import { api } from '@/api/client';
import type { Direction, DriverSummary, FuelPreference, GeoPoint, Vehicle } from '@/api/rides';

type PassengerSummary = DriverSummary;

type VehicleSummary = {
  vehicle_type: Vehicle['vehicle_type'];
  make_and_model: string;
  color: string;
  is_verified: boolean;
};

/** Typed access to `/api/v1/trips` — the lifecycle of a matched journey (§10). */

export type TripStatus = 'CONFIRMED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED' | 'NO_SHOW';
export type TripRole = 'DRIVER' | 'PASSENGER';

export type Counterpart = {
  id: string;
  full_name: string;
  profile_photo_url: string | null;
  department: string;
  phone: string | null;
};

export type Trip = {
  id: string;
  ride_id: string;
  status: TripStatus;
  direction: Direction | null;

  meeting_point: string | null;
  meeting_location: GeoPoint | null;
  departure_at: string | null;
  pickup_area: string | null;
  destination_area: string | null;
  vehicle: VehicleSummary | null;
  fuel_preference: FuelPreference | null;

  driver: DriverSummary;
  passenger: PassengerSummary;
  counterpart: Counterpart;
  driver_phone: string | null;
  passenger_phone: string | null;

  conversation_id: string | null;

  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  cancelled_by_id: string | null;
  cancellation_reason: string | null;
  driver_confirmed_complete: boolean;
  passenger_confirmed_complete: boolean;
  awaiting_my_confirmation: boolean;

  can_review: boolean;
  viewer_reviewed: boolean;

  my_role: TripRole;
  can_start: boolean;
  can_complete: boolean;
  can_cancel: boolean;
  can_mark_no_show: boolean;

  created_at: string;
};

export type TripList = { items: Trip[]; count: number };

export type TripFilters = {
  role?: TripRole;
  status?: TripStatus;
  upcoming?: boolean;
  limit?: number;
};

export async function listTrips(filters: TripFilters = {}): Promise<TripList> {
  const { data } = await api.get<TripList>('/trips/mine', {
    params: Object.fromEntries(
      Object.entries(filters).filter(([, value]) => value !== undefined && value !== null),
    ),
  });
  return data;
}

export async function getTrip(id: string): Promise<Trip> {
  const { data } = await api.get<Trip>(`/trips/${id}`);
  return data;
}

export async function startTrip(id: string): Promise<Trip> {
  const { data } = await api.post<Trip>(`/trips/${id}/start`);
  return data;
}

export async function completeTrip(id: string, reason?: string): Promise<Trip> {
  const { data } = await api.post<Trip>(`/trips/${id}/complete`, { reason });
  return data;
}

export async function cancelTrip(id: string, reason?: string): Promise<Trip> {
  const { data } = await api.post<Trip>(`/trips/${id}/cancel`, { reason });
  return data;
}

export async function markNoShow(id: string, reason?: string): Promise<Trip> {
  const { data } = await api.post<Trip>(`/trips/${id}/no-show`, { reason });
  return data;
}
