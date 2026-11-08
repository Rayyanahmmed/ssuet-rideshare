import { Link } from 'react-router-dom';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useAdminActions, useDashboard } from '@/api/admin';
import { PageHeader, StatCard, StatusBadge, InlineError } from '@/components/ui';
import { relative, shortDay } from '@/lib/format';
import { useHealth } from '@/api/queries';

const PIE_COLORS = ['#12B76A', '#17335A', '#F79009', '#D92D20', '#7C3AED', '#0EA5E9'];

/** Real aggregates from GET /api/v1/admin/dashboard — computed by SQL, not the browser. */
export default function Dashboard() {
  const dashboard = useDashboard();
  const actions = useAdminActions(1);
  const health = useHealth();

  const stats = dashboard.data?.stats;
  const toChart = (points?: { day: string; count: number }[]) =>
    (points ?? []).map((point) => ({ day: shortDay(point.day), count: point.count }));

  const tripsByStatus = Object.entries(dashboard.data?.trips_by_status ?? {}).map(([name, value]) => ({
    name: name.replaceAll('_', ' ').toLowerCase(),
    value,
  }));

  return (
    <div>
      <PageHeader
        title="Operations overview"
        subtitle="Live platform health, verification queues and trip throughput."
        actions={
          <span className="rounded-full bg-brandgreen-tint px-3 py-1 text-xs font-semibold text-brandgreen-dark">
            API {health.data ? `v${health.data.version}` : '—'} · {health.data?.environment ?? '—'}
          </span>
        }
      />

      <InlineError error={dashboard.error} />

      {dashboard.isLoading || !stats ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="card h-28 animate-pulse bg-white" />
          ))}
        </div>
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Members"
              value={stats.total_users}
              hint={`${stats.verified_users} verified`}
              tone="info"
            />
            <StatCard
              label="Pending verifications"
              value={stats.pending_verifications}
              hint={stats.pending_verifications ? 'Action needed' : 'Queue clear'}
              tone={stats.pending_verifications ? 'warn' : 'ok'}
            />
            <StatCard
              label="Vehicles awaiting review"
              value={stats.pending_vehicles}
              hint={stats.pending_vehicles ? 'Action needed' : 'Queue clear'}
              tone={stats.pending_vehicles ? 'warn' : 'ok'}
            />
            <StatCard
              label="Suspended accounts"
              value={stats.suspended_accounts}
              hint="Restricted access"
              tone={stats.suspended_accounts ? 'danger' : 'ok'}
            />
            <StatCard label="Published rides" value={stats.published_rides} hint={`${stats.open_rides} open now`} />
            <StatCard label="Active trips" value={stats.active_trips} hint={`${stats.trips_today} today`} />
            <StatCard
              label="Completed trips"
              value={stats.completed_trips}
              hint="All time"
              tone="ok"
            />
            <StatCard
              label="Open reports"
              value={stats.open_reports}
              hint={stats.open_reports ? 'Needs review' : 'All handled'}
              tone={stats.open_reports ? 'danger' : 'ok'}
            />
          </section>

          <section className="mt-6 grid gap-6 lg:grid-cols-3">
            <div className="card p-5 lg:col-span-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">
                Signups vs rides — last 14 days
              </h3>
              <div className="mt-4 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={toChart(dashboard.data?.users_per_day).map((point, index) => ({
                      ...point,
                      rides: toChart(dashboard.data?.rides_per_day)[index]?.count ?? 0,
                    }))}
                  >
                    <defs>
                      <linearGradient id="usersFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#12B76A" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#12B76A" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="ridesFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#17335A" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="#17335A" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E3E9F2" vertical={false} />
                    <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#5A6B85' }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#5A6B85' }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ borderRadius: 12, borderColor: '#E3E9F2', fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area type="monotone" dataKey="count" name="New members" stroke="#12B76A" fill="url(#usersFill)" strokeWidth={2} />
                    <Area type="monotone" dataKey="rides" name="Rides published" stroke="#17335A" fill="url(#ridesFill)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card p-5">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Trips by status</h3>
              {tripsByStatus.length === 0 ? (
                <p className="mt-10 text-center text-xs text-muted">No trips recorded yet.</p>
              ) : (
                <div className="mt-2 h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={tripsByStatus} dataKey="value" nameKey="name" innerRadius={48} outerRadius={78} paddingAngle={2}>
                        {tripsByStatus.map((entry, index) => (
                          <Cell key={entry.name} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ borderRadius: 12, borderColor: '#E3E9F2', fontSize: 12 }} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </section>

          <section className="mt-6 grid gap-6 lg:grid-cols-3">
            <div className="card p-5">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Rides by status</h3>
              <div className="mt-4 h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={Object.entries(dashboard.data?.rides_by_status ?? {}).map(([name, value]) => ({
                      name: name.replaceAll('_', ' ').toLowerCase(),
                      value,
                    }))}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#E3E9F2" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#5A6B85' }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#5A6B85' }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ borderRadius: 12, borderColor: '#E3E9F2', fontSize: 12 }} />
                    <Bar dataKey="value" name="Rides" fill="#12B76A" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card p-5 lg:col-span-2">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Recent admin activity</h3>
                <Link to="/analytics" className="btn-ghost">
                  Analytics →
                </Link>
              </div>
              {actions.isLoading ? (
                <p className="mt-6 text-xs text-muted">Loading…</p>
              ) : (actions.data?.items.length ?? 0) === 0 ? (
                <p className="mt-6 text-xs text-muted">
                  No administrative actions yet. Every verification, suspension and cancellation is recorded here.
                </p>
              ) : (
                <ul className="mt-3 divide-y divide-hairline text-sm">
                  {actions.data?.items.slice(0, 6).map((action) => (
                    <li key={action.id} className="flex items-center justify-between gap-3 py-2.5">
                      <div className="min-w-0">
                        <p className="truncate font-medium">
                          <StatusBadge status={action.action_type} />{' '}
                          <span className="text-muted">
                            {action.target_user_name ? `· ${action.target_user_name}` : ''}
                          </span>
                        </p>
                        <p className="truncate text-xs text-muted">
                          {action.admin_name ?? 'System'} {action.notes ? `— ${action.notes}` : ''}
                        </p>
                      </div>
                      <span className="shrink-0 text-xs text-muted">{relative(action.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
