import { Platform } from 'react-native';
import { biapTheme } from '@/theme/biap';

// BIAP brand palette (docs/BIAP_DESIGN_DIRECTION.md, src/theme/biap.ts).
// `light` matches the design direction exactly. `dark` is a matching
// adaptation (the direction only specifies one, light-first palette) that
// keeps the same brand hues so system dark mode still looks intentional
// instead of falling back to the old pre-rebrand tones.
export const Colors = {
  light: {
    text: biapTheme.colors.text,
    background: biapTheme.colors.background,
    backgroundElement: biapTheme.colors.surface,
    backgroundSelected: biapTheme.colors.border,
    textSecondary: biapTheme.colors.textMuted,
  },
  dark: {
    text: '#EEF1FA',
    background: '#0A0E1C',
    backgroundElement: '#141A30',
    backgroundSelected: '#1F2745',
    textSecondary: '#8B93B0',
  },
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;
export type ThemeColors = (typeof Colors)['light'] | (typeof Colors)['dark'];

// Kept as the app's stable brand-color names (used across every screen) but
// repointed to the new BIAP design system so the whole app re-skins from
// this one place. `positive`/`negative`/`primary`/`secondary`/`warning` are
// the doc's own names, exported alongside for new code.
export const Brand = {
  primary: biapTheme.colors.primary,
  secondary: biapTheme.colors.secondary,
  positive: biapTheme.colors.positive,
  negative: biapTheme.colors.negative,
  warning: biapTheme.colors.warning,
  // legacy aliases so every existing screen picks up the rebrand for free
  stockGreen: biapTheme.colors.positive,
  bizBlue: biapTheme.colors.primary,
  dataViolet: biapTheme.colors.secondary,
  saffron: biapTheme.colors.warning,
} as const;

export const Radius = biapTheme.radius;

export const Fonts = Platform.select({
  ios: {
    sans: 'Vazirmatn_400Regular',
    serif: 'ui-serif',
    rounded: 'ui-rounded',
    mono: 'ui-monospace',
  },
  default: {
    sans: 'Vazirmatn_400Regular',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: 'Vazirmatn_400Regular, sans-serif',
    serif: 'var(--font-serif)',
    rounded: 'var(--font-rounded)',
    mono: 'var(--font-mono)',
  },
});

export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  three: 16,
  four: 24,
  five: 32,
  six: 64,
} as const;

export const BottomTabInset = Platform.select({ ios: 50, android: 80 }) ?? 0;
export const MaxContentWidth = 800;

export const BiapLogo = require('@/assets/brand/biap-logo.png');
