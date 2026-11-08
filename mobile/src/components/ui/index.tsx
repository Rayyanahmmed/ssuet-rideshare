import {
  ActivityIndicator,
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
  type ViewStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useEffect, useState } from 'react';
import { Platform } from 'react-native';
import { getAccessToken } from '@/api/client';
import { mediaUrl } from '@/api/media';
import { colors, radius, shadow, spacing, typography } from '@/theme';

/**
 * SSUET RideShare design-system primitives (§21).
 *
 * A small, hand-built component set (instead of a heavy UI kit) keeps the visual
 * language consistent — one radius scale, one shadow scale, one palette — and
 * keeps the bundle lean for an Android APK.
 */

export function Screen({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.screen, style]}>{children}</View>;
}

export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <View style={styles.sectionRow}>
      <Text style={styles.sectionTitle}>{children}</Text>
      {action}
    </View>
  );
}

type ButtonProps = {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  loading?: boolean;
  disabled?: boolean;
  icon?: keyof typeof Ionicons.glyphMap;
  fullWidth?: boolean;
};

export function Button({
  label,
  onPress,
  variant = 'primary',
  loading = false,
  disabled = false,
  icon,
  fullWidth = true,
}: ButtonProps) {
  const isDisabled = disabled || loading;
  const palette = {
    primary: { bg: colors.green, text: colors.textInverse, border: colors.green },
    secondary: { bg: colors.surface, text: colors.navy, border: colors.border },
    ghost: { bg: 'transparent', text: colors.navy, border: 'transparent' },
    danger: { bg: colors.dangerTint, text: colors.danger, border: colors.dangerTint },
  }[variant];

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: isDisabled, busy: loading }}
      onPress={isDisabled ? undefined : onPress}
      style={({ pressed }) => [
        styles.button,
        fullWidth && styles.buttonFull,
        {
          backgroundColor: palette.bg,
          borderColor: palette.border,
          opacity: isDisabled ? 0.5 : pressed ? 0.85 : 1,
        },
      ]}
    >
      {loading ? (
        <ActivityIndicator color={palette.text} size="small" />
      ) : (
        <View style={styles.buttonInner}>
          {icon ? <Ionicons name={icon} size={18} color={palette.text} /> : null}
          <Text style={[styles.buttonLabel, { color: palette.text }]}>{label}</Text>
        </View>
      )}
    </Pressable>
  );
}

type TextFieldProps = TextInputProps & {
  label: string;
  error?: string;
  hint?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  right?: React.ReactNode;
};

export function TextField({ label, error, hint, icon, right, style, ...inputProps }: TextFieldProps) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={[styles.inputWrap, Boolean(error) && styles.inputWrapError]}>
        {icon ? <Ionicons name={icon} size={18} color={colors.textMuted} /> : null}
        <TextInput
          placeholderTextColor={colors.textMuted}
          style={[styles.input, style]}
          {...inputProps}
        />
        {right}
      </View>
      {error ? (
        <Text style={styles.fieldError}>{error}</Text>
      ) : hint ? (
        <Text style={styles.fieldHint}>{hint}</Text>
      ) : null}
    </View>
  );
}

