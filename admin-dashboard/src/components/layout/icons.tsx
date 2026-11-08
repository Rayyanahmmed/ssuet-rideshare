/**
 * Inline SVG icon set for the console navigation.
 *
 * Inline strokes (rather than emoji or an icon package) keep the sidebar crisp at
 * any size, inherit `currentColor` for active states, and avoid an extra dependency
 * (§11 — no unnecessary dependencies).
 */
export type IconName =
  | 'dashboard'
  | 'users'
  | 'verification'
  | 'vehicle'
  | 'rides'
  | 'active'
  | 'completed'
  | 'reports'
  | 'suspended'
  | 'analytics'
  | 'map'
  | 'download'
  | 'settings'
  | 'logout';

const PATHS: Record<IconName, JSX.Element> = {
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="2" />
      <rect x="14" y="3" width="7" height="7" rx="2" />
      <rect x="3" y="14" width="7" height="7" rx="2" />
      <rect x="14" y="14" width="7" height="7" rx="2" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
      <path d="M16 5.6a3.2 3.2 0 0 1 0 6.1" />
      <path d="M17.5 14.4A5.1 5.1 0 0 1 20.5 19" />
    </>
  ),
  verification: (
    <>
      <path d="M12 3.2 19 6v5.4c0 4.2-2.8 7.1-7 9.4-4.2-2.3-7-5.2-7-9.4V6z" />
      <path d="m9 12 2.2 2.2L15.4 10" />
    </>
  ),
  vehicle: (
    <>
      <path d="M4 16v-3.2L6 8h12l2 4.8V16" />
      <path d="M4 16h16" />
      <circle cx="7.5" cy="17.5" r="1.6" />
      <circle cx="16.5" cy="17.5" r="1.6" />
      <path d="M6.5 12h11" />
    </>
  ),
  rides: (
    <>
      <circle cx="6" cy="6" r="2.4" />
      <circle cx="18" cy="18" r="2.4" />
      <path d="M8.4 6h5.1a3 3 0 0 1 0 6H10a3 3 0 0 0 0 6h5.6" />
    </>
  ),
  active: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m10.2 9 5 3-5 3z" />
    </>
  ),
  completed: (
    <>
      <path d="M6 21V4" />
      <path d="M6 5h10.5l-1.6 3.4L16.5 12H6z" />
    </>
  ),
  reports: (
    <>
      <path d="M12 4.5 21 19.5H3z" />
      <path d="M12 10v4" />
      <circle cx="12" cy="17" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  suspended: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m6.4 17.6 11.2-11.2" />
    </>
  ),
  analytics: (
    <>
      <path d="M4 20h16" />
      <path d="M7 20v-6" />
      <path d="M12 20V7" />
      <path d="M17 20v-9" />
    </>
  ),
  map: (
    <>
      <path d="M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20z" />
      <path d="M9 4v13.5M15 6.5V20" />
    </>
  ),
  download: (
    <>
      <path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" />
      <path d="M5 19.5h14" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v2.4M12 18.6V21M4.2 7.5l2 1.2M17.8 15.3l2 1.2M4.2 16.5l2-1.2M17.8 8.7l2-1.2" />
    </>
  ),
  logout: (
    <>
      <path d="M14 4H6a1.6 1.6 0 0 0-1.6 1.6v12.8A1.6 1.6 0 0 0 6 20h8" />
      <path d="M15 8.5 18.5 12 15 15.5" />
      <path d="M9.5 12h9" />
    </>
  ),
};

export function Icon({ name, className = 'h-[18px] w-[18px]' }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {PATHS[name]}
    </svg>
  );
}
