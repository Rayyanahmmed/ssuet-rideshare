import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAdminAuth } from '@/store/auth';
import { useMe } from '@/api/queries';

/**
 * Admin-only gate (§17).
 *
 * Three checks, all server-backed:
 * 1. a token exists locally,
 * 2. `GET /auth/me` accepts it,
 * 3. the account role really is ADMIN — the API rejects non-admin tokens, and the
 *    client refuses to render the console even if one slipped through.
 */
export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { accessToken, status, hydrate, signOut } = useAdminAuth();
  const me = useMe(Boolean(accessToken));

  useEffect(() => {
    if (status === 'loading') hydrate();
  }, [status, hydrate]);


  const unauthorized = me.isError || (me.isSuccess && (me.data as { role?: string })?.role !== 'ADMIN');

  // Signing out is a side effect — never a state update during render.
  useEffect(() => {
    if (unauthorized) signOut();
  }, [unauthorized, signOut]);

  if (status === 'loading') {
    return <CenteredMessage text="Restoring session…" />;
  }
  if (!accessToken) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (me.isLoading) {
    return <CenteredMessage text="Checking administrator access…" />;
  }
  if (unauthorized) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

function CenteredMessage({ text }: { text: string }) {
  return (
    <div className="grid h-full place-items-center bg-canvas">
      <p className="text-sm text-muted">{text}</p>
    </div>
  );
}
