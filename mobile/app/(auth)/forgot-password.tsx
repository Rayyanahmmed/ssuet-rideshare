import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ApiError } from '@/api/client';
import * as authApi from '@/api/auth';
import { Banner, Button, Card, TextField } from '@/components/ui';
import { forgotPasswordSchema, type ForgotPasswordValues } from '@/lib/schemas';
import { colors, spacing, typography } from '@/theme';

export default function ForgotPasswordScreen() {
  const router = useRouter();
  const [sent, setSent] = useState<{ message: string; detail?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { control, handleSubmit } = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: '' },
  });

  const onSubmit = async (values: ForgotPasswordValues) => {
    setError(null);
    setSubmitting(true);
    try {
      const response = await authApi.requestPasswordReset(values.email.trim());
      setSent(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send the reset link.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Reset your password</Text>
        <Text style={styles.subtitle}>
          Enter the email you registered with and we will send you a reset link.
        </Text>

        {error ? <Banner tone="danger" message={error} /> : null}

        {sent ? (
          <Card>
            <Banner
              tone="success"
              title="Check your inbox"
              message={sent.message}
            />
            {sent.detail ? (
              <View style={styles.devNote}>
                <Text style={styles.devNoteText}>{sent.detail}</Text>
              </View>
            ) : null}
            <View style={styles.gap} />
            <Button label="Back to sign in" variant="secondary" onPress={() => router.replace('/(auth)/login')} />
          </Card>
        ) : (
          <Card>
            <Controller
              control={control}
              name="email"
              render={({ field, fieldState }) => (
                <TextField
                  label="Email address"
                  placeholder="yourname@ssuet.edu.pk"
                  icon="mail-outline"
                  autoCapitalize="none"
                  keyboardType="email-address"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message}
                />
              )}
            />
            <Button label="Send reset link" onPress={handleSubmit(onSubmit)} loading={submitting} icon="send-outline" />
          </Card>
        )}

        <Pressable onPress={() => router.push('/(auth)/reset-password')} style={styles.footerLink}>
          <Text style={styles.link}>Already have a reset code?</Text>
        </Pressable>

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
  devNote: {
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: 14,
    backgroundColor: colors.surfaceAlt,
  },
  devNoteText: { color: colors.textMuted, ...typography.caption },
  gap: { height: spacing.md },
  footerLink: { alignItems: 'center', paddingVertical: spacing.md },
  link: { color: colors.navy, ...typography.bodyStrong },
});
