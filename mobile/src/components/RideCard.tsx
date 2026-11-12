import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Avatar, Badge } from '@/components/ui';
import { formatDeparture, fuelShareLabel, relativeDay } from '@/lib/format';
import type { Ride } from '@/api/rides';
import { colors, radius, shadow, spacing, typography } from '@/theme';

/**
 * The card users decide from (§8): who is driving, whether they are verified,
 * where from, when, in what — and whether the seat is free or fuel-shared.
 */
export function RideCard({ ride, onPress }: { ride: Ride; onPress: () => void }) {
  const isFree = ride.fuel_preference === 'FREE';
  const vehicleIcon = ride.vehicle?.vehicle_type === 'BIKE' ? 'bicycle' : 'car-sport';

  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
      <View style={styles.header}>
        <Avatar name={ride.driver.full_name} size={44} />
        <View style={styles.headerText}>
          <View style={styles.nameRow}>
            <Text style={styles.name} numberOfLines={1}>
              {ride.driver.full_name}
            </Text>
            {ride.driver.verification_status === 'VERIFIED' ? (
              <Ionicons name="shield-checkmark" size={14} color={colors.green} />
            ) : null}
          </View>
          <Text style={styles.sub} numberOfLines={1}>
            {ride.driver.role === 'TEACHER' ? 'Teacher' : 'Student'} · {ride.driver.department}
          </Text>
        </View>
        <View style={styles.rating}>
          <Ionicons name="star" size={12} color={colors.star} />
          <Text style={styles.ratingText}>
            {ride.driver.rating_count > 0 ? ride.driver.rating_average.toFixed(1) : 'New'}
          </Text>
        </View>
      </View>

      <View style={styles.route}>
        <View style={styles.routeRow}>
          <View style={[styles.dot, styles.dotFrom]} />
          <Text style={styles.routeText} numberOfLines={1}>
            {ride.pickup_area}
          </Text>
        </View>
        <View style={styles.routeLine} />
        <View style={styles.routeRow}>
          <View style={[styles.dot, styles.dotTo]} />
          <Text style={styles.routeText} numberOfLines={1}>
            {ride.destination_area}
          </Text>
        </View>
      </View>

      <View style={styles.metaRow}>
        <View style={styles.metaItem}>
          <Ionicons name="time-outline" size={14} color={colors.textMuted} />
          <Text style={styles.metaText}>
            {relativeDay(ride.departure_at)} · {formatDeparture(ride.departure_at).split(' · ')[1]}
          </Text>
        </View>
        <View style={styles.metaItem}>
          <Ionicons name={vehicleIcon} size={14} color={colors.textMuted} />
          <Text style={styles.metaText} numberOfLines={1}>
            {ride.vehicle?.make_and_model ?? (ride.vehicle?.vehicle_type === 'BIKE' ? 'Bike' : 'Car')}
          </Text>
        </View>
      </View>

      <View style={styles.footer}>
        {isFree ? (
          <Badge label="Free ride" tone="success" icon="heart-outline" />
        ) : (
          <Badge
            label={fuelShareLabel(ride.contribution)}
            tone="info"
            icon="wallet-outline"
          />
        )}
        <View style={styles.seat}>
          <Ionicons name="person-outline" size={13} color={colors.textMuted} />
          <Text style={styles.seatText}>
            {ride.seats_remaining} {ride.seats_remaining === 1 ? 'seat' : 'seats'}
          </Text>
        </View>
      </View>

      {ride.my_request_status ? (
        <View style={styles.statusRow}>
          <Badge
            label={
              ride.my_request_status === 'PENDING'
                ? 'Request pending'
                : ride.my_request_status === 'ACCEPTED'
                  ? 'You are confirmed'
                  : `Request ${ride.my_request_status.toLowerCase()}`
            }
            tone={ride.my_request_status === 'ACCEPTED' ? 'success' : 'warning'}
            icon={ride.my_request_status === 'ACCEPTED' ? 'checkmark-circle' : 'time-outline'}
          />
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadow.card,
  },
  pressed: { opacity: 0.9 },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  headerText: { flex: 1, gap: 2 },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  name: { color: colors.text, ...typography.bodyStrong, flexShrink: 1 },
  sub: { color: colors.textMuted, ...typography.caption },
  rating: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  ratingText: { color: colors.textMuted, ...typography.caption, fontWeight: '600' },
  route: { gap: 2 },
  routeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  dot: { width: 8, height: 8, borderRadius: 4 },
  dotFrom: { backgroundColor: colors.green },
  dotTo: { backgroundColor: colors.navy },
  routeLine: { width: 2, height: 14, backgroundColor: colors.border, marginLeft: 3 },
  routeText: { color: colors.text, ...typography.body, flex: 1 },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 5, flexShrink: 1 },
  metaText: { color: colors.textMuted, ...typography.caption, flexShrink: 1 },
  footer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  seat: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  seatText: { color: colors.textMuted, ...typography.caption },
  statusRow: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm },
});
