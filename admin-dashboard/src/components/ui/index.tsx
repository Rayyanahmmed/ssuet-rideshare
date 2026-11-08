import { useState, type ReactNode } from 'react';
import { describeError } from '@/api/client';

/** Small, dependency-free UI kit shared by every admin screen. */

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">{title}</h2>
        {subtitle ? <p className="mt-1 text-sm text-muted">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  label: string;
  value: number | string;
  hint?: string;
  tone?: 'neutral' | 'ok' | 'warn' | 'danger' | 'info';
}) {
  const tones: Record<string, string> = {
    neutral: 'bg-canvas text-navy',
    ok: 'bg-brandgreen-tint text-brandgreen-dark',
    warn: 'bg-amber-50 text-warn',
    danger: 'bg-red-50 text-dangr',
    info: 'bg-navy-tint text-navy',
  };
  return (
    <div className="card p-5">
      <p className="stat-label">{label}</p>
      <p className="mt-2 text-2xl font-bold tabular-nums">{value}</p>
      {hint ? (
        <span className={`mt-3 inline-block rounded-full px-2.5 py-1 text-[11px] font-semibold ${tones[tone]}`}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}

const STATUS_STYLES: Record<string, string> = {
  VERIFIED: 'bg-brandgreen-tint text-brandgreen-dark',
  ACTIVE: 'bg-brandgreen-tint text-brandgreen-dark',
  COMPLETED: 'bg-brandgreen-tint text-brandgreen-dark',
  OPEN: 'bg-blue-50 text-blue-700',
  CONFIRMED: 'bg-blue-50 text-blue-700',
  MATCHED: 'bg-indigo-50 text-indigo-700',
  IN_PROGRESS: 'bg-indigo-50 text-indigo-700',
  UNDER_REVIEW: 'bg-amber-50 text-warn',
  PENDING: 'bg-amber-50 text-warn',
  NO_SHOW: 'bg-amber-50 text-warn',
  REJECTED: 'bg-red-50 text-dangr',
  SUSPENDED: 'bg-red-50 text-dangr',
  CANCELLED: 'bg-red-50 text-dangr',
  EXPIRED: 'bg-slate-100 text-slate-600',
  DISMISSED: 'bg-slate-100 text-slate-600',
  RESOLVED: 'bg-brandgreen-tint text-brandgreen-dark',
  UNVERIFIED: 'bg-slate-100 text-slate-600',
  DEACTIVATED: 'bg-slate-100 text-slate-600',
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${
        STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-600'
      }`}
    >
      {status.replaceAll('_', ' ').toLowerCase()}
    </span>
  );
}

export function TableShell({
  headers,
  isLoading,
  error,
  isEmpty,
  emptyTitle,
  emptyMessage,
  children,
  footer,
}: {
  headers: string[];
  isLoading: boolean;
  error: unknown;
  isEmpty: boolean;
  emptyTitle: string;
  emptyMessage: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="bg-canvas text-[11px] uppercase tracking-wide text-muted">
            <tr>
              {headers.map((header) => (
                <th key={header} className="px-4 py-3 font-semibold">
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {isLoading ? (
              <tr>
                <td colSpan={headers.length} className="px-4 py-10 text-center text-muted">
                  Loading…
                </td>
              </tr>
            ) : error ? (
              <tr>
                <td colSpan={headers.length} className="px-4 py-10 text-center text-dangr">
                  {describeError(error)}
                </td>
              </tr>
            ) : isEmpty ? (
              <tr>
                <td colSpan={headers.length} className="px-4 py-12 text-center">
                  <p className="font-semibold text-navy">{emptyTitle}</p>
                  <p className="mx-auto mt-1 max-w-md text-xs text-muted">{emptyMessage}</p>
                </td>
              </tr>
            ) : (
              children
            )}
          </tbody>
        </table>
      </div>
      {footer ? <div className="border-t border-hairline px-4 py-3">{footer}</div> : null}
    </div>
  );
}

export function Pagination({
  page,
  pages,
  total,
  onChange,
}: {
  page: number;
  pages: number;
  total: number;
  onChange: (page: number) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
      <span>
        Page {page} of {pages} · {total} record{total === 1 ? '' : 's'}
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          className="btn-secondary"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          Previous
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

/**
 * Reason prompt used by every destructive/decision action.
 *
 * It is a real dialog (not a `window.prompt`) so the console can require a reason
 * before a rejection or suspension can ever reach the API.
 */
export function ReasonDialog({
  open,
  title,
  description,
  confirmLabel,
  requireReason = true,
  tone = 'danger',
  busy = false,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel: string;
  requireReason?: boolean;
  tone?: 'danger' | 'primary';
  busy?: boolean;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState('');
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-navy/40 p-4">
      <div className="w-full max-w-lg rounded-xl2 bg-white p-6 shadow-card">
        <h3 className="text-lg font-semibold">{title}</h3>
        {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
        <label className="stat-label mt-4 block" htmlFor="reason">
          Reason {requireReason ? '' : '(optional)'}
        </label>
        <textarea
          id="reason"
          className="input mt-1 h-24 resize-none"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Shown to the member and stored in the audit log"
        />
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className={tone === 'danger' ? 'btn-danger' : 'btn-primary'}
            disabled={busy || (requireReason && reason.trim().length < 3)}
            onClick={() => onConfirm(reason.trim())}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function InlineError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="mb-4 rounded-xl2 border border-red-200 bg-red-50 px-4 py-3 text-sm text-dangr">
      {describeError(error)}
    </div>
  );
}

export function Filters({ children }: { children: ReactNode }) {
  return <div className="card mb-4 flex flex-wrap items-end gap-3 p-4">{children}</div>;
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-semibold text-muted">
      {label}
      {children}
    </label>
  );
}
