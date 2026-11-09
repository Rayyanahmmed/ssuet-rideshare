import { goBackOr } from '@/lib/navigation';
import { useState } from 'react';
import { ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '@/api/client';
import {
  cancelTrip,
  completeTrip,
  getTrip,
  markNoShow,
  startTrip,
  type Trip,
  type TripStatus,
} from '@/api/trips';
import { Avatar, Badge, Banner, Button, Card } from '@/components/ui';
import { formatDeparture, relativeDay } from '@/lib/format';
import { colors, radius, spacing, typography } from '@/theme';
import { appAlert } from '@/lib/appAlert';

const STATUS_TONE: Record<TripStatus, 'success' | 'warning' | 'danger' | 'neutral' | 'info'> = {
  CONFIRMED: 'success',
  IN_PROGRESS: 'info',
  COMPLETED: 'neutral',
  CANCELLED: 'danger',
  NO_SHOW: 'warning',
};

const STATUS_COPY: Record<TripStatus, string> = {
  CONFIRMED: 'Confirmed — waiting to start',
  IN_PROGRESS: 'Journey in progress',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  NO_SHOW: 'Passenger no-show',
};

export default function TripScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState('');
  const [showReason, setShowReason] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({ queryKey: ['trip', id], queryFn: () => getTrip(id), enabled: Boolean(id) });

  const refresh = async (trip: Trip) => {
    queryClient.setQueryData(['trip', trip.id], trip);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['trips'] }),
      queryClient.invalidateQueries({ queryKey: ['my-rides'] }),
      queryClient.invalidateQueries({ queryKey: ['rides'] }),
    ]);
  };

  const action = (mutationFn: (values: { id: string; reason?: string }) => Promise<Trip>) =>
    useMutation({
      mutationFn,
      onSuccess: (trip) => {
        setError(null);
        setShowReason(false);
        setReason('');
        return refresh(trip);
      },
      onError: (err) => {
        setError(err instanceof ApiError ? err.message : 'That action could not be completed.');
        void query.refetch();
      },
    });

  const startMutation = useMutation({
    mutationFn: () => startTrip(id),
    onSuccess: refresh,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'The journey could not be started.'),
  });

  const completeMutation = useMutation({
    mutationFn: () => completeTrip(id),
    onSuccess: async (trip) => {
      await refresh(trip);
      if (trip.status === 'COMPLETED') {
          appAlert(
          'Journey completed',
          `Thank you for pooling. You can now rate ${firstName}.`,
          [
            { text: 'Later', style: 'cancel' },
            { text: 'Rate now', onPress: () => router.push(`/review/${id}`) },
          ],
        );
      }
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Could not confirm the trip.'),
  });

  const cancelMutation = useMutation({
    mutationFn: (note?: string) => cancelTrip(id, note),
    onSuccess: refresh,
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Could not cancel this trip.'),
  });

  const blockMutation = useMutation({
    mutationFn: async (userId: string) => {
      await api.post(`/users/${userId}/block`);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['rides'] }),
        queryClient.invalidateQueries({ queryKey: ['trips'] }),
        queryClient.invalidateQueries({ queryKey: ['blocked'] }),
      ]);
      appAlert('Member blocked', 'You will not be matched with them again.');
    },
    onError: (err) =>
      appAlert('Could not block', err instanceof ApiError ? err.message : 'Please try again.'),
  });

  const noShowMutation = useMutation({
    mutationFn: (note?: string) => markNoShow(id, note),
    onSuccess: refresh,
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Could not record the no-show.'),
  });

  if (query.isLoading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.centre}>
          <ActivityIndicator color={colors.green} />
          <Text style={styles.muted}>Loading your trip…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (query.isError || !query.data) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.centre}>
          <Text style={styles.muted}>
            {query.error instanceof ApiError ? query.error.message : 'This trip is unavailable.'}
          </Text>
          <Button label="Go back" variant="secondary" fullWidth={false} onPress={() => goBackOr(router)} />
        </View>
      </SafeAreaView>
    );
  }

  const trip = query.data;
  const counterpart = trip.counterpart;
  const isDriver = trip.my_role === 'DRIVER';
  const firstName: string = counterpart.full_name.split(' ')[0] ?? counterpart.full_name;
  const live = ['CONFIRMED', 'IN_PROGRESS'].includes(trip.status);
  const busy =
    startMutation.isPending ||
    completeMutation.isPending ||
    cancelMutation.isPending ||
    noShowMutation.isPending;

  const call = () => {
    if (!counterpart.phone) {
      appAlert('No phone number', 'This member has not shared a phone number.');
      return;
    }
    void Linking.openURL(`tel:${counterpart.phone}`);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => goBackOr(router)} style={styles.back}>
          <Ionicons name="arrow-back" size={20} color={colors.navy} />
        </Pressable>
        <Text style={styles.headerTitle}>Your trip</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {error ? <Banner tone="danger" message={error} /> : null}

        <Card style={styles.card}>
          <View style={styles.rowBetween}>
            <Badge label={STATUS_COPY[trip.status]} tone={STATUS_TONE[trip.status]} icon="pulse-outline" />
            <Text style={styles.muted}>{isDriver ? 'You are driving' : 'You are the passenger'}</Text>
          </View>
          <Text style={styles.route}>
            {trip.pickup_area} → {trip.destination_area}
          </Text>
          {trip.departure_at ? (
            <Text style={styles.muted}>
              {relativeDay(trip.departure_at)} · {formatDeparture(trip.departure_at).split(' · ')[1]}
              {trip.vehicle ? ` · ${trip.vehicle.make_and_model} (${trip.vehicle.color})` : ''}
            </Text>
          ) : null}
        </Card>

        {trip.awaiting_my_confirmation ? (
          <Banner
            tone="warning"
            title="Confirm the journey"
            message={`${firstName} marked this trip as finished. Confirm on your side to close it.`}
          />
        ) : null}

        <Card style={styles.card}>
          <Text style={styles.sectionLabel}>{isDriver ? 'Your passenger' : 'Your driver'}</Text>
          <View style={styles.personRow}>
            <Avatar name={counterpart.full_name} size={48} photoUrl={counterpart.profile_photo_url} />
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={styles.name}>{counterpart.full_name}</Text>
              <Text style={styles.muted}>{counterpart.department}</Text>
            </View>
            <Pressable onPress={call} style={styles.callButton} accessibilityLabel="Call">
              <Ionicons name="call" size={18} color={colors.textInverse} />
            </Pressable>
          </View>
          {trip.meeting_point ? (
            <View style={styles.meeting}>
              <Ionicons name="location" size={16} color={colors.greenDark} />
              <Text style={styles.meetingText}>
                Meeting point: {trip.meeting_point}
              </Text>
            </View>
          ) : null}
          <Text style={styles.hint}>
            The exact meeting point and phone number are shared only between the two of you — never
            with other members.
          </Text>
        </Card>

        {trip.status === 'IN_PROGRESS' ? (
          <Card style={styles.card}>
            <Text style={styles.sectionLabel}>Completion</Text>
            <ConfirmRow
              label={isDriver ? 'You (driver)' : 'You (passenger)'}
              done={isDriver ? trip.driver_confirmed_complete : trip.passenger_confirmed_complete}
            />
            <ConfirmRow
              label={firstName}
              done={isDriver ? trip.passenger_confirmed_complete : trip.driver_confirmed_complete}
            />
            <Text style={styles.hint}>
              Both sides confirm before the trip counts as completed for either member.
            </Text>
          </Card>
        ) : null}

        {trip.status === 'CANCELLED' || trip.status === 'NO_SHOW' ? (
          <Card style={styles.card}>
            <Text style={styles.sectionLabel}>Why</Text>
            <Text style={styles.body}>{trip.cancellation_reason ?? 'No reason recorded.'}</Text>
          </Card>
        ) : null}

        {trip.status === 'COMPLETED' ? (
          <Card style={styles.card}>
            <Text style={styles.sectionLabel}>Rate this trip</Text>
            {trip.viewer_reviewed ? (
              <Text style={styles.hint}>
                Thanks — your rating of {firstName} is on their profile. Ratings build the trust the
                whole community relies on.
              </Text>
            ) : (
              <>
                <Text style={styles.hint}>
                  You travelled with {firstName}. A quick rating helps other SSUET members decide who
                  to pool with.
                </Text>
                <Button
                  label="Rate your trip"
                  icon="star-outline"
                  onPress={() => router.push(`/review/${trip.id}`)}
                />
              </>
            )}
          </Card>
        ) : null}

        {['COMPLETED', 'CANCELLED', 'NO_SHOW'].includes(trip.status) ? (
          <Card style={styles.card}>
            <Text style={styles.sectionLabel}>Safety &amp; support</Text>
            <Text style={styles.hint}>
              Something felt wrong on this journey? Reports go straight to the SSUET ride-share
              office and you will see the outcome here.
            </Text>
            <View style={styles.actionRow}>
              <Button
                label="Report a problem"
                variant="secondary"
                icon="flag-outline"
                fullWidth={false}
                onPress={() => router.push(`/report/${trip.id}`)}
              />
              <Button
                label="Block member"
                variant="ghost"
                icon="ban-outline"
                fullWidth={false}
                onPress={() =>
                  appAlert(
                    `Block ${firstName}?`,
                    'You will never be matched with this member again and neither of you can message the other.',
                    [
                      { text: 'Cancel', style: 'cancel' },
                      {
                        text: 'Block',
                        style: 'destructive',
                        onPress: () => blockMutation.mutate(counterpart.id),
                      },
                    ],
                  )
                }
              />
            </View>
          </Card>
        ) : null}

        <Card style={styles.card}>
          <Text style={styles.sectionLabel}>Trip chat</Text>
          <Text style={styles.hint}>
            A private conversation between you and {firstName} — live typing, read receipts and
            message history, visible only to the two of you.
          </Text>
          {trip.conversation_id ? (
            <Button
              label="Open chat"
              variant="secondary"
              icon="chatbubbles-outline"
              onPress={() => router.push(`/chat/${trip.conversation_id}`)}
            />
          ) : null}
        </Card>

        {live && (trip.can_cancel || trip.can_mark_no_show) ? (
          <Card style={styles.card}>
            <Text style={styles.sectionLabel}>Something went wrong?</Text>
            {showReason ? (
              <>
                <TextInput
                  style={styles.input}
                  placeholder="Add a short reason (visible to the other member and admins)"
                  value={reason}
                  onChangeText={setReason}
                  multiline
                />
                <View style={styles.actionRow}>
                  <Button
                    label="Cancel trip"
                    variant="danger"
                    fullWidth={false}
                    loading={cancelMutation.isPending}
                    onPress={() => cancelMutation.mutate(reason.trim() || undefined)}
                  />
                  <Button label="Back" variant="ghost" fullWidth={false} onPress={() => setShowReason(false)} />
                </View>
              </>
            ) : (
              <View style={styles.actionRow}>
                <Button
                  label="Cancel trip"
                  variant="danger"
                  fullWidth={false}
                  disabled={!trip.can_cancel || busy}
                  onPress={() => setShowReason(true)}
                />
                {isDriver ? (
                  <Button
                    label="Passenger no-show"
                    variant="secondary"
                    fullWidth={false}
                    disabled={!trip.can_mark_no_show || busy}
                    onPress={() =>
                      appAlert(
                        'Mark as no-show?',
                        'This records that the passenger never turned up and frees the seat.',
                        [
                          { text: 'Back', style: 'cancel' },
                          {
                            text: 'Mark no-show',
                            style: 'destructive',
                            onPress: () => noShowMutation.mutate(reason.trim() || undefined),
                          },
                        ],
                      )
                    }
                  />
                ) : null}
              </View>
            )}
          </Card>
        ) : null}
      </ScrollView>

      {live ? (
        <View style={styles.footer}>
          {trip.can_start ? (
            <Button
              label="Start journey"
              icon="navigate-outline"
              loading={startMutation.isPending}
              onPress={() => startMutation.mutate()}
            />
          ) : trip.can_complete ? (
            <Button
              label={isDriver ? 'Confirm trip finished' : 'Confirm I travelled'}
              icon="checkmark-circle-outline"
              loading={completeMutation.isPending}
              onPress={() => completeMutation.mutate()}
            />
          ) : trip.status === 'CONFIRMED' ? (
            <Button
              label={isDriver ? 'Starting opens closer to departure' : 'Waiting for the driver to start'}
              variant="secondary"
              disabled
              onPress={() => undefined}
            />
          ) : (
            <Button label="You have confirmed this trip" variant="secondary" disabled onPress={() => undefined} />
          )}
        </View>
      ) : trip.status === 'NO_SHOW' && isDriver ? (
        <View style={styles.footer}>
          <Button
            label="Close this journey"
            icon="checkmark-circle-outline"
            loading={completeMutation.isPending}
            onPress={() => completeMutation.mutate()}
          />
        </View>
      ) : null}
    </SafeAreaView>
  );
}

