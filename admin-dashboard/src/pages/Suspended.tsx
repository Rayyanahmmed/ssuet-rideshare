import { useState } from 'react';
import { useAdminUsers, useReactivateUser, useSuspendUser } from '@/api/admin';
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
import { dateOnly, dateTime } from '@/lib/format';

/** Suspended accounts: the single place where access restrictions are lifted. */
export default function Suspended() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [target, setTarget] = useState<{ id: string; name: string } | null>(null);

  const users = useAdminUsers({ status: 'SUSPENDED', search, page, limit: 20 });
  const reactivate = useReactivateUser();
  const suspend = useSuspendUser();

  return (
    <div>
      <PageHeader
        title="Suspended accounts"
        subtitle="Suspended members cannot sign in or use the API. Reactivation restores access immediately."
      />

      <Filters>
        <Field label="Search">
          <input
            className="input w-64"
            placeholder="Name, email or university ID"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </Field>
      </Filters>

      <InlineError error={reactivate.error ?? suspend.error} />

      <TableShell
        headers={['Member', 'Department', 'Role', 'Joined', 'Last login', 'Status', '']}
        isLoading={users.isLoading}
        error={users.error}
        isEmpty={(users.data?.items.length ?? 0) === 0}
        emptyTitle="No suspended accounts"
        emptyMessage="Nobody is currently restricted. Suspensions made from Users or Reports appear here."
        footer={
          users.data ? (
            <Pagination page={users.data.page} pages={users.data.pages} total={users.data.total} onChange={setPage} />
          ) : null
        }
      >
        {users.data?.items.map((user) => (
          <tr key={user.id} className="hover:bg-canvas/60">
            <td className="px-4 py-3">
              <p className="font-semibold">{user.full_name}</p>
              <p className="text-xs text-muted">{user.email}</p>
            </td>
            <td className="px-4 py-3 text-xs">{user.department || '—'}</td>
            <td className="px-4 py-3 text-xs">{user.role}</td>
            <td className="px-4 py-3 text-xs text-muted">{dateOnly(user.created_at)}</td>
            <td className="px-4 py-3 text-xs text-muted">{user.last_login_at ? dateTime(user.last_login_at) : '—'}</td>
            <td className="px-4 py-3"><StatusBadge status={user.account_status} /></td>
            <td className="px-4 py-3 text-right">
              <button
                type="button"
                className="btn-ghost text-brandgreen-dark"
                onClick={() => setTarget({ id: user.id, name: user.full_name })}
              >
                Reactivate
              </button>
            </td>
          </tr>
        ))}
      </TableShell>

      <ReasonDialog
        open={target !== null}
        title={`Reactivate ${target?.name ?? ''}?`}
        description="Full access is restored and the member receives a notification."
        confirmLabel="Reactivate"
        requireReason={false}
        tone="primary"
        busy={reactivate.isPending}
        onCancel={() => setTarget(null)}
        onConfirm={() => reactivate.mutate({ id: target!.id }, { onSuccess: () => setTarget(null) })}
      />
    </div>
  );
}
