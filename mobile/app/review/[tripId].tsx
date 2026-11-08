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
import { submitReview } from '@/api/reviews';
import { Avatar, Banner, Button, Card } from '@/components/ui';
import { colors, radius, spacing, typography } from '@/theme';

const RATING_COPY: Record<number, string> = {
  1: 'Poor',
  2: 'Below expectations',
  3: 'Fine',
  4: 'Good',
  5: 'Excellent',
};

/**
 * Rate the other participant of a completed trip (§14).
 *
 * One review per side, editable never — so the screen is explicit about what it
 * is about to publish, and the API is the final authority on eligibility.
 */
export default function ReviewScreen() {
  const { tripId } = useLocalSearchParams<{ tripId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);

  const trip = useQuery({ queryKey: ['trip', tripId], queryFn: () => getTrip(tripId), enabled: Boolean(tripId) });

  const mutation = useMutation({
    mutationFn: () => submitReview(tripId, { rating, comment: comment.trim() || undefined }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['trip', tripId] }),
        queryClient.invalidateQueries({ queryKey: ['trips'] }),
        queryClient.invalidateQueries({ queryKey: ['pending-reviews'] }),
        queryClient.invalidateQueries({ queryKey: ['reviews'] }),
      ]);
      goBackOr(router);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Your rating could not be submitted.'),
  });

  const counterpart = trip.data?.counterpart;
  const firstName = counterpart?.full_name.split(' ')[0] ?? 'this member';

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" onPress={() => goBackOr(router)} style={styles.back} accessibilityLabel="Close">
          <Ionicons name="close" size={20} color={colors.navy} />
        </Pressable>
        <Text style={styles.headerTitle}>Rate your trip</Text>
        <View style={{ width: 36 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {error ? <Banner tone="danger" message={error} /> : null}

          {trip.isLoading ? (
            <View style={styles.centre}>
              <ActivityIndicator color={colors.green} />
            </View>
          ) : trip.isError || !trip.data ? (
            <Banner
              tone="danger"
              title="This trip is unavailable"
              message={trip.error instanceof ApiError ? trip.error.message : 'Please try again later.'}
            />
          ) : (
            <>
              <Card style={styles.card}>
                <View style={styles.personRow}>
                  <Avatar
                    name={counterpart?.full_name ?? 'Member'}
                    size={56}
                    photoUrl={counterpart?.profile_photo_url}
                  />
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={styles.name}>How was your trip with {firstName}?</Text>
                    <Text style={styles.muted}>
                      {trip.data.pickup_area} → {trip.data.destination_area}
                    </Text>
                  </View>
                </View>

                <View style={styles.stars}>
                  {[1, 2, 3, 4, 5].map((value) => (
                    <Pressable
                      key={value}
                      onPress={() => setRating(value)}
                      accessibilityRole="radio"
                      accessibilityState={{ selected: rating === value }}
                      accessibilityLabel={`${value} star${value === 1 ? '' : 's'}`}
                      hitSlop={6}
                    >
                      <Ionicons
                        name={value <= rating ? 'star' : 'star-outline'}
                        size={38}
                        color={value <= rating ? colors.star : colors.border}
                      />
                    </Pressable>
                  ))}
                </View>
                <Text style={styles.ratingCopy}>{RATING_COPY[rating]}</Text>
              </Card>

              <Card style={styles.card}>
                <Text style={styles.sectionLabel}>Add a comment (optional)</Text>
                <TextInput
                  style={styles.input}
                  value={comment}
                  onChangeText={setComment}
                  placeholder="Punctual, friendly driving — anything helpful for other members."
                  placeholderTextColor={colors.textMuted}
                  multiline
                  maxLength={500}
                />
                <Text style={styles.counter}>{comment.length}/500</Text>
                <Text style={styles.hint}>
                  Your first name and department are shown next to the rating. Your phone number and
                  home area never are.
                </Text>
              </Card>
            </>
          )}
        </ScrollView>

        <View style={styles.footer}>
          <Button
            label="Submit rating"
            icon="star-outline"
            loading={mutation.isPending}
            disabled={!trip.data?.can_review || mutation.isPending}
            onPress={() => mutation.mutate()}
          />
          {trip.data && !trip.data.can_review ? (
            <Text style={styles.hint}>This trip has already been rated.</Text>
          ) : null}
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
  name: { color: colors.text, ...typography.h2 },
  muted: { color: colors.textMuted, ...typography.caption },
  sectionLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  stars: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
  },
  ratingCopy: { color: colors.text, textAlign: 'center', ...typography.bodyStrong },
  input: {
    minHeight: 96,
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
