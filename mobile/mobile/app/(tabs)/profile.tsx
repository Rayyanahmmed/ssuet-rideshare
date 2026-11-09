import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import { deleteProfilePhoto, uploadProfilePhoto } from '@/api/media';
import { Avatar, Badge, Button, Card } from '@/components/ui';
import { useAuthStore } from '@/store/auth';
import { colors, radius, spacing, typography } from '@/theme';
import { appAlert } from '@/lib/appAlert';

function verificationBadge(status?: string) {
  switch (status) {
    case 'VERIFIED':
      return { tone: 'success' as const, label: 'University verified', icon: 'shield-checkmark' as const };
    case 'PENDING':
      return { tone: 'warning' as const, label: 'Verification in review', icon: 'time' as const };
    case 'REJECTED':
      return { tone: 'danger' as const, label: 'Verification rejected', icon: 'close-circle' as const };
    default:
      return { tone: 'neutral' as const, label: 'Not verified', icon: 'alert-circle-outline' as const };
  }
}

export default function ProfileScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const signOut = useAuthStore((state) => state.signOut);
  const updateUser = useAuthStore((state) => state.updateUser);
  const [signingOut, setSigningOut] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);

  if (!user) return null;

  /**
   * Pick and upload a profile photo (§5, Phase 13).
   *
   * The picker narrows to a square crop and the client downsizes with `quality`, so a
   * phone camera photo lands well under the 2 MB server cap. Failures are shown as the
   * server's own message — "This file is larger than 2 MB" is more useful than a
   * generic "upload failed".
   */
  const changePhoto = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      appAlert('Photo access needed', 'Allow photo access in Settings to add a profile photo.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.6,
      allowsEditing: true,
      aspect: [1, 1],
    });
    const picked = result.canceled ? undefined : result.assets?.[0];
    if (!picked) return;

    setPhotoBusy(true);
    try {
      const updated = await uploadProfilePhoto({
        uri: picked.uri,
        name: picked.fileName ?? `avatar.${(picked.mimeType ?? 'image/jpeg').split('/')[1] ?? 'jpg'}`,
        type: picked.mimeType ?? 'image/jpeg',
      });
      updateUser(updated);
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : 'The photo could not be uploaded. Try again.';
      appAlert('Photo not saved', message);
    } finally {
      setPhotoBusy(false);
    }
  };

  const removePhoto = () => {
    appAlert('Remove photo', 'Your initials will be shown instead.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: async () => {
          setPhotoBusy(true);
          try {
            const updated = await deleteProfilePhoto();
            updateUser(updated);
          } catch {
            appAlert('Not removed', 'The photo could not be removed. Try again.');
          } finally {
            setPhotoBusy(false);
          }
        },
      },
    ]);
  };

  const badge = verificationBadge(user.verification_status);
  const homeArea = user.student_profile?.home_area ?? user.teacher_profile?.home_area ?? null;
  const designation =
    user.role === 'TEACHER'
      ? (user.teacher_profile?.designation ?? 'Faculty Member')
      : `${user.student_profile?.degree_programme ?? user.department}${
          user.student_profile?.semester ? ` · Semester ${user.student_profile.semester}` : ''
        }`;

  const confirmSignOut = () => {
    appAlert('Sign out', 'You will need your password to sign in again on this device.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign out',
        style: 'destructive',
        onPress: async () => {
          setSigningOut(true);
          queryClient.clear();
          await signOut();
        },
      },
    ]);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.profileRow}>
          <Pressable
            onPress={changePhoto}
            disabled={photoBusy}
            accessibilityRole="button"
            accessibilityLabel="Change profile photo"
            style={styles.avatarWrap}
          >
            <Avatar name={user.full_name} size={64} photoUrl={user.profile_photo_url} />
            <View style={styles.avatarBadge}>
              {photoBusy ? (
                <ActivityIndicator size="small" color={colors.textInverse} />
              ) : (
                <Ionicons name="camera" size={13} color={colors.textInverse} />
              )}
            </View>
          </Pressable>
          <View style={styles.profileText}>
            <Text style={styles.name}>{user.full_name}</Text>
            <Text style={styles.meta}>{designation}</Text>
            <Text style={styles.meta}>{user.department}</Text>
          </View>
        </View>

        <View style={styles.photoActions}>
          <Pressable onPress={changePhoto} disabled={photoBusy} accessibilityRole="button">
            <Text style={styles.photoAction}>{user.profile_photo_url ? 'Change photo' : 'Add a photo'}</Text>
          </Pressable>
          {user.profile_photo_url ? (
            <Pressable onPress={removePhoto} disabled={photoBusy} accessibilityRole="button">
              <Text style={[styles.photoAction, styles.photoActionDanger]}>Remove</Text>
            </Pressable>
          ) : null}
        </View>

        <View style={styles.badgeRow}>
          <Badge label={badge.label} tone={badge.tone} icon={badge.icon} />
          <Badge label={user.role === 'TEACHER' ? 'Teacher' : 'Student'} tone="info" />
        </View>

        <Card style={styles.statsCard}>
          <Stat value={user.rating_average ? user.rating_average.toFixed(1) : '—'} label="Rating" />
          <View style={styles.divider} />
          <Stat value={String(user.rating_count)} label="Reviews" />
          <View style={styles.divider} />
          <Stat value={String(user.completed_trips_count)} label="Trips" />
        </Card>

        <Card style={styles.card}>
          <Row icon="mail-outline" label="Email" value={user.email} />
          <Row icon="call-outline" label="Phone" value={user.phone} hint="Private — shared only after a match" />
          <Row icon="card-outline" label="University ID" value={user.university_id} />
          {homeArea ? <Row icon="location-outline" label="Home area" value={homeArea} /> : null}
        </Card>

        <Card style={styles.card}>
          <Text style={styles.sectionLabel}>Verification</Text>
          <Text style={styles.sectionBody}>
            {user.verification_status === 'VERIFIED'
              ? 'Your university membership is confirmed. You can publish rides and send requests.'
              : user.verification_status === 'PENDING'
                ? 'An administrator is reviewing your submitted ID.'
                : 'Submit your student or employee ID to unlock ride sharing.'}
          </Text>
          {user.verification_status !== 'VERIFIED' ? (
            <Button
              label={user.verification_status === 'PENDING' ? 'View submitted ID' : 'Submit my university ID'}
              variant="secondary"
              onPress={() => router.push('/verification')}
              icon="shield-checkmark-outline"
            />
          ) : null}
        </Card>

        <Card style={styles.card}>
          <Text style={styles.sectionLabel}>Vehicles</Text>
          <Text style={styles.sectionBody}>
            Register your car or bike to publish journeys. Every vehicle is verified by an
            administrator before it is used.
          </Text>
          <Button
            label="Manage my vehicles"
            variant="secondary"
            onPress={() => router.push('/vehicles')}
            icon="car-outline"
          />
        </Card>

        <Card style={styles.card}>
          <Text style={styles.sectionLabel}>Trust &amp; safety</Text>
          <Text style={styles.sectionBody}>
            Your rating is built only from trips you actually took, one review per side. Reports go
            to the SSUET ride-share office and you can see every outcome.
          </Text>
          <LinkRow
            icon="star-outline"
            label="My ratings"
            hint={`${user.rating_count} review${user.rating_count === 1 ? '' : 's'} from travel partners`}
            onPress={() => router.push('/reviews')}
          />
          <LinkRow
            icon="flag-outline"
            label="My reports"
            hint="Complaints you have filed and their status"
            onPress={() => router.push('/my-reports')}
          />
          <LinkRow
            icon="ban-outline"
            label="Blocked members"
            hint="Members you never want to be matched with"
            onPress={() => router.push('/blocked')}
          />
        </Card>

        <Button
          label="Sign out"
          variant="danger"
          onPress={confirmSignOut}
          loading={signingOut}
          icon="log-out-outline"
        />

        <Text style={styles.version}>SSUET RideShare · v1.0.0</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function LinkRow({
  icon,
  label,
  hint,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  hint: string;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={styles.linkRow} accessibilityRole="button">
      <View style={styles.rowIcon}>
        <Ionicons name={icon} size={16} color={colors.navy} />
      </View>
      <View style={styles.rowText}>
        <Text style={styles.rowLabel}>{label}</Text>
        <Text style={styles.rowHint}>{hint}</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
    </Pressable>
  );
}

