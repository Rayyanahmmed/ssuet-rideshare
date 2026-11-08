import { goBackOr } from '@/lib/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActivityIndicator,
  Alert,
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
import { ApiError, api } from '@/api/client';
import { Avatar, Banner, Button, Card, EmptyState } from '@/components/ui';
import { colors, spacing, typography } from '@/theme';

type BlockedMember = {
  id: string;
  full_name: string;
  profile_photo_url: string | null;
  department: string;
};

/** Members I have blocked — and the way back (§15). */
export default function BlockedScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['blocked'],
    queryFn: async () => (await api.get<BlockedMember[]>('/users/me/blocks')).data,
  });

  const unblock = useMutation({
    mutationFn: async (userId: string) => {
      await api.delete(`/users/${userId}/block`);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['blocked'] }),
        queryClient.invalidateQueries({ queryKey: ['rides'] }),
      ]);
    },
    onError: (err) =>
      Alert.alert('Could not unblock', err instanceof ApiError ? err.message : 'Please try again.'),
  });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" onPress={() => goBackOr(router)} style={styles.back} accessibilityLabel="Back">
          <Ionicons name="arrow-back" size={20} color={colors.navy} />
        </Pressable>
        <Text style={styles.headerTitle}>Blocked members</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} tintColor={colors.green} />
        }
      >
        <Banner
          tone="info"
          title="What blocking does"
          message="You will never be matched with a blocked member again, their rides disappear from Explore, and neither of you can send messages."
        />

        {query.isError ? (
          <Banner
            tone="danger"
            title="Could not load the list"
            message={query.error instanceof ApiError ? query.error.message : 'Please try again.'}
          />
        ) : null}

        {query.isLoading ? (
          <View style={styles.centre}>
            <ActivityIndicator color={colors.green} />
          </View>
        ) : (query.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon="ban-outline"
            title="Nobody is blocked"
            message="You can block a member from a trip screen if a journey does not feel right."
          />
        ) : (
          query.data?.map((member) => (
            <Card key={member.id} style={styles.card}>
              <View style={styles.personRow}>
                <Avatar name={member.full_name} size={44} photoUrl={member.profile_photo_url} />
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={styles.name}>{member.full_name}</Text>
                  <Text style={styles.muted}>{member.department}</Text>
                </View>
                <Button
                  label="Unblock"
                  variant="secondary"
                  fullWidth={false}
                  loading={unblock.isPending && unblock.variables === member.id}
                  onPress={() => unblock.mutate(member.id)}
                />
              </View>
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
  personRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  name: { color: colors.text, ...typography.bodyStrong },
  muted: { color: colors.textMuted, ...typography.caption },
});
