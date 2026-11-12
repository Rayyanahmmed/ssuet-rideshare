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
  confirmPayment,
  getInvoice,
  getTrip,
  markArrived,
  markNoShow,
  markPaid,
  reportNonPayment,
  startTrip,
  type Trip,
  type TripStatus,
} from '@/api/trips';
import { Avatar, Badge, Banner, Button, Card } from '@/components/ui';
import { formatDeparture, relativeDay, rupees } from '@/lib/format';
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
  const [amountPkr, setAmountPkr] = useState('');
  const [showNonPayment, setShowNonPayment] = useState(false);
  const [nonPaymentNote, setNonPaymentNote] = useState('');

  const query = useQuery({ queryKey: ['trip', id], queryFn: () => getTrip(id), enabled: Boolean(id) });

  const invoiceQuery = useQuery({
    queryKey: ['invoice', id],
    queryFn: () => getInvoice(id),
    enabled: Boolean(id) && query.data?.payment_status === 'VERIFIED',
  });

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

  const confirmPaymentMutation = useMutation({
    mutationFn: () => {
      const parsed = Number.parseInt(amountPkr, 10);
      return confirmPayment(id, Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined);
    },
    onSuccess: async (payment) => {
      setError(null);
      await refresh(await getTrip(id));
      await queryClient.invalidateQueries({ queryKey: ['invoice', id] });
      queryClient.setQueryData(['trip', id], (current: Trip | undefined) =>
        current ? { ...current, payment_status: payment.status, invoice_number: payment.invoice_number, can_confirm_payment: false, can_report_non_payment: false } : current,
      );
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'The payment could not be recorded.'),
  });

  const nonPaymentMutation = useMutation({
    mutationFn: () => reportNonPayment(id, nonPaymentNote.trim()),
    onSuccess: async () => {
      setError(null);
      setShowNonPayment(false);
      setNonPaymentNote('');
      await refresh(await getTrip(id));
      await queryClient.invalidateQueries({ queryKey: ['my-reports'] });
      appAlert('Report sent', 'The SSUET ride-share office will review this non-payment report.');
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'The report could not be sent.'),
  });

  const arriveMutation = useMutation({
    mutationFn: () => markArrived(id),
    onSuccess: async (trip) => {
      setError(null);
      await refresh(trip);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Could not mark your arrival.'),
  });

  const markPaidMutation = useMutation({
    mutationFn: () => markPaid(id),
    onSuccess: async () => {
      setError(null);
      await refresh(await getTrip(id));
      appAlert('Payment marked', 'The driver has been asked to confirm the cash was received.');
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Could not mark the payment.'),
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

  // Cash payment for fuel-share rides opens as soon as the journey starts.
  const paymentOpen =
    trip.payment_required &&
    (trip.status === 'IN_PROGRESS' || trip.status === 'COMPLETED' || trip.payment_status !== null);
  // The driver cannot finish a paid ride until the cash is verified or reported.
  const blockedByPayment = isDriver && trip.status === 'IN_PROGRESS' && trip.payment_required && !trip.completion_ready;

  const driverSettle = (
    <>
      <TextInput
        style={styles.amountInput}
        placeholder="Amount received in Rs (optional)"
        keyboardType="number-pad"
        value={amountPkr}
        onChangeText={setAmountPkr}
      />
      <Button
        label="Cash received, verify payment"
        icon="cash-outline"
        loading={confirmPaymentMutation.isPending}
        onPress={() => confirmPaymentMutation.mutate()}
      />
      {showNonPayment ? (
        <>
          <TextInput
            style={styles.input}
            placeholder="Describe what happened (10 characters or more)"
            value={nonPaymentNote}
            onChangeText={setNonPaymentNote}
            multiline
          />
          <View style={styles.actionRow}>
            <Button
              label="Send report"
              variant="danger"
              fullWidth={false}
              loading={nonPaymentMutation.isPending}
              disabled={nonPaymentNote.trim().length < 10}
              onPress={() => nonPaymentMutation.mutate()}
            />
            <Button label="Back" variant="ghost" fullWidth={false} onPress={() => setShowNonPayment(false)} />
          </View>
        </>
      ) : (
        <Button
          label={`${firstName} has not paid`}
          variant="secondary"
          icon="alert-circle-outline"
          onPress={() => setShowNonPayment(true)}
        />
      )}
    </>
  );

  const agreedAmount =
    trip.fuel_contribution_type === 'NEGOTIABLE'
      ? 'Negotiable. Agree the amount with ' + firstName + ' before the trip.'
      : trip.fuel_contribution_amount
        ? `${rupees(trip.fuel_contribution_amount)} per passenger`
        : 'Amount not set by the driver';

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

        {trip.driver_arrived_at && !isDriver ? (
          <Banner
            tone="info"
            title="Driver has arrived"
            message="Head to the meeting point now. The journey is ready to start."
          />
        ) : null}

        {live && trip.fuel_preference === 'SHARE_FUEL' ? (
          <Card style={styles.card}>
            <Text style={styles.sectionLabel}>Fuel share agreement</Text>
            <Text style={styles.route}>{agreedAmount}</Text>
            <Text style={styles.hint}>
              Paid in cash at the meeting point. After the journey the driver confirms the cash was
              received, and an invoice is issued as evidence.
            </Text>
          </Card>
        ) : null}

        {live && isDriver ? (
          <Card style={styles.card}>
            <Text style={styles.sectionLabel}>Meeting point</Text>
            {trip.driver_arrived_at ? (
              <Badge label="You marked arrival" tone="success" icon="location-outline" />
            ) : (
              <Text style={styles.hint}>
                When you reach {trip.meeting_point ?? 'the meeting point'}, tap below. {firstName} is
                told straight away.
              </Text>
            )}
            {trip.can_mark_arrived ? (
              <Button
                label="I have arrived at the meeting point"
                icon="location-outline"
                loading={arriveMutation.isPending}
                onPress={() => arriveMutation.mutate()}
              />
            ) : null}
          </Card>
        ) : null}

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

        {paymentOpen ? (
          <Card style={styles.card}>
            <Text style={styles.sectionLabel}>Cash payment</Text>
            {trip.payment_status === 'VERIFIED' ? (
              <>
                <Badge label="Verified transaction" tone="success" icon="shield-checkmark-outline" />
                <Text style={styles.hint}>Invoice {trip.invoice_number}</Text>
                {invoiceQuery.data ? (
                  <Text style={styles.hint}>
                    Amount: {invoiceQuery.data.amount_pkr !== null ? `Rs ${invoiceQuery.data.amount_pkr}` : 'not recorded'} (cash)
                    {'\n'}Driver: {invoiceQuery.data.driver_name} · Passenger: {invoiceQuery.data.passenger_name}
                  </Text>
                ) : null}
              </>
            ) : trip.payment_status === 'NON_PAYMENT_REPORTED' ? (
              <Banner tone="warning" message="A non-payment report is open. The SSUET ride-share office will review it." />
            ) : trip.payment_status === 'PAID_BY_PASSENGER' ? (
              isDriver ? (
                <>
                  <Banner
                    tone="info"
                    title="Passenger says the cash is paid"
                    message="Confirm only if you have received the cash. If it has not arrived, report it."
                  />
                  {driverSettle}
                </>
              ) : (
                <Banner
                  tone="info"
                  title="Waiting for the driver"
                  message="The driver will confirm that the cash was received. The invoice appears here once they do."
                />
              )
            ) : isDriver ? (
              <>
                <Text style={styles.hint}>
                  Once {firstName} has paid you in cash, confirm it here. This creates a verified
                  transaction and an invoice you can show as evidence.
                </Text>
                {driverSettle}
              </>
            ) : (
              <>
                <Text style={styles.hint}>
                  After the journey, tap below once you have paid the cash fuel share. Your driver then
                  confirms it, and the invoice is issued.
                </Text>
                {trip.can_mark_paid ? (
                  <Button
                    label="I have paid the cash"
                    icon="cash-outline"
                    loading={markPaidMutation.isPending}
                    onPress={() => markPaidMutation.mutate()}
                  />
                ) : (
                  <Text style={styles.hint}>The payment opens when the driver confirms the journey is finished.</Text>
                )}
              </>
            )}
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

        {trip.id ? (
          <Card style={styles.card}>
            <Text style={styles.sectionLabel}>Safety &amp; support</Text>
            <Text style={styles.hint}>
              Something went wrong? You can report harassment, a broken commitment, a scam or a
              payment problem at any time. Reports go straight to the SSUET ride-share office and you
              will see the outcome here.
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
          ) : blockedByPayment ? (
            <Button
              label="Verify the cash payment to finish"
              icon="cash-outline"
              variant="secondary"
              disabled
              onPress={() => undefined}
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
  amountInput: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.text,
    ...typography.body,
  },
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
