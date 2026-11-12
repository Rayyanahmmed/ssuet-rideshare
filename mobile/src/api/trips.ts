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

/** Cash payment state for a trip. PENDING means nothing has been recorded yet. */
export type PaymentStatus = 'PENDING' | 'PAID_BY_PASSENGER' | 'VERIFIED' | 'NON_PAYMENT_REPORTED';

export type Payment = {
  trip_id: string;
  status: PaymentStatus;
  amount_pkr: number | null;
  invoice_number: string | null;
  verified_at: string | null;
  non_payment_report_id: string | null;
};

export type Invoice = {
  invoice_number: string;
  trip_id: string;
  issued_at: string;
  payment_method: 'CASH';
  amount_pkr: number | null;
  status: PaymentStatus;
  driver_name: string;
  passenger_name: string;
  pickup_area: string | null;
  destination_area: string | null;
  departure_at: string | null;
  completed_at: string | null;
  note: string;
};

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

  driver_arrived_at: string | null;
  can_mark_arrived: boolean;
  fuel_contribution_type: 'NONE' | 'FIXED' | 'EXPECTED' | 'NEGOTIABLE' | null;
  fuel_contribution_amount: number | null;

  payment_status: PaymentStatus | null;
  can_mark_paid: boolean;
  can_confirm_payment: boolean;
  can_report_non_payment: boolean;
  invoice_number: string | null;

  my_role: TripRole;
  can_start: boolean;
  can_complete: boolean;
  payment_required: boolean;
  completion_ready: boolean;
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

/** Driver confirms the cash was received. Creates the verified transaction and invoice. */
export async function confirmPayment(id: string, amountPkr?: number): Promise<Payment> {
  const { data } = await api.post<Payment>(`/trips/${id}/payment/confirm`, {
    amount_pkr: amountPkr ?? null,
  });
  return data;
}

/** Driver reports that the passenger did not pay. Opens a report for the admin office. */
export async function reportNonPayment(id: string, description: string): Promise<Payment> {
  const { data } = await api.post<Payment>(`/trips/${id}/payment/non-payment-report`, { description });
  return data;
}

export async function getInvoice(id: string): Promise<Invoice> {
  const { data } = await api.get<Invoice>(`/trips/${id}/invoice`);
  return data;
}

/** Driver says "I have arrived" at the meeting point. The passenger is notified. */
export async function markArrived(id: string): Promise<Trip> {
  const { data } = await api.post<Trip>(`/trips/${id}/arrived`);
  return data;
}

/** Passenger says the cash fuel share is paid. The driver must then verify it. */
export async function markPaid(id: string): Promise<Payment> {
  const { data } = await api.post<Payment>(`/trips/${id}/payment/mark-paid`);
  return data;
}
