import { create } from 'zustand';
import { clearTokens, loadTokens, saveTokens } from '@/lib/secureStore';
import { ApiError, setAccessToken, setRefreshToken, onUnauthorized } from '@/api/client';
import { resetQueryCache } from '@/lib/queryClient';
import * as authApi from '@/api/auth';

/**
 * Session state.
 *
 * Tokens are mirrored in memory for request headers and persisted in the device
 * keystore. `hydrate()` runs once at launch: it restores the token pair and then
 * asks the API who the user is (`GET /auth/me`), so a stale token can never put
 * the app into a fake signed-in state.
 */
export type SessionUser = {
  id: string;
  email: string;
  phone: string;
  full_name: string;
  profile_photo_url?: string | null;
  role: 'STUDENT' | 'TEACHER' | 'ADMIN';
  department: string;
  university_id: string;
  verification_status: 'UNVERIFIED' | 'PENDING' | 'VERIFIED' | 'REJECTED';
  account_status: 'ACTIVE' | 'SUSPENDED' | 'DEACTIVATED';
  rating_average: number;
  rating_count: number;
  completed_trips_count: number;
  email_verified_at?: string | null;
  created_at: string;
  student_profile?: { semester?: number | null; home_area?: string | null; degree_programme?: string | null } | null;
  teacher_profile?: { designation?: string | null; home_area?: string | null } | null;
};

type AuthState = {
  user: SessionUser | null;
  refreshToken: string | null;
  status: 'loading' | 'signedOut' | 'signedIn';
  hydrate: () => Promise<void>;
  completeSignIn: (response: authApi.AuthResponse) => Promise<void>;
  signOut: () => Promise<void>;
  updateUser: (user: SessionUser) => void;
};

type SetState = (partial: Partial<AuthState>) => void;

/** React 18 invokes effects twice in development; one hydrate, one `GET /auth/me`. */
let hydrateInFlight: Promise<void> | null = null;

async function runHydrate(set: SetState, get: () => AuthState): Promise<void> {
  let accessToken: string | null = null;
  let refreshToken: string | null = null;

  try {
    ({ accessToken, refreshToken } = await loadTokens());
  } catch {
    // Keystore unavailable: treat as signed out instead of hanging on the splash screen.
    set({ status: 'signedOut' });
    return;
  }

  if (!accessToken || !refreshToken) {
    set({ status: 'signedOut' });
    return;
  }

  setAccessToken(accessToken);
  setRefreshToken(refreshToken);
  set({ refreshToken });

  try {
    const user = await authApi.fetchMe();
    set({ user, status: 'signedIn' });
  } catch (error) {
    // "Cannot reach the API" is not "your session is invalid". Wiping the keystore here
    // signed the member out every time the laptop server happened to be down.
    const unreachable = error instanceof ApiError && error.code === 'NETWORK_ERROR';
    if (!unreachable) {
      await clearTokens().catch(() => undefined);
      setAccessToken(null);
      setRefreshToken(null);
    }
    set({ user: null, refreshToken: unreachable ? refreshToken : null, status: 'signedOut' });
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  refreshToken: null,
  status: 'loading',

  hydrate: () => {
    hydrateInFlight = hydrateInFlight ?? runHydrate(set, get);
    return hydrateInFlight;
  },

  completeSignIn: async (response) => {
    setAccessToken(response.access_token);
    setRefreshToken(response.refresh_token);
    try {
      await saveTokens(response.access_token, response.refresh_token);
    } catch {
      // Keystore write failed — the session still works until the app is closed.
    }
    resetQueryCache(); // a previous account's rides must never render for this one
    hydrateInFlight = null;
    set({ user: response.user, refreshToken: response.refresh_token, status: 'signedIn' });
  },

  signOut: async () => {
    // Offline, or a dead server, must never trap the member in a session: local state is
    // cleared in `finally`, and the server-side revoke is best-effort.
    try {
      await authApi.logout(get().refreshToken);
    } catch {
      // ignore — the token is discarded locally either way
    } finally {
      await clearTokens().catch(() => undefined);
      setAccessToken(null);
      setRefreshToken(null);
      resetQueryCache();
      hydrateInFlight = null;
      set({ user: null, refreshToken: null, status: 'signedOut' });
    }
  },

  updateUser: (user) => set({ user }),
}));

// A refresh failure anywhere in the app drops the user back to the auth flow.
onUnauthorized(() => {
  // The pair is dead server-side too, so the keystore and the cache must not keep it.
  void clearTokens().catch(() => undefined);
  resetQueryCache();
  hydrateInFlight = null;
  useAuthStore.setState({ user: null, refreshToken: null, status: 'signedOut' });
});
