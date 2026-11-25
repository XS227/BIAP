import { useState, type ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type TextStyle } from 'react-native';
import { Brand, Fonts, Radius, type ThemeColors } from '@/constants/theme';
import { tr, type Lang } from '@/lib/agent-i18n';
import type { Tone } from '@/lib/agent-format';

export const TONE_COLOR: Record<Tone, string> = {
  positive: Brand.positive, neutral: '#64748b', warning: Brand.warning, negative: Brand.negative, severe: '#7f1d1d', muted: '#94a3b8',
};

/** Right-to-left text for Persian; English is left unchanged. */
export function rtl(lang: Lang): TextStyle { return lang === 'fa' ? { textAlign: 'right', writingDirection: 'rtl' } : {}; }

export function LevelChip({ text, tone, arrowDown, testID }: { text: string; tone: Tone; arrowDown?: boolean; testID?: string }) {
  const c = TONE_COLOR[tone];
  return <View testID={testID} style={[s.chip, { borderColor: c, backgroundColor: `${c}1f` }]}><Text style={[s.chipText, { color: c }]}>{arrowDown ? '↓ ' : ''}{text}</Text></View>;
}

export function Tag({ text, color = Brand.warning }: { text: string; color?: string }) {
  return <View style={[s.tag, { borderColor: color }]}><Text style={[s.tagText, { color }]}>{text}</Text></View>;
}

/** Card with a title, the language toggle and the fixed advisory line. */
export function AgentCard({ title, lang, onLang, colors, children, right }: { title: string; lang: Lang; onLang: (l: Lang) => void; colors: ThemeColors; children: ReactNode; right?: ReactNode }) {
  return <View style={[s.card, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
    <View style={s.head}>
      <Text style={[s.title, { color: colors.text }, rtl(lang)]}>{title}</Text>
      {right}
      <Pressable onPress={() => onLang(lang === 'fa' ? 'en' : 'fa')} accessibilityRole="button" style={[s.lang, { borderColor: colors.backgroundSelected }]}><Text style={[s.langText, { color: colors.textSecondary }]}>{tr(lang, 'language')}</Text></Pressable>
    </View>
    <Text style={[s.advisory, { color: colors.textSecondary }, rtl(lang)]}>{tr(lang, 'advisory')}</Text>
    {children}
  </View>;
}

export function Loading({ lang, colors }: { lang: Lang; colors: ThemeColors }) {
  return <View style={s.loading}><ActivityIndicator size="small" color={Brand.primary} /><Text style={[s.body, { color: colors.textSecondary }]}>{tr(lang, 'loading')}</Text></View>;
}

export function Unavailable({ lang, colors, onRetry }: { lang: Lang; colors: ThemeColors; onRetry?: () => void }) {
  return <View style={s.loading}><Text style={[s.body, { color: colors.textSecondary }, rtl(lang)]}>{tr(lang, 'unavailable')}</Text>{onRetry ? <Pressable onPress={onRetry}><Text style={[s.link]}>{tr(lang, 'retry')}</Text></Pressable> : null}</View>;
}

export function Bullets({ lines, colors, lang }: { lines: string[]; colors: ThemeColors; lang: Lang }) {
  return <View style={{ marginTop: 6 }}>{lines.map((l, i) => <Text key={`${i}-${l}`} style={[s.body, { color: colors.text }, rtl(lang)]}>{lang === 'fa' ? '' : '• '}{l}{lang === 'fa' ? ' •' : ''}</Text>)}</View>;
}

/** "Data behind this": collapsed by default; shows exactly what the API returned. */
export function Expandable({ lang, colors, children, testID }: { lang: Lang; colors: ThemeColors; children: ReactNode; testID?: string }) {
  const [open, setOpen] = useState(false);
  return <View style={{ marginTop: 10 }}>
    <Pressable testID={testID} onPress={() => setOpen(!open)} accessibilityRole="button"><Text style={[s.link, rtl(lang)]}>{open ? '▾' : '▸'} {open ? tr(lang, 'hide') : tr(lang, 'dataBehind')}</Text></Pressable>
    {open ? <View style={{ marginTop: 6 }}>{children}</View> : null}
  </View>;
}

export function Row({ label, value, colors, lang, dot, sub }: { label: string; value: string; colors: ThemeColors; lang: Lang; dot?: string; sub?: string }) {
  return <View style={[s.row, { borderBottomColor: colors.backgroundSelected }, lang === 'fa' && { flexDirection: 'row-reverse' }]}>
    <View style={{ flex: 1 }}>
      <Text style={[s.rowLabel, { color: colors.textSecondary }, rtl(lang)]}>{dot ? <Text style={{ color: dot }}>● </Text> : null}{label}</Text>
      {sub ? <Text style={[s.sub, { color: colors.textSecondary }, rtl(lang)]}>{sub}</Text> : null}
    </View>
    <Text style={[s.rowValue, { color: colors.text }]}>{value}</Text>
  </View>;
}

export const s = StyleSheet.create({
  card: { borderRadius: Radius.md, borderWidth: 1, padding: 14, marginTop: 12 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { flex: 1, fontFamily: Fonts.sans, fontSize: 15, fontWeight: '900' },
  lang: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 3 },
  langText: { fontFamily: Fonts.sans, fontSize: 10, fontWeight: '800' },
  advisory: { fontFamily: Fonts.sans, fontSize: 10, marginTop: 4 },
  chip: { borderWidth: 1.5, borderRadius: 999, paddingHorizontal: 11, paddingVertical: 4, alignSelf: 'flex-start' },
  chipText: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '900' },
  tag: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 1, alignSelf: 'flex-start' },
  tagText: { fontFamily: Fonts.sans, fontSize: 9.5, fontWeight: '900' },
  loading: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10 },
  body: { fontFamily: Fonts.sans, fontSize: 11.5, lineHeight: 18 },
  link: { fontFamily: Fonts.sans, fontSize: 11.5, fontWeight: '800', color: Brand.primary },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth },
  rowLabel: { fontFamily: Fonts.sans, fontSize: 11 },
  sub: { fontFamily: Fonts.sans, fontSize: 9.5, marginTop: 1 },
  rowValue: { fontFamily: Fonts.mono, fontSize: 11, fontWeight: '700', textAlign: 'right' },
});
