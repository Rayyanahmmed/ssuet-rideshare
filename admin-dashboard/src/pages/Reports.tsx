import { useState } from 'react';
import {
  useAdminReviews,
  useHideReview,
  useReports,
  useUnhideReview,
  useUpdateReport,
  type AdminReport,
  type AdminReview,
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
import { dateTime, label } from '@/lib/format';
import { MemberAvatar } from '@/components/MemberAvatar';

/**
 * Complaints and review moderation.
 *
 * Both live on one screen because they answer the same question — *what did the
 * community report?* — and a complaint often explains a suspicious review.
 */
export default function Reports() {
  const [tab, setTab] = useState<'complaints' | 'reviews'>('complaints');
  const [status, setStatus] = useState('OPEN');
  const [page, setPage] = useState(1);
  const [active, setActive] = useState<AdminReport | null>(null);
  const [resolution, setResolution] = useState('');
  const [nextStatus, setNextStatus] = useState<'UNDER_REVIEW' | 'RESOLVED' | 'DISMISSED'>('RESOLVED');
  const [removePhoto, setRemovePhoto] = useState(false);

  const reports = useReports({ status, page, limit: 20 });
  const update = useUpdateReport();

  return (
    <div>
      <PageHeader
        title="Reports & complaints"
        subtitle="Every report keeps its reporter, subject and handling notes. Suspension stays a separate, explicit action."
      />

      <div className="mb-4 inline-flex rounded-xl border border-hairline bg-white p-1">
        {(['complaints', 'reviews'] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setTab(option)}
            className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition ${
              tab === option ? 'bg-navy text-white' : 'text-muted hover:text-navy'
            }`}
          >
            {option === 'complaints' ? 'Complaints' : 'Reviews & ratings'}
          </button>
        ))}
      </div>

      {tab === 'reviews' ? <ReviewModeration /> : null}

      <div className={tab === 'complaints' ? '' : 'hidden'}>
      <Filters>
        <Field label="Queue">
          <select className="input w-44" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
            <option value="OPEN">Open</option>
            <option value="UNDER_REVIEW">Under review</option>
            <option value="RESOLVED">Resolved</option>
            <option value="DISMISSED">Dismissed</option>
            <option value="">All reports</option>
          </select>
        </Field>
      </Filters>

      <InlineError error={update.error} />

      <TableShell
        headers={['Reporter', 'Reported member', 'Category', 'Description', 'Filed', 'Status', '']}
        isLoading={reports.isLoading}
        error={reports.error}
        isEmpty={(reports.data?.items.length ?? 0) === 0}
        emptyTitle="Nothing waiting in this queue"
        emptyMessage="Reports filed by members land here and stay until an administrator records a resolution."
        footer={
          reports.data ? (
            <Pagination page={reports.data.page} pages={reports.data.pages} total={reports.data.total} onChange={setPage} />
          ) : null
        }
      >
        {reports.data?.items.map((report) => (
          <tr key={report.id} className="hover:bg-canvas/60">
            <td className="px-4 py-3 text-xs font-medium">{report.reporter_name}</td>
            <td className="px-4 py-3 text-xs">
              <p className="font-medium">{report.reported_user_name}</p>
              {report.trip_id ? <p className="text-muted">trip {report.trip_id.slice(0, 8)}</p> : null}
            </td>
            <td className="px-4 py-3 text-xs">
              {report.category === 'PROFILE_PHOTO' ? (
                <span className="inline-flex items-center gap-1">
                  <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[11px] font-semibold text-warning">
                    Photo
                  </span>
                  {report.photo_reason ? (
                    <span className="text-muted">{label(report.photo_reason)}</span>
                  ) : null}
                </span>
              ) : (
                label(report.category)
              )}
            </td>
            <td className="max-w-[280px] px-4 py-3 text-xs text-muted">{report.description}</td>
            <td className="px-4 py-3 text-xs text-muted">{dateTime(report.created_at)}</td>
            <td className="px-4 py-3"><StatusBadge status={report.status} /></td>
            <td className="px-4 py-3 text-right">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => {
                  setActive(report);
                  setResolution(report.resolution_note ?? '');
                  setNextStatus(report.status === 'OPEN' ? 'UNDER_REVIEW' : 'RESOLVED');
                  setRemovePhoto(false);
                }}
              >
                Handle
              </button>
            </td>
          </tr>
        ))}
      </TableShell>

      </div>

      {active ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-navy/40 p-4">
          <div className="w-full max-w-xl rounded-xl2 bg-white p-6 shadow-card">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-semibold">{label(active.category)}</h3>
                <p className="text-xs text-muted">
                  {active.reporter_name} reported {active.reported_user_name} · {dateTime(active.created_at)}
                </p>
              </div>
              <StatusBadge status={active.status} />
            </div>

            {active.reported_photo_url ? (
              <div className="mt-4 flex items-center gap-4 rounded-xl2 border border-hairline p-3">
                <MemberAvatar
                  name={active.reported_user_name}
                  photoPath={active.reported_photo_url}
                  size={72}
                />
                <div className="text-xs">
                  <p className="font-semibold text-navy">Reported picture</p>
                  <p className="text-muted">
                    This exact file is kept even if the member uploads another one, so the
                    decision stays auditable.
                  </p>
                </div>
              </div>
            ) : null}

            <p className="mt-4 rounded-xl2 bg-canvas p-4 text-sm">{active.description}</p>

            <Field label="Outcome">
              <select
                className="input mt-1"
                value={nextStatus}
                onChange={(event) => setNextStatus(event.target.value as typeof nextStatus)}
              >
                <option value="UNDER_REVIEW">Mark as under review</option>
                <option value="RESOLVED">Resolve with note</option>
                <option value="DISMISSED">Dismiss with note</option>
              </select>
            </Field>

            <Field label="Resolution note">
              <textarea
                className="input mt-1 h-24 resize-none"
                value={resolution}
                onChange={(event) => setResolution(event.target.value)}
                placeholder="What did you check, and what was decided?"
              />
            </Field>

            {active.category === 'PROFILE_PHOTO' && nextStatus !== 'UNDER_REVIEW' ? (
              <label className="mt-4 flex items-start gap-2 rounded-xl2 border border-hairline p-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={removePhoto}
                  onChange={(event) => setRemovePhoto(event.target.checked)}
                />
                <span>
                  <span className="font-semibold text-navy">Also remove the photo</span>
                  <span className="block text-xs text-muted">
                    Deletes the member&apos;s current picture and tells them why. The reported
                    file itself is kept as evidence.
                  </span>
                </span>
              </label>
            ) : null}

            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setActive(null)}>
                Close
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={
                  update.isPending ||
                  (nextStatus !== 'UNDER_REVIEW' && resolution.trim().length < 5)
                }
                onClick={() =>
                  update.mutate(
                    {
                      id: active.id,
                      status: nextStatus,
                      resolution_note: resolution.trim() || undefined,
                      remove_photo: removePhoto && nextStatus !== 'UNDER_REVIEW',
                    },
                    { onSuccess: () => setActive(null) },
                  )
                }
              >
                {update.isPending ? 'Saving…' : 'Save decision'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}


/**
 * Review moderation: hide a rating that breaks the community rules.
 *
 * Hiding recomputes the subject's average server-side, so a hidden review really
 * does disappear from their profile — the button never lies.
 */
function ReviewModeration() {
  const [hiddenFilter, setHiddenFilter] = useState('');
  const [minRating, setMinRating] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [target, setTarget] = useState<{ review: AdminReview; hide: boolean } | null>(null);

  const reviews = useAdminReviews({
    hidden: hiddenFilter === '' ? undefined : hiddenFilter === 'hidden',
    min_rating: minRating || undefined,
    search,
    page,
    limit: 20,
  });
  const hide = useHideReview();
  const unhide = useUnhideReview();

  return (
    <div>
      <Filters>
        <Field label="Search">
          <input
            className="input w-56"
            placeholder="Comment, author or subject"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </Field>
        <Field label="Visibility">
          <select
            className="input w-40"
            value={hiddenFilter}
            onChange={(event) => {
              setHiddenFilter(event.target.value);
              setPage(1);
            }}
          >
            <option value="">All reviews</option>
            <option value="visible">Visible only</option>
            <option value="hidden">Hidden only</option>
          </select>
        </Field>
        <Field label="Minimum rating">
          <select
            className="input w-36"
            value={minRating}
            onChange={(event) => {
              setMinRating(event.target.value);
              setPage(1);
            }}
          >
            <option value="">Any</option>
            <option value="5">5 stars</option>
            <option value="4">4+ stars</option>
            <option value="3">3+ stars</option>
            <option value="2">2+ stars</option>
            <option value="1">1+ stars</option>
          </select>
        </Field>
      </Filters>

      <InlineError error={hide.error ?? unhide.error} />

      <TableShell
        headers={['Rating', 'Author → subject', 'Comment', 'Trip reported?', 'Posted', 'State', '']}
        isLoading={reviews.isLoading}
        error={reviews.error}
        isEmpty={(reviews.data?.items.length ?? 0) === 0}
        emptyTitle="No reviews match this view"
        emptyMessage="Reviews appear here as soon as a completed trip is rated by either participant."
        footer={
          reviews.data ? (
            <Pagination page={reviews.data.page} pages={reviews.data.pages} total={reviews.data.total} onChange={setPage} />
          ) : null
        }
      >
        {reviews.data?.items.map((review) => (
          <tr key={review.id} className="hover:bg-canvas/60">
            <td className="px-4 py-3">
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-warn">
                {review.rating} ★
              </span>
            </td>
            <td className="px-4 py-3 text-xs">
              <p className="font-medium">{review.author_name}</p>
              <p className="text-muted">→ {review.subject_name}</p>
            </td>
            <td className="max-w-[320px] px-4 py-3 text-xs text-muted">
              {review.comment ?? <span className="italic">no comment</span>}
            </td>
            <td className="px-4 py-3 text-xs">
              {review.has_report ? (
                <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-warn">
                  reported
                </span>
              ) : (
                <span className="text-muted">—</span>
              )}
            </td>
            <td className="px-4 py-3 text-xs text-muted">{dateTime(review.created_at)}</td>
            <td className="px-4 py-3">
              <span
                className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                  review.is_hidden ? 'bg-slate-100 text-slate-600' : 'bg-brandgreen-tint text-brandgreen-dark'
                }`}
              >
                {review.is_hidden ? 'hidden' : 'visible'}
              </span>
            </td>
            <td className="px-4 py-3 text-right">
              {review.is_hidden ? (
                <button
                  type="button"
                  className="btn-ghost text-brandgreen-dark"
                  onClick={() => setTarget({ review, hide: false })}
                >
                  Restore
                </button>
              ) : (
                <button
                  type="button"
                  className="btn-ghost text-dangr"
                  onClick={() => setTarget({ review, hide: true })}
                >
                  Hide
                </button>
              )}
            </td>
          </tr>
        ))}
      </TableShell>

      <ReasonDialog
        open={target !== null}
        title={target?.hide ? 'Hide this review?' : 'Restore this review?'}
        description={
          target?.hide
            ? `${target?.review.rating}★ from ${target?.review.author_name} about ${target?.review.subject_name}. The subject's average rating is recomputed immediately.`
            : `${target?.review.rating}★ from ${target?.review.author_name} will be visible again and counted in the average.`
        }
        confirmLabel={target?.hide ? 'Hide review' : 'Restore review'}
        requireReason={Boolean(target?.hide)}
        tone={target?.hide ? 'danger' : 'primary'}
        busy={hide.isPending || unhide.isPending}
        onCancel={() => setTarget(null)}
        onConfirm={(reason) => {
          if (!target) return;
          const done = () => setTarget(null);
          if (target.hide) hide.mutate({ id: target.review.id, reason }, { onSuccess: done });
          else unhide.mutate({ id: target.review.id, note: reason || undefined }, { onSuccess: done });
        }}
      />
    </div>
  );
}
