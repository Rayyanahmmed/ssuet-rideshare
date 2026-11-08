import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useAuthStore } from '@/store/auth';
import { colors, spacing, typography } from '@/theme';

/**
 * Launch gate: the only decision the app makes before showing a real screen.
 * `status === 'loading'` covers the keystore read + `GET /auth/me` round-trip.
 */
export default function BootScreen() {
  const status = useAuthStore((state) => state.status);

  if (status === 'loading') {
    return (
      <View style={styles.container}>
        <View style={styles.logo}>
          <Text style={styles.logoText}>S</Text>
        </View>
        <Text style={styles.title}>SSUET RideShare</Text>
        <Text style={styles.subtitle}>Ride together, save together</Text>
        <ActivityIndicator color={colors.green} style={styles.spinner} />
      </View>
    );
  }

  return <Redirect href={status === 'signedIn' ? '/(tabs)' : '/(auth)/welcome'} />;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.navy,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  logo: {
    width: 72,
    height: 72,
    borderRadius: 20,
    backgroundColor: colors.green,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  logoText: { color: colors.navy, fontSize: 34, fontWeight: '800' },
  title: { color: colors.textInverse, ...typography.h1 },
  subtitle: { color: '#A9BAD4', ...typography.caption },
  spinner: { marginTop: spacing.xl },
});
