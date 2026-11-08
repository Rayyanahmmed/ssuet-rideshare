import { goBackOr } from '@/lib/navigation';
import { useQuery } from '@tanstack/react-query';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { ApiError } from '@/api/client';
import { listMyReceivedReviews } from '@/api/reviews';
import { Avatar, Badge, Banner, Card, EmptyState } from '@/components/ui';
import { formatDate } from '@/lib/format';
import { colors, radius, spacing, typography } from '@/theme';

/** Everything other members have said about me (§14) — read-only by design. */
export default function MyReviewsScreen() {
  const router = useRouter();
  const query = useQuery({
    queryKey: ['reviews', 'received'],
    queryFn: () => listMyReceivedReviews(1, 50),
  });

  const page = query.data;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" onPress={() => goBackOr(router)} style={styles.back} accessibilityLabel="Back">
          <Ionicons name="arrow-back" size={20} color={colors.navy} />
        </Pressable>
        <Text style={styles.headerTitle}>My ratings</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} tintColor={colors.green} />
        }
      >
        {query.isError ? (
          <Banner
            tone="danger"
            title="Could not load your ratings"
            message={query.error instanceof ApiError ? query.error.message : 'Please try again.'}
          />
        ) : null}

        {query.isLoading ? (
          <View style={styles.centre}>
            <ActivityIndicator color={colors.green} />
          </View>
        ) : page ? (
          <>
            <Card style={styles.card}>
              <View style={styles.summary}>
                <View style={styles.scoreBox}>
                  <Text style={styles.score}>{page.average ? page.average.toFixed(1) : '—'}</Text>
                  <View style={styles.stars}>
                    {[1, 2, 3, 4, 5].map((star) => (
                      <Ionicons
                        key={star}
                        name={star <= Math.round(page.average) ? 'star' : 'star-outline'}
                        size={14}
                        color={colors.star}
                      />
                    ))}
                  </View>
                  <Text style={styles.muted}>
                    {page.total} review{page.total === 1 ? '' : 's'}
                  </Text>
                </View>
                <View style={styles.breakdown}>
                  {[5, 4, 3, 2, 1].map((star) => {
                    const count = page.breakdown[String(star)] ?? 0;
                    const width = page.total ? Math.round((count / page.total) * 100) : 0;
                    return (
                      <View key={star} style={styles.barRow}>
                        <Text style={styles.barLabel}>{star}</Text>
                        <View style={styles.barTrack}>
                          <View style={[styles.barFill, { width: `${width}%` }]} />
                        </View>
                        <Text style={styles.barCount}>{count}</Text>
                      </View>
                    );
                  })}
                </View>
              </View>
              <Text style={styles.hint}>
                Only members who travelled with you can rate you, and only once per trip.
              </Text>
            </Card>

            {page.items.length === 0 ? (
              <EmptyState
                icon="star-outline"
                title="No ratings yet"
                message="Complete a trip and your travel partner can rate the journey. Ratings build the trust that makes pooling work."
              />
            ) : (
              page.items.map((review) => (
                <Card key={review.id} style={styles.card}>
                  <View style={styles.reviewHead}>
                    <Avatar
                      name={review.author.full_name}
                      size={40}
                      photoUrl={review.author.profile_photo_url}
                    />
                    <View style={{ flex: 1, gap: 2 }}>
                      <Text style={styles.name}>{review.author.full_name}</Text>
                      <Text style={styles.muted}>{review.author.department}</Text>
                    </View>
                    <Badge label={`${review.rating} ★`} tone={review.rating >= 4 ? 'success' : review.rating === 3 ? 'warning' : 'danger'} />
                  </View>
                  {review.comment ? <Text style={styles.body}>{review.comment}</Text> : null}
                  <Text style={styles.muted}>
                    {review.pickup_area} → {review.destination_area} · {formatDate(review.created_at)}
                  </Text>
                </Card>
              ))
            )}
          </>
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
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  centre: { paddingVertical: spacing.xxl, alignItems: 'center' },
  card: { gap: spacing.sm },
  summary: { flexDirection: 'row', gap: spacing.lg, alignItems: 'center' },
  scoreBox: { alignItems: 'center', gap: 4, width: 96 },
  score: { color: colors.text, fontSize: 40, fontWeight: '700' },
  stars: { flexDirection: 'row', gap: 2 },
  breakdown: { flex: 1, gap: 6 },
  barRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  barLabel: { color: colors.textMuted, width: 10, ...typography.caption },
  barTrack: { flex: 1, height: 8, borderRadius: radius.pill, backgroundColor: colors.surfaceAlt, overflow: 'hidden' },
  barFill: { height: '100%', borderRadius: radius.pill, backgroundColor: colors.star },
  barCount: { color: colors.textMuted, width: 22, textAlign: 'right', ...typography.caption },
  reviewHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  name: { color: colors.text, ...typography.bodyStrong },
  muted: { color: colors.textMuted, ...typography.caption },
  body: { color: colors.text, ...typography.body, lineHeight: 21 },
  hint: { color: colors.textMuted, ...typography.caption, lineHeight: 18 },
});
