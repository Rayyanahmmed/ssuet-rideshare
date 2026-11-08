import { useState } from 'react';
import {
  useAdminUser,
  useAdminUsers,
  useRejectUser,
  useIssuePasswordResetCode,
  type PasswordResetCode,
  useReactivateUser,
  useSuspendUser,
  useVerifyUser,
  type AdminUser,
} from '@/api/admin';
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
import { MemberAvatar } from '@/components/MemberAvatar';
import { dateOnly, dateTime, label } from '@/lib/format';

type Action = { kind: 'verify' | 'reject' | 'suspend' | 'reactivate'; user: AdminUser } | null;

/** Members directory: search, filter, drill into a dossier, and act with an audit trail. */
export default function Users() {
  const [search, setSearch] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('');
  const [verification, setVerification] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [action, setAction] = useState<Action>(null);

  const users = useAdminUsers({ search, role, status, verification, page, limit: 20 });
  const verify = useVerifyUser();
  const reject = useRejectUser();
  const suspend = useSuspendUser();
  const reactivate = useReactivateUser();

  const run = (reason: string) => {
    if (!action) return;
    const { kind, user } = action;
    const done = () => setAction(null);
    if (kind === 'verify') verify.mutate({ id: user.id, note: reason || undefined }, { onSuccess: done });
    if (kind === 'reject') reject.mutate({ id: user.id, reason }, { onSuccess: done });
    if (kind === 'suspend') suspend.mutate({ id: user.id, reason }, { onSuccess: done });
    if (kind === 'reactivate') reactivate.mutate({ id: user.id }, { onSuccess: done });
  };

  return (
    <div>
      <PageHeader
        title="Users"
        subtitle="Students, teachers and administrators. Exact contact details stay private to members and admins."
      />
      <Filters>
        <Field label="Search">
          <input
            className="input w-64"
            placeholder="Name, email, university ID, phone"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </Field>
        <Field label="Role">
          <select className="input w-36" value={role} onChange={(event) => { setRole(event.target.value); setPage(1); }}>
            <option value="">All roles</option>
            <option value="STUDENT">Student</option>
            <option value="TEACHER">Teacher</option>
            <option value="ADMIN">Admin</option>
          </select>
        </Field>
        <Field label="Account">
          <select className="input w-40" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
            <option value="">All accounts</option>
            <option value="ACTIVE">Active</option>
            <option value="SUSPENDED">Suspended</option>
          </select>
        </Field>
        <Field label="Verification">
          <select
            className="input w-44"
            value={verification}
            onChange={(event) => { setVerification(event.target.value); setPage(1); }}
          >
            <option value="">Any status</option>
            <option value="VERIFIED">Verified</option>
            <option value="PENDING">Pending</option>
            <option value="REJECTED">Rejected</option>
            <option value="UNVERIFIED">Unverified</option>
          </select>
        </Field>
      </Filters>

      <InlineError error={verify.error ?? reject.error ?? suspend.error ?? reactivate.error} />

      <TableShell
        headers={['Member', 'Department', 'Role', 'Verification', 'Account', 'Rating', 'Joined', '']}
        isLoading={users.isLoading}
        error={users.error}
        isEmpty={(users.data?.items.length ?? 0) === 0}
        emptyTitle="No members match these filters"
        emptyMessage="Adjust the search terms or clear the filters. New signups appear here the moment they register."
        footer={
          users.data ? (
            <Pagination page={users.data.page} pages={users.data.pages} total={users.data.total} onChange={setPage} />
          ) : null
        }
      >
        {users.data?.items.map((user) => (
          <tr key={user.id} className="hover:bg-canvas/60">
            <td className="px-4 py-3">
              <button
                type="button"
                className="flex items-center gap-3 text-left"
                onClick={() => setSelected(user.id)}
              >
                <MemberAvatar name={user.full_name} photoPath={user.profile_photo_url} />
                <span>
                  <p className="font-semibold text-navy hover:underline">{user.full_name}</p>
                  <p className="text-xs text-muted">{user.email}</p>
                </span>
              </button>
            </td>
            <td className="px-4 py-3 text-xs">
              <p>{user.department || '—'}</p>
              <p className="text-muted">{user.university_id || '—'}</p>
            </td>
            <td className="px-4 py-3 text-xs">{label(user.role)}</td>
            <td className="px-4 py-3"><StatusBadge status={user.verification_status} /></td>
            <td className="px-4 py-3"><StatusBadge status={user.account_status} /></td>
            <td className="px-4 py-3 text-xs tabular-nums">
              {user.rating_count ? `${user.rating_average.toFixed(1)} (${user.rating_count})` : '—'}
            </td>
            <td className="px-4 py-3 text-xs text-muted">{dateOnly(user.created_at)}</td>
            <td className="px-4 py-3 text-right">
              <div className="flex justify-end gap-1">
                <button type="button" className="btn-ghost" onClick={() => setSelected(user.id)}>
                  View
                </button>
                {user.account_status === 'ACTIVE' ? (
                  <button
                    type="button"
                    className="btn-ghost text-dangr"
                    disabled={user.role === 'ADMIN'}
                    title={user.role === 'ADMIN' ? 'Administrators cannot be suspended' : 'Suspend'}
                    onClick={() => setAction({ kind: 'suspend', user })}
                  >
                    Suspend
                  </button>
                ) : (
                  <button type="button" className="btn-ghost text-brandgreen-dark" onClick={() => setAction({ kind: 'reactivate', user })}>
                    Reactivate
                  </button>
                )}
              </div>
            </td>
          </tr>
        ))}
      </TableShell>

      {selected ? (
        <UserDrawer
          userId={selected}
          onClose={() => setSelected(null)}
          onAction={(kind, user) => setAction({ kind, user })}
        />
      ) : null}

      <ReasonDialog
        open={action !== null}
        title={
          action?.kind === 'verify'
            ? `Verify ${action.user.full_name}?`
            : action?.kind === 'reject'
              ? `Reject verification for ${action?.user.full_name}?`
              : action?.kind === 'suspend'
                ? `Suspend ${action?.user.full_name}?`
                : `Reactivate ${action?.user.full_name}?`
        }
        description={
          action?.kind === 'suspend'
            ? 'The member is signed out of the API immediately and their open rides are cancelled.'
            : action?.kind === 'reactivate'
              ? 'Access is restored and the member is notified.'
              : 'The decision is stored in the audit log and the member is notified.'
        }
        confirmLabel={action?.kind === 'reactivate' ? 'Reactivate' : 'Confirm'}
        requireReason={action?.kind !== 'reactivate' && action?.kind !== 'verify'}
        tone={action?.kind === 'suspend' || action?.kind === 'reject' ? 'danger' : 'primary'}
        busy={verify.isPending || reject.isPending || suspend.isPending || reactivate.isPending}
        onCancel={() => setAction(null)}
        onConfirm={run}
      />
    </div>
  );
}

