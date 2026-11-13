import { goBackOr } from '@/lib/navigation';
import { useState } from 'react';
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { ApiError } from '@/api/client';
import * as authApi from '@/api/auth';
import { Banner, Button, Card, ChipRow, TextField } from '@/components/ui';
import { useAuthStore } from '@/store/auth';
import { colors, spacing, typography } from '@/theme';

const MAX_UPLOAD_BYTES = 5 * 1024 * 1024; // mirrors settings.MAX_UPLOAD_BYTES

const schema = z.object({
  verification_type: z.enum(['STUDENT_ID', 'EMPLOYEE_ID', 'MANUAL']),
  submitted_value: z.string().min(3, 'Enter the ID printed on your card').max(180),
  // Optional here because an uploaded photo is the other valid source; the screen
  // enforces "exactly one" before submitting so the API never sees an empty request.
  document_url: z.union([z.literal(''), z.string().url('Enter a valid https link')]).optional(),
  note: z.string().max(500).optional(),
});
type Values = z.infer<typeof schema>;

type PickedDocument = {
  assetId: string;
  uri: string;
  name: string;
  contentType: string;
  byteSize: number;
};

/**
 * Manual university verification (§4, Phase 9).
 *
 * The member photographs or picks a picture of their student/employee card. The
 * screen uploads it immediately (`POST /uploads/verification`), shows a preview and
 * submits the returned asset id — the file then lives inside the platform and is
 * readable only by its owner and by the reviewing administrator. A pasted https
 * link is still offered for members who keep their card in Drive; sending both is
 * rejected by the API, so the two modes are mutually exclusive here as well.
 */
