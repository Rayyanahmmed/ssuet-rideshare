import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

/**
 * Android APK download link (shown on the public web app).
 *
 * Builds are made with EAS. After a new build, the administrator pastes its link and version
 * here: the web app's download button changes at once, with no redeploy.
 */

export type AppDownload = {
  available: boolean;
  url: string | null;
  version: string | null;
  updated_at: string | null;
};

export const useAppDownload = () =>
  useQuery({
    queryKey: ['admin', 'app-download'],
    queryFn: async () => (await api.get<AppDownload>('/admin/integrations/app-download')).data,
  });

export const useUpdateAppDownload = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { url: string; version: string }) =>
      (await api.put<AppDownload>('/admin/integrations/app-download', payload)).data,
    onSuccess: (data) => {
      queryClient.setQueryData(['admin', 'app-download'], data);
    },
  });
};
