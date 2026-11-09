import { useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import {
  acceptRequest,
  cancelMyRequest,
  cancelRide,
  driverInbox,
  myRequests,
  myRides,
  rejectRequest,
  type DriverRequest,
  type Ride,
} from '@/api/rides';
import { listTrips, type Trip } from '@/api/trips';
import { TripCard } from '@/components/TripCard';
import { Avatar, Badge, Button, Card, EmptyState } from '@/components/ui';
import { formatDeparture, relativeDay } from '@/lib/format';
import { colors, radius, spacing, typography } from '@/theme';
import { appAlert } from '@/lib/appAlert';

const TABS = ['Published', 'Requested', 'Upcoming', 'Completed', 'Cancelled'] as const;
type Tab = (typeof TABS)[number];

const STATUS_TONE: Record<string, 'success' | 'warning' | 'danger' | 'neutral' | 'info'> = {
  OPEN: 'success',
  MATCHED: 'info',
  IN_PROGRESS: 'info',
  COMPLETED: 'neutral',
  CANCELLED: 'danger',
  EXPIRED: 'neutral',
  PENDING: 'warning',
  ACCEPTED: 'success',
  REJECTED: 'danger',
};

export default function MyRidesScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>('Published');

  const ridesQuery = useQuery({ queryKey: ['my-rides'], queryFn: () => myRides() });
  const inboxQuery = useQuery({ queryKey: ['driver-inbox'], queryFn: driverInbox });
  const requestsQuery = useQuery({ queryKey: ['my-requests'], queryFn: myRequests });
  const upcomingTripsQuery = useQuery({
    queryKey: ['trips', 'upcoming'],
    queryFn: () => listTrips({ upcoming: true }),
  });
  const historyTripsQuery = useQuery({
    queryKey: ['trips', 'history'],
    queryFn: () => listTrips({ upcoming: false }),
  });

  const refreshAll = async () => {
    await Promise.all([
      ridesQuery.refetch(),
      inboxQuery.refetch(),
      requestsQuery.refetch(),
      upcomingTripsQuery.refetch(),
      historyTripsQuery.refetch(),
    ]);
  };

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['my-rides'] }),
      queryClient.invalidateQueries({ queryKey: ['driver-inbox'] }),
      queryClient.invalidateQueries({ queryKey: ['my-requests'] }),
      queryClient.invalidateQueries({ queryKey: ['rides'] }),
      queryClient.invalidateQueries({ queryKey: ['trips'] }),
    ]);
  };

  const acceptMutation = useMutation({
    mutationFn: (requestId: string) => acceptRequest(requestId),
    onSuccess: async () => {
      await invalidate();
      appAlert('Passenger confirmed', 'The seat is reserved, a private trip chat has been opened and other requesters were informed.');
    },
    onError: (error) =>
      appAlert(
        'Could not accept',
        error instanceof ApiError ? error.message : 'Please try again.',
      ),
  });

  const rejectMutation = useMutation({
    mutationFn: (requestId: string) => rejectRequest(requestId, 'Not available for this journey.'),
    onSuccess: invalidate,
  });

  const cancelRideMutation = useMutation({
    mutationFn: (rideId: string) => cancelRide(rideId, 'Cancelled by the driver'),
    onSuccess: invalidate,
  });

  const cancelRequestMutation = useMutation({
    mutationFn: (requestId: string) => cancelMyRequest(requestId),
    onSuccess: invalidate,
  });

  const rides = ridesQuery.data ?? [];
  const inbox = inboxQuery.data ?? [];
  const myRequestsList = requestsQuery.data?.items ?? [];

  const pendingByRide = useMemo(() => {
    const map = new Map<string, DriverRequest[]>();
    inbox
      .filter((item) => item.status === 'PENDING')
      .forEach((item) => {
        const list = map.get(item.ride_id) ?? [];
        list.push(item);
        map.set(item.ride_id, list);
      });
    return map;
  }, [inbox]);

  const published = rides.filter((ride) => ['OPEN', 'MATCHED', 'IN_PROGRESS'].includes(ride.status));
  const upcomingTrips = upcomingTripsQuery.data?.items ?? [];
  const historyTrips = historyTripsQuery.data?.items ?? [];
  const completedTrips = historyTrips.filter((trip) => trip.status === 'COMPLETED');
  const cancelledTrips = historyTrips.filter((trip) =>
    ['CANCELLED', 'NO_SHOW'].includes(trip.status),
  );
  const closedRides = rides.filter((ride) => ['CANCELLED', 'EXPIRED'].includes(ride.status));

  const isLoading = ridesQuery.isLoading || inboxQuery.isLoading || requestsQuery.isLoading;
  const error = ridesQuery.error ?? inboxQuery.error ?? requestsQuery.error;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>My rides</Text>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.tabScroll}
        contentContainerStyle={styles.tabRow}
      >
        {TABS.map((item) => {
          const active = item === tab;
          return (
            <Pressable
              key={item}
              onPress={() => setTab(item)}
              style={[styles.tab, active && styles.tabActive]}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
            >
              <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>{item}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={false} onRefresh={refreshAll} tintColor={colors.green} />}
      >
        {error ? (
          <Card>
            <EmptyState
              icon="cloud-offline-outline"
              title="Couldn't load your rides"
              message={error instanceof ApiError ? error.message : 'Check your connection and pull to refresh.'}
              action={<Button label="Retry" onPress={() => void refreshAll()} />}
            />
          </Card>
        ) : null}

        {isLoading && !error ? <Text style={styles.muted}>Loading your rides…</Text> : null}

        {tab === 'Published' && !isLoading ? (
          published.length === 0 ? (
            <Card>
              <EmptyState
                icon="car-outline"
                title="No published rides"
                message="Publish a journey you are already making — your empty seat can help someone get to campus."
                action={<Button label="Publish a ride" onPress={() => router.push('/(tabs)/publish')} />}
              />
            </Card>
          ) : (
            published.map((ride) => (
              <PublishedRideCard
                key={ride.id}
                ride={ride}
                requests={pendingByRide.get(ride.id) ?? []}
                onOpen={() => router.push(`/ride/${ride.id}`)}
                onAccept={(requestId) => acceptMutation.mutate(requestId)}
                onReject={(requestId) => rejectMutation.mutate(requestId)}
                onCancel={() =>
                  appAlert('Cancel journey?', 'Anyone waiting or confirmed will be notified.', [
                    { text: 'Keep it', style: 'cancel' },
                    {
                      text: 'Cancel journey',
                      style: 'destructive',
                      onPress: () => cancelRideMutation.mutate(ride.id),
                    },
                  ])
                }
                busy={acceptMutation.isPending || rejectMutation.isPending || cancelRideMutation.isPending}
              />
            ))
          )
        ) : null}

        {tab === 'Requested' && !isLoading ? (
          myRequestsList.length === 0 ? (
            <Card>
              <EmptyState
                icon="paper-plane-outline"
                title="No requests sent"
                message="Find a journey in Explore and ask to join — you will be notified as soon as the driver answers."
                action={<Button label="Explore rides" onPress={() => router.push('/(tabs)/explore')} />}
              />
            </Card>
          ) : (
            myRequestsList.map((request) => (
              <Card key={request.id} style={styles.card}>
                <View style={styles.rowBetween}>
                  <Text style={styles.cardTitle}>To {request.ride.destination_area}</Text>
                  <Badge label={request.status} tone={STATUS_TONE[request.status] ?? 'neutral'} />
                </View>
                <Text style={styles.muted}>
                  {request.ride.driver.full_name} · {relativeDay(request.ride.departure_at)} ·{' '}
                  {formatDeparture(request.ride.departure_at).split(' · ')[1]}
                </Text>
                {request.message ? <Text style={styles.note}>“{request.message}”</Text> : null}
                {request.response_note ? (
                  <Text style={styles.response}>Driver: {request.response_note}</Text>
                ) : null}
                <View style={styles.actionRow}>
                  <Button
                    label="View journey"
                    variant="secondary"
                    fullWidth={false}
                    onPress={() => router.push(`/ride/${request.ride_id}`)}
                  />
                  {request.status === 'PENDING' ? (
                    <Button
                      label="Withdraw"
                      variant="danger"
                      fullWidth={false}
                      onPress={() => cancelRequestMutation.mutate(request.id)}
                    />
                  ) : null}
                </View>
              </Card>
            ))
          )
        ) : null}

        {tab === 'Upcoming' ? (
          upcomingTripsQuery.isLoading ? (
            <Text style={styles.muted}>Loading your trips…</Text>
          ) : upcomingTrips.length === 0 ? (
            <Card>
              <EmptyState
                icon="calendar-outline"
                title="No upcoming trips"
                message="When a driver accepts your request — or a passenger joins your journey — the confirmed trip appears here."
                action={<Button label="Explore rides" onPress={() => router.push('/(tabs)/explore')} />}
              />
            </Card>
          ) : (
            upcomingTrips.map((trip: Trip) => (
              <TripCard key={trip.id} trip={trip} onPress={() => router.push(`/trip/${trip.id}`)} />
            ))
          )
        ) : null}

        {tab === 'Completed' ? (
          historyTripsQuery.isLoading ? (
            <Text style={styles.muted}>Loading history…</Text>
          ) : completedTrips.length === 0 ? (
            <Card>
              <EmptyState
                icon="ribbon-outline"
                title="No completed trips yet"
                message="A trip is completed once you and the other member both confirm it happened. After that you can rate each other."
              />
            </Card>
          ) : (
            completedTrips.map((trip: Trip) => (
              <TripCard key={trip.id} trip={trip} onPress={() => router.push(`/trip/${trip.id}`)} />
            ))
          )
        ) : null}

        {tab === 'Cancelled' ? (
          <>
            {cancelledTrips.map((trip: Trip) => (
              <TripCard key={trip.id} trip={trip} onPress={() => router.push(`/trip/${trip.id}`)} />
            ))}
            {closedRides.map((ride) => (
              <Card key={ride.id} style={styles.card}>
                <View style={styles.rowBetween}>
                  <Text style={styles.cardTitle}>
                    {ride.pickup_area} → {ride.destination_area}
                  </Text>
                  <Badge label={ride.status} tone={STATUS_TONE[ride.status] ?? 'neutral'} />
                </View>
                <Text style={styles.muted}>
                  {relativeDay(ride.departure_at)} ·{' '}
                  {formatDeparture(ride.departure_at).split(' · ')[1]} · no passenger travelled
                </Text>
              </Card>
            ))}
            {cancelledTrips.length === 0 && closedRides.length === 0 ? (
              <Card>
                <EmptyState
                  icon="close-circle-outline"
                  title="Nothing cancelled"
                  message="Cancelled trips and expired journeys stay here for your records."
                />
              </Card>
            ) : null}
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function PublishedRideCard({
  ride,
  requests,
  onOpen,
  onAccept,
  onReject,
  onCancel,
  busy,
}: {
  ride: Ride;
  requests: DriverRequest[];
  onOpen: () => void;
  onAccept: (requestId: string) => void;
  onReject: (requestId: string) => void;
  onCancel: () => void;
  busy: boolean;
}) {
  return (
    <Card style={styles.card}>
      <View style={styles.rowBetween}>
        <Text style={styles.cardTitle}>
          {ride.pickup_area} → {ride.destination_area}
        </Text>
        <Badge label={ride.status} tone={STATUS_TONE[ride.status] ?? 'neutral'} />
      </View>
      <Text style={styles.muted}>
        {relativeDay(ride.departure_at)} · {formatDeparture(ride.departure_at).split(' · ')[1]} ·{' '}
        {ride.fuel_preference === 'FREE' ? 'Free ride' : 'Fuel share'}
      </Text>

      <View style={styles.actionRow}>
        <Button label="Details" variant="secondary" fullWidth={false} onPress={onOpen} />
        {['OPEN', 'MATCHED'].includes(ride.status) ? (
          <Button label="Cancel" variant="danger" fullWidth={false} onPress={onCancel} disabled={busy} />
        ) : null}
      </View>

      {requests.length > 0 ? (
        <View style={styles.requestsBox}>
          <Text style={styles.requestsTitle}>
            {requests.length} request{requests.length > 1 ? 's' : ''} waiting
          </Text>
          {requests.map((request) => (
            <View key={request.id} style={styles.requestRow}>
              <Avatar
                name={request.passenger.full_name}
                size={36}
                photoUrl={request.passenger.profile_photo_url}
              />
              <View style={{ flex: 1, gap: 2 }}>
                <View style={styles.nameRow}>
                  <Text style={styles.requestName}>{request.passenger.full_name}</Text>
                  {request.passenger.verification_status === 'VERIFIED' ? (
                    <Ionicons name="shield-checkmark" size={13} color={colors.green} />
                  ) : null}
                </View>
                <Text style={styles.muted}>
                  {request.passenger.department} ·{' '}
                  {request.passenger.rating_count > 0
                    ? `${request.passenger.rating_average.toFixed(1)}★`
                    : 'New member'}
                </Text>
                {request.message ? <Text style={styles.note}>“{request.message}”</Text> : null}
              </View>
              <View style={styles.requestActions}>
                <Pressable
                  onPress={() => onAccept(request.id)}
                  style={[styles.iconButton, styles.iconAccept]}
                  disabled={busy}
                >
                  <Ionicons name="checkmark" size={18} color={colors.textInverse} />
                </Pressable>
                <Pressable
                  onPress={() => onReject(request.id)}
                  style={[styles.iconButton, styles.iconReject]}
                  disabled={busy}
                >
                  <Ionicons name="close" size={18} color={colors.danger} />
                </Pressable>
              </View>
            </View>
          ))}
          <Text style={styles.hint}>
            Accepting reserves your single seat and opens a private chat with your passenger.
          </Text>
        </View>
      ) : ride.status === 'OPEN' ? (
        <Text style={styles.hint}>No requests yet — your journey is visible in Explore.</Text>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  title: { color: colors.text, ...typography.display },
  tabScroll: { flexGrow: 0 },
  tabRow: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm, alignItems: 'center' },
  tab: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  tabActive: { backgroundColor: colors.navy, borderColor: colors.navy },
  tabLabel: { color: colors.textMuted, ...typography.caption, fontWeight: '600' },
  tabLabelActive: { color: colors.textInverse },
  content: { padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.md },
  card: { gap: spacing.sm },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  cardTitle: { color: colors.text, ...typography.bodyStrong, flex: 1 },
  muted: { color: colors.textMuted, ...typography.caption },
  note: { color: colors.text, ...typography.caption, fontStyle: 'italic' },
  response: { color: colors.info, ...typography.caption },
  actionRow: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  requestsBox: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
    gap: spacing.sm,
  },
  requestsTitle: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  requestRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
  requestName: { color: colors.text, ...typography.bodyStrong },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  requestActions: { flexDirection: 'row', gap: spacing.xs },
  iconButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconAccept: { backgroundColor: colors.green },
  iconReject: { backgroundColor: colors.dangerTint },
  hint: { color: colors.textMuted, ...typography.caption },
});
