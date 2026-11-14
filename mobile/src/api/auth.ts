import { api } from '@/api/client';
import { deleteMediaAsset, uploadDocument } from '@/api/media';
import type { SessionUser } from '@/store/auth';

/** Typed wrappers around `/api/v1/auth` and `/api/v1/users/me`. */

export type AuthResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: SessionUser;
};

export type SignupPayload = {
  full_name: string;
  email: string;
  password: string;
  phone: string;
  role: 'STUDENT' | 'TEACHER';
  university_id: string;
  department: string;
  home_area?: string;
  semester?: number;
  designation?: string;
};

export async function login(email: string, password: string): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/auth/login', { email, password });
  return data;
}

export async function signup(payload: SignupPayload): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/auth/register', payload);
  return data;
}

export async function fetchMe(): Promise<SessionUser> {
  const { data } = await api.get<SessionUser>('/auth/me');
  return data;
}

export async function requestPasswordReset(email: string): Promise<{ message: string; detail?: string }> {
  const { data } = await api.post('/auth/forgot-password', { email });
  return data;
}

export async function resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
  const { data } = await api.post('/auth/reset-password', { token, new_password: newPassword });
  return data;
}

/** Confirms the email address with the single-use token from the confirmation email. */
export async function verifyEmail(token: string): Promise<SessionUser> {
  const { data } = await api.post<SessionUser>('/auth/verify-email', { token });
  return data;
}

/** Sends a fresh confirmation email to the signed-in member (rate limited by the API). */
export async function resendVerificationEmail(): Promise<{ message: string }> {
  const { data } = await api.post('/auth/resend-verification');
  return data;
}

export async function logout(refreshToken: string | null): Promise<void> {
  if (!refreshToken) return;
  try {
    await api.post('/auth/logout', { refresh_token: refreshToken });
  } catch {
    // Signing out must always succeed locally, even if the API is unreachable.
  }
}

export type VerificationSubmission = {
  verification_type: 'STUDENT_ID' | 'EMPLOYEE_ID' | 'MANUAL';
  submitted_value?: string;
  /** Preferred: id returned by `uploadVerificationDocument`. */
  document_asset_id?: string;
  /** Alternative: an external https link the member keeps in Drive. */
  document_url?: string;
  note?: string;
};

export type { MediaAsset } from '@/api/media';

/** Upload an ID photo (§4, Phase 9) — thin wrapper so screens read naturally. */
export async function uploadVerificationDocument(file: { uri: string; name: string; type: string }) {
  return uploadDocument('/uploads/verification', file);
}

export { deleteMediaAsset } from '@/api/media';

export async function submitVerification(payload: VerificationSubmission) {
  const { data } = await api.post('/users/me/verification', payload);
  return data;
}
