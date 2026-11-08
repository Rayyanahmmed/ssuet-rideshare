import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { AndroidDownload } from '@/components/AndroidDownload';
import { Button } from '@/components/ui';
import { colors, radius, spacing, typography } from '@/theme';

const SLIDES = [
  {
    icon: 'people-outline' as const,
    title: 'Travel with your campus',
    body: 'Verified SSUET students and teachers share the journeys they already make every day.',
  },
  {
    icon: 'shield-checkmark-outline' as const,
    title: 'Only verified members',
    body: 'Every account is tied to a university email or a student / employee ID reviewed by an administrator.',
  },
  {
    icon: 'wallet-outline' as const,
    title: 'Free or fuel sharing',
    body: 'Ride free, or agree to share fuel cost between yourselves. SSUET RideShare never takes a cut.',
  },
];

export default function WelcomeScreen() {
  const router = useRouter();
  const [index, setIndex] = useState(0);
  const slide = SLIDES[index]!;
  const isLast = index === SLIDES.length - 1;

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.brand}>
        <View style={styles.logo}>
          <Text style={styles.logoText}>S</Text>
        </View>
        <Text style={styles.brandName}>SSUET RideShare</Text>
      </View>

      <ScrollView contentContainerStyle={styles.body}>
        <View style={styles.iconCircle}>
          <Ionicons name={slide.icon} size={34} color={colors.greenDark} />
        </View>
        <Text style={styles.title}>{slide.title}</Text>
        <Text style={styles.bodyText}>{slide.body}</Text>

        <View style={styles.dots}>
          {SLIDES.map((item, dotIndex) => (
            <View key={item.title} style={[styles.dot, dotIndex === index && styles.dotActive]} />
          ))}
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <AndroidDownload />
        <Button
          label={isLast ? 'Get started' : 'Continue'}
          onPress={() => (isLast ? router.push('/(auth)/signup') : setIndex(index + 1))}
        />
        <Pressable onPress={() => router.replace('/(auth)/login')} style={styles.ghostLink}>
          <Text style={styles.ghostLinkText}>
            I already have an account · <Text style={styles.ghostLinkStrong}>Sign in</Text>
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  brand: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, padding: spacing.lg },
  logo: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    backgroundColor: colors.navy,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoText: { color: colors.green, fontSize: 20, fontWeight: '800' },
  brandName: { color: colors.navy, ...typography.bodyStrong },
  body: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: spacing.xl, gap: spacing.md },
  iconCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.greenTint,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  title: { color: colors.text, ...typography.display },
  bodyText: { color: colors.textMuted, ...typography.body, lineHeight: 22 },
  dots: { flexDirection: 'row', gap: spacing.xs, marginTop: spacing.lg },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.border },
  dotActive: { width: 22, backgroundColor: colors.green },
  footer: { padding: spacing.lg, gap: spacing.md },
  ghostLink: { alignItems: 'center', paddingVertical: spacing.sm },
  ghostLinkText: { color: colors.textMuted, ...typography.caption },
  ghostLinkStrong: { color: colors.navy, fontWeight: '700' },
});
