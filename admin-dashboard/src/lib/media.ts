import { api } from '@/api/client';

/**
 * Open an uploaded verification document.
 *
 * The file is served by `GET /media/{id}`, which requires the administrator's
 * bearer token — a plain `<a href>` would be rejected with 401. So the blob is
 * fetched with the normal API client (token + refresh handled there) and handed to
 * the browser as an object URL, which is revoked after a minute.
 */
export async function openMediaDocument(assetId: string): Promise<void> {
  // Open the tab inside the click gesture, otherwise browsers block the popup.
  const tab = window.open('', '_blank');
  try {
    const response = await api.get(`/media/${assetId}`, { responseType: 'blob' });
    const url = URL.createObjectURL(response.data as Blob);
    if (tab) {
      tab.location.href = url;
    } else {
      window.open(url, '_blank', 'noopener');
    }
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (error) {
    tab?.close();
    throw error;
  }
}

/**
 * Profile photos (§5, Phase 13).
 *
 * `GET /users/{id}/photo` needs the administrator's bearer token, so — exactly like a
 * verification document — the bytes are fetched through the API client and handed to
 * `<img>` as an object URL. Object URLs are cached per API path for the session: the
 * path contains the asset id, so a new upload produces a new key and the old one is
 * simply never asked for again. The cache is capped so a long admin session cannot
 * grow without bound.
 */
const photoCache = new Map<string, string>();
const MAX_CACHED_PHOTOS = 200;

/** Thumbnails (Phase 14) are derived server-side; small avatars ask for the 128 px one. */
export function withThumbVariant(apiPath: string): string {
  return apiPath.includes('?') ? `${apiPath}&size=thumb` : `${apiPath}?size=thumb`;
}

export async function fetchProfilePhotoUrl(apiPath: string): Promise<string> {
  const cached = photoCache.get(apiPath);
  if (cached) return cached;

  const response = await api.get(apiPath.replace(/^\/api\/v1\//, ''), { responseType: 'blob' });
  const url = URL.createObjectURL(response.data as Blob);
  if (photoCache.size >= MAX_CACHED_PHOTOS) {
    const oldest = photoCache.keys().next().value;
    if (oldest) {
      const stale = photoCache.get(oldest);
      photoCache.delete(oldest);
      if (stale) URL.revokeObjectURL(stale);
    }
  }
  photoCache.set(apiPath, url);
  return url;
}
