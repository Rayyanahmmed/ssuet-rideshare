import { goBackOr } from '@/lib/navigation';
import { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import { cancelRide, getRide, requestSeat } from '@/api/rides';
import { Avatar, Badge, Banner, Button, Card, TextField } from '@/components/ui';
import { WebMap } from '@/components/map/WebMap';
import { formatDeparture, relativeDay, rupees } from '@/lib/format';
import { useAuthStore } from '@/store/auth';
import { colors, radius, spacing, typography } from '@/theme';

export default function RideDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);

  const [sheetOpen, setSheetOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({ queryKey: ['ride', id], queryFn: () => getRide(id), enabled: Boolean(id) });

  const requestMutation = useMutation({
    mutationFn: () => requestSeat(id, message.trim() || undefined),
    onSuccess: async () => {
      setSheetOpen(false);
      setMessage('');
      await queryClient.invalidateQueries({ queryKey: ['ride', id] });
      await queryClient.invalidateQueries({ queryKey: ['rides'] });
      Alert.alert('Request sent', 'The driver will be notified. You can follow the status in My Rides.');
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : 'Could not send your request.');
      void query.refetch();
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelRide(id, 'Cancelled by the driver'),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['ride', id] });
      await queryClient.invalidateQueries({ queryKey: ['rides'] });
      await queryClient.invalidateQueries({ queryKey: ['my-rides'] });
    },
  });

  if (query.isLoading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.loading}>
          <ActivityIndicator color={colors.green} />
          <Text style={styles.loadingText}>Loading journey…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (query.isError || !query.data) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.header}>
          <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => goBackOr(router)} style={styles.back}>
            <Ionicons name="arrow-back" size={20} color={colors.navy} />
          </Pressable>
        </View>
        <View style={styles.loading}>
          <Text style={styles.loadingText}>
            {query.error instanceof ApiError ? query.error.message : 'This journey is unavailable.'}
          </Text>
          <Button label="Go back" variant="secondary" onPress={() => goBackOr(router)} fullWidth={false} />
        </View>
      </SafeAreaView>
    );
  }

  const ride = query.data;
  const isFree = ride.fuel_preference === 'FREE';
  const verified = user?.verification_status === 'VERIFIED';
  const requestPending = ride.my_request_status === 'PENDING';
  const requestAccepted = ride.my_request_status === 'ACCEPTED';

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => goBackOr(router)} style={styles.back}>
          <Ionicons name="arrow-back" size={20} color={colors.navy} />
        </Pressable>
        <Text style={styles.headerTitle}>Journey details</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {ride.pickup_point && ride.destination_point ? (
          <View style={styles.mapWrap}>
            <WebMap
              latitude={ride.pickup_point.latitude}
              longitude={ride.pickup_point.longitude}
              height={180}
              fit
              pins={[
                { id: 'pickup', latitude: ride.pickup_point.latitude, longitude: ride.pickup_point.longitude, color: colors.green },
                {
                  id: 'destination',
                  latitude: ride.destination_point.latitude,
                  longitude: ride.destination_point.longitude,
                  color: colors.navy,
                },
              ]}
            />
          </View>
        ) : (
          <Card style={styles.routeCard}>
            <View style={styles.routeRow}>
              <View style={[styles.dot, { backgroundColor: colors.green }]} />
              <View style={{ flex: 1 }}>
                <Text style={styles.routeLabel}>Pickup area</Text>
                <Text style={styles.routeValue}>{ride.pickup_area}</Text>
              </View>
            </View>
            <View style={styles.routeDivider} />
            <View style={styles.routeRow}>
              <View style={[styles.dot, { backgroundColor: colors.navy }]} />
              <View style={{ flex: 1 }}>
                <Text style={styles.routeLabel}>Destination</Text>
                <Text style={styles.routeValue}>{ride.destination_area}</Text>
              </View>
            </View>
            <Text style={styles.routeHint}>
              The exact meeting point is shared once your request is accepted.
            </Text>
          </Card>
        )}

        <Card style={styles.card}>
          <View style={styles.driverRow}>
            <Avatar
              name={ride.driver.full_name}
              size={52}
              photoUrl={ride.driver.profile_photo_url}
            />
            <View style={{ flex: 1, gap: 2 }}>
              <View style={styles.nameRow}>
                <Text style={styles.name}>{ride.driver.full_name}</Text>
                {ride.driver.verification_status === 'VERIFIED' ? (
                  <Ionicons name="shield-checkmark" size={15} color={colors.green} />
                ) : null}
              </View>
              <Text style={styles.muted}>
                {ride.driver.role === 'TEACHER' ? 'Teacher' : 'Student'} · {ride.driver.department}
              </Text>
              <View style={styles.ratingRow}>
                <Ionicons name="star" size={13} color={colors.star} />
                <Text style={styles.muted}>
                  {ride.driver.rating_count > 0
                    ? `${ride.driver.rating_average.toFixed(1)} · ${ride.driver.rating_count} reviews`
                    : 'No reviews yet'}
                </Text>
                <Text style={styles.muted}> · {ride.driver.completed_trips_count} trips</Text>
              </View>
            </View>
            {ride.driver.profile_photo_url && !ride.is_own_ride ? (
              <Pressable
                onPress={() =>
                  router.push({
                    pathname: '/report-photo/[userId]',
                    params: { userId: ride.driver.id, name: ride.driver.full_name },
                  })
                }
                accessibilityRole="button"
                accessibilityLabel={`Report ${ride.driver.full_name}'s photo`}
                hitSlop={10}
                style={styles.photoReportButton}
              >
                <Ionicons name="flag-outline" size={16} color={colors.textMuted} />
              </Pressable>
            ) : null}
          </View>

          {ride.vehicle ? (
            <View style={styles.vehicleRow}>
              <Ionicons
                name={ride.vehicle.vehicle_type === 'BIKE' ? 'bicycle' : 'car-sport'}
                size={18}
                color={colors.navy}
              />
              <Text style={styles.vehicleText}>
                {ride.vehicle.make_and_model} · {ride.vehicle.color}
              </Text>
              {ride.vehicle.is_verified ? (
                <Badge label="Vehicle verified" tone="success" icon="checkmark-circle" />
              ) : (
                <Badge label="Vehicle pending" tone="warning" />
              )}
            </View>
          ) : null}
        </Card>

        <Card style={styles.card}>
          <Row icon="calendar-outline" label="Departure" value={`${relativeDay(ride.departure_at)} · ${formatDeparture(ride.departure_at).split(' · ')[1]}`} />
          <Row
            icon="people-outline"
            label="Seats"
            value={`${ride.seats_remaining} of ${ride.available_seats} available`}
          />
          <Row
            icon={isFree ? 'heart-outline' : 'wallet-outline'}
            label="Contribution"
            value={
              isFree
                ? 'Free ride'
                : ride.contribution?.type === 'NEGOTIABLE'
                  ? 'Fuel share · negotiable'
                  : ride.contribution?.amount
                    ? `Fuel share · ${rupees(ride.contribution.amount)}`
                    : 'Fuel share'
            }
          />
          {!isFree ? (
            <View style={styles.disclaimer}>
              <Text style={styles.disclaimerText}>
                Fuel contributions are a voluntary agreement between the two members, settled
                offline. SSUET RideShare takes no payment and no commission.
              </Text>
            </View>
          ) : null}
          {ride.note ? <Row icon="information-circle-outline" label="Driver's note" value={ride.note} /> : null}
        </Card>

        {error ? <Banner tone="danger" message={error} /> : null}

        {requestAccepted ? (
          <Banner
            tone="success"
            title="You are confirmed"
            message={`Meeting point: ${ride.pickup_area}. Open the trip to start the journey, confirm completion and call your driver.`}
          />
        ) : null}
      </ScrollView>

      <View style={styles.footer}>
        {ride.is_own_ride ? (
          <Button
            label={cancelMutation.isPending ? 'Cancelling…' : 'Cancel this journey'}
            variant="danger"
            loading={cancelMutation.isPending}
            onPress={() =>
              Alert.alert('Cancel journey?', 'The passenger (if any) will be notified immediately.', [
                { text: 'Keep it', style: 'cancel' },
                { text: 'Cancel journey', style: 'destructive', onPress: () => cancelMutation.mutate() },
              ])
            }
          />
        ) : requestPending ? (
          <Button label="Request pending" variant="secondary" disabled onPress={() => undefined} />
        ) : requestAccepted ? (
          <Button
            label="Open trip"
            onPress={() =>
              ride.my_trip_id
                ? router.push(`/trip/${ride.my_trip_id}`)
                : router.push('/(tabs)/my-rides')
            }
            icon="navigate-outline"
          />
        ) : !verified ? (
          <Button label="Verify your account to request" onPress={() => router.push('/verification')} icon="shield-checkmark-outline" />
        ) : ride.can_request ? (
          <Button label="Request to join" onPress={() => setSheetOpen(true)} icon="paper-plane-outline" />
        ) : (
          <Button label="This journey is no longer available" variant="secondary" disabled onPress={() => undefined} />
        )}
      </View>

      <Modal visible={sheetOpen} animationType="slide" transparent onRequestClose={() => setSheetOpen(false)}>
        <View style={styles.sheetBackdrop}>
          <View style={styles.sheet}>
            <View style={styles.sheetHandle} />
            <Text style={styles.sheetTitle}>Request to join</Text>
            <Text style={styles.sheetSubtitle}>
              Add a short note so {ride.driver.full_name.split(' ')[0]} knows where you are travelling from.
            </Text>
            <TextField
              label="Message (optional)"
              placeholder="Assalam-o-Alaikum, I live near Five Star Chowrangi."
              value={message}
              onChangeText={setMessage}
              multiline
            />
            <Button
              label="Send request"
              onPress={() => requestMutation.mutate()}
              loading={requestMutation.isPending}
            />
            <Button label="Cancel" variant="ghost" onPress={() => setSheetOpen(false)} />
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function Row({
  icon,
  label,
  value,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
}) {
  return (
    <View style={styles.row}>
      <Ionicons name={icon} size={16} color={colors.textMuted} />
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue} numberOfLines={2}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  photoReportButton: { padding: spacing.xs, alignSelf: 'flex-start' },
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
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.md, padding: spacing.lg },
  loadingText: { color: colors.textMuted, ...typography.body, textAlign: 'center' },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  mapWrap: { borderRadius: radius.lg, overflow: 'hidden' },
  map: { height: 180 },
  routeCard: { gap: spacing.sm },
  routeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  dot: { width: 10, height: 10, borderRadius: 5 },
  routeLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  routeValue: { color: colors.text, ...typography.bodyStrong },
  routeDivider: { height: 1, backgroundColor: colors.border, marginLeft: 18 },
  routeHint: { color: colors.textMuted, ...typography.caption, marginTop: spacing.xs },
  card: { gap: spacing.md },
  driverRow: { flexDirection: 'row', gap: spacing.md, alignItems: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  name: { color: colors.text, ...typography.h2 },
  muted: { color: colors.textMuted, ...typography.caption },
  ratingRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  vehicleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
  },
  vehicleText: { color: colors.text, ...typography.caption, flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  rowLabel: { color: colors.textMuted, ...typography.caption, width: 110 },
  rowValue: { color: colors.text, ...typography.bodyStrong, flex: 1 },
  disclaimer: {
    backgroundColor: colors.infoTint,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  disclaimerText: { color: colors.info, ...typography.caption, lineHeight: 17 },
  footer: {
    padding: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  sheetBackdrop: { flex: 1, backgroundColor: 'rgba(11,31,58,0.45)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.md,
    paddingBottom: spacing.xxl,
  },
  sheetHandle: { width: 44, height: 4, borderRadius: 2, backgroundColor: colors.border, alignSelf: 'center' },
  sheetTitle: { color: colors.text, ...typography.h1 },
  sheetSubtitle: { color: colors.textMuted, ...typography.caption },
});
