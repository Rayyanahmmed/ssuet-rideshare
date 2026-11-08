import { useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useAnalytics, useAdminActions } from '@/api/admin';
import { Field, InlineError, PageHeader, StatCard, StatusBadge, TableShell } from '@/components/ui';
import { dateTime, shortDay } from '@/lib/format';

const COLORS = ['#12B76A', '#17335A', '#F79009', '#D92D20', '#7C3AED', '#0EA5E9'];

/** Growth, demand and quality analytics — every series comes from `/admin/analytics`. */
export default function Analytics() {
  const [days, setDays] = useState(30);
  const [logPage, setLogPage] = useState(1);
  const analytics = useAnalytics(days);
  const actions = useAdminActions(logPage);

  const data = analytics.data;
  const toSeries = (points?: { day: string; count: number }[]) =>
    (points ?? []).map((point) => ({ day: shortDay(point.day), count: point.count }));
  const asPie = (record?: Record<string, number>) =>
    Object.entries(record ?? {}).map(([name, value]) => ({
      name: name.replaceAll('_', ' ').toLowerCase(),
      value,
    }));

  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Demand patterns, fuel-sharing mix and service quality across the platform."
        actions={
          <Field label="Window">
            <select className="input w-36" value={days} onChange={(event) => setDays(Number(event.target.value))}>
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
          </Field>
        }
      />

      <InlineError error={analytics.error} />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Completion rate" value={`${data?.completion_rate ?? 0}%`} hint="Completed / all trips" tone="ok" />
        <StatCard label="Cancellation rate" value={`${data?.cancellation_rate ?? 0}%`} hint="Cancelled / all trips" tone="warn" />
        <StatCard
          label="Average rating"
          value={data?.average_rating ? data.average_rating.toFixed(2) : '—'}
          hint="Post-trip reviews"
          tone="info"
        />
        <StatCard label="Fuel-shared rides" value={asPie(data?.fuel_split).find((item) => item.name === 'share fuel')?.value ?? 0} hint="Members splitting fuel" />
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="card p-5">
          <h3 className="stat-label">Signups over time</h3>
          <div className="mt-4 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={toSeries(data?.users_per_day)}>
                <defs>
                  <linearGradient id="aUsers" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#12B76A" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#12B76A" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#E3E9F2" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#5A6B85' }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#5A6B85' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ borderRadius: 12, borderColor: '#E3E9F2', fontSize: 12 }} />
                <Area type="monotone" dataKey="count" name="New members" stroke="#12B76A" fill="url(#aUsers)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-5">
          <h3 className="stat-label">Rides published over time</h3>
          <div className="mt-4 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={toSeries(data?.rides_per_day)}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E3E9F2" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#5A6B85' }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#5A6B85' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ borderRadius: 12, borderColor: '#E3E9F2', fontSize: 12 }} />
                <Line type="monotone" dataKey="count" name="Rides" stroke="#17335A" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-5">
          <h3 className="stat-label">Fuel preference</h3>
          <div className="mt-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={asPie(data?.fuel_split)} dataKey="value" nameKey="name" innerRadius={44} outerRadius={74} paddingAngle={2}>
                  {asPie(data?.fuel_split).map((entry, index) => (
                    <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 12, borderColor: '#E3E9F2', fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-5">
          <h3 className="stat-label">Vehicle mix &amp; direction of travel</h3>
          <div className="mt-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={[
                  ...asPie(data?.vehicle_split).map((item) => ({ name: `${item.name} rides`, value: item.value })),
                  ...asPie(data?.direction_split).map((item) => ({ name: item.name.replace(' to ', ' → '), value: item.value })),
                ]}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#E3E9F2" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#5A6B85' }} axisLine={false} tickLine={false} interval={0} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#5A6B85' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ borderRadius: 12, borderColor: '#E3E9F2', fontSize: 12 }} />
                <Bar dataKey="value" name="Rides" fill="#12B76A" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-5">
          <h3 className="stat-label">Busiest pickup areas</h3>
          <ul className="mt-3 space-y-2 text-sm">
            {(data?.top_pickup_areas ?? []).slice(0, 6).map((row) => (
              <li key={row.area} className="flex items-center justify-between rounded-xl bg-canvas px-3 py-2">
                <span>{row.area}</span>
                <span className="font-semibold tabular-nums">{row.count}</span>
              </li>
            ))}
            {(data?.top_pickup_areas ?? []).length === 0 ? <li className="text-xs text-muted">No rides yet.</li> : null}
          </ul>
        </div>

        <div className="card p-5">
          <h3 className="stat-label">Top destinations</h3>
          <ul className="mt-3 space-y-2 text-sm">
            {(data?.top_destinations ?? []).slice(0, 6).map((row) => (
              <li key={row.area} className="flex items-center justify-between rounded-xl bg-canvas px-3 py-2">
                <span>{row.area}</span>
                <span className="font-semibold tabular-nums">{row.count}</span>
              </li>
            ))}
            {(data?.top_destinations ?? []).length === 0 ? <li className="text-xs text-muted">No rides yet.</li> : null}
          </ul>
        </div>
      </section>

      <section className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Action history</h3>
          <div className="flex gap-2">
            <button type="button" className="btn-secondary" disabled={logPage <= 1} onClick={() => setLogPage((p) => p - 1)}>
              Previous
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={logPage >= (actions.data?.pages ?? 1)}
              onClick={() => setLogPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
        <TableShell
          headers={['Action', 'Target', 'Administrator', 'Notes', 'When']}
          isLoading={actions.isLoading}
          error={actions.error}
          isEmpty={(actions.data?.items.length ?? 0) === 0}
          emptyTitle="No administrative actions recorded"
          emptyMessage="Verifications, suspensions, vehicle reviews and ride cancellations are all written to this immutable log."
        >
          {actions.data?.items.map((action) => (
            <tr key={action.id} className="hover:bg-canvas/60">
              <td className="px-4 py-3"><StatusBadge status={action.action_type} /></td>
              <td className="px-4 py-3 text-xs">{action.target_user_name ?? action.entity_type ?? '—'}</td>
              <td className="px-4 py-3 text-xs">{action.admin_name ?? 'System'}</td>
              <td className="max-w-[320px] px-4 py-3 text-xs text-muted">{action.notes ?? '—'}</td>
              <td className="px-4 py-3 text-xs text-muted">{dateTime(action.created_at)}</td>
            </tr>
          ))}
        </TableShell>
      </section>
    </div>
  );
}
