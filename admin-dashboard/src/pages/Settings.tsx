import { useHealth, useMeta } from '@/api/queries';
import { useSettings } from '@/api/admin';
import { InlineError, PageHeader } from '@/components/ui';
import { useAdminAuth } from '@/store/auth';

/**
 * Read-only operational settings.
 *
 * Secrets are never rendered: the API only exposes booleans describing whether a
 * capability is configured (§19). Changing configuration happens through the
 * environment, which keeps credentials out of the browser entirely.
 */
export default function Settings() {
  const settings = useSettings();
  const health = useHealth();
  const meta = useMeta();
  const user = useAdminAuth((state) => state.user);

  const rows: [string, string][] = settings.data
    ? [
        ['Environment', settings.data.environment],
        ['API version', settings.data.api_version],
        ['University', meta.data?.university.name ?? '—'],
        ['Campus area', meta.data?.university.default_area_label ?? '—'],
        ['Accepted email domains', settings.data.university_domains.join(', ') || '—'],
        ['Auto-verify university emails', settings.data.auto_verify_university_emails ? 'Enabled' : 'Disabled'],
        ['Confirmed passengers per ride', String(settings.data.max_confirmed_passengers)],
        ['Ride auto-expire grace', `${settings.data.ride_auto_expire_grace_minutes} minutes`],
        ['Maintenance sweep interval', `${settings.data.maintenance_interval_minutes} minutes`],
        [
          'Map tiles',
          settings.data.maps_configured
            ? 'Provided by the Map API tab (server-side key)'
            : 'OpenStreetMap default — no key needed',
        ],
        ['Email (SMTP)', settings.data.smtp_configured ? 'Configured' : 'Not configured'],
        ['Expo push notifications', settings.data.expo_push_enabled ? 'Enabled' : 'Disabled'],
        ['Rate limiting', settings.data.rate_limit_enabled ? 'Enabled' : 'Disabled'],
        ['Admin bootstrap on start', settings.data.admin_bootstrap_enabled ? 'Enabled' : 'Disabled'],
      ]
    : [];

  return (
    <div>
      <PageHeader
        title="Settings"
        subtitle="Effective runtime configuration. Values are read from the server environment — never editable from the browser."
      />

      <InlineError error={settings.error} />

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card p-6 lg:col-span-2">
          <h3 className="stat-label">Platform configuration</h3>
          {settings.isLoading ? (
            <p className="mt-4 text-sm text-muted">Loading…</p>
          ) : (
            <dl className="mt-4 divide-y divide-hairline text-sm">
              {rows.map(([label, value]) => (
                <div key={label} className="flex items-start justify-between gap-6 py-2.5">
                  <dt className="text-muted">{label}</dt>
                  <dd className="text-right font-medium">{value}</dd>
                </div>
              ))}
            </dl>
          )}
          <p className="mt-4 rounded-xl2 bg-canvas p-3 text-xs text-muted">
            To change any of these, edit <code>backend/.env</code> and restart the API. Passwords, JWT keys and API
            keys are never sent to this console — the map provider is the one exception, and it has its own tab
            (<strong>Map API</strong>) where the key can be rotated without rebuilding the app.
          </p>
        </section>

        <section className="space-y-6">
          <div className="card p-6">
            <h3 className="stat-label">Signed in as</h3>
            <p className="mt-2 text-sm font-semibold">{user?.full_name ?? 'Administrator'}</p>
            <p className="text-xs text-muted">{user?.email}</p>
            <p className="mt-3 inline-flex rounded-full bg-brandgreen-tint px-2.5 py-1 text-[11px] font-semibold text-brandgreen-dark">
              {user?.role ?? 'ADMIN'}
            </p>
          </div>

          <div className="card p-6">
            <h3 className="stat-label">Service health</h3>
            <ul className="mt-3 space-y-2 text-sm">
              <li className="flex items-center justify-between">
                <span className="text-muted">API</span>
                <span className="font-medium">{health.isError ? 'Unreachable' : `Online v${health.data?.version ?? '—'}`}</span>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-muted">Environment</span>
                <span className="font-medium">{health.data?.environment ?? '—'}</span>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-muted">Push (mobile)</span>
                <span className="font-medium">{meta.data?.features.push_notifications ? 'Enabled' : 'Disabled'}</span>
              </li>
            </ul>
          </div>

          <div className="card p-6">
            <h3 className="stat-label">Non-payment platform</h3>
            <p className="mt-2 text-xs text-muted">
              SSUET RideShare processes no payments. Fuel sharing is arranged in cash between members and is never
              recorded as platform revenue.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
