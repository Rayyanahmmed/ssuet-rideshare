import { goBackOr } from '@/lib/navigation';
import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import { getTrip } from '@/api/trips';
import { fileReport, REPORT_CATEGORIES, type ReportCategory } from '@/api/reports';
import { Avatar, Banner, Button, Card } from '@/components/ui';
import { colors, radius, spacing, typography } from '@/theme';

/**
 * Report a problem with a journey (§15).
 *
 * The trip id is sent with the report, so the API can verify that the reported
 * member really is the other participant — a report can never be pointed at a
 * stranger by guessing an id.
 */
export default function ReportScreen() {
  const { tripId } = useLocalSearchParams<{ tripId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<ReportCategory>('SAFETY_CONCERN');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);

  const trip = useQuery({ queryKey: ['trip', tripId], queryFn: () => getTrip(tripId), enabled: Boolean(tripId) });

  const mutation = useMutation({
    mutationFn: () =>
      fileReport({
        category,
        description: description.trim(),
        trip_id: tripId,
        reported_user_id: trip.data?.counterpart.id,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['my-reports'] });
      goBackOr(router);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Your report could not be sent.'),
  });

  const counterpart = trip.data?.counterpart;
  const tooShort = description.trim().length < 10;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" onPress={() => goBackOr(router)} style={styles.back} accessibilityLabel="Close">
          <Ionicons name="close" size={20} color={colors.navy} />
        </Pressable>
        <Text style={styles.headerTitle}>Report a problem</Text>
        <View style={{ width: 36 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {error ? <Banner tone="danger" message={error} /> : null}

          {trip.isLoading ? (
            <View style={styles.centre}>
              <ActivityIndicator color={colors.green} />
            </View>
          ) : !trip.data ? (
            <Banner tone="danger" title="Trip unavailable" message="Open the trip from My Rides and try again." />
          ) : (
            <>
              <Card style={styles.card}>
                <View style={styles.personRow}>
                  <Avatar
                    name={counterpart?.full_name ?? 'Member'}
                    size={44}
                    photoUrl={counterpart?.profile_photo_url}
                  />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.name}>About {counterpart?.full_name}</Text>
                    <Text style={styles.muted}>
                      {trip.data.pickup_area} → {trip.data.destination_area}
                    </Text>
                  </View>
                </View>
                <Text style={styles.hint}>
                  Reports go to the SSUET ride-share office with your name attached — never anonymously.
                  You will see the outcome here once it is handled.
                </Text>
              </Card>

              <Card style={styles.card}>
                <Text style={styles.sectionLabel}>What happened?</Text>
                {REPORT_CATEGORIES.map((option) => {
                  const active = option.value === category;
                  return (
                    <Pressable
                      key={option.value}
                      onPress={() => setCategory(option.value)}
                      accessibilityRole="radio"
                      accessibilityState={{ selected: active }}
                      style={[styles.option, active && styles.optionActive]}
                    >
                      <Ionicons
                        name={active ? 'radio-button-on' : 'radio-button-off'}
                        size={20}
                        color={active ? colors.greenDark : colors.border}
                      />
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.optionLabel, active && styles.optionLabelActive]}>
                          {option.label}
                        </Text>
                        <Text style={styles.muted}>{option.hint}</Text>
                      </View>
                    </Pressable>
                  );
                })}
              </Card>

              <Card style={styles.card}>
                <Text style={styles.sectionLabel}>Tell us what happened</Text>
                <TextInput
                  style={styles.input}
                  value={description}
                  onChangeText={setDescription}
                  placeholder="Times, places, what was said or done — as much detail as you can share."
                  placeholderTextColor={colors.textMuted}
                  multiline
                  maxLength={1000}
                />
                <Text style={styles.counter}>{description.trim().length}/1000</Text>
              </Card>
            </>
          )}
        </ScrollView>

        <View style={styles.footer}>
          <Button
            label="Send report"
            variant="danger"
            icon="flag-outline"
            loading={mutation.isPending}
            disabled={tooShort || mutation.isPending || !trip.data}
            onPress={() => mutation.mutate()}
          />
          {tooShort ? <Text style={styles.hint}>Add at least a sentence so the office can act on it.</Text> : null}
        </View>
      </KeyboardAvoidingView>
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
    paddingVertical: spacing.sm,
  },
  back: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  headerTitle: { color: colors.text, ...typography.h2 },
  content: { padding: spacing.lg, gap: spacing.md },
  centre: { paddingVertical: spacing.xxl, alignItems: 'center' },
  card: { gap: spacing.sm },
  personRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  name: { color: colors.text, ...typography.bodyStrong },
  muted: { color: colors.textMuted, ...typography.caption },
  sectionLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  optionActive: { borderColor: colors.green, backgroundColor: colors.greenTint },
  optionLabel: { color: colors.text, ...typography.body },
  optionLabelActive: { fontWeight: '700' },
  input: {
    minHeight: 120,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceAlt,
    padding: spacing.md,
    color: colors.text,
    textAlignVertical: 'top',
    ...typography.body,
  },
  counter: { color: colors.textMuted, textAlign: 'right', ...typography.caption },
  hint: { color: colors.textMuted, ...typography.caption, lineHeight: 18 },
  footer: {
    padding: spacing.lg,
    gap: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
});
