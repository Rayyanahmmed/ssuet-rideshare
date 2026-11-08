import { Platform } from 'react-native';
import { api } from '@/api/client';
import type { SessionUser } from '@/store/auth';

/**
 * Uploads shared by every screen that attaches a document (§4, §16, Phase 9–10).
 *
 * React Native sends `multipart/form-data` from a local file descriptor — the object
 * below is what RN's FormData understands, not a browser `Blob`. The access token and
 * the 401 refresh are handled by the shared axios client, so uploads behave exactly
 * like every other call.
 */

export type MediaAsset = {
  id: string;
  purpose: string;
  content_type: string;
  byte_size: number;
  checksum_sha256: string;
  original_filename: string | null;
  url: string;
  created_at: string;
};

export type UploadEndpoint = '/uploads/verification' | '/uploads/vehicle';

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024; // mirrors settings.MAX_UPLOAD_BYTES

/** Absolute URL for an API-relative media path (`/api/v1/users/{id}/photo`). */
export function mediaUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path; // legacy external link
  const base = api.defaults.baseURL ?? '';
  const origin = base.replace(/\/api\/v1\/?$/, '');
  return `${origin}${path}`;
}

/**
 * Upload the signed-in member's profile photo (§5, Phase 13).
 *
 * A face is validated server-side (JPG/PNG/WebP by magic number, 2 MB) and then
 * readable by every signed-in member at `GET /users/{id}/photo` — unlike an ID card,
 * which stays owner+admin only.
 */
export const MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024;

/**
 * Build the multipart part for one picked file.
 * - Native (Android/iOS): React Native accepts a `{ uri, name, type }` object.
 * - Web (browser): that object is NOT a file, so the server receives no `file` field and
 *   answers "Some of the submitted values are invalid". Turn the picked blob: URL into a
 *   real File first.
 */
async function toFormPart(file: { uri: string; name: string; type: string }): Promise<Blob> {
  if (Platform.OS !== 'web') {
    return { uri: file.uri, name: file.name, type: file.type } as unknown as Blob;
  }
  const response = await fetch(file.uri);
  const blob = await response.blob();
  const type = file.type || blob.type || 'image/jpeg';
  const name = file.name || `upload.${type.split('/')[1] || 'jpg'}`;
  return new File([blob], name, { type });
}

export async function uploadProfilePhoto(file: {
  uri: string;
  name: string;
  type: string;
}): Promise<SessionUser> {
  const form = new FormData();
  form.append('file', await toFormPart(file));
  const { data } = await api.post('/users/me/photo', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  });
  return data;
}

export async function deleteProfilePhoto(): Promise<SessionUser> {
  const { data } = await api.delete('/users/me/photo');
  return data;
}

export async function uploadDocument(
  endpoint: UploadEndpoint,
  file: { uri: string; name: string; type: string },
): Promise<MediaAsset> {
  const form = new FormData();
  form.append('file', await toFormPart(file));
  const { data } = await api.post<MediaAsset>(endpoint, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000, // uploads on a campus network can be slow
  });
  return data;
}

/** Remove an upload the member withdrew or replaced. */
export async function deleteMediaAsset(id: string): Promise<void> {
  await api.delete(`/media/${id}`);
}
