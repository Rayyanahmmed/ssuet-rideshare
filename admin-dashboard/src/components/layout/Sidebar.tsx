import { NavLink } from 'react-router-dom';
import { Icon, type IconName } from './icons';
import { useAdminAuth } from '@/store/auth';

export type NavItem = { to: string; label: string; icon: IconName };

/** Sidebar structure mirrors §16 exactly. */
export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: 'dashboard' },
  { to: '/users', label: 'Users', icon: 'users' },
  { to: '/verifications', label: 'Verification Requests', icon: 'verification' },
  { to: '/vehicles', label: 'Vehicle Verification', icon: 'vehicle' },
  { to: '/rides', label: 'Published Rides', icon: 'rides' },
  { to: '/trips/active', label: 'Active Trips', icon: 'active' },
  { to: '/trips/completed', label: 'Completed Trips', icon: 'completed' },
  { to: '/reports', label: 'Reports & Complaints', icon: 'reports' },
  { to: '/suspended', label: 'Suspended Accounts', icon: 'suspended' },
  { to: '/analytics', label: 'Analytics', icon: 'analytics' },
  { to: '/map-api', label: 'Map API', icon: 'map' },
  { to: '/app-download', label: 'App download', icon: 'download' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
];

export function Sidebar() {
  const user = useAdminAuth((state) => state.user);
  const signOut = useAdminAuth((state) => state.signOut);

  return (
    <aside className="flex w-72 shrink-0 flex-col bg-navy text-white">
      <div className="flex items-center gap-3 px-6 py-6">
        <div className="grid h-10 w-10 place-items-center rounded-xl2 bg-brandgreen text-lg font-bold text-navy">
          S
        </div>
        <div>
          <p className="text-sm font-semibold leading-tight">SSUET RideShare</p>
          <p className="text-xs text-white/60">Admin Console</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors',
                isActive ? 'bg-white/10 font-semibold text-white' : 'text-white/70 hover:bg-white/5 hover:text-white',
              ].join(' ')
            }
          >
            <Icon name={item.icon} className="h-[18px] w-[18px] shrink-0" />
            <span className="flex-1">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-white/10 px-3 py-3">
        <div className="mb-2 px-3">
          <p className="truncate text-xs font-semibold text-white">{user?.full_name ?? 'Administrator'}</p>
          <p className="truncate text-[11px] text-white/50">{user?.email ?? ''}</p>
        </div>
        <button
          type="button"
          onClick={signOut}
          className="w-full rounded-lg px-3 py-2.5 text-left text-sm text-white/70 transition-colors hover:bg-white/5 hover:text-white"
        >
          <span className="flex items-center gap-3">
            <Icon name="logout" className="h-[18px] w-[18px]" /> Logout
          </span>
        </button>
      </div>
    </aside>
  );
}