function ConfirmRow({ label, done }: { label: string; done: boolean }) {
  return (
    <View style={styles.confirmRow}>
      <Ionicons
        name={done ? 'checkmark-circle' : 'ellipse-outline'}
        size={18}
        color={done ? colors.green : colors.border}
      />
      <Text style={[styles.body, !done && styles.muted]}>{label}</Text>
      <Text style={styles.muted}>{done ? 'confirmed' : 'pending'}</Text>
    </View>
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
  centre: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.md, padding: spacing.lg },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  card: { gap: spacing.sm },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  route: { color: colors.text, ...typography.h1 },
  muted: { color: colors.textMuted, ...typography.caption },
  body: { color: colors.text, ...typography.body },
  sectionLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  personRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  name: { color: colors.text, ...typography.bodyStrong },
  callButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.green,
    alignItems: 'center',
    justifyContent: 'center',
  },
  meeting: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.greenTint,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  meetingText: { color: colors.greenDark, ...typography.caption, flex: 1, fontWeight: '600' },
  hint: { color: colors.textMuted, ...typography.caption, lineHeight: 17 },
  confirmRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  actionRow: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    minHeight: 70,
    color: colors.text,
    ...typography.body,
    textAlignVertical: 'top',
  },
  footer: {
    padding: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
});
