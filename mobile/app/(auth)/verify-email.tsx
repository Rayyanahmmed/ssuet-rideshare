import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { ApiError } from '@/api/client';
import * as authApi from '@/api/auth';
import { Button, Card } from '@/components/ui';
import { useAuthStore } from '@/store/auth';
import { colors, spacing, typography } from '@/theme';

/**
 * Landing screen for the emailed link `ssuetrideshare://verify-email?token=...`.
 * Confirms the address once, then sends the member to the right place.
 */
export default function VerifyEmailScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ token?: string | string[] }>();
  const token = (Array.isArray(params.token) ? params.token[0] : params.token)?.trim() ?? '';
  const status = useAuthStore((state) => state.status);
  const updateUser = useAuthStore((state) => state.updateUser);
  const [state, setState] = useState<'working' | 'done' | 'failed'>('working');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setState('failed');
      setMessage('This link is missing its code. Open the link from your confirmation email again.');
      return;
    }
    authApi
      .verifyEmail(token)
      .then(async () => {
        if (cancelled) return;
        // If the member is signed in on this device, refresh their cached profile.
        if (useAuthStore.getState().status === 'signedIn') {
          const fresh = await authApi.fetchMe().catch(() => null);
          if (fresh) updateUser(fresh);
        }
        setState('done');
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState('failed');
        setMessage(
          error instanceof ApiError
            ? error.message
            : 'Could not confirm your email. Check your connection and try again.',
        );
      });
    return () => {
      cancelled = true;
    };
    // The link is used once; run only for the token in the URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const continueTo = () => router.replace(status === 'signedIn' ? '/' : '/(auth)/login');

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.wrap}>
        <Card style={styles.card}>
          {state === 'working' ? (
            <>
              <ActivityIndicator color={colors.green} />
              <Text style={styles.title}>Confirming your email…</Text>
            </>
          ) : state === 'done' ? (
            <>
              <Ionicons name="checkmark-circle" size={48} color={colors.green} />
              <Text style={styles.title}>Email confirmed</Text>
              <Text style={styles.body}>Your email address is now confirmed. Thank you!</Text>
              <Button label={status === 'signedIn' ? 'Continue' : 'Sign in'} onPress={continueTo} />
            </>
          ) : (
            <>
              <Ionicons name="alert-circle" size={48} color={colors.danger} />
              <Text style={styles.title}>Link not valid</Text>
              <Text style={styles.body}>{message}</Text>
              <Button label="Back" variant="secondary" onPress={continueTo} />
            </>
          )}
        </Card>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  wrap: { flex: 1, justifyContent: 'center', padding: spacing.lg },
  card: { alignItems: 'center', gap: spacing.md },
  title: { ...typography.h2, color: colors.navy, textAlign: 'center' },
  body: { ...typography.body, color: colors.textMuted, textAlign: 'center' },
});
