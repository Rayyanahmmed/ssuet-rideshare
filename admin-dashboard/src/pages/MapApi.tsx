import { useEffect, useState } from 'react';
import {
  useMapSettings,
  useTestMapConnection,
  useUpdateMapSettings,
  type MapTestResult,
} from '@/api/maps';
import { describeError } from '@/api/client';
import { InlineError, PageHeader } from '@/components/ui';

/**
 * Map API (§13).
 *
 * This tab exists because the map used to ship its key *inside the APK*: when that key
 * expired, every phone showed a blank map and nothing could be done except build and
 * distribute a new app. Now the app asks the server which provider to use and fetches tiles
 * through `/api/v1/maps/tiles/...`, so changing the key here fixes every installed app
 * immediately — no code change, no rebuild, no update.
 */

const HINTS: Record<string, { label: string; keyUrl: string; free: string }> = {
  osm: {
    label: 'OpenStreetMap (default)',
    keyUrl: 'https://www.openstreetmap.org',
    free: 'No key needed. Free for light traffic; tiles are cached by the server.',
  },
  geoapify: {
    label: 'Geoapify',
    keyUrl: 'https://myprojects.geoapify.com',
    free: 'Free tier: 3,000 credits/day. Paste the key from the Geoapify dashboard.',
  },
  maptiler: {
    label: 'MapTiler',
    keyUrl: 'https://cloud.maptiler.com/account/keys',
    free: 'Free tier available. Paste the key from the MapTiler account page.',
  },
};

