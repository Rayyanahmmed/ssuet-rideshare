import { useCallback, useMemo, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { ApiError } from '@/api/client';
import { listRides, type Direction, type Ride, type RideFilters } from '@/api/rides';
import { RideCard } from '@/components/RideCard';
import { RideCardSkeleton } from '@/components/Skeleton';
import { Badge, Button, ChipRow, EmptyState, TextField } from '@/components/ui';
import { useAuthStore } from '@/store/auth';
import { colors, radius, spacing, typography } from '@/theme';

type FuelFilter = 'ALL' | 'FREE' | 'SHARE_FUEL';
type VehicleFilter = 'ALL' | 'CAR' | 'BIKE';

export default function ExploreScreen() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);

  const [direction, setDirection] = useState<Direction>('HOME_TO_UNIVERSITY');
  const [fuel, setFuel] = useState<FuelFilter>('ALL');
  const [vehicle, setVehicle] = useState<VehicleFilter>('ALL');
  const [area, setArea] = useState('');
  const [search, setSearch] = useState('');

  const filters = useMemo<RideFilters>(() => {
    const base: RideFilters = { direction, exclude_own: true, limit: 10 };
    if (fuel !== 'ALL') base.fuel_preference = fuel;
    if (vehicle !== 'ALL') base.vehicle_type = vehicle;
    if (search.trim()) base.area = search.trim();
    return base;
  }, [direction, fuel, vehicle, search]);

  const query = useInfiniteQuery({
    queryKey: ['rides', filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => listRides({ ...filters, cursor: pageParam }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const rides: Ride[] = query.data?.pages.flatMap((page) => page.items) ?? [];

  const onRefresh = useCallback(() => {
    void query.refetch();
  }, [query]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <FlatList
        data={rides}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={query.isRefetching && !query.isFetchingNextPage} onRefresh={onRefresh} tintColor={colors.green} />
        }
        ListHeaderComponent={
          <View style={styles.header}>
            <Text style={styles.title}>Explore rides</Text>
            <Text style={styles.subtitle}>
              Journeys published by verified SSUET members. Ask to join — the driver decides.
            </Text>

            <ChipRow
              options={[
                { value: 'HOME_TO_UNIVERSITY' as Direction, label: 'To university' },
                { value: 'UNIVERSITY_TO_HOME' as Direction, label: 'Back home' },
              ]}
              value={direction}
              onChange={setDirection}
            />

            <TextField
              label="Search area"
              placeholder="Gulshan-e-Iqbal, Malir, SSUET…"
              icon="search-outline"
              value={area}
              onChangeText={setArea}
              onSubmitEditing={() => setSearch(area)}
              returnKeyType="search"
              right={
                <Pressable onPress={() => setSearch(area)} hitSlop={8}>
                  <Ionicons name="arrow-forward-circle" size={22} color={colors.navy} />
                </Pressable>
              }
            />

            <View style={styles.filterRow}>
              <SmallChip label="All fares" active={fuel === 'ALL'} onPress={() => setFuel('ALL')} />
              <SmallChip label="Free" active={fuel === 'FREE'} onPress={() => setFuel('FREE')} />
              <SmallChip label="Fuel share" active={fuel === 'SHARE_FUEL'} onPress={() => setFuel('SHARE_FUEL')} />
            </View>
            <View style={styles.filterRow}>
              <SmallChip label="Any vehicle" active={vehicle === 'ALL'} onPress={() => setVehicle('ALL')} />
              <SmallChip label="Car" active={vehicle === 'CAR'} onPress={() => setVehicle('CAR')} />
              <SmallChip label="Bike" active={vehicle === 'BIKE'} onPress={() => setVehicle('BIKE')} />
            </View>

            {!user?.verification_status || user.verification_status !== 'VERIFIED' ? (
              <View style={styles.noticeWrap}>
                <Badge label="Verify your account to request a seat" tone="warning" icon="alert-circle" />
              </View>
            ) : null}

            {query.isSuccess ? (
              <Text style={styles.count}>
                {rides.length} {rides.length === 1 ? 'journey' : 'journeys'} available
              </Text>
            ) : null}
          </View>
        }
        renderItem={({ item }) => (
          <RideCard ride={item} onPress={() => router.push(`/ride/${item.id}`)} />
        )}
        ItemSeparatorComponent={() => <View style={{ height: spacing.md }} />}
        ListEmptyComponent={
          query.isLoading ? (
            <View style={{ gap: spacing.md }}>
              <RideCardSkeleton />
              <RideCardSkeleton />
            </View>
          ) : query.isError ? (
            <View style={styles.stateCard}>
              <EmptyState
                icon="cloud-offline-outline"
                title="Couldn't load journeys"
                message={
                  query.error instanceof ApiError
                    ? query.error.message
                    : 'Check your connection and try again.'
                }
                action={<Button label="Retry" onPress={() => void query.refetch()} />}
              />
            </View>
          ) : (
            <View style={styles.stateCard}>
              <EmptyState
                icon="compass-outline"
                title="No journeys match yet"
                message="Try a wider time window, another area, or publish the ride yourself — someone may be heading your way."
                action={<Button label="Publish a ride" onPress={() => router.push('/(tabs)/publish')} />}
              />
            </View>
          )
        }
        ListFooterComponent={
          <View style={styles.footer}>
            {query.hasNextPage ? (
              <Button
                label={query.isFetchingNextPage ? 'Loading…' : 'Load more'}
                variant="secondary"
                loading={query.isFetchingNextPage}
                onPress={() => void query.fetchNextPage()}
              />
            ) : rides.length > 0 ? (
              <Text style={styles.footerText}>You have reached the end of the list.</Text>
            ) : null}
          </View>
        }
      />
    </SafeAreaView>
  );
}

function SmallChip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.smallChip, active && styles.smallChipActive]}>
      <Text style={[styles.smallChipLabel, active && styles.smallChipLabelActive]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.md },
  header: { gap: spacing.md },
  title: { color: colors.text, ...typography.display },
  subtitle: { color: colors.textMuted, ...typography.caption, lineHeight: 18 },
  filterRow: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  smallChip: {
    paddingVertical: 6,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  smallChipActive: { backgroundColor: colors.greenTint, borderColor: colors.green },
  smallChipLabel: { color: colors.textMuted, ...typography.caption },
  smallChipLabelActive: { color: colors.greenDark, fontWeight: '700' },
  noticeWrap: { marginTop: spacing.xs },
  count: { color: colors.textMuted, ...typography.caption },
  stateCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  footer: { paddingTop: spacing.md, gap: spacing.sm },
  footerText: { color: colors.textMuted, ...typography.caption, textAlign: 'center' },
});
