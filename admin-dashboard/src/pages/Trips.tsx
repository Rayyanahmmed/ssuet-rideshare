import { useState } from 'react';
import { useAdminTrips } from '@/api/admin';
import { InlineError, PageHeader, Pagination, StatusBadge, TableShell } from '@/components/ui';
import { dateTime } from '@/lib/format';

/**
 * Active and completed trips share one endpoint; the sidebar exposes two views.
 * There is no admin action here on purpose — trips are driven by their participants.
 */
export default function Trips({ mode }: { mode: 'active' | 'completed' }) {
  const [page, setPage] = useState(1);
  const params =
    mode === 'active'
      ? { active_only: true, page, limit: 20 }
      : { status: 'COMPLETED', page, limit: 20 };
  const trips = useAdminTrips(params);

  return (
    <div>
      <PageHeader
        title={mode === 'active' ? 'Active trips' : 'Completed trips'}
        subtitle={
          mode === 'active'
            ? 'Confirmed, in-progress and awaiting-completion journeys right now.'
            : 'Finished journeys with both participants confirmed.'
        }
      />

      <InlineError error={trips.error} />

      <TableShell
        headers={['Route', 'Driver', 'Passenger', 'Departure', 'Started', 'Completed', 'Status']}
        isLoading={trips.isLoading}
        error={trips.error}
        isEmpty={(trips.data?.items.length ?? 0) === 0}
        emptyTitle={mode === 'active' ? 'No journeys in motion' : 'No completed trips yet'}
        emptyMessage={
          mode === 'active'
            ? 'Trips appear here once a driver accepts a request and the member confirms.'
            : 'Completed trips are recorded when both participants confirm the journey is finished.'
        }
        footer={
          trips.data ? (
            <Pagination page={trips.data.page} pages={trips.data.pages} total={trips.data.total} onChange={setPage} />
          ) : null
        }
      >
        {trips.data?.items.map((trip) => (
          <tr key={trip.id} className="hover:bg-canvas/60">
            <td className="px-4 py-3">
              <p className="font-semibold">
                {trip.pickup_area || '—'} → {trip.destination_area || '—'}
              </p>
              <p className="text-xs text-muted">Trip {trip.id.slice(0, 8)}</p>
            </td>
            <td className="px-4 py-3 text-xs">{trip.driver_name}</td>
            <td className="px-4 py-3 text-xs">{trip.passenger_name}</td>
            <td className="px-4 py-3 text-xs text-muted">{dateTime(trip.departure_at)}</td>
            <td className="px-4 py-3 text-xs text-muted">{dateTime(trip.started_at)}</td>
            <td className="px-4 py-3 text-xs text-muted">{dateTime(trip.completed_at)}</td>
            <td className="px-4 py-3"><StatusBadge status={trip.status} /></td>
          </tr>
        ))}
      </TableShell>
    </div>
  );
}
