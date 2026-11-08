/** Presentation helpers. Pure formatting only — never business logic (§21). */

export const dateTime = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString('en-PK', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';

export const dateOnly = (value?: string | null) =>
  value ? new Date(value).toLocaleDateString('en-PK', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';

export const shortDay = (value: string) =>
  new Date(value).toLocaleDateString('en-PK', { day: '2-digit', month: 'short' });

export const relative = (value?: string | null) => {
  if (!value) return '—';
  const diff = Date.now() - new Date(value).getTime();
  const minutes = Math.round(diff / 60_000);
  if (Math.abs(minutes) < 60) return `${minutes <= 0 ? 'in ' : ''}${Math.abs(minutes)}m${minutes > 0 ? ' ago' : ''}`;
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return `${hours <= 0 ? 'in ' : ''}${Math.abs(hours)}h${hours > 0 ? ' ago' : ''}`;
  const days = Math.round(hours / 24);
  return `${days <= 0 ? 'in ' : ''}${Math.abs(days)}d${days > 0 ? ' ago' : ''}`;
};

export const label = (value?: string | null) =>
  value ? value.replaceAll('_', ' ').toLowerCase().replace(/^\w/, (char) => char.toUpperCase()) : '—';

export const areaLabel = (value?: string | null) => value || '—';
