import { useMemo } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Avatar, Badge, Banner, Button, Card, EmptyState, SectionTitle } from '@/components/ui';
import { fetchMeta } from '@/api/client';
import { listRides, myRides, myVehicles } from '@/api/rides';
import { getUnreadCount } from '@/api/notifications';
import { listTrips } from '@/api/trips';
import { TripCard } from '@/components/TripCard';
import { RideCard } from '@/components/RideCard';
import { RideCardSkeleton } from '@/components/Skeleton';
import { buildOnboardingSteps, nextOnboardingStep, onboardingProgress } from '@/lib/onboarding';
import { useAuthStore } from '@/store/auth';
import { colors, radius, shadow, spacing, typography } from '@/theme';

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

export default function HomeScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const meta = useQuery({ queryKey: ['meta'], queryFn: fetchMeta });
  const nearby = useQuery({
    queryKey: ['rides', 'home-preview'],
    queryFn: () => listRides({ direction: 'HOME_TO_UNIVERSITY', exclude_own: true, limit: 3 }),
  });
  const unread = useQuery({
    queryKey: ['notifications', 'unread'],
    queryFn: getUnreadCount,
    refetchInterval: 60_000,
  });
  const unreadCount = unread.data ?? 0;
  const upcomingTrip = useQuery({
    queryKey: ['trips', 'upcoming'],
    queryFn: () => listTrips({ upcoming: true }),
  });
  const nextTrip = upcomingTrip.data?.items[0] ?? null;

  const firstName = useMemo(() => user?.full_name?.split(' ')[0] ?? 'there', [user?.full_name]);
  const isVerified = user?.verification_status === 'VERIFIED';

  // Setup checklist: same query keys as the onboarding screen, so the cache is shared.
  const setupVehicles = useQuery({ queryKey: ['vehicles'], queryFn: myVehicles });
  const setupRides = useQuery({ queryKey: ['rides', 'mine', 'onboarding'], queryFn: () => myRides() });
  const setupSteps = user
    ? buildOnboardingSteps(user, setupVehicles.data ?? [], setupRides.data?.length ?? 0)
    : [];
  const setupNext = nextOnboardingStep(setupSteps);
  const setupProgress = onboardingProgress(setupSteps);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={meta.isFetching || nearby.isFetching}
            onRefresh={() => {
              void queryClient.invalidateQueries({ queryKey: ['meta'] });
              void queryClient.invalidateQueries({ queryKey: ['rides'] });
              void queryClient.invalidateQueries({ queryKey: ['notifications'] });
            }}
            tintColor={colors.green}
          />
        }
      >
        {/* header */}
        <View style={styles.headerRow}>
          <View style={styles.headerLeft}>
            <Avatar name={user?.full_name ?? 'SSUET Member'} photoUrl={user?.profile_photo_url} />
            <View>
              <Text style={styles.greeting}>
                {greeting()}, {firstName}
              </Text>
              <Text style={styles.headerSub}>
                {user?.role === 'TEACHER' ? 'Faculty' : 'Student'} · {user?.department ?? 'SSUET'}
              </Text>
            </View>
          </View>
          <Pressable
            onPress={() => router.push('/notifications')}
            style={styles.bell}
            accessibilityLabel={
              unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'
            }
          >
            <Ionicons name="notifications-outline" size={20} color={colors.navy} />
            {unreadCount > 0 ? (
              <View style={styles.bellBadge}>
                <Text style={styles.bellBadgeText}>{unreadCount > 9 ? '9+' : unreadCount}</Text>
              </View>
            ) : null}
          </Pressable>
        </View>

        {!isVerified ? (
          <Pressable onPress={() => router.push('/verification')}>
            <Banner
              tone="warning"
              title="Verify your university account"
              message={
                user?.verification_status === 'PENDING'
                  ? 'Your ID is under review. We will notify you once an administrator approves it.'
                  : 'Submit your student / employee ID to publish rides and send requests. Tap here.'
              }
            />
          </Pressable>
        ) : null}

        {setupNext ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Account setup, ${setupProgress.done} of ${setupProgress.total} done. Next: ${setupNext.title}`}
            onPress={() => router.push('/onboarding')}
          >
            <Card style={styles.setupCard}>
              <View style={styles.setupRow}>
                <View style={styles.setupIcon}>
                  <Ionicons name="list" size={20} color={colors.green} />
                </View>
                <View style={styles.setupBody}>
                  <Text style={styles.setupTitle}>
                    Finish account setup · {setupProgress.done}/{setupProgress.total}
                  </Text>
                  <Text style={styles.setupNext} numberOfLines={1}>
                    Next: {setupNext.title}
                  </Text>
                </View>
                <Ionicons name="arrow-forward-circle" size={28} color={colors.green} />
              </View>
            </Card>
          </Pressable>
        ) : null}

        {/* university destination card */}
        <Card style={styles.universityCard}>
          <View style={styles.universityTop}>
            <View style={styles.universityIcon}>
              <Ionicons name="school" size={22} color={colors.green} />
            </View>
            <Badge label="SSUET" tone="success" icon="shield-checkmark" />
          </View>
          <Text style={styles.universityName}>
            {meta.data?.university.name ?? 'Sir Syed University of Engineering & Technology'}
          </Text>
          <Text style={styles.universityArea}>
            {meta.data?.university.default_area_label ?? 'University Road, Karachi'}
          </Text>
        </Card>

        {/* search */}
        <Pressable style={styles.search} onPress={() => router.push('/(tabs)/explore')}>
          <Ionicons name="search" size={18} color={colors.textMuted} />
          <Text style={styles.searchText}>Where are you travelling from?</Text>
        </Pressable>

        <View style={styles.quickRow}>
          <QuickAction
            icon="home-outline"
            label="To university"
            onPress={() => router.push({ pathname: '/(tabs)/explore', params: { direction: 'HOME_TO_UNIVERSITY' } })}
          />
          <QuickAction
            icon="moon-outline"
            label="Back home"
            onPress={() => router.push({ pathname: '/(tabs)/explore', params: { direction: 'UNIVERSITY_TO_HOME' } })}
          />
          <QuickAction
            icon="chatbubbles-outline"
            label="Messages"
            onPress={() => router.push('/chats')}
          />
          <QuickAction
            icon="add-circle-outline"
            label="Publish ride"
            highlight
            onPress={() => router.push('/(tabs)/publish')}
          />
        </View>

        {/* upcoming trip */}
        <View style={styles.section}>
          <SectionTitle
            action={
              <Pressable onPress={() => router.push('/(tabs)/my-rides')}>
                <Text style={styles.seeAll}>My rides</Text>
              </Pressable>
            }
          >
            Upcoming trip
          </SectionTitle>
          {nextTrip ? (
            <TripCard trip={nextTrip} onPress={() => router.push(`/trip/${nextTrip.id}`)} />
          ) : (
            <Card>
              <EmptyState
                icon="calendar-outline"
                title="No confirmed trip yet"
                message="Once a driver accepts your request — or someone joins your ride — your next trip appears here with meeting details and chat."
              />
            </Card>
          )}
        </View>

        {/* available rides */}
        <View style={styles.section}>
          <SectionTitle
            action={
              <Pressable onPress={() => router.push('/(tabs)/explore')}>
                <Text style={styles.seeAll}>See all</Text>
              </Pressable>
            }
          >
            Available near you
          </SectionTitle>
          {nearby.isLoading ? (
            <View style={{ gap: spacing.md }}>
              <RideCardSkeleton />
            </View>
          ) : nearby.isError ? (
            <Card>
              <EmptyState
                icon="cloud-offline-outline"
                title="Couldn't load journeys"
                message="Check your connection and pull down to refresh."
              />
            </Card>
          ) : (nearby.data?.items.length ?? 0) === 0 ? (
            <Card>
              <EmptyState
                icon="compass-outline"
                title="No journeys published yet"
                message="Be the first today — publish your trip to campus and someone nearby may join you."
              />
            </Card>
          ) : (
            (nearby.data?.items ?? []).map((ride) => (
              <RideCard key={ride.id} ride={ride} onPress={() => router.push(`/ride/${ride.id}`)} />
            ))
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function QuickAction({
  icon,
  label,
  onPress,
  highlight = false,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  highlight?: boolean;
}) {
  return (
    <Pressable onPress={onPress} style={[styles.quick, highlight && styles.quickHighlight]}>
      <Ionicons name={icon} size={20} color={highlight ? colors.textInverse : colors.navy} />
      <Text
        numberOfLines={1}
        style={[styles.quickLabel, highlight && styles.quickLabelHighlight]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.xxl },
  headerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  bellBadge: {
    position: 'absolute',
    top: -2,
    right: -4,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    paddingHorizontal: 3,
    backgroundColor: colors.danger,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bellBadgeText: { color: colors.textInverse, fontSize: 9, fontWeight: '700' },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, flex: 1 },
  greeting: { color: colors.text, ...typography.h2 },
  headerSub: { color: colors.textMuted, ...typography.caption },
  bell: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadow.card,
  },
  universityCard: { backgroundColor: colors.navy, gap: spacing.xs },
  universityTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  universityIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    backgroundColor: 'rgba(18,183,106,0.15)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  universityName: { color: colors.textInverse, ...typography.h2, marginTop: spacing.sm },
  universityArea: { color: '#A9BAD4', ...typography.caption },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    minHeight: 50,
  },
  searchText: { color: colors.textMuted, ...typography.body },
  quickRow: { flexDirection: 'row', gap: spacing.sm },
  quick: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    alignItems: 'center',
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
  },
  quickHighlight: { backgroundColor: colors.green, borderColor: colors.green },
  quickLabel: { color: colors.navy, ...typography.caption, fontWeight: '600', textAlign: 'center' },
  quickLabelHighlight: { color: colors.textInverse },
  section: { gap: spacing.xs },
  seeAll: { color: colors.navy, ...typography.caption, fontWeight: '700' },
  setupCard: { padding: spacing.md },
  setupRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  setupIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.greenTint,
  },
  setupBody: { flex: 1, gap: 2 },
  setupTitle: { ...typography.bodyStrong, color: colors.navy },
  setupNext: { ...typography.caption, color: colors.textMuted },
});
