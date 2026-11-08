import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { Linking, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { api } from '@/api/client';
import { colors, radius, spacing, typography } from '@/theme';

type AppDownloadInfo = {
  available: boolean;
  url: string | null;
  version: string | null;
  updated_at: string | null;
};

/**
 * Web app only: offers the latest Android APK that the administrator published.
 * The link comes from the server, so a new EAS build is announced without a redeploy.
 * Renders nothing on native and when no build is published.
 */
export function AndroidDownload() {
  const isWeb = Platform.OS === 'web';
  const query = useQuery({
    queryKey: ['app', 'download'],
    queryFn: async () => (await api.get<AppDownloadInfo>('/app/download')).data,
    enabled: isWeb,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  if (!isWeb || !query.data?.available || !query.data.url) return null;
  const { url, version } = query.data;

  return (
    <View style={styles.wrap}>
      <Pressable
        onPress={() => void Linking.openURL(url)}
        style={styles.button}
        accessibilityRole="link"
        accessibilityLabel="Download the Android app"
      >
        <Ionicons name="logo-android" size={18} color={colors.navy} />
        <Text style={styles.label}>
          Download Android app{version ? ` · v${version}` : ''}
        </Text>
      </Pressable>
      <Text style={styles.note}>
        Already on a phone? The app works in this browser too. On Android, allow installs from this
        browser when prompted.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs, alignItems: 'center' },
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  label: { color: colors.navy, ...typography.bodyStrong },
  note: { color: colors.textMuted, ...typography.caption, textAlign: 'center' },
});
