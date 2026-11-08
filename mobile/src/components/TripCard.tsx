import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Avatar, Badge } from '@/components/ui';
import { formatTime, relativeDay } from '@/lib/format';
import type { Trip, TripStatus } from '@/api/trips';
import { colors, radius, shadow, spacing, typography } from '@/theme';

const STATUS_TONE: Record<TripStatus, 'success' | 'warning' | 'danger' | 'neutral' | 'info'> = {
  CONFIRMED: 'success',
  IN_PROGRESS: 'info',
  COMPLETED: 'neutral',
  CANCELLED: 'danger',
  NO_SHOW: 'warning',
};

const STATUS_LABEL: Record<TripStatus, string> = {
  CONFIRMED: 'Confirmed',
  IN_PROGRESS: 'In progress',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  NO_SHOW: 'No-show',
};

/** A matched journey card — the counterpart, when, and what needs doing next. */
export function TripCard({ trip, onPress }: { trip: Trip; onPress: () => void }) {
  const counterpart = trip.counterpart;
  const firstName = counterpart.full_name.split(' ')[0] ?? counterpart.full_name;
  const needsAction =
    trip.can_start || (trip.can_complete && !trip.awaiting_my_confirmation) || trip.awaiting_my_confirmation;

  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
      <View style={styles.header}>
        <Avatar name={counterpart.full_name} size={40} />
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={styles.name}>
            {firstName} · {trip.my_role === 'DRIVER' ? 'your passenger' : 'your driver'}
          </Text>
          <Text style={styles.muted}>
            {trip.departure_at
              ? `${relativeDay(trip.departure_at)} · ${formatTime(trip.departure_at)}`
              : 'Departure unavailable'}
          </Text>
        </View>
        <Badge label={STATUS_LABEL[trip.status]} tone={STATUS_TONE[trip.status]} />
      </View>

      <View style={styles.routeRow}>
        <Ionicons name="navigate-outline" size={14} color={colors.textMuted} />
        <Text style={styles.route} numberOfLines={1}>
          {trip.pickup_area} → {trip.destination_area}
        </Text>
      </View>

      {trip.awaiting_my_confirmation ? (
        <View style={styles.action}>
          <Ionicons name="alert-circle" size={14} color={colors.warning} />
          <Text style={styles.actionText}>Waiting for your confirmation</Text>
        </View>
      ) : trip.can_start ? (
        <View style={styles.action}>
          <Ionicons name="play-circle" size={14} color={colors.info} />
          <Text style={styles.actionText}>Ready to start</Text>
        </View>
      ) : needsAction ? (
        <View style={styles.action}>
          <Ionicons name="checkmark-circle" size={14} color={colors.greenDark} />
          <Text style={styles.actionText}>Confirm when you arrive</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.sm,
    ...shadow.card,
  },
  pressed: { opacity: 0.9 },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  name: { color: colors.text, ...typography.bodyStrong },
  muted: { color: colors.textMuted, ...typography.caption },
  routeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  route: { color: colors.text, ...typography.body, flex: 1 },
  action: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.sm,
    padding: spacing.sm,
  },
  actionText: { color: colors.text, ...typography.caption, fontWeight: '600' },
});