export default function VerificationScreen() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const updateUser = useAuthStore((state) => state.updateUser);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [document, setDocument] = useState<PickedDocument | null>(null);
  const [uploading, setUploading] = useState(false);
  // Two mutually exclusive ways to supply the card; 'upload' is the default because
  // it keeps the document inside the platform.
  const [mode, setMode] = useState<'upload' | 'link'>('upload');

  const { control, handleSubmit } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      verification_type: user?.role === 'TEACHER' ? 'EMPLOYEE_ID' : 'STUDENT_ID',
      submitted_value: user?.university_id ?? '',
      document_url: '',
      note: '',
    },
  });

  const pickAndUpload = async (source: 'library' | 'camera') => {
    setError(null);
    try {
      if (source === 'camera') {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!permission.granted) {
          setError('Allow camera access in Settings, or pick a photo from your library instead.');
          return;
        }
      } else {
        const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (!permission.granted) {
          setError('Allow photo access in Settings, or paste a link to the picture instead.');
          return;
        }
      }

      const result =
        source === 'camera'
          ? await ImagePicker.launchCameraAsync({ quality: 0.7, allowsEditing: true })
          : await ImagePicker.launchImageLibraryAsync({
              mediaTypes: ['images'],
              quality: 0.7,
              allowsEditing: true,
            });
      const asset = result.canceled ? undefined : result.assets?.[0];
      if (!asset) return;
      const byteSize = asset.fileSize ?? 0;
      if (byteSize > MAX_UPLOAD_BYTES) {
        setError('That picture is larger than 5 MB. Take a new one or choose a smaller file.');
        return;
      }

      // Replace any previous upload so a withdrawn file is not left on the server.
      if (document) {
        await authApi.deleteMediaAsset(document.assetId).catch(() => undefined);
        setDocument(null);
      }

      setUploading(true);
      const contentType = asset.mimeType ?? 'image/jpeg';
      const extension = contentType.split('/')[1] ?? 'jpg';
      const uploaded = await authApi.uploadVerificationDocument({
        uri: asset.uri,
        name: asset.fileName ?? `ssuet-card.${extension}`,
        type: contentType,
      });
      setDocument({
        assetId: uploaded.id,
        uri: asset.uri,
        name: uploaded.original_filename ?? `ssuet-card.${extension}`,
        contentType: uploaded.content_type,
        byteSize: uploaded.byte_size,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not upload that picture. Try again.');
    } finally {
      setUploading(false);
    }
  };

  const removeDocument = async () => {
    const current = document;
    setDocument(null);
    if (current) {
      await authApi.deleteMediaAsset(current.assetId).catch(() => undefined);
    }
  };

  const onSubmit = async (values: Values) => {
    setError(null);

    if (mode === 'upload' && !document) {
      setError('Attach a photo of your card, or switch to pasting a link.');
      return;
    }
    if (mode === 'link' && !values.document_url) {
      setError('Paste a link to a clear photo of your card.');
      return;
    }

    setSubmitting(true);
    try {
      await authApi.submitVerification({
        verification_type: values.verification_type,
        submitted_value: values.submitted_value,
        note: values.note || undefined,
        ...(mode === 'upload'
          ? { document_asset_id: document?.assetId }
          : { document_url: values.document_url }),
      });
      if (user) {
        updateUser({ ...user, verification_status: 'PENDING' });
      }
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not submit your verification.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => goBackOr(router)} style={styles.close}>
              <Ionicons name="close" size={22} color={colors.navy} />
            </Pressable>
            <Text style={styles.title}>University verification</Text>
          </View>

          {done ? (
            <Card style={styles.card}>
              <Banner
                tone="success"
                title="Submitted for review"
                message="An administrator will check your ID. You will be notified as soon as your account is verified."
              />
              <Button label="Back to profile" onPress={() => goBackOr(router)} />
            </Card>
          ) : (
            <Card style={styles.card}>
              <Text style={styles.help}>
                Only SSUET students and teachers may share rides. Attach a clear photo of your
                student or employee card — only you and the reviewing administrator can open it.
              </Text>

              {error ? <Banner tone="danger" message={error} /> : null}

              <Text style={styles.label}>Document type</Text>
              <Controller
                control={control}
                name="verification_type"
                render={({ field }) => (
                  <ChipRow
                    options={[
                      { value: 'STUDENT_ID' as const, label: 'Student card' },
                      { value: 'EMPLOYEE_ID' as const, label: 'Employee card' },
                    ]}
                    value={field.value === 'MANUAL' ? 'STUDENT_ID' : field.value}
                    onChange={field.onChange}
                  />
                )}
              />

              <Controller
                control={control}
                name="submitted_value"
                render={({ field, fieldState }) => (
                  <TextField
                    label="ID number"
                    placeholder="2023F-Bcs-301"
                    hint="Students: YEAR, F or S, programme, 3-digit roll (e.g. 2023F-Bcs-301)"
                    icon="card-outline"
                    value={field.value}
                    onChangeText={field.onChange}
                    error={fieldState.error?.message}
                  />
                )}
              />
              <Text style={styles.label}>University card</Text>
              <ChipRow
                options={[
                  { value: 'upload' as const, label: 'Attach a photo' },
                  { value: 'link' as const, label: 'Paste a link' },
                ]}
                value={mode}
                onChange={(next) => {
                  setMode(next);
                  setError(null);
                }}
              />

              {mode === 'upload' ? (
                document ? (
                  <View style={styles.preview}>
                    <Image source={{ uri: document.uri }} style={styles.thumbnail} resizeMode="cover" />
                    <View style={styles.previewMeta}>
                      <Text style={styles.previewName} numberOfLines={1}>
                        {document.name}
                      </Text>
                      <Text style={styles.previewSize}>
                        {(document.byteSize / 1024).toFixed(0)} KB · uploaded
                      </Text>
                      <Pressable onPress={removeDocument} hitSlop={8}>
                        <Text style={styles.remove}>Remove</Text>
                      </Pressable>
                    </View>
                  </View>
                ) : (
                  <View style={styles.pickerRow}>
                    <Button
                      label={uploading ? 'Uploading…' : 'Choose photo'}
                      variant="secondary"
                      icon="images-outline"
                      onPress={() => pickAndUpload('library')}
                      loading={uploading}
                      disabled={uploading}
                    />
                    <Button
                      label="Take photo"
                      variant="ghost"
                      icon="camera-outline"
                      onPress={() => pickAndUpload('camera')}
                      disabled={uploading}
                    />
                  </View>
                )
              ) : (
                <Controller
                  control={control}
                  name="document_url"
                  render={({ field, fieldState }) => (
                    <TextField
                      label="Photo link"
                      placeholder="https://…/my-ssuet-card.jpg"
                      icon="link-outline"
                      autoCapitalize="none"
                      keyboardType="url"
                      value={field.value ?? ''}
                      onChangeText={field.onChange}
                      error={fieldState.error?.message}
                      hint="Keep the link shareable (anyone with the link can open it) until your account is reviewed."
                    />
                  )}
                />
              )}
              <Controller
                control={control}
                name="note"
                render={({ field }) => (
                  <TextField
                    label="Note for the admin (optional)"
                    placeholder="My card photo is a little blurry at the bottom."
                    value={field.value}
                    onChangeText={field.onChange}
                    multiline
                  />
                )}
              />

              <Button label="Submit for review" onPress={handleSubmit(onSubmit)} loading={submitting} />
            </Card>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  flex: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginTop: spacing.sm },
  close: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { color: colors.text, ...typography.h1 },
  card: { gap: spacing.md },
  help: { color: colors.textMuted, ...typography.caption, lineHeight: 18 },
  pickerRow: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  preview: {
    flexDirection: 'row',
    gap: spacing.md,
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: spacing.sm,
  },
  thumbnail: { width: 64, height: 64, borderRadius: 8, backgroundColor: colors.border },
  previewMeta: { flex: 1, gap: 2 },
  previewName: { color: colors.text, ...typography.body, flexShrink: 1 },
  previewSize: { color: colors.textMuted, ...typography.caption },
  remove: { color: colors.danger, ...typography.caption, fontWeight: '600' },
  label: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
});
