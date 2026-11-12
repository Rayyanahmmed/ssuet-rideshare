import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import { myVehicles, publishRide, type ContributionType, type Direction } from '@/api/rides';
import { LocationPicker } from '@/components/LocationPicker';
import { Badge, Banner, Button, Card, ChipRow, TextField } from '@/components/ui';
import { SSUET, type AreaPoint } from '@/lib/areas';
import { formatTime, rupees } from '@/lib/format';
import { useAuthStore } from '@/store/auth';
import { colors, radius, spacing, typography } from '@/theme';
import { appAlert } from '@/lib/appAlert';

type FuelChoice = 'FREE' | 'SHARE_FUEL';

const STEPS = ['Direction', 'Location', 'Time', 'Vehicle', 'Fare'] as const;
const TIME_SLOTS = Array.from({ length: 33 }, (_, index) => {
  const totalMinutes = 6 * 60 + index * 30; // 06:00 → 22:00
  return { hour: Math.floor(totalMinutes / 60), minute: totalMinutes % 60 };
});

function nextDays(count: number) {
  const days: Date[] = [];
  const now = new Date();
  for (let index = 0; index < count; index += 1) {
    const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() + index);
    days.push(day);
  }
  return days;
}

function dayLabel(date: Date, index: number): string {
  if (index === 0) return 'Today';
  if (index === 1) return 'Tomorrow';
  return new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric' }).format(date);
}