export function ChipRow<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <View style={styles.chipRow}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <Pressable
            key={option.value}
            onPress={() => onChange(option.value)}
            accessibilityRole="radio"
            accessibilityState={{ selected: active }}
            style={[styles.chip, active && styles.chipActive]}
          >
            <Text style={[styles.chipLabel, active && styles.chipLabelActive]}>{option.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Badge({
  label,
  tone = 'neutral',
  icon,
}: {
  label: string;
  tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info';
  icon?: keyof typeof Ionicons.glyphMap;
}) {
  const tones = {
    neutral: { bg: colors.surfaceAlt, text: colors.textMuted },
    success: { bg: colors.greenTint, text: colors.greenDark },
    warning: { bg: colors.warningTint, text: colors.warning },
    danger: { bg: colors.dangerTint, text: colors.danger },
    info: { bg: colors.infoTint, text: colors.info },
  }[tone];

  return (
    <View style={[styles.badge, { backgroundColor: tones.bg }]}>
      {icon ? <Ionicons name={icon} size={12} color={tones.text} /> : null}
      <Text style={[styles.badgeLabel, { color: tones.text }]}>{label}</Text>
    </View>
  );
}

/**
 * A member's picture, or their initials when there is none (§21, Phase 13–14).
 *
 * The photo is served from an authenticated endpoint, so React Native's `Image` is
 * given the access token as a header — the same token the API client uses. If the
 * image fails (expired token, deleted photo) the initials fall back in place: an
 * avatar must never leave a hole in the layout.
 *
 * Small avatars ask for `size=thumb` (128 px, ~1 KB) instead of the 512 px original:
 * a chat list of twenty faces should not pull twenty full-size pictures over a campus
 * network. The rule is the size of the rendered avatar, not the screen.
 */
const THUMB_UP_TO = 48;

/**
 * Browsers cannot send a bearer header with `<img src>`, and react-native-web renders
 * `Image` as `<img>` — so on the web the photo is fetched with the token and shown from an
 * object URL (same approach as the admin console). Native builds keep the header form.
 */
const webPhotoCache = new Map<string, string>();
const MAX_WEB_PHOTOS = 200;

function useWebAuthedPhoto(uri: string | null, token: string | null): { src: string | null; failed: boolean } {
  const [state, setState] = useState<{ src: string | null; failed: boolean }>({ src: null, failed: false });

  useEffect(() => {
    if (Platform.OS !== 'web' || !uri || !token) {
      setState({ src: null, failed: false });
      return undefined;
    }
    const cached = webPhotoCache.get(uri);
    if (cached) {
      setState({ src: cached, failed: false });
      return undefined;
    }
    let cancelled = false;
    fetch(uri, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => {
        if (!response.ok) throw new Error(`photo ${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        const objectUrl = URL.createObjectURL(blob);
        if (webPhotoCache.size >= MAX_WEB_PHOTOS) {
          const oldest = webPhotoCache.keys().next().value;
          if (oldest) webPhotoCache.delete(oldest);
        }
        webPhotoCache.set(uri, objectUrl);
        if (!cancelled) setState({ src: objectUrl, failed: false });
      })
      .catch(() => {
        if (!cancelled) setState({ src: null, failed: true });
      });
    return () => {
      cancelled = true;
    };
  }, [uri, token]);

  return state;
}

export function Avatar({
  name,
  size = 44,
  photoUrl,
}: {
  name: string;
  size?: number;
  photoUrl?: string | null;
}) {
  const [failed, setFailed] = useState(false);
  const initials = name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
  const base = mediaUrl(photoUrl);
  // Only our own photo endpoint understands the variant; a legacy external link is
  // used exactly as the member supplied it.
  const canVary = Boolean(base && base.includes('/photo?'));
  const canUseThumb = canVary && size <= THUMB_UP_TO;
  const uri = base && canUseThumb ? `${base}&size=thumb` : base;
  const token = getAccessToken();
  const web = useWebAuthedPhoto(uri, token);
  const isWeb = Platform.OS === 'web';
  const photoSrc = isWeb ? web.src : uri;
  const showPhoto = Boolean(photoSrc) && !failed && !(isWeb && web.failed);

  return (
    <View style={[styles.avatar, { width: size, height: size, borderRadius: size / 2 }]}>
      {showPhoto ? (
        <Image
          source={
            isWeb || !token ? { uri: photoSrc as string } : { uri: photoSrc as string, headers: { Authorization: `Bearer ${token}` } }
          }
          style={{ width: size, height: size, borderRadius: size / 2 }}
          onError={() => setFailed(true)}
          accessibilityLabel={`${name}'s profile photo`}
        />
      ) : (
        <Text style={[styles.avatarText, { fontSize: size * 0.36 }]}>{initials || 'S'}</Text>
      )}
    </View>
  );
}

export function EmptyState({
  icon,
  title,
  message,
  action,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <View style={styles.empty}>
      <View style={styles.emptyIcon}>
        <Ionicons name={icon} size={26} color={colors.greenDark} />
      </View>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyMessage}>{message}</Text>
      {action ? <View style={styles.emptyAction}>{action}</View> : null}
    </View>
  );
}

type BannerProps = { tone?: 'info' | 'warning' | 'danger' | 'success'; title?: string; message: string };

export function Banner({ tone = 'info', title, message }: BannerProps) {
  const tones = {
    info: { bg: colors.infoTint, text: colors.info, icon: 'information-circle' as const },
    warning: { bg: colors.warningTint, text: colors.warning, icon: 'alert-circle' as const },
    danger: { bg: colors.dangerTint, text: colors.danger, icon: 'close-circle' as const },
    success: { bg: colors.greenTint, text: colors.greenDark, icon: 'checkmark-circle' as const },
  }[tone];

  return (
    <View style={[styles.banner, { backgroundColor: tones.bg }]}>
      <Ionicons name={tones.icon} size={18} color={tones.text} />
      <View style={{ flex: 1 }}>
        {title ? <Text style={[styles.bannerTitle, { color: tones.text }]}>{title}</Text> : null}
        <Text style={[styles.bannerMessage, { color: tones.text }]}>{message}</Text>
      </View>
    </View>
  );
}

export function ErrorText({ children }: { children: React.ReactNode }) {
  return <Text style={styles.errorText}>{children}</Text>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    ...shadow.card,
  },
  sectionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  sectionTitle: { color: colors.text, ...typography.h2 },
  button: {
    minHeight: 52,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    paddingHorizontal: spacing.lg,
  },
  buttonFull: { alignSelf: 'stretch' },
  buttonInner: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  buttonLabel: { fontSize: 15, fontWeight: '600' },
  field: { gap: spacing.xs, marginBottom: spacing.md },
  fieldLabel: { color: colors.textMuted, ...typography.label, textTransform: 'uppercase' },
  inputWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    minHeight: 50,
  },
  inputWrapError: { borderColor: colors.danger },
  input: { flex: 1, color: colors.text, fontSize: 15, paddingVertical: spacing.sm },
  fieldError: { color: colors.danger, ...typography.caption },
  fieldHint: { color: colors.textMuted, ...typography.caption },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    flex: 1,
    minWidth: 96,
    alignItems: 'center',
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActive: { backgroundColor: colors.navy, borderColor: colors.navy },
  chipLabel: { color: colors.textMuted, ...typography.bodyStrong },
  chipLabelActive: { color: colors.textInverse },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
    alignSelf: 'flex-start',
  },
  badgeLabel: { ...typography.label },
  avatar: {
    backgroundColor: colors.navy,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  avatarText: { color: colors.textInverse, fontWeight: '700' },
  empty: { alignItems: 'center', paddingVertical: spacing.xxl, paddingHorizontal: spacing.lg, gap: spacing.sm },
  emptyIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.greenTint,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyTitle: { color: colors.text, ...typography.h2, textAlign: 'center' },
  emptyMessage: { color: colors.textMuted, ...typography.body, textAlign: 'center' },
  emptyAction: { marginTop: spacing.md, alignSelf: 'stretch' },
  banner: {
    flexDirection: 'row',
    gap: spacing.sm,
    alignItems: 'flex-start',
    borderRadius: radius.md,
    padding: spacing.md,
  },
  bannerTitle: { ...typography.bodyStrong, marginBottom: 2 },
  bannerMessage: { ...typography.caption },
  errorText: { color: colors.danger, ...typography.caption, textAlign: 'center' },
});
