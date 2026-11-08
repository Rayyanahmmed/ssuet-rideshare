import { goBackOr } from '@/lib/navigation';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as ImagePicker from 'expo-image-picker';
import { ApiError } from '@/api/client';
import { MAX_UPLOAD_BYTES, deleteMediaAsset, uploadDocument } from '@/api/media';
import { createVehicle, myVehicles, type VehicleKind } from '@/api/rides';
import { Badge, Banner, Button, Card, ChipRow, TextField } from '@/components/ui';
import { colors, radius, spacing, typography } from '@/theme';

/** Vehicle registration (§5). Every vehicle is verified by an administrator. */
export default function VehiclesScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [vehicleType, setVehicleType] = useState<VehicleKind>('CAR');
  const [model, setModel] = useState('');
  const [color, setColor] = useState('');
  const [registration, setRegistration] = useState('');
  const [error, setError] = useState<string | null>(null);
  // Optional proof for the reviewer (Phase 10): a photo of the car and of the
  // registration book. Uploaded immediately so the admin queue sees them.
  const [photo, setPhoto] = useState<{ id: string; name: string; size: number } | null>(null);
  const [papers, setPapers] = useState<{ id: string; name: string; size: number } | null>(null);
  const [uploading, setUploading] = useState<'photo' | 'papers' | null>(null);

  const attach = async (slot: 'photo' | 'papers') => {
    setError(null);
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        setError('Allow photo access in Settings to attach a picture.');
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 0.7,
        allowsEditing: true,
      });
      const asset = result.canceled ? undefined : result.assets?.[0];
      if (!asset) return;
      if ((asset.fileSize ?? 0) > MAX_UPLOAD_BYTES) {
        setError('That picture is larger than 5 MB. Choose a smaller one.');
        return;
      }

      setUploading(slot);
      const contentType = asset.mimeType ?? 'image/jpeg';
      const uploaded = await uploadDocument('/uploads/vehicle', {
        uri: asset.uri,
        name: asset.fileName ?? `vehicle-${slot}.jpg`,
        type: contentType,
      });
      const record = {
        id: uploaded.id,
        name: uploaded.original_filename ?? `vehicle-${slot}.jpg`,
        size: uploaded.byte_size,
      };
      // Replacing an attachment withdraws the previous upload so nothing is orphaned.
      const previous = slot === 'photo' ? photo : papers;
      if (previous) await deleteMediaAsset(previous.id).catch(() => undefined);
      if (slot === 'photo') setPhoto(record);
      else setPapers(record);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not upload that picture. Try again.');
    } finally {
      setUploading(null);
    }
  };

  const vehiclesQuery = useQuery({ queryKey: ['vehicles'], queryFn: myVehicles });

  const mutation = useMutation({
    mutationFn: () =>
      createVehicle({
        vehicle_type: vehicleType,
        make_and_model: model.trim(),
        color: color.trim(),
        registration_number: registration.trim(),
        passenger_capacity: 1,
        photo_asset_id: photo?.id ?? null,
        registration_asset_id: papers?.id ?? null,
        is_primary: true,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['vehicles'] });
      setAdding(false);
      setModel('');
      setColor('');
      setRegistration('');
      setPhoto(null);
      setPapers(null);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Could not save the vehicle.'),
  });

  const vehicles = vehiclesQuery.data ?? [];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.header}>
          <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => goBackOr(router)} style={styles.back}>
            <Ionicons name="arrow-back" size={20} color={colors.navy} />
          </Pressable>
          <Text style={styles.title}>My vehicles</Text>
          <Pressable onPress={() => setAdding(!adding)} style={styles.back}>
            <Ionicons name={adding ? 'close' : 'add'} size={20} color={colors.navy} />
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {adding ? (
            <Card style={styles.card}>
              <Text style={styles.cardTitle}>Register a vehicle</Text>
              <ChipRow
                options={[
                  { value: 'CAR' as VehicleKind, label: 'Car' },
                  { value: 'BIKE' as VehicleKind, label: 'Bike' },
                ]}
                value={vehicleType}
                onChange={setVehicleType}
              />
              {error ? <Banner tone="danger" message={error} /> : null}
              <TextField
                label="Make & model"
                placeholder={vehicleType === 'CAR' ? 'Toyota Corolla 2019' : 'Honda CD 70'}
                value={model}
                onChangeText={setModel}
              />
              <TextField label="Colour" placeholder="White" value={color} onChangeText={setColor} />
              <TextField
                label="Registration number"
                placeholder="ABC-1234"
                autoCapitalize="characters"
                value={registration}
                onChangeText={setRegistration}
              />
              <View style={styles.attachRow}>
                <Pressable style={styles.attach} onPress={() => attach('photo')} disabled={uploading !== null}>
                  <Ionicons
                    name={photo ? 'checkmark-circle' : 'camera-outline'}
                    size={18}
                    color={photo ? colors.green : colors.navy}
                  />
                  <Text style={styles.attachLabel} numberOfLines={1}>
                    {uploading === 'photo'
                      ? 'Uploading…'
                      : photo
                        ? `${photo.name} · ${Math.round(photo.size / 1024)} KB`
                        : 'Add a photo of the vehicle'}
                  </Text>
                </Pressable>
                <Pressable style={styles.attach} onPress={() => attach('papers')} disabled={uploading !== null}>
                  <Ionicons
                    name={papers ? 'checkmark-circle' : 'document-outline'}
                    size={18}
                    color={papers ? colors.green : colors.navy}
                  />
                  <Text style={styles.attachLabel} numberOfLines={1}>
                    {uploading === 'papers'
                      ? 'Uploading…'
                      : papers
                        ? `${papers.name} · ${Math.round(papers.size / 1024)} KB`
                        : 'Add the registration book'}
                  </Text>
                </Pressable>
              </View>
              <Banner
                tone="info"
                message="Both pictures are optional but speed up verification. An administrator sees them; other members never do. You can publish journeys while verification is pending."
              />
              <Button
                label="Save vehicle"
                onPress={() => mutation.mutate()}
                loading={mutation.isPending}
                disabled={model.trim().length < 2 || color.trim().length < 2 || registration.trim().length < 3}
              />
            </Card>
          ) : null}

          {vehicles.length === 0 && !adding ? (
            <Card>
              <Text style={styles.cardTitle}>No vehicles yet</Text>
              <Text style={styles.hint}>
                Add your car or bike to publish journeys. Only the make, model and colour are shown to
                other members — never your registration number.
              </Text>
              <Button label="Add a vehicle" onPress={() => setAdding(true)} icon="add-circle-outline" />
            </Card>
          ) : null}

          {vehicles.map((vehicle) => (
            <Card key={vehicle.id} style={styles.vehicleCard}>
              <View style={styles.vehicleTop}>
                <Ionicons
                  name={vehicle.vehicle_type === 'BIKE' ? 'bicycle' : 'car-sport'}
                  size={22}
                  color={colors.navy}
                />
                <View style={{ flex: 1 }}>
                  <Text style={styles.vehicleName}>{vehicle.make_and_model}</Text>
                  <Text style={styles.hint}>
                    {vehicle.color} · {vehicle.registration_number}
                  </Text>
                </View>
                <Badge
                  label={vehicle.status === 'VERIFIED' ? 'Verified' : vehicle.status === 'PENDING' ? 'Pending' : 'Rejected'}
                  tone={vehicle.status === 'VERIFIED' ? 'success' : vehicle.status === 'PENDING' ? 'warning' : 'danger'}
                  icon={vehicle.status === 'VERIFIED' ? 'checkmark-circle' : 'time-outline'}
                />
              </View>
              {vehicle.review_note ? <Text style={styles.hint}>{vehicle.review_note}</Text> : null}
            </Card>
          ))}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    gap: spacing.md,
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
  title: { color: colors.text, ...typography.h2, flex: 1, textAlign: 'center' },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  card: { gap: spacing.md },
  cardTitle: { color: colors.text, ...typography.h2 },
  hint: { color: colors.textMuted, ...typography.caption, lineHeight: 17 },
  vehicleCard: { gap: spacing.sm },
  vehicleTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  attachRow: { gap: spacing.xs },
  attach: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  attachLabel: { flex: 1, color: colors.text, ...typography.caption },
  vehicleName: { color: colors.text, ...typography.bodyStrong },
});
