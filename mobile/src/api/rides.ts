import { api } from '@/api/client';

/** Typed access to `/api/v1/rides`, `/requests` and `/vehicles` (§7–§9). */

export type Direction = 'HOME_TO_UNIVERSITY' | 'UNIVERSITY_TO_HOME';
export type FuelPreference = 'FREE' | 'SHARE_FUEL';
export type ContributionType = 'NONE' | 'FIXED' | 'EXPECTED' | 'NEGOTIABLE';
export type RideStatus = 'OPEN' | 'MATCHED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED' | 'EXPIRED';
export type RequestStatus = 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'CANCELLED';
export type VehicleKind = 'CAR' | 'BIKE';

export type GeoPoint = { latitude: number; longitude: number };

export type DriverSummary = {
  id: string;
  full_name: string;
  profile_photo_url: string | null;
  role: 'STUDENT' | 'TEACHER';
  department: string;
  verification_status: 'UNVERIFIED' | 'PENDING' | 'VERIFIED' | 'REJECTED';
  rating_average: number;
  rating_count: number;
  completed_trips_count: number;
};

export type Ride = {
  id: string;
  direction: Direction;
  status: RideStatus;
  driver: DriverSummary;
  vehicle: { vehicle_type: VehicleKind; make_and_model: string; color: string; is_verified: boolean } | null;
  pickup_area: string;
  destination_area: string;
  departure_at: string;
  departure_date: string;
  available_seats: number;
  seats_remaining: number;
  fuel_preference: FuelPreference;
  contribution: { type: ContributionType; amount: number | null; note: string | null } | null;
  note: string | null;
  created_at: string;
  is_own_ride: boolean;
  can_request: boolean;
  my_request_status: RequestStatus | null;
  my_trip_id: string | null;
  pickup_point: GeoPoint | null;
};

export type RideDetail = Ride & {
  destination_point: GeoPoint | null;
  driver_note: string | null;
  pending_requests_count: number;
  driver_phone: string | null;
};

export type RideFilters = {
  direction?: Direction;
  vehicle_type?: VehicleKind;
  fuel_preference?: FuelPreference;
  area?: string;
  departure_after?: string;
  departure_before?: string;
  lat?: number;
  lng?: number;
  radius_km?: number;
  exclude_own?: boolean;
  limit?: number;
  cursor?: string;
};

export type RidePage = { items: Ride[]; next_cursor: string | null; count: number };

export async function listRides(filters: RideFilters): Promise<RidePage> {
  const { data } = await api.get<RidePage>('/rides', {
    params: Object.fromEntries(
      Object.entries(filters).filter(([, value]) => value !== undefined && value !== ''),
    ),
  });
  return data;
}

export async function getRide(id: string): Promise<RideDetail> {
  const { data } = await api.get<RideDetail>(`/rides/${id}`);
  return data;
}

export type PublishPayload = {
  direction: Direction;
  pickup_area?: string;
  pickup_point?: GeoPoint;
  destination_area?: string;
  destination_point?: GeoPoint;
  departure_at: string;
  vehicle_id: string;
  available_seats?: number;
  fuel_preference: FuelPreference;
  contribution_type: ContributionType;
  contribution_amount?: number | null;
  contribution_note?: string | null;
  note?: string | null;
};

export async function publishRide(payload: PublishPayload): Promise<RideDetail> {
  const { data } = await api.post<RideDetail>('/rides', payload);
  return data;
}

export async function myRides(status?: RideStatus): Promise<Ride[]> {
  const { data } = await api.get<Ride[]>('/rides/mine', { params: status ? { status } : {} });
  return data;
}

export async function cancelRide(id: string, reason?: string): Promise<RideDetail> {
  const { data } = await api.post<RideDetail>(`/rides/${id}/cancel`, { reason });
  return data;
}

export async function requestSeat(rideId: string, message?: string) {
  const { data } = await api.post(`/rides/${rideId}/requests`, { message });
  return data;
}

export type RequestOut = {
  id: string;
  ride_id: string;
  status: RequestStatus;
  message: string | null;
  response_note: string | null;
  responded_at: string | null;
  created_at: string;
};

export type MyRequest = RequestOut & { ride: Ride };

export async function myRequests(): Promise<{ items: MyRequest[]; count: number }> {
  const { data } = await api.get('/requests/mine');
  return data;
}

export type DriverRequest = RequestOut & {
  passenger: {
    id: string;
    full_name: string;
    profile_photo_url: string | null;
    department: string;
    role: 'STUDENT' | 'TEACHER';
    verification_status: string;
    rating_average: number;
    rating_count: number;
    completed_trips_count: number;
  };
  ride_pickup_area: string;
  ride_departure_at: string;
};

export async function driverInbox(): Promise<DriverRequest[]> {
  const { data } = await api.get('/requests/inbox');
  return data;
}

export async function acceptRequest(requestId: string) {
  const { data } = await api.post(`/requests/${requestId}/accept`);
  return data;
}

export async function rejectRequest(requestId: string, message?: string) {
  const { data } = await api.post(`/requests/${requestId}/reject`, { message });
  return data;
}

export async function cancelMyRequest(requestId: string) {
  const { data } = await api.post(`/requests/${requestId}/cancel`);
  return data;
}

// ------------------------------------------------------------------ vehicles

export type Vehicle = {
  id: string;
  vehicle_type: VehicleKind;
  make_and_model: string;
  color: string;
  registration_number: string;
  passenger_capacity: number;
  vehicle_photo_url: string | null;
  photo_asset_id: string | null;
  registration_asset_id: string | null;
  is_primary: boolean;
  status: 'PENDING' | 'VERIFIED' | 'REJECTED';
  review_note: string | null;
  created_at: string;
};

export async function myVehicles(): Promise<Vehicle[]> {
  const { data } = await api.get<Vehicle[]>('/vehicles');
  return data;
}

export type VehiclePayload = {
  vehicle_type: VehicleKind;
  make_and_model: string;
  color: string;
  registration_number: string;
  passenger_capacity: number;
  photo_asset_id?: string | null;
  registration_asset_id?: string | null;
  is_primary?: boolean;
};

export async function createVehicle(payload: VehiclePayload): Promise<Vehicle> {
  const { data } = await api.post<Vehicle>('/vehicles', payload);
  return data;
}
