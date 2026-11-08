import { useState } from 'react';
import { useAdminVehicles, useRejectVehicle, useVerifyVehicle } from '@/api/admin';
import { describeError } from '@/api/client';
import { openMediaDocument } from '@/lib/media';
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

/** Vehicle verification — a ride can only be published with a VERIFIED vehicle. */
export default function Vehicles() {
  const [status, setStatus] = useState('PENDING');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<{ id: string; name: string; kind: 'verify' | 'reject' } | null>(null);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);

  const openDocument = async (assetId: string) => {
    setDocumentError(null);
    setOpening(assetId);
    try {
      await openMediaDocument(assetId);
    } catch (error) {
      setDocumentError(describeError(error));
    } finally {
      setOpening(null);
    }
  };

  const vehicles = useAdminVehicles({ status, search, page, limit: 20 });
  const verify = useVerifyVehicle();
  const reject = useRejectVehicle();

  return (
    <div>
      <PageHeader
        title="Vehicle verification"
        subtitle="Registration details are checked here. A rejected vehicle can never be used; set REQUIRE_VERIFIED_VEHICLE_FOR_PUBLISH=true to require approval before the first ride."
      />

      <Filters>
        <Field label="Queue">
          <select
            className="input w-40"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
          >
            <option value="PENDING">Pending</option>
            <option value="VERIFIED">Verified</option>
            <option value="REJECTED">Rejected</option>
            <option value="">All vehicles</option>
          </select>
        </Field>
        <Field label="Search">
          <input
            className="input w-64"
            placeholder="Registration number, model or owner"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </Field>
      </Filters>

      <InlineError error={verify.error ?? reject.error ?? documentError} />

      <TableShell
        headers={['Vehicle', 'Owner', 'Proof', 'Type', 'Capacity', 'Status', 'Review note', 'Registered', '']}
        isLoading={vehicles.isLoading}
        error={vehicles.error}
        isEmpty={(vehicles.data?.items.length ?? 0) === 0}
        emptyTitle="Nothing in this queue"
        emptyMessage="No vehicles match the current filter. Switch the queue filter to see verified or rejected vehicles."
        footer={
          vehicles.data ? (
            <Pagination page={vehicles.data.page} pages={vehicles.data.pages} total={vehicles.data.total} onChange={setPage} />
          ) : null
        }
      >
        {vehicles.data?.items.map((vehicle) => (
          <tr key={vehicle.id} className="hover:bg-canvas/60">
            <td className="px-4 py-3">
              <p className="font-semibold">
                {vehicle.make_and_model} · {vehicle.color}
              </p>
              <p className="text-xs uppercase tracking-wide text-muted">{vehicle.registration_number}</p>
            </td>
            <td className="px-4 py-3 text-xs">{vehicle.owner_name}</td>
            <td className="px-4 py-3 text-xs">
              <div className="flex flex-col gap-0.5">
                {vehicle.photo_asset_id ? (
                  <button
                    type="button"
                    className="text-left text-brandgreen-dark underline disabled:opacity-60"
                    disabled={opening === vehicle.photo_asset_id}
                    onClick={() => openDocument(vehicle.photo_asset_id as string)}
                  >
                    {opening === vehicle.photo_asset_id ? 'Opening…' : 'Vehicle photo'}
                  </button>
                ) : vehicle.vehicle_photo_url ? (
                  <a className="text-brandgreen-dark underline" href={vehicle.vehicle_photo_url} target="_blank" rel="noreferrer">
                    Photo link
                  </a>
                ) : null}
                {vehicle.registration_asset_id ? (
                  <button
                    type="button"
                    className="text-left text-brandgreen-dark underline disabled:opacity-60"
                    disabled={opening === vehicle.registration_asset_id}
                    onClick={() => openDocument(vehicle.registration_asset_id as string)}
                  >
                    {opening === vehicle.registration_asset_id ? 'Opening…' : 'Registration book'}
                  </button>
                ) : null}
                {!vehicle.photo_asset_id && !vehicle.registration_asset_id && !vehicle.vehicle_photo_url ? '—' : null}
              </div>
            </td>
            <td className="px-4 py-3 text-xs">{label(vehicle.vehicle_type)}</td>
            <td className="px-4 py-3 text-xs tabular-nums">{vehicle.passenger_capacity}</td>
            <td className="px-4 py-3"><StatusBadge status={vehicle.status} /></td>
            <td className="max-w-[220px] px-4 py-3 text-xs text-muted">{vehicle.review_note || '—'}</td>
            <td className="px-4 py-3 text-xs text-muted">{dateTime(vehicle.created_at)}</td>
            <td className="px-4 py-3">
              <div className="flex justify-end gap-1">
                {vehicle.status !== 'VERIFIED' ? (
                  <button
                    type="button"
                    className="btn-ghost text-brandgreen-dark"
                    onClick={() => setPending({ id: vehicle.id, name: `${vehicle.make_and_model} (${vehicle.owner_name})`, kind: 'verify' })}
                  >
                    Approve
                  </button>
                ) : null}
                {vehicle.status !== 'REJECTED' ? (
                  <button
                    type="button"
                    className="btn-ghost text-dangr"
                    onClick={() => setPending({ id: vehicle.id, name: `${vehicle.make_and_model} (${vehicle.owner_name})`, kind: 'reject' })}
                  >
                    Reject
                  </button>
                ) : null}
              </div>
            </td>
          </tr>
        ))}
      </TableShell>

      <ReasonDialog
        open={pending !== null}
        title={pending?.kind === 'verify' ? `Approve ${pending?.name}?` : `Reject ${pending?.name}?`}
        description="Approval lets the owner publish rides with this vehicle. Rejection requires a reason for the member."
        confirmLabel={pending?.kind === 'verify' ? 'Approve vehicle' : 'Reject vehicle'}
        requireReason={pending?.kind === 'reject'}
        tone={pending?.kind === 'reject' ? 'danger' : 'primary'}
        busy={verify.isPending || reject.isPending}
        onCancel={() => setPending(null)}
        onConfirm={(reason) => {
          if (!pending) return;
          const done = () => setPending(null);
          if (pending.kind === 'verify') verify.mutate({ id: pending.id, note: reason || undefined }, { onSuccess: done });
          else reject.mutate({ id: pending.id, reason }, { onSuccess: done });
        }}
      />
    </div>
  );
}
