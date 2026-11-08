import { create } from 'zustand';

/**
 * Admin session.
 *
 * Tokens are held in memory and mirrored in `sessionStorage` (cleared when the
 * browser tab closes) so a page refresh does not sign the administrator out.
 * Production hardening (documented in documentation/06): move the refresh token
 * to an httpOnly, SameSite=Strict cookie issued by the API.
 *
 * Credentials are NEVER compiled into this bundle — login goes to
 * `POST /api/v1/auth/login` and the returned role must be ADMIN (§17).
 */
export type AdminUser = {
  id: string;
  full_name: string;
  email: string;
  role: 'STUDENT' | 'TEACHER' | 'ADMIN';
  department: string;
  account_status: string;
};

type AuthState = {
  user: AdminUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  status: 'loading' | 'signedOut' | 'signedIn';
  setSession: (user: AdminUser, accessToken: string, refreshToken: string) => void;
  setAccessToken: (token: string) => void;
  signOut: () => void;
  hydrate: () => void;
};

const ACCESS_KEY = 'ssuet.admin.access';
const REFRESH_KEY = 'ssuet.admin.refresh';

export const useAdminAuth = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  refreshToken: null,
  status: 'loading',

  setSession: (user, accessToken, refreshToken) => {
    sessionStorage.setItem(ACCESS_KEY, accessToken);
    sessionStorage.setItem(REFRESH_KEY, refreshToken);
    set({ user, accessToken, refreshToken, status: 'signedIn' });
  },

  setAccessToken: (token) => {
    sessionStorage.setItem(ACCESS_KEY, token);
    set({ accessToken: token });
  },

  signOut: () => {
    const refreshToken = get().refreshToken;
    if (refreshToken) {
      // best-effort server-side revocation
      void fetch(`${import.meta.env.VITE_API_BASE_URL || '/api/v1'}/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${get().accessToken ?? ''}` },
        body: JSON.stringify({ refresh_token: refreshToken }),
      }).catch(() => undefined);
    }
    sessionStorage.removeItem(ACCESS_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
    set({ user: null, accessToken: null, refreshToken: null, status: 'signedOut' });
  },

  hydrate: () => {
    const accessToken = sessionStorage.getItem(ACCESS_KEY);
    const refreshToken = sessionStorage.getItem(REFRESH_KEY);
    if (!accessToken || !refreshToken) {
      set({ status: 'signedOut' });
      return;
    }
    // The token is verified against /auth/me by the ProtectedRoute guard.
    set({ accessToken, refreshToken, status: 'signedIn' });
  },
}));
