/**
 * SSUET RideShare design system (§21).
 *
 * Identity: deep navy (trust, university), fresh green (movement, go),
 * generous white space, soft 20px radii, one shadow scale.
 * Nothing in the app should use a raw hex value outside this file.
 */
export const colors = {
  // brand
  navy: '#0B1F3A',
  navySoft: '#17335A',
  green: '#12B76A',
  greenDark: '#0E9156',
  greenTint: '#E7F8F0',

  // surfaces
  background: '#F6F8FB',
  surface: '#FFFFFF',
  surfaceAlt: '#EEF2F7',
  border: '#E3E9F2',

  // text
  text: '#0B1F3A',
  textMuted: '#5A6B85',
  textInverse: '#FFFFFF',

  // semantic
  warning: '#F79009',
  warningTint: '#FEF4E6',
  danger: '#D92D20',
  dangerTint: '#FDECEA',
  info: '#2E90FA',
  infoTint: '#EAF3FF',
  star: '#F5A623',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radius = {
  sm: 8,
  md: 14,
  lg: 20,
  pill: 999,
} as const;

export const typography = {
  display: { fontSize: 28, fontWeight: '700' as const, letterSpacing: -0.5 },
  h1: { fontSize: 22, fontWeight: '700' as const },
  h2: { fontSize: 18, fontWeight: '600' as const },
  body: { fontSize: 15, fontWeight: '400' as const },
  bodyStrong: { fontSize: 15, fontWeight: '600' as const },
  caption: { fontSize: 13, fontWeight: '400' as const },
  label: { fontSize: 12, fontWeight: '600' as const, letterSpacing: 0.4 },
} as const;

export const shadow = {
  card: {
    shadowColor: '#0B1F3A',
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
  },
  floating: {
    shadowColor: '#0B1F3A',
    shadowOpacity: 0.12,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },
} as const;

export const theme = { colors, spacing, radius, typography, shadow };
export type Theme = typeof theme;
