import { goBackOr } from '@/lib/navigation';
import { useState } from 'react';
import {
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
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import { PHOTO_REPORT_REASONS, reportProfilePhoto, type PhotoReportReason } from '@/api/reports';
import { Banner, Button, Card } from '@/components/ui';
import { colors, radius, spacing, typography } from '@/theme';

/**
 * Report a member's profile photo (§15, Phase 15).
 *
 * Addressed by member rather than by image: if the member uploads a different picture
 * before an administrator looks, the report still points at what was reported, because
 * the server pinned the file when the complaint was filed.
 */
export default function ReportPhotoScreen() {
  const { userId, name } = useLocalSearchParams<{ userId: string; name?: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState<PhotoReportReason>('OFFENSIVE');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => reportProfilePhoto(userId, { reason, description: description.trim() }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['my-reports'] });
      goBackOr(router);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Your report could not be sent.'),
  });

  const tooShort = description.trim().length < 10;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={styles.header}>
          <Pressable accessibilityLabel="Go back" onPress={() => goBackOr(router)} accessibilityRole="button" hitSlop={12}>
            <Ionicons name="arrow-back" size={22} color={colors.navy} />
          </Pressable>
          <Text style={styles.headerTitle}>Report photo</Text>
        </View>

        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Text style={styles.intro}>
            {name ? `${name}'s picture` : 'This picture'} will be reviewed by the SSUET ride-share
            office. They see the exact photo you are reporting, even if it changes later.
          </Text>

          {error ? <Banner tone="danger" title="Not sent" message={error} /> : null}

          <Card style={styles.card}>
            <Text style={styles.sectionLabel}>What is wrong with it?</Text>
            {PHOTO_REPORT_REASONS.map((option) => {
              const selected = reason === option.value;
              return (
                <Pressable
                  key={option.value}
                  onPress={() => setReason(option.value)}
                  accessibilityRole="radio"
                  accessibilityState={{ selected }}
                  style={[styles.option, selected && styles.optionSelected]}
                >
                  <Ionicons
                    name={selected ? 'radio-button-on' : 'radio-button-off'}
                    size={18}
                    color={selected ? colors.greenDark : colors.textMuted}
                  />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.optionLabel}>{option.label}</Text>
                    <Text style={styles.optionHint}>{option.hint}</Text>
                  </View>
                </Pressable>
              );
            })}
          </Card>

          <Card style={styles.card}>
            <Text style={styles.sectionLabel}>What happened?</Text>
            <TextInput
              style={styles.input}
              value={description}
              onChangeText={setDescription}
              placeholder="Describe the problem in a sentence or two."
              placeholderTextColor={colors.textMuted}
              multiline
              maxLength={1000}
            />
            <Text style={styles.counter}>{description.trim().length}/1000</Text>
          </Card>

          <Button
            label="Send report"
            onPress={() => mutation.mutate()}
            disabled={tooShort || mutation.isPending}
            loading={mutation.isPending}
            icon="flag-outline"
          />
          <Text style={styles.footnote}>
            False reports are visible to the office. Use it for pictures that break the
            community rules, not for people you disagree with.
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  headerTitle: { ...typography.h1, color: colors.navy },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  intro: { ...typography.body, color: colors.textMuted },
  card: { gap: spacing.sm },
  sectionLabel: { ...typography.label, color: colors.navy },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
  },
  optionSelected: { borderColor: colors.greenDark, backgroundColor: colors.greenTint },
  optionLabel: { ...typography.body, fontWeight: '600', color: colors.navy },
  optionHint: { ...typography.caption, color: colors.textMuted },
  input: {
    minHeight: 110,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    textAlignVertical: 'top',
    color: colors.navy,
  },
  counter: { ...typography.caption, color: colors.textMuted, textAlign: 'right' },
  footnote: { ...typography.caption, color: colors.textMuted },
});