function PasswordResetPanel({ userId, canIssue }: { userId: string; canIssue: boolean }) {
  const issue = useIssuePasswordResetCode();
  const [copied, setCopied] = useState(false);
  const result = issue.data as PasswordResetCode | undefined;

  const copy = async () => {
    if (!result) return;
    await navigator.clipboard.writeText(result.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Section title="Password reset (when email is not set up)">
      <p className="text-xs text-muted">
        Creates a one-time code valid for {result?.expires_in_minutes ?? 30} minutes. Send it to the member
        privately (WhatsApp or in person). They enter it on the &quot;Reset password&quot; screen in the app.
        Using the code replaces the current password and signs out all devices.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-secondary"
          disabled={!canIssue || issue.isPending}
          title={canIssue ? undefined : 'Reactivate the account first'}
          onClick={() => issue.mutate({ id: userId })}
        >
          {issue.isPending ? 'Creating…' : 'Create reset code'}
        </button>
      </div>
      <InlineError error={issue.error} />
      {result ? (
        <div className="mt-3 rounded-xl2 bg-canvas p-3">
          <p className="text-xs text-muted">Reset code (shown once for this member):</p>
          <div className="mt-1 flex items-center gap-2">
            <code className="flex-1 break-all rounded bg-white px-2 py-1 text-sm">{result.code}</code>
            <button type="button" className="btn-secondary" onClick={copy}>
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <p className="mt-2 text-xs text-muted">Expires at {dateTime(result.expires_at)}.</p>
        </div>
      ) : null}
    </Section>
  );
}

function UserDrawer({
  userId,
  onClose,
  onAction,
}: {
  userId: string;
  onClose: () => void;
  onAction: (kind: 'verify' | 'reject' | 'suspend' | 'reactivate', user: AdminUser) => void;
}) {
  const detail = useAdminUser(userId);

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-navy/40">
      <div className="h-full w-full max-w-xl overflow-y-auto bg-white p-6 shadow-card">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <MemberAvatar
              name={detail.data?.user.full_name ?? 'Member'}
              photoPath={detail.data?.user.profile_photo_url}
              size={56}
            />
            <div>
              <h3 className="text-lg font-semibold">{detail.data?.user.full_name ?? 'Loading member…'}</h3>
              <p className="text-xs text-muted">{detail.data?.user.email}</p>
            </div>
          </div>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>

        <InlineError error={detail.error} />

        {detail.isLoading || !detail.data ? (
          <p className="mt-6 text-sm text-muted">Loading dossier…</p>
        ) : (
          <>
            <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
              <Item label="Role" value={label(detail.data.user.role)} />
              <Item label="Account" value={label(detail.data.user.account_status)} />
              <Item label="Verification" value={label(detail.data.user.verification_status)} />
              <Item label="Department" value={detail.data.user.department || '—'} />
              <Item label="University ID" value={detail.data.user.university_id || '—'} />
              <Item label="Semester" value={detail.data.semester ? String(detail.data.semester) : '—'} />
              <Item label="Phone" value={detail.data.user.phone || '—'} />
              <Item label="Home area (approximate)" value={detail.data.home_area || '—'} />
              <Item label="Rating" value={detail.data.user.rating_count ? `${detail.data.user.rating_average.toFixed(1)} / 5 (${detail.data.user.rating_count})` : 'No ratings yet'} />
              <Item label="Joined" value={dateTime(detail.data.user.created_at)} />
              <Item label="Last login" value={detail.data.user.last_login_at ? dateTime(detail.data.user.last_login_at) : 'Never'} />
              <Item label="Suspension reason" value={detail.data.suspension_reason || '—'} />
            </dl>

            <div className="mt-5 grid grid-cols-4 gap-2 text-center">
              {[
                ['As driver', detail.data.trips_as_driver],
                ['As passenger', detail.data.trips_as_passenger],
                ['Reports filed', detail.data.reports_filed],
                ['Reports against', detail.data.reports_against],
              ].map(([caption, value]) => (
                <div key={String(caption)} className="rounded-xl2 bg-canvas p-3">
                  <p className="text-lg font-bold tabular-nums">{String(value)}</p>
                  <p className="text-[10px] uppercase tracking-wide text-muted">{String(caption)}</p>
                </div>
              ))}
            </div>

            <div className="mt-6 flex flex-wrap gap-2">
              {detail.data.user.verification_status !== 'VERIFIED' ? (
                <button type="button" className="btn-primary" onClick={() => onAction('verify', detail.data!.user)}>
                  Approve verification
                </button>
              ) : null}
              {detail.data.user.verification_status === 'PENDING' ? (
                <button type="button" className="btn-danger" onClick={() => onAction('reject', detail.data!.user)}>
                  Reject verification
                </button>
              ) : null}
              {detail.data.user.account_status === 'ACTIVE' && detail.data.user.role !== 'ADMIN' ? (
                <button type="button" className="btn-secondary" onClick={() => onAction('suspend', detail.data!.user)}>
                  Suspend account
                </button>
              ) : null}
              {detail.data.user.account_status === 'SUSPENDED' ? (
                <button type="button" className="btn-secondary" onClick={() => onAction('reactivate', detail.data!.user)}>
                  Reactivate account
                </button>
              ) : null}
            </div>

            <PasswordResetPanel
              userId={detail.data.user.id}
              canIssue={detail.data.user.account_status === 'ACTIVE' && detail.data.user.role !== 'ADMIN'}
            />

            <Section title="Vehicles">
              {detail.data.vehicles.length === 0 ? (
                <p className="text-xs text-muted">No vehicles registered.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {detail.data.vehicles.map((vehicle) => (
                    <li key={vehicle.id} className="flex items-center justify-between rounded-xl border border-hairline px-3 py-2">
                      <span>
                        {vehicle.make_and_model} · {vehicle.registration_number}
                      </span>
                      <StatusBadge status={vehicle.status} />
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title="Recent published rides">
              {detail.data.recent_rides.length === 0 ? (
                <p className="text-xs text-muted">No rides published.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {detail.data.recent_rides.map((ride) => (
                    <li key={ride.id} className="rounded-xl border border-hairline px-3 py-2">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">
                          {ride.pickup_area} → {ride.destination_area}
                        </span>
                        <StatusBadge status={ride.status} />
                      </div>
                      <p className="text-xs text-muted">{dateTime(ride.departure_at)}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title="Verification submissions">
              {detail.data.verifications.length === 0 ? (
                <p className="text-xs text-muted">No submissions on file.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {detail.data.verifications.map((item) => (
                    <li key={item.id} className="rounded-xl border border-hairline px-3 py-2">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{label(item.verification_type)}</span>
                        <StatusBadge status={item.status} />
                      </div>
                      <p className="text-xs text-muted">
                        {item.submitted_value || '—'} · submitted {dateTime(item.created_at)}
                      </p>
                      {item.review_note ? <p className="text-xs text-muted">Note: {item.review_note}</p> : null}
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </>
        )}
      </div>
    </div>
  );
}

function Item({ label: caption, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="stat-label">{caption}</dt>
      <dd className="mt-0.5 font-medium">{value}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h4 className="stat-label mb-2">{title}</h4>
      {children}
    </section>
  );
}
