import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

/**
 * Map integration (§13, §16).
 *
 * The provider credential lives in the database, encrypted, and is only ever *written* from
 * this console — the API never returns it. That is what makes a key rotation a two-click job
 * instead of a new APK: the app renders tiles from `/maps/tiles/...`, where the key is added
 * server-side.
 */

export type ProviderOption = { value: string; needs_key: boolean; default_style: string };

export type MapSettings = {
  provider: string;
  style: string;
  enabled: boolean;
  has_key: boolean;
  needs_key: boolean;
  attribution: string;
  updated_at: string | null;
  updated_by: string | null;
  available_providers: ProviderOption[];
};

export type MapTestResult = { ok: boolean; provider: string; reason: string; latency_ms: number | null };

export type MapSettingsPatch = {
  provider?: string;
  style?: string;
  api_key?: string;
  enabled?: boolean;
};

export const useMapSettings = () =>
  useQuery({
    queryKey: ['admin', 'map-settings'],
    queryFn: async () => (await api.get<MapSettings>('/admin/integrations/maps')).data,
  });

export const useUpdateMapSettings = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (patch: MapSettingsPatch) =>
      (await api.put<MapSettings>('/admin/integrations/maps', patch)).data,
    onSuccess: (data) => {
      queryClient.setQueryData(['admin', 'map-settings'], data);
      // The Settings screen shows a maps summary too.
      void queryClient.invalidateQueries({ queryKey: ['admin', 'settings'] });
    },
  });
};

export const useTestMapConnection = () =>
  useMutation({
    mutationFn: async () => (await api.post<MapTestResult>('/admin/integrations/maps/test')).data,
  });
