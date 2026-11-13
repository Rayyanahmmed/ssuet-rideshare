import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ApiError } from '@/api/client';
import * as authApi from '@/api/auth';
import { Banner, Button, Card, TextField } from '@/components/ui';
import { resetPasswordSchema, type ResetPasswordValues } from '@/lib/schemas';
import { colors, spacing, typography } from '@/theme';

/**
 * Sets a new password from a one-time code.
 *
 * Two ways in:
 * - the emailed link `ssuetrideshare://reset-password?token=...` (token pre-filled);
 * - a code the administrator gave the member when email is not set up (typed or pasted).
 */
export default function ResetPasswordScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ token?: string | string[] }>();
  const initialToken = Array.isArray(params.token) ? params.token[0] : params.token;
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { control, handleSubmit, setValue } = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { token: initialToken ?? '', password: '', confirm_password: '' },
  });

  useEffect(() => {
    if (initialToken) setValue('token', initialToken);
  }, [initialToken, setValue]);

  const onSubmit = async (values: ResetPasswordValues) => {
    setError(null);
    setSubmitting(true);
    try {
      await authApi.resetPassword(values.token.trim(), values.password);
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Could not reset the password. Check your connection and try again.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Set a new password</Text>
        <Text style={styles.subtitle}>
          Enter the reset code (from the link or from the administrator) and choose a new password.
          The code can be used once and expires after 30 minutes.
        </Text>

        {error ? <Banner tone="danger" message={error} /> : null}

        {done ? (
          <Card>
            <Banner tone="success" title="Password changed" message="You can now sign in with your new password." />
            <View style={styles.gap} />
            <Button label="Go to sign in" onPress={() => router.replace('/(auth)/login')} />
          </Card>
        ) : (
          <Card>
            <Controller
              control={control}
              name="token"
              render={({ field, fieldState }) => (
                <TextField
                  label="Reset code"
                  placeholder="Paste the code here"
                  icon="key-outline"
                  autoCapitalize="none"
                  autoCorrect={false}
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message}
                />
              )}
            />
            <Controller
              control={control}
              name="password"
              render={({ field, fieldState }) => (
                <TextField
                  label="New password"
                  placeholder="Choose a new password"
                  icon="lock-closed-outline"
                  secureTextEntry
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message}
                />
              )}
            />
            <Controller
              control={control}
              name="confirm_password"
              render={({ field, fieldState }) => (
                <TextField
                  label="Confirm new password"
                  placeholder="Type the password again"
                  icon="lock-closed-outline"
                  secureTextEntry
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message}
                />
              )}
            />
            <Button label="Change password" onPress={handleSubmit(onSubmit)} loading={submitting} icon="checkmark-outline" />
          </Card>
        )}

        <Pressable onPress={() => router.replace('/(auth)/login')} style={styles.footerLink}>
          <Text style={styles.link}>Back to sign in</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  title: { color: colors.text, ...typography.display, marginTop: spacing.lg },
  subtitle: { color: colors.textMuted, ...typography.body, marginBottom: spacing.sm },
  gap: { height: spacing.md },
  footerLink: { alignItems: 'center', paddingVertical: spacing.md },
  link: { color: colors.navy, ...typography.bodyStrong },
});
