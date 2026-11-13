import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import * as authApi from '@/api/auth';
import { myRides, myVehicles } from '@/api/rides';
import { Banner, Button, Card } from '@/components/ui';
import { goBackOr } from '@/lib/navigation';
import {
  buildOnboardingSteps,
  nextOnboardingStep,
  onboardingProgress,
  type OnboardingStep,
} from '@/lib/onboarding';
import { useAuthStore } from '@/store/auth';
import { colors, radius, spacing, typography } from '@/theme';

/**
 * Guided setup for new members: confirm email, verify student ID, add and get a vehicle
 * approved, then publish the first ride. Each row opens its screen; the arrow button
 * always points at the first unfinished step.
 */
export default function OnboardingScreen() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const updateUser = useAuthStore((state) => state.updateUser);
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  const queryClient = useQueryClient();
  const vehicles = useQuery({ queryKey: ['vehicles'], queryFn: myVehicles });
  const rides = useQuery({ queryKey: ['rides', 'mine', 'onboarding'], queryFn: () => myRides() });

  // Coming back from the verification or vehicle screens must show fresh status.
  useFocusEffect(
    useCallback(() => {
      void authApi.fetchMe().then(updateUser).catch(() => undefined);
      void queryClient.invalidateQueries({ queryKey: ['vehicles'] });
      void queryClient.invalidateQueries({ queryKey: ['rides', 'mine'] });
    }, [queryClient, updateUser]),
  );

  const resend = useMutation({
    mutationFn: authApi.resendVerificationEmail,
    onSuccess: (data) => setNotice({ tone: 'success', text: data.message }),
    onError: (error) =>
      setNotice({
        tone: 'error',
        text: error instanceof ApiError ? error.message : 'Could not send the email. Try again in a minute.',
      }),
  });

  const steps = useMemo(
    () =>
      user
        ? buildOnboardingSteps(user, vehicles.data ?? [], rides.data?.length ?? 0)
        : [],
    [user, vehicles.data, rides.data],
  );
  const next = nextOnboardingStep(steps);
  const progress = onboardingProgress(steps);
  const loading = vehicles.isPending || rides.isPending;

  const openStep = (step: OnboardingStep) => {
    if (step.route) router.push(step.route as never);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => goBackOr(router)} style={styles.back}>
          <Ionicons name="arrow-back" size={20} color={colors.navy} />
        </Pressable>
        <Text style={styles.title}>Account setup</Text>
        <View style={styles.back} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <Card style={styles.progressCard}>
          <Text style={styles.progressTitle}>
            {progress.done} of {progress.total} steps done
          </Text>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${progress.percent}%` }]} />
          </View>
          <Text style={styles.progressHint}>
            Finish these steps before you publish a ride. Passengers see your verified status, which keeps the community safe.
          </Text>
        </Card>

        {notice ? (
          <Banner
            tone={notice.tone === 'success' ? 'success' : 'warning'}
            title={notice.tone === 'success' ? 'Sent' : 'Not sent'}
            message={notice.text}
          />
        ) : null}

        {loading ? (
          <ActivityIndicator color={colors.green} style={styles.loader} />
        ) : (
          steps.map((step, index) => {
            const isCurrent = next?.key === step.key;
            return (
              <Card key={step.key} style={isCurrent ? { ...styles.stepCard, ...styles.stepCurrent } : styles.stepCard}>
                <View style={styles.stepRow}>
                  <View style={[styles.badge, step.done ? styles.badgeDone : isCurrent ? styles.badgeCurrent : undefined]}>
                    {step.done ? (
                      <Ionicons name="checkmark" size={18} color={colors.surface} />
                    ) : (
                      <Text style={[styles.badgeText, isCurrent ? styles.badgeTextCurrent : undefined]}>{index + 1}</Text>
                    )}
                  </View>
                  <View style={styles.stepBody}>
                    <Text style={styles.stepTitle}>
                      {step.title}
                      {step.driverOnly ? <Text style={styles.driverTag}>  Drivers</Text> : null}
                    </Text>
                    <Text style={styles.stepDetail}>{step.detail}</Text>
                  </View>
                </View>

                {!step.done && isCurrent ? (
                  step.route ? (
                    <Button
                      label={`${step.actionLabel}  →`}
                      onPress={() => openStep(step)}
                    />
                  ) : (
                    <Button
                      label={resend.isPending ? 'Sending…' : `${step.actionLabel}  →`}
                      variant="secondary"
                      loading={resend.isPending}
                      onPress={() => resend.mutate()}
                    />
                  )
                ) : !step.done && step.route ? (
                  <Pressable accessibilityRole="button" onPress={() => openStep(step)} style={styles.linkRow}>
                    <Text style={styles.linkText}>{step.actionLabel}</Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.green} />
                  </Pressable>
                ) : null}
              </Card>
            );
          })
        )}

        {!loading && !next ? (
          <Card style={styles.doneCard}>
            <Ionicons name="checkmark-circle" size={28} color={colors.green} />
            <Text style={styles.doneTitle}>You are all set</Text>
            <Text style={styles.stepDetail}>You can publish rides and send requests.</Text>
            <Button label="Publish a ride" onPress={() => router.push('/(tabs)/publish')} />
          </Card>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  back: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
  },
  title: { ...typography.h2, color: colors.navy },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl },
  progressCard: { gap: spacing.sm },
  progressTitle: { ...typography.bodyStrong, color: colors.navy },
  track: { height: 8, borderRadius: 4, backgroundColor: colors.surfaceAlt, overflow: 'hidden' },
  fill: { height: 8, backgroundColor: colors.green, borderRadius: 4 },
  progressHint: { ...typography.caption, color: colors.textMuted },
  loader: { marginTop: spacing.xl },
  stepCard: { gap: spacing.sm },
  stepCurrent: { borderWidth: 1, borderColor: colors.green },
  stepRow: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  badge: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceAlt,
  },
  badgeDone: { backgroundColor: colors.green },
  badgeCurrent: { backgroundColor: colors.greenTint },
  badgeText: { ...typography.bodyStrong, color: colors.textMuted },
  badgeTextCurrent: { color: colors.greenDark },
  stepBody: { flex: 1, gap: 2 },
  stepTitle: { ...typography.bodyStrong, color: colors.navy },
  driverTag: { ...typography.caption, color: colors.textMuted },
  stepDetail: { ...typography.caption, color: colors.textMuted },
  linkRow: { flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-end' },
  linkText: { ...typography.bodyStrong, color: colors.green },
  doneCard: { alignItems: 'center', gap: spacing.sm, borderRadius: radius.md },
  doneTitle: { ...typography.h2, color: colors.navy },
});
