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
import { listMyReports, REPORT_CATEGORIES, type ReportStatus } from '@/api/reports';
import { Badge, Banner, Card, EmptyState } from '@/components/ui';
import { formatDate } from '@/lib/format';
import { colors, spacing, typography } from '@/theme';

const STATUS_TONE: Record<ReportStatus, 'warning' | 'info' | 'success' | 'neutral'> = {
  OPEN: 'warning',
  UNDER_REVIEW: 'info',
  RESOLVED: 'success',
  DISMISSED: 'neutral',
};

const STATUS_COPY: Record<ReportStatus, string> = {
  OPEN: 'Received — queued for review',
  UNDER_REVIEW: 'The office is reviewing this',
  RESOLVED: 'Resolved',
  DISMISSED: 'Closed — no action taken',
};

const categoryLabel = (value: string) =>
  REPORT_CATEGORIES.find((option) => option.value === value)?.label ?? 'Report';

/** Reports I have filed, with the office's decision (§15). */
export default function MyReportsScreen() {
  const router = useRouter();
  const query = useQuery({ queryKey: ['my-reports'], queryFn: () => listMyReports() });
  const page = query.data;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" onPress={() => goBackOr(router)} style={styles.back} accessibilityLabel="Back">
          <Ionicons name="arrow-back" size={20} color={colors.navy} />
        </Pressable>
        <Text style={styles.headerTitle}>My reports</Text>
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
            title="Could not load your reports"
            message={query.error instanceof ApiError ? query.error.message : 'Please try again.'}
          />
        ) : null}

        {query.isLoading ? (
          <View style={styles.centre}>
            <ActivityIndicator color={colors.green} />
          </View>
        ) : (page?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon="shield-checkmark-outline"
            title="You have not reported anyone"
            message="If a journey ever feels unsafe, open the trip and choose “Report a problem”. The ride-share office reviews every report."
          />
        ) : (
          page?.items.map((report) => (
            <Card key={report.id} style={styles.card}>
              <View style={styles.rowBetween}>
                <Text style={styles.category}>{categoryLabel(report.category)}</Text>
                <Badge label={STATUS_COPY[report.status]} tone={STATUS_TONE[report.status]} />
              </View>
              <Text style={styles.muted}>About {report.reported_user.full_name}</Text>
              <Text style={styles.body}>{report.description}</Text>
              {report.resolution_note ? (
                <View style={styles.note}>
                  <Ionicons name="information-circle-outline" size={16} color={colors.greenDark} />
                  <Text style={styles.noteText}>{report.resolution_note}</Text>
                </View>
              ) : null}
              <Text style={styles.muted}>Filed {formatDate(report.created_at)}</Text>
            </Card>
          ))
        )}
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
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  category: { color: colors.text, ...typography.bodyStrong },
  muted: { color: colors.textMuted, ...typography.caption },
  body: { color: colors.text, ...typography.body, lineHeight: 21 },
  note: {
    flexDirection: 'row',
    gap: spacing.sm,
    alignItems: 'flex-start',
    backgroundColor: colors.greenTint,
    borderRadius: 12,
    padding: spacing.md,
  },
  noteText: { flex: 1, color: colors.greenDark, ...typography.caption, lineHeight: 18 },
});
