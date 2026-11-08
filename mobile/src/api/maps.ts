import { api } from '@/api/client';
import { getApiBaseUrl } from '@/lib/config';
import { stripTrailingSlashes } from '@/lib/apiUrl';

/**
 * Map access for the app (§13).
 *
 * The app holds **no** map provider credential. It asks the backend what to render, and the
 * backend proxies the tiles — so an administrator can rotate or replace the provider's key
 * in the dashboard and every installed app picks it up on the next request. No rebuild.
 */

export type MapConfig = {
  enabled: boolean;
  provider: string;
  style: string;
  needs_key: boolean;
  has_key: boolean;
  attribution: string;
  tile_url_template: string;
  updated_at: string | null;
};

export type GeoResult = { label: string; latitude: number; longitude: number };

export async function getMapConfig(): Promise<MapConfig> {
  const { data } = await api.get<MapConfig>('/maps/config');
  return data;
}

export async function searchPlaces(query: string, limit = 5): Promise<GeoResult[]> {
  const { data } = await api.get<GeoResult[]>('/maps/search', { params: { q: query, limit } });
  return data;
}

export async function reverseGeocode(latitude: number, longitude: number): Promise<GeoResult> {
  const { data } = await api.get<GeoResult>('/maps/reverse', { params: { lat: latitude, lng: longitude } });
  return data;
}

/**
 * Absolute tile base for the WebView. Tiles must be requested from *our* API because that is
 * where the provider key is injected server-side.
 */
export function tileBaseUrl(): string {
  return `${stripTrailingSlashes(getApiBaseUrl())}/maps/tiles`;
}
