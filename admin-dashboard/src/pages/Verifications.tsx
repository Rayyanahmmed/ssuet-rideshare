import { useState } from 'react';
import { useRejectUser, useVerifications, useVerifyUser } from '@/api/admin';
import { describeError } from '@/api/client';
import { openMediaDocument } from '@/lib/media';
import {
  InlineError,
  PageHeader,
  Pagination,
  ReasonDialog,
  StatusBadge,
  TableShell,
} from '@/components/ui';
import { dateTime, label } from '@/lib/format';

/** Verification queue — university IDs, documents and pending member accounts. */
export default function Verifications() {
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<{ id: string; name: string; kind: 'verify' | 'reject' } | null>(null);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);

  const queue = useVerifications({ status: 'PENDING', page, limit: 20 });
  const verify = useVerifyUser();
  const reject = useRejectUser();

  return (
    <div>
      <PageHeader
        title="Verification requests"
        subtitle="Members are auto-verified when they register with a university email; everyone else is reviewed here."
      />

      <InlineError error={verify.error ?? reject.error ?? documentError} />

      <TableShell
        headers={['Member', 'Type', 'Submitted value', 'Document', 'Submitted', 'Status', '']}
        isLoading={queue.isLoading}
        error={queue.error}
        isEmpty={(queue.data?.items.length ?? 0) === 0}
        emptyTitle="The verification queue is clear"
        emptyMessage="No member is currently waiting for review. New submissions appear here instantly."
        footer={
          queue.data ? (
            <Pagination page={queue.data.page} pages={queue.data.pages} total={queue.data.total} onChange={setPage} />
          ) : null
        }
      >
        {queue.data?.items.map((item) => (
          <tr key={item.id} className="hover:bg-canvas/60">
            <td className="px-4 py-3">
              <p className="font-semibold">{item.user_name}</p>
              <p className="text-xs text-muted">{item.user_email}</p>
              <p className="text-xs text-muted">
                {item.department || '—'} · {item.university_id || '—'}
              </p>
            </td>
            <td className="px-4 py-3 text-xs">{label(item.verification_type)}</td>
            <td className="px-4 py-3 text-xs">{item.submitted_value || '—'}</td>
            <td className="px-4 py-3 text-xs">
              {item.document_asset_id ? (
                <button
                  type="button"
                  className="text-brandgreen-dark underline disabled:opacity-60"
                  disabled={opening === item.document_asset_id}
                  onClick={async () => {
                    setDocumentError(null);
                    setOpening(item.document_asset_id);
                    try {
                      await openMediaDocument(item.document_asset_id as string);
                    } catch (error) {
                      setDocumentError(describeError(error));
                    } finally {
                      setOpening(null);
                    }
                  }}
                >
                  {opening === item.document_asset_id ? 'Opening…' : 'View upload'}
                </button>
              ) : item.document_url ? (
                <a className="text-brandgreen-dark underline" href={item.document_url} target="_blank" rel="noreferrer">
                  Open link
                </a>
              ) : (
                '—'
              )}
            </td>
            <td className="px-4 py-3 text-xs text-muted">{dateTime(item.created_at)}</td>
            <td className="px-4 py-3"><StatusBadge status={item.status} /></td>
            <td className="px-4 py-3">
              <div className="flex justify-end gap-1">
                <button
                  type="button"
                  className="btn-ghost text-brandgreen-dark"
                  onClick={() => setPending({ id: item.user_id, name: item.user_name, kind: 'verify' })}
                >
                  Approve
                </button>
                <button
                  type="button"
                  className="btn-ghost text-dangr"
                  onClick={() => setPending({ id: item.user_id, name: item.user_name, kind: 'reject' })}
                >
                  Reject
                </button>
              </div>
            </td>
          </tr>
        ))}
      </TableShell>

      <ReasonDialog
        open={pending !== null}
        title={pending?.kind === 'verify' ? `Approve ${pending?.name}?` : `Reject ${pending?.name}?`}
        description="The member is notified and the decision is written to the audit log."
        confirmLabel={pending?.kind === 'verify' ? 'Approve' : 'Reject'}
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
