import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ApiError } from '@/api/client';
import * as authApi from '@/api/auth';
import { Banner, Button, Card, TextField } from '@/components/ui';
import { ServerPanel } from '@/components/ServerPanel';
import { loginSchema, type LoginValues } from '@/lib/schemas';
import { useAuthStore } from '@/store/auth';
import { env } from '@/lib/config';
import { colors, spacing, typography } from '@/theme';

export default function LoginScreen() {
  const router = useRouter();
  const completeSignIn = useAuthStore((state) => state.completeSignIn);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { control, handleSubmit } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = async (values: LoginValues) => {
    setFormError(null);
    setSubmitting(true);
    try {
      const response = await authApi.login(values.email.trim(), values.password);
      await completeSignIn(response);
      router.replace('/(tabs)');
    } catch (error) {
      setFormError(
        error instanceof ApiError ? error.message : 'Something went wrong. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Text style={styles.title}>Welcome back</Text>
          <Text style={styles.subtitle}>Sign in with your SSUET email to continue.</Text>

          {formError ? (
            <View style={styles.bannerWrap}>
              <Banner tone="danger" message={formError} />
            </View>
          ) : null}

          <Card>
            <Controller
              control={control}
              name="email"
              render={({ field, fieldState }) => (
                <TextField
                  label="University email"
                  placeholder="yourname@ssuet.edu.pk"
                  icon="mail-outline"
                  autoCapitalize="none"
                  autoComplete="email"
                  keyboardType="email-address"
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
                  label="Password"
                  placeholder="Your password"
                  icon="lock-closed-outline"
                  secureTextEntry
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message}
                />
              )}
            />

            <Pressable onPress={() => router.push('/(auth)/forgot-password')} style={styles.forgot}>
              <Text style={styles.link}>Forgot password?</Text>
            </Pressable>

            <Button
              label="Sign in"
              onPress={handleSubmit(onSubmit)}
              loading={submitting}
              icon="log-in-outline"
            />
          </Card>

          {env.allowServerOverride ? <ServerPanel /> : null}

          <Pressable onPress={() => router.replace('/(auth)/signup')} style={styles.footerLink}>
            <Text style={styles.footerText}>
              New to SSUET RideShare? <Text style={styles.link}>Create an account</Text>
            </Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  flex: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  title: { color: colors.text, ...typography.display, marginTop: spacing.lg },
  subtitle: { color: colors.textMuted, ...typography.body, marginBottom: spacing.sm },
  bannerWrap: { marginBottom: spacing.xs },
  forgot: { alignSelf: 'flex-end', marginBottom: spacing.md },
  link: { color: colors.navy, ...typography.bodyStrong, textDecorationLine: 'underline' },
  footerLink: { alignItems: 'center', paddingVertical: spacing.md },
  footerText: { color: colors.textMuted, ...typography.caption },
});
