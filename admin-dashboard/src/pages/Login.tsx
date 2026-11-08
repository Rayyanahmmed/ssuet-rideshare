import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { describeError } from '@/api/client';
import { useLogin } from '@/api/queries';
import { useAdminAuth } from '@/store/auth';

/** Administrator sign-in. Credentials live only in backend environment variables. */
export default function Login() {
  const navigate = useNavigate();
  const accessToken = useAdminAuth((state) => state.accessToken);
  const login = useLogin();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (accessToken) return <Navigate to="/" replace />;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await login.mutateAsync({ email: email.trim(), password });
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error && !('response' in err) ? err.message : describeError(err));
    }
  };

  return (
    <div className="flex min-h-full items-center justify-center bg-navy px-6 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl2 bg-brandgreen text-lg font-bold text-navy">
            S
          </div>
          <div>
            <p className="text-sm font-semibold text-white">SSUET RideShare</p>
            <p className="text-xs text-white/60">Administration console</p>
          </div>
        </div>

        <form onSubmit={submit} className="card space-y-4 p-6">
          <div>
            <h1 className="text-lg font-semibold">Sign in</h1>
            <p className="mt-1 text-xs text-muted">
              Administrator access only. Accounts are created from backend environment variables, never
              from this page.
            </p>
          </div>

          {error ? (
            <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-dangr">
              {error}
            </div>
          ) : null}

          <label className="block">
            <span className="stat-label">Email</span>
            <input
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 w-full rounded-lg border border-hairline px-3 py-2 text-sm outline-none focus:border-brandgreen"
              placeholder="admin@example.com"
            />
          </label>

          <label className="block">
            <span className="stat-label">Password</span>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 w-full rounded-lg border border-hairline px-3 py-2 text-sm outline-none focus:border-brandgreen"
              placeholder="••••••••"
            />
          </label>

          <button
            type="submit"
            disabled={login.isPending}
            className="w-full rounded-lg bg-brandgreen px-4 py-2.5 text-sm font-semibold text-navy transition hover:bg-brandgreen-dark hover:text-white disabled:opacity-50"
          >
            {login.isPending ? 'Signing in…' : 'Sign in'}
          </button>

          <p className="text-center text-[11px] text-muted">
            Sessions are stored in sessionStorage and revoked on sign-out.
          </p>
        </form>
      </div>
    </div>
  );
}
