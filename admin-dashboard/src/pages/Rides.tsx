import { useState } from 'react';
import { useAdminRides, useCancelRide } from '@/api/admin';
import {
  Field,
  Filters,
  InlineError,
  PageHeader,
  Pagination,
  ReasonDialog,
  StatusBadge,
  TableShell,
} from '@/components/ui';
import { dateTime, label } from '@/lib/format';

/** Every published ride, with the ability to force-cancel an unsafe journey. */
export default function Rides() {
  const [status, setStatus] = useState('');
  const [direction, setDirection] = useState('');
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);
  const [cancelTarget, setCancelTarget] = useState<{ id: string; label: string } | null>(null);

  const rides = useAdminRides({ status, direction, search, date_from: dateFrom, date_to: dateTo, page, limit: 20 });
  const cancelRide = useCancelRide();

  const reset = () => {
    setStatus('');
    setDirection('');
    setSearch('');
    setDateFrom('');
    setDateTo('');
    setPage(1);
  };

  return (
    <div>
      <PageHeader
        title="Published rides"
        subtitle="One confirmed passenger per ride is enforced by the database; admins can cancel a ride at any time."
        actions={
          <button type="button" className="btn-secondary" onClick={reset}>
            Reset filters
          </button>
        }
      />

      <Filters>
        <Field label="Status">
          <select className="input w-40" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
            <option value="">Any status</option>
            <option value="OPEN">Open</option>
            <option value="MATCHED">Matched</option>
            <option value="IN_PROGRESS">In progress</option>
            <option value="COMPLETED">Completed</option>
            <option value="CANCELLED">Cancelled</option>
            <option value="EXPIRED">Expired</option>
          </select>
        </Field>
        <Field label="Direction">
          <select className="input w-52" value={direction} onChange={(event) => { setDirection(event.target.value); setPage(1); }}>
            <option value="">Both directions</option>
            <option value="HOME_TO_UNIVERSITY">Home → University</option>
            <option value="UNIVERSITY_TO_HOME">University → Home</option>
          </select>
        </Field>
        <Field label="Search area or driver">
          <input className="input w-56" placeholder="Pickup, destination, driver" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} />
        </Field>
        <Field label="From">
          <input type="date" className="input w-40" value={dateFrom} onChange={(event) => { setDateFrom(event.target.value); setPage(1); }} />
        </Field>
        <Field label="To">
          <input type="date" className="input w-40" value={dateTo} onChange={(event) => { setDateTo(event.target.value); setPage(1); }} />
        </Field>
      </Filters>

      <InlineError error={cancelRide.error} />

      <TableShell
        headers={['Route', 'Driver', 'Departure', 'Fuel', 'Requests', 'Status', '']}
        isLoading={rides.isLoading}
        error={rides.error}
        isEmpty={(rides.data?.items.length ?? 0) === 0}
        emptyTitle="No rides match this view"
        emptyMessage="Rides appear here as soon as a verified member publishes one."
        footer={
          rides.data ? (
            <Pagination page={rides.data.page} pages={rides.data.pages} total={rides.data.total} onChange={setPage} />
          ) : null
        }
      >
        {rides.data?.items.map((ride) => (
          <tr key={ride.id} className="hover:bg-canvas/60">
            <td className="px-4 py-3">
              <p className="font-semibold">
                {ride.pickup_area} → {ride.destination_area}
              </p>
              <p className="text-xs text-muted">{label(ride.direction)}</p>
            </td>
            <td className="px-4 py-3 text-xs">
              <p>{ride.driver_name}</p>
              {ride.matched_passenger_name ? (
                <p className="text-muted">with {ride.matched_passenger_name}</p>
              ) : null}
            </td>
            <td className="px-4 py-3 text-xs text-muted">{dateTime(ride.departure_at)}</td>
            <td className="px-4 py-3 text-xs">{label(ride.fuel_preference)}</td>
            <td className="px-4 py-3 text-xs tabular-nums">{ride.requests_count}</td>
            <td className="px-4 py-3"><StatusBadge status={ride.status} /></td>
            <td className="px-4 py-3 text-right">
              {['OPEN', 'MATCHED', 'IN_PROGRESS'].includes(ride.status) ? (
                <button
                  type="button"
                  className="btn-ghost text-dangr"
                  onClick={() => setCancelTarget({ id: ride.id, label: `${ride.pickup_area} → ${ride.destination_area} by ${ride.driver_name}` })}
                >
                  Cancel ride
                </button>
              ) : (
                <span className="text-xs text-muted">—</span>
              )}
            </td>
          </tr>
        ))}
      </TableShell>

      <ReasonDialog
        open={cancelTarget !== null}
        title="Force-cancel this ride?"
        description={`${cancelTarget?.label ?? ''}. Any confirmed passenger is notified and the trip is cancelled.`}
        confirmLabel="Cancel ride"
        requireReason
        busy={cancelRide.isPending}
        onCancel={() => setCancelTarget(null)}
        onConfirm={(reason) =>
          cancelRide.mutate({ id: cancelTarget!.id, reason }, { onSuccess: () => setCancelTarget(null) })
        }
      />
    </div>
  );
}