export default function PublishScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);

  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState<Direction>('HOME_TO_UNIVERSITY');
  const [area, setArea] = useState('');
  const [point, setPoint] = useState<AreaPoint | null>(null);
  const [dayIndex, setDayIndex] = useState(1);
  const [slotIndex, setSlotIndex] = useState(4); // 08:00
  const [vehicleId, setVehicleId] = useState<string | null>(null);
  const [fuel, setFuel] = useState<FuelChoice>('FREE');
  const [contributionType, setContributionType] = useState<ContributionType>('NEGOTIABLE');
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  const vehiclesQuery = useQuery({ queryKey: ['vehicles'], queryFn: myVehicles });
  const vehicles = vehiclesQuery.data ?? [];
  const selectedVehicle = vehicles.find((vehicle) => vehicle.id === vehicleId) ?? vehicles[0] ?? null;

  const days = useMemo(() => nextDays(7), []);
  const departureAt = useMemo(() => {
    const day = days[dayIndex] ?? days[0]!;
    const slot = TIME_SLOTS[slotIndex] ?? TIME_SLOTS[0]!;
    const date = new Date(day.getFullYear(), day.getMonth(), day.getDate(), slot.hour, slot.minute, 0, 0);
    return date;
  }, [days, dayIndex, slotIndex]);

  const isReturn = direction === 'UNIVERSITY_TO_HOME';

  const publishMutation = useMutation({
    mutationFn: () => {
      if (!selectedVehicle) throw new ApiError('VALIDATION_ERROR', 'Select a vehicle first.');
      const parsedAmount = Number(amount);
      if (
        fuel === 'SHARE_FUEL' &&
        contributionType !== 'NEGOTIABLE' &&
        (!amount.trim() || !Number.isFinite(parsedAmount) || parsedAmount <= 0)
      ) {
        throw new ApiError(
          'VALIDATION_ERROR',
          'Enter the amount per passenger (Rs.) for a fixed or expected fuel share.',
        );
      }
      const shared = {
        direction,
        departure_at: departureAt.toISOString(),
        vehicle_id: selectedVehicle.id,
        fuel_preference: fuel,
        contribution_type: fuel === 'FREE' ? ('NONE' as ContributionType) : contributionType,
        contribution_amount: fuel === 'SHARE_FUEL' && contributionType !== 'NEGOTIABLE' && amount ? Number(amount) : null,
        note: note.trim() || null,
      };
      return publishRide(
        isReturn
          ? {
              ...shared,
              destination_area: area.trim(),
              destination_point: point ?? SSUET,
            }
          : { ...shared, pickup_area: area.trim(), pickup_point: point ?? SSUET },
      );
    },
    onSuccess: async (ride) => {
      await queryClient.invalidateQueries({ queryKey: ['rides'] });
      await queryClient.invalidateQueries({ queryKey: ['my-rides'] });
      appAlert('Journey published', 'It is now visible in Explore. We will notify you when someone asks to join.');
      router.replace(`/ride/${ride.id}`);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : 'Could not publish your journey.');
    },
  });

  if (user?.verification_status !== 'VERIFIED') {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <ScrollView contentContainerStyle={styles.content}>
          <Text style={styles.title}>Publish a ride</Text>
          <Banner
            tone="warning"
            title="Verification required"
            message="Only verified SSUET members can publish journeys. Submit your student or employee ID and an administrator will review it."
          />
          <Button label="Verify my account" onPress={() => router.push('/verification')} />
        </ScrollView>
      </SafeAreaView>
    );
  }

  const canContinue =
    (step === 0 && Boolean(direction)) ||
    (step === 1 && area.trim().length > 2) ||
    step === 2 ||
    (step === 3 && Boolean(selectedVehicle)) ||
    step === 4;

  const goNext = () => {
    setError(null);
    if (step === 2 && departureAt.getTime() < Date.now() + 5 * 60 * 1000) {
      setError('Choose a departure time at least 5 minutes in the future.');
      return;
    }
    if (step < STEPS.length - 1) {
      setStep(step + 1);
      return;
    }
    publishMutation.mutate();
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Publish a ride</Text>
        <Text style={styles.stepLabel}>
          Step {step + 1} of {STEPS.length} · {STEPS[step]}
        </Text>
        <View style={styles.progress}>
          {STEPS.map((name, index) => (
            <View
              key={name}
              style={[styles.progressSegment, index <= step && styles.progressSegmentActive]}
            />
          ))}
        </View>
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {error ? <Banner tone="danger" message={error} /> : null}

        {step === 0 ? (
          <Card style={styles.card}>
            <Text style={styles.cardTitle}>Where are you going?</Text>
            <ChipRow
              options={[
                { value: 'HOME_TO_UNIVERSITY' as Direction, label: 'Home → SSUET' },
                { value: 'UNIVERSITY_TO_HOME' as Direction, label: 'SSUET → Home' },
              ]}
              value={direction}
              onChange={setDirection}
            />
            <Text style={styles.helper}>
              The campus end is fixed to SSUET. One seat is offered per journey, so your passenger is
              confirmed personally by you.
            </Text>
          </Card>
        ) : null}

        {step === 1 ? (
          <Card style={styles.card}>
            <LocationPicker
              label={isReturn ? 'Destination area' : 'Pickup area'}
              value={area}
              point={point}
              onChange={(nextArea, nextPoint) => {
                setArea(nextArea);
                setPoint(nextPoint);
              }}
            />
            <Text style={styles.helper}>
              {isReturn
                ? `You start at ${SSUET.name}. Pick the area you are dropping your passenger in.`
                : 'Other members only see this area name until you accept their request.'}
            </Text>
          </Card>
        ) : null}

        {step === 2 ? (
          <Card style={styles.card}>
            <Text style={styles.cardTitle}>When are you leaving?</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
              {days.map((day, index) => (
                <Pressable
                  key={day.toISOString()}
                  onPress={() => setDayIndex(index)}
                  style={[styles.chip, dayIndex === index && styles.chipActive]}
                >
                  <Text style={[styles.chipLabel, dayIndex === index && styles.chipLabelActive]}>
                    {dayLabel(day, index)}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
            <Text style={styles.fieldLabel}>Departure time</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
              {TIME_SLOTS.map((slot, index) => (
                <Pressable
                  key={`${slot.hour}-${slot.minute}`}
                  onPress={() => setSlotIndex(index)}
                  style={[styles.chip, slotIndex === index && styles.chipActive]}
                >
                  <Text style={[styles.chipLabel, slotIndex === index && styles.chipLabelActive]}>
                    {formatTime(new Date(2026, 0, 1, slot.hour, slot.minute).toISOString())}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
          </Card>
        ) : null}

        {step === 3 ? (
          <Card style={styles.card}>
            <Text style={styles.cardTitle}>Your vehicle</Text>
            {vehiclesQuery.isLoading ? <Text style={styles.helper}>Loading vehicles…</Text> : null}
            {!vehiclesQuery.isLoading && vehicles.length === 0 ? (
              <>
                <Banner
                  tone="info"
                  message="Add your car or bike first — an administrator verifies every vehicle before it is used."
                />
                <Button label="Add a vehicle" onPress={() => router.push('/vehicles')} icon="add-circle-outline" />
              </>
            ) : null}
            {vehicles.map((vehicle) => {
              const selected = selectedVehicle?.id === vehicle.id;
              return (
                <Pressable
                  key={vehicle.id}
                  onPress={() => setVehicleId(vehicle.id)}
                  style={[styles.vehicleCard, selected && styles.vehicleCardSelected]}
                >
                  <Ionicons
                    name={vehicle.vehicle_type === 'BIKE' ? 'bicycle' : 'car-sport'}
                    size={20}
                    color={selected ? colors.greenDark : colors.navy}
                  />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.vehicleName}>{vehicle.make_and_model}</Text>
                    <Text style={styles.helper}>
                      {vehicle.color} · {vehicle.registration_number}
                    </Text>
                  </View>
                  <Badge
                    label={vehicle.status === 'VERIFIED' ? 'Verified' : vehicle.status === 'PENDING' ? 'Pending' : 'Rejected'}
                    tone={vehicle.status === 'VERIFIED' ? 'success' : vehicle.status === 'PENDING' ? 'warning' : 'danger'}
                  />
                </Pressable>
              );
            })}
            {vehicles.length > 0 ? (
              <Button label="Manage vehicles" variant="ghost" onPress={() => router.push('/vehicles')} />
            ) : null}
          </Card>
        ) : null}

        {step === 4 ? (
          <Card style={styles.card}>
            <Text style={styles.cardTitle}>Free or fuel sharing?</Text>
            <ChipRow
              options={[
                { value: 'FREE' as FuelChoice, label: 'Free ride' },
                { value: 'SHARE_FUEL' as FuelChoice, label: 'Share fuel' },
              ]}
              value={fuel}
              onChange={setFuel}
            />
            {fuel === 'SHARE_FUEL' ? (
              <>
                <ChipRow
                  options={[
                    { value: 'FIXED' as ContributionType, label: 'Fixed' },
                    { value: 'EXPECTED' as ContributionType, label: 'Expected' },
                    { value: 'NEGOTIABLE' as ContributionType, label: 'Negotiable' },
                  ]}
                  value={contributionType}
                  onChange={setContributionType}
                />
                {contributionType !== 'NEGOTIABLE' ? (
                  <TextField
                    label="Amount per passenger (Rs.)"
                    placeholder="150"
                    keyboardType="number-pad"
                    value={amount}
                    onChangeText={setAmount}
                    hint={amount ? `Passenger sees: ${rupees(Number(amount) || 0)}` : undefined}
                  />
                ) : null}
                <Banner
                  tone="info"
                  message="Fuel money is paid in cash between you and your passenger. After the trip you confirm the payment, and an invoice is created as evidence. SSUET RideShare never handles payments."
                />
              </>
            ) : (
              <Text style={styles.helper}>
                You are offering this seat for free — a small favour that makes campus travel easier
                for everyone.
              </Text>
            )}

            <TextField
              label="Note (optional)"
              placeholder="Leaving sharp at 8:00, AC car, no smoking please."
              value={note}
              onChangeText={setNote}
              multiline
            />

            <View style={styles.review}>
              <Text style={styles.reviewTitle}>Review</Text>
              <Text style={styles.reviewLine}>
                {isReturn ? 'SSUET → ' : `${area.trim() || 'Pickup'} → `}
                {isReturn ? area.trim() || 'Destination' : 'SSUET'}
              </Text>
              <Text style={styles.reviewLine}>
                {dayLabel(days[dayIndex]!, dayIndex)} · {formatTime(departureAt.toISOString())}
              </Text>
              <Text style={styles.reviewLine}>
                {selectedVehicle ? selectedVehicle.make_and_model : 'No vehicle'} · 1 seat
              </Text>
              <Text style={styles.reviewLine}>
                {fuel === 'FREE'
                  ? 'Free ride'
                  : contributionType === 'NEGOTIABLE'
                    ? 'Fuel share · negotiable'
                    : `Fuel share · ${rupees(Number(amount) || 0)}`}
              </Text>
            </View>
          </Card>
        ) : null}
      </ScrollView>

      <View style={styles.footer}>
        {step > 0 ? (
          <Button label="Back" variant="secondary" onPress={() => setStep(step - 1)} fullWidth={false} />
        ) : null}
        <View style={{ flex: 1 }}>
          <Button
            label={step === STEPS.length - 1 ? 'Publish journey' : 'Continue'}
            onPress={goNext}
            disabled={!canContinue}
            loading={publishMutation.isPending}
            icon={step === STEPS.length - 1 ? 'checkmark-circle-outline' : 'arrow-forward-outline'}
          />
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, gap: spacing.xs },
  title: { color: colors.text, ...typography.display },
  stepLabel: { color: colors.textMuted, ...typography.caption },
  progress: { flexDirection: 'row', gap: 4, marginTop: spacing.sm },
  progressSegment: { flex: 1, height: 4, borderRadius: 2, backgroundColor: colors.border },
  progressSegmentActive: { backgroundColor: colors.green },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  card: { gap: spacing.md },
  cardTitle: { color: colors.text, ...typography.h2 },
  helper: { color: colors.textMuted, ...typography.caption, lineHeight: 17 },
  fieldLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  chipRow: { gap: spacing.sm, paddingVertical: 2 },
  chip: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipActive: { backgroundColor: colors.navy, borderColor: colors.navy },
  chipLabel: { color: colors.textMuted, ...typography.caption },
  chipLabelActive: { color: colors.textInverse, fontWeight: '700' },
  vehicleCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  vehicleCardSelected: { borderColor: colors.green, backgroundColor: colors.greenTint },
  vehicleName: { color: colors.text, ...typography.bodyStrong },
  review: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: 4,
  },
  reviewTitle: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  reviewLine: { color: colors.text, ...typography.body },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
});
