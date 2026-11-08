import { useEffect, useState } from 'react';
import { useAppDownload, useUpdateAppDownload } from '@/api/appDownload';
import { describeError } from '@/api/client';
import { InlineError, PageHeader } from '@/components/ui';

/**
 * Android app download (web app → "Download Android app" button).
 *
 * The APK itself is hosted by EAS (expo.dev). Paste the build link here; users on the web
 * app get the latest build immediately, without a redeploy.
 */
export default function AppDownload() {
  const current = useAppDownload();
  const update = useUpdateAppDownload();

  const [url, setUrl] = useState('');
  const [version, setVersion] = useState('');
  const [notice, setNotice] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (!current.data) return;
    setUrl(current.data.url ?? '');
    setVersion(current.data.version ?? '');
  }, [current.data]);

  const save = async () => {
    setNotice(null);
    try {
      const saved = await update.mutateAsync({ url: url.trim(), version: version.trim() });
      setNotice({
        tone: 'ok',
        text: saved.available
          ? `Published version ${saved.version ?? '—'}. The web app now offers this build.`
          : 'Download withdrawn. The web app will show no Android download button.',
      });
    } catch (error) {
      setNotice({ tone: 'error', text: describeError(error) });
    }
  };

  const dirty =
    Boolean(current.data) && (url.trim() !== (current.data!.url ?? '') || version.trim() !== (current.data!.version ?? ''));

  return (
    <div>
      <PageHeader
        title="App download"
        subtitle="Paste the EAS build link for the Android APK. The web app's download button uses it immediately."
      />

      <InlineError error={current.error} />

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card space-y-5 p-6 lg:col-span-2">
          <h3 className="stat-label">Android build</h3>

          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Download link (APK)</span>
            <input
              className="input w-full"
              placeholder="https://expo.dev/accounts/…/builds/…"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              maxLength={500}
            />
            <span className="block text-xs text-muted">
              Must start with https://. Leave empty to hide the download button.
            </span>
          </label>

          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Version</span>
            <input
              className="input w-full"
              placeholder="1.0.3"
              value={version}
              onChange={(event) => setVersion(event.target.value)}
              maxLength={40}
            />
          </label>

          <div className="flex flex-wrap items-center gap-3">
            <button className="btn-primary" onClick={save} disabled={!dirty || update.isPending}>
              {update.isPending ? 'Saving…' : 'Publish'}
            </button>
            {current.data?.updated_at ? (
              <span className="text-xs text-muted">
                Last published {new Date(current.data.updated_at).toLocaleString()}
              </span>
            ) : null}
          </div>

          {notice ? (
            <p className={notice.tone === 'ok' ? 'text-sm text-brandgreen-dark' : 'text-sm text-dangr'} role="status">
              {notice.text}
            </p>
          ) : null}
        </section>

        <section className="card space-y-3 p-6">
          <h3 className="stat-label">Current</h3>
          {current.data?.available ? (
            <>
              <p className="text-sm">
                Version <strong>{current.data.version ?? '—'}</strong> is offered on the web app.
              </p>
              <a className="btn-ghost inline-flex" href={current.data.url ?? '#'} target="_blank" rel="noreferrer">
                Open link
              </a>
            </>
          ) : (
            <p className="text-sm text-muted">No Android build is published. The web app hides the download button.</p>
          )}
        </section>
      </div>
    </div>
  );
}
