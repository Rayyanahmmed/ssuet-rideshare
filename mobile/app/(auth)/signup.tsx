import { useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ApiError } from '@/api/client';
import * as authApi from '@/api/auth';
import { Banner, Button, Card, ChipRow, TextField } from '@/components/ui';
import { ServerPanel } from '@/components/ServerPanel';
import { DEPARTMENTS, signupSchema, type SignupValues } from '@/lib/schemas';
import { useAuthStore } from '@/store/auth';
import { env } from '@/lib/config';
import { colors, spacing, typography } from '@/theme';

const FIELD_LABELS: Record<string, string> = {
  full_name: 'Full name',
  email: 'Email',
  phone: 'Phone number',
  password: 'Password',
  confirm_password: 'Confirm password',
  university_id: 'Student ID',
  department: 'Department',
  semester: 'Semester',
  home_area: 'Home area',
  role: 'Role',
};

/** "Value error, Password must contain at least one number." → "Password: …". */
function describeFieldErrors(details: Record<string, string>): string {
  return Object.entries(details)
    .map(([field, message]) => `${FIELD_LABELS[field] ?? field}: ${message.replace(/^Value error,\s*/i, '')}`)
    .join(' · ');
}

export default function SignupScreen() {
  const router = useRouter();
  const completeSignIn = useAuthStore((state) => state.completeSignIn);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const scrollRef = useRef<ScrollView>(null);
  const [submitting, setSubmitting] = useState(false);

  const { control, handleSubmit, watch, setValue } = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      full_name: '',
      email: '',
      phone: '',
      password: '',
      confirm_password: '',
      role: 'STUDENT',
      university_id: '',
      department: '',
      home_area: '',
      semester: '',
      designation: '',
    },
  });

  const role = watch('role');
  const department = watch('department');

  const onSubmit = async (values: SignupValues) => {
    setFormError(null);
    setFieldErrors({});
    setSubmitting(true);
    try {
      const response = await authApi.signup({
        full_name: values.full_name.trim(),
        email: values.email.trim().toLowerCase(),
        password: values.password,
        phone: values.phone.trim(),
        role: values.role,
        university_id: values.university_id.trim(),
        department: values.department,
        home_area: values.home_area?.trim() || undefined,
        semester: values.role === 'STUDENT' && values.semester ? Number(values.semester) : undefined,
        designation: values.role === 'TEACHER' ? values.designation?.trim() || undefined : undefined,
      });
      await completeSignIn(response);
      router.replace('/(tabs)');
    } catch (error) {
      if (error instanceof ApiError && Object.keys(error.details).length > 0) {
        // Show the *actual* reason ("Password must contain at least one number.") instead of
        // the generic "Some of the submitted values are invalid." — a generic banner with no
        // visible field hint was impossible to act on (§21).
        setFieldErrors(error.details);
        setFormError(describeFieldErrors(error.details) || error.message);
      } else {
        setFormError(error instanceof ApiError ? error.message : 'Could not create your account.');
      }
      scrollRef.current?.scrollTo({ y: 0, animated: true });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.title}>Create your account</Text>
          <Text style={styles.subtitle}>
            Students and teachers of SSUET only. Verification keeps everyone safe.
          </Text>

          {formError ? (
            <Banner
              tone="danger"
              title={Object.keys(fieldErrors).length > 0 ? 'Please check the highlighted fields' : undefined}
              message={formError}
            />
          ) : null}

          <Card>
            <Text style={styles.groupLabel}>I am a</Text>
            <Controller
              control={control}
              name="role"
              render={({ field }) => (
                <ChipRow
                  options={[
                    { value: 'STUDENT' as const, label: 'Student' },
                    { value: 'TEACHER' as const, label: 'Teacher' },
                  ]}
                  value={field.value}
                  onChange={field.onChange}
                />
              )}
            />

            <View style={styles.gap} />

            <Controller
              control={control}
              name="full_name"
              render={({ field, fieldState }) => (
                <TextField
                  label="Full name"
                  placeholder="Ali Raza"
                  icon="person-outline"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.full_name}
                />
              )}
            />
            <Controller
              control={control}
              name="email"
              render={({ field, fieldState }) => (
                <TextField
                  label="Email address"
                  placeholder="yourname@ssuet.edu.pk"
                  icon="mail-outline"
                  autoCapitalize="none"
                  keyboardType="email-address"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.email}
                  hint="University emails are verified instantly. Other emails are verified by an admin."
                />
              )}
            />
            <Controller
              control={control}
              name="phone"
              render={({ field, fieldState }) => (
                <TextField
                  label="Phone number"
                  placeholder="+923001234567"
                  icon="call-outline"
                  keyboardType="phone-pad"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.phone}
                  hint="Shared only with a passenger you have matched with."
                />
              )}
            />
            <Controller
              control={control}
              name="university_id"
              render={({ field, fieldState }) => (
                <TextField
                  label={role === 'STUDENT' ? 'Student ID' : 'Employee ID'}
                  placeholder={role === 'STUDENT' ? 'SSUET-2022-101' : 'SSUET-EMP-1001'}
                  icon="card-outline"
                  autoCapitalize="characters"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.university_id}
                />
              )}
            />

            <Text style={styles.groupLabel}>Department</Text>
            <Controller
              control={control}
              name="department"
              render={({ field, fieldState }) => (
                <View>
                  <View style={styles.departmentWrap}>
                    {DEPARTMENTS.map((item) => {
                      const active = department === item;
                      return (
                        <Pressable
                          key={item}
                          onPress={() => setValue('department', item, { shouldValidate: true })}
                          style={[styles.departmentChip, active && styles.departmentChipActive]}
                        >
                          <Text style={[styles.departmentLabel, active && styles.departmentLabelActive]}>
                            {item}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </View>
                  {fieldState.error ? (
                    <Text style={styles.errorText}>{fieldState.error.message}</Text>
                  ) : null}
                  <Text style={styles.hiddenField}>{field.value}</Text>
                </View>
              )}
            />

            {role === 'STUDENT' ? (
              <>
                <Controller
                  control={control}
                  name="semester"
                  render={({ field, fieldState }) => (
                    <TextField
                      label="Current semester"
                      placeholder="5"
                      icon="school-outline"
                      keyboardType="number-pad"
                      maxLength={2}
                      value={field.value}
                      onChangeText={field.onChange}
                      onBlur={field.onBlur}
                      error={fieldState.error?.message ?? fieldErrors.semester}
                      hint="A number from 1 to 12 — for example 5."
                    />
                  )}
                />
                <Controller
                  control={control}
                  name="home_area"
                  render={({ field }) => (
                    <TextField
                      label="Home area (optional)"
                      placeholder="Gulshan-e-Iqbal"
                      icon="location-outline"
                      value={field.value}
                      onChangeText={field.onChange}
                      hint="Only the area name is shown to others — never your address."
                    />
                  )}
                />
              </>
            ) : (
              <>
                <Controller
                  control={control}
                  name="designation"
                  render={({ field }) => (
                    <TextField
                      label="Designation"
                      placeholder="Assistant Professor"
                      icon="briefcase-outline"
                      value={field.value}
                      onChangeText={field.onChange}
                    />
                  )}
                />
                <Controller
                  control={control}
                  name="home_area"
                  render={({ field }) => (
                    <TextField
                      label="Home area (optional)"
                      placeholder="Scheme 33"
                      icon="location-outline"
                      value={field.value}
                      onChangeText={field.onChange}
                    />
                  )}
                />
              </>
            )}

            <Controller
              control={control}
              name="password"
              render={({ field, fieldState }) => (
                <TextField
                  label="Password"
                  placeholder="At least 8 characters"
                  icon="lock-closed-outline"
                  secureTextEntry
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.password}
                  hint="At least 8 characters, including one letter and one number."
                />
              )}
            />
            <Controller
              control={control}
              name="confirm_password"
              render={({ field, fieldState }) => (
                <TextField
                  label="Confirm password"
                  placeholder="Repeat your password"
                  icon="lock-closed-outline"
                  secureTextEntry
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? fieldErrors.confirm_password}
                />
              )}
            />

            <Button
              label="Create account"
              onPress={handleSubmit(onSubmit)}
              loading={submitting}
              icon="checkmark-circle-outline"
            />
          </Card>

          {env.allowServerOverride ? <ServerPanel /> : null}

          <Pressable onPress={() => router.replace('/(auth)/login')} style={styles.footerLink}>
            <Text style={styles.footerText}>
              Already registered? <Text style={styles.link}>Sign in</Text>
            </Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  flex: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  title: { color: colors.text, ...typography.display, marginTop: spacing.lg },
  subtitle: { color: colors.textMuted, ...typography.body },
  groupLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase', marginBottom: spacing.sm },
  gap: { height: spacing.md },
  departmentWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  departmentChip: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  departmentChipActive: { backgroundColor: colors.greenTint, borderColor: colors.green },
  departmentLabel: { color: colors.textMuted, ...typography.caption },
  departmentLabelActive: { color: colors.greenDark, fontWeight: '700' },
  errorText: { color: colors.danger, ...typography.caption, marginTop: spacing.xs },
  hiddenField: { display: 'none' },
  footerLink: { alignItems: 'center', paddingVertical: spacing.md },
  footerText: { color: colors.textMuted, ...typography.caption },
  link: { color: colors.navy, ...typography.bodyStrong, textDecorationLine: 'underline' },
});