export default function MapApi() {
  const settings = useMapSettings();
  const update = useUpdateMapSettings();
  const test = useTestMapConnection();

  const [provider, setProvider] = useState('osm');
  const [style, setStyle] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [result, setResult] = useState<MapTestResult | null>(null);

  useEffect(() => {
    if (!settings.data) return;
    setProvider(settings.data.provider);
    setStyle(settings.data.style);
    setEnabled(settings.data.enabled);
    setApiKey('');
  }, [settings.data]);

  const dirty =
    Boolean(settings.data) &&
    (provider !== settings.data!.provider ||
      style !== settings.data!.style ||
      enabled !== settings.data!.enabled ||
      apiKey.trim().length > 0);

  const meta = settings.data?.available_providers.find((option) => option.value === provider);
  const hint = HINTS[provider];

  const save = async () => {
    setNotice(null);
    setResult(null);
    try {
      const patch: Record<string, unknown> = { provider, style: style.trim() || undefined, enabled };
      // An empty box must not wipe a working key: only send it when the admin typed one.
      if (apiKey.trim()) patch.api_key = apiKey.trim();
      const saved = await update.mutateAsync(patch);
      setApiKey('');
      setNotice(
        provider === saved.provider
          ? `Saved. Provider “${saved.provider}” is now live for every installed app — no rebuild needed.`
          : 'Saved.',
      );
    } catch (error) {
      setNotice(describeError(error));
    }
  };

  const runTest = async () => {
    setResult(null);
    try {
      setResult(await test.mutateAsync());
    } catch (error) {
      setResult({ ok: false, provider, reason: describeError(error), latency_ms: null });
    }
  };

  const clearKey = async () => {
    setNotice(null);
    setResult(null);
    try {
      await update.mutateAsync({ api_key: '' });
      setNotice('Stored key removed.');
    } catch (error) {
      setNotice(describeError(error));
    }
  };

  return (
    <div>
      <PageHeader
        title="Map API"
        subtitle="Choose the map provider and rotate its key. Changes apply to every installed app at once — the app never stores a map key."
      />

      <InlineError error={settings.error} />

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card space-y-5 p-6 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="stat-label">Current provider</h3>
            {settings.data ? (
              <span
                className={[
                  'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold',
                  !settings.data.enabled
                    ? 'bg-canvas text-muted'
                    : settings.data.needs_key && !settings.data.has_key
                      ? 'bg-amber-50 text-warn'
                      : 'bg-brandgreen-tint text-brandgreen-dark',
                ].join(' ')}
              >
                <span
                  className={[
                    'badge-dot',
                    !settings.data.enabled
                      ? 'bg-muted'
                      : settings.data.needs_key && !settings.data.has_key
                        ? 'bg-warn'
                        : 'bg-brandgreen',
                  ].join(' ')}
                  aria-hidden
                />
                {!settings.data.enabled
                  ? 'Maps disabled'
                  : settings.data.needs_key && !settings.data.has_key
                    ? 'Key missing — app falls back to area lists'
                    : 'Connected'}
              </span>
            ) : null}
          </div>

          {settings.isLoading ? (
            <p className="text-sm text-muted">Loading…</p>
          ) : (
            <dl className="divide-y divide-hairline text-sm">
              <Row label="Provider" value={settings.data?.provider ?? '—'} />
              <Row label="Style" value={settings.data?.style ?? '—'} />
              <Row
                label="API key"
                value={settings.data?.needs_key ? (settings.data?.has_key ? 'Stored (encrypted)' : 'Not set') : 'Not required'}
              />
              <Row label="Last changed" value={settings.data?.updated_at ? new Date(settings.data.updated_at).toLocaleString() : '—'} />
              <Row label="Changed by" value={settings.data?.updated_by ?? '—'} />
            </dl>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">Provider</span>
              <select
                className="input"
                value={provider}
                onChange={(event) => {
                  const next = event.target.value;
                  setProvider(next);
                  const nextMeta = settings.data?.available_providers.find((option) => option.value === next);
                  setStyle(nextMeta?.default_style ?? '');
                  setResult(null);
                }}
              >
                {(settings.data?.available_providers ?? [{ value: 'osm', needs_key: false, default_style: 'standard' }]).map(
                  (option) => (
                    <option key={option.value} value={option.value}>
                      {HINTS[option.value]?.label ?? option.value}
                      {option.needs_key ? ' — needs key' : ' — no key'}
                    </option>
                  ),
                )}
              </select>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">Style / map ID</span>
              <input
                className="input"
                value={style}
                placeholder={meta?.default_style ?? 'standard'}
                onChange={(event) => setStyle(event.target.value)}
              />
            </label>
          </div>

          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
              API key {settings.data?.has_key ? '(stored — leave empty to keep it)' : ''}
            </span>
            <input
              className="input font-mono"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={apiKey}
              placeholder={meta?.needs_key ? 'Paste the new provider key' : 'Not needed for OpenStreetMap'}
              onChange={(event) => setApiKey(event.target.value)}
            />
            <span className="mt-1.5 block text-xs text-muted">
              {hint?.free ?? ''} The key is stored encrypted on the server and is never sent to the mobile app or back to
              this browser.
              {hint?.keyUrl ? (
                <>
                  {' '}
                  Get one at{' '}
                  <a className="text-brandgreen-dark underline" href={hint.keyUrl} target="_blank" rel="noreferrer">
                    {hint.keyUrl.replace('https://', '')}
                  </a>
                  .
                </>
              ) : null}
            </span>
          </label>

          <label className="flex items-center gap-3 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            <span>
              Show maps in the app
              <span className="ml-2 text-xs text-muted">(when off, members pick from the area list)</span>
            </span>
          </label>

          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className="btn-primary" onClick={save} disabled={!dirty || update.isPending}>
              {update.isPending ? 'Saving…' : 'Save and apply'}
            </button>
            <button type="button" className="btn-ghost" onClick={runTest} disabled={test.isPending}>
              {test.isPending ? 'Testing…' : 'Test connection'}
            </button>
            {settings.data?.has_key ? (
              <button type="button" className="text-xs font-semibold text-dangr underline" onClick={clearKey}>
                Remove stored key
              </button>
            ) : null}
            {notice ? <span className="text-xs font-medium text-muted">{notice}</span> : null}
          </div>

          {result ? (
            <div
              className={[
                'rounded-xl2 border p-4 text-sm',
                result.ok ? 'border-brandgreen/30 bg-brandgreen-tint' : 'border-warn/30 bg-amber-50',
              ].join(' ')}
            >
              <p className="font-semibold">
                {result.ok ? 'Provider answered with a tile' : 'Provider failed'}
                {result.latency_ms !== null ? ` · ${result.latency_ms} ms` : ''}
              </p>
              <p className="mt-1 text-xs text-muted">{result.reason}</p>
              <p className="mt-1 text-xs text-muted">Provider: {result.provider}</p>
            </div>
          ) : null}
        </section>

        <section className="space-y-6">
          <div className="card p-6">
            <h3 className="stat-label">Why this works without a rebuild</h3>
            <ol className="mt-3 space-y-2 text-xs leading-relaxed text-muted">
              <li>
                <span className="font-semibold text-navy">1.</span> The app asks{' '}
                <code className="rounded bg-canvas px-1">GET /api/v1/maps/config</code> which provider to use.
              </li>
              <li>
                <span className="font-semibold text-navy">2.</span> Every tile comes from{' '}
                <code className="rounded bg-canvas px-1">/api/v1/maps/tiles/&#123;z&#125;/&#123;x&#125;/&#123;y&#125;.png</code>{' '}
                — our server adds the key.
              </li>
              <li>
                <span className="font-semibold text-navy">3.</span> Rotating the key here changes what the server adds,
                so all phones follow on their next tile. Nothing is compiled into the APK.
              </li>
            </ol>
          </div>

          <div className="card p-6">
            <h3 className="stat-label">Status summary</h3>
            <ul className="mt-3 space-y-2 text-xs text-muted">
              <li>Provider in use: <span className="font-semibold text-navy">{settings.data?.provider ?? '—'}</span></li>
              <li>Attribution shown in the app: <span dangerouslySetInnerHTML={{ __html: settings.data?.attribution ?? '—' }} /></li>
              <li>App fallback when unavailable: area list + manual pin.</li>
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-6 py-2.5">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}
