import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { useAdminAuth } from '@/store/auth';

export function AppLayout() {
  const user = useAdminAuth((state) => state.user);
  const initials = (user?.full_name ?? 'SA')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');

  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-hairline bg-white px-8 py-4">
          <div>
            <h1 className="text-lg font-semibold">SSUET RideShare — Administration</h1>
            <p className="text-xs text-muted">
              Verified community · car &amp; bike pooling · Sir Syed University of Engineering &amp; Technology
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-brandgreen-tint px-3 py-1 text-xs font-semibold text-brandgreen-dark">
              <span className="badge-dot bg-brandgreen" aria-hidden /> Live data from the API
            </span>
            <div className="grid h-9 w-9 place-items-center rounded-full bg-navy text-xs font-bold text-white">
              {initials || 'SA'}
            </div>
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