function Row({
  icon,
  label,
  value,
  hint,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.rowIcon}>
        <Ionicons name={icon} size={16} color={colors.textMuted} />
      </View>
      <View style={styles.rowText}>
        <Text style={styles.rowLabel}>{label}</Text>
        <Text style={styles.rowValue}>{value}</Text>
        {hint ? <Text style={styles.rowHint}>{hint}</Text> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  avatarWrap: { position: 'relative' },
  avatarBadge: {
    position: 'absolute',
    right: -2,
    bottom: -2,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: colors.greenDark,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: colors.surface,
  },
  photoActions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm },
  photoAction: { color: colors.greenDark, fontWeight: '600', fontSize: 13 },
  photoActionDanger: { color: colors.danger },
  profileRow: { flexDirection: 'row', gap: spacing.md, alignItems: 'center', marginTop: spacing.sm },
  profileText: { flex: 1, gap: 2 },
  name: { color: colors.text, ...typography.h1 },
  meta: { color: colors.textMuted, ...typography.caption },
  badgeRow: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  statsCard: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around' },
  stat: { alignItems: 'center', gap: 2, flex: 1 },
  statValue: { color: colors.navy, ...typography.h1 },
  statLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  divider: { width: 1, height: 28, backgroundColor: colors.border },
  card: { gap: spacing.md },
  sectionLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  sectionBody: { color: colors.textMuted, ...typography.caption, lineHeight: 18 },
  row: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  rowIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceAlt,
    alignItems: 'center',
    justifyContent: 'center',
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  rowText: { flex: 1 },
  rowLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  rowValue: { color: colors.text, ...typography.bodyStrong },
  rowHint: { color: colors.textMuted, ...typography.caption },
  version: { color: colors.textMuted, ...typography.caption, textAlign: 'center', marginTop: spacing.md },
});
