import { View, Text, StyleSheet } from 'react-native';
import { Brand, Fonts, Spacing, ThemeColors } from '@/constants/theme';

/**
 * Safe production gate for real-money trading.
 *
 * This component deliberately does not collect card credentials and does not
 * submit orders. It becomes actionable only after the licensed broker adapter,
 * hosted funding flow and broker authorization are configured on the backend.
 */
export function RealTradeGate({ colors }: { colors: ThemeColors }) {
  return (
    <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
      <View style={styles.head}>
        <View style={styles.liveBadge}><Text style={styles.liveBadgeText}>REAL</Text></View>
        <Text style={[styles.title, { color: colors.text }]}>معامله با پول واقعی</Text>
      </View>

      <Text style={[styles.body, { color: colors.textSecondary }]}>
        کارگزاری اولیه برای اتصال: فارابی. ساختار BIAP آماده است تا بعد از دریافت مستندات رسمی، URLها و کلیدهای API فقط روی سرور وارد شوند؛ هیچ کلید محرمانه‌ای داخل اپ موبایل قرار نمی‌گیرد.
      </Text>

      <View style={[styles.flow, { backgroundColor: colors.backgroundSelected }]}>
        <Text style={[styles.flowText, { color: colors.text }]}>کارت بانکی ← درگاه امن کارگزاری/PSP ← قدرت خرید کارگزاری ← سفارش تأییدشده BIAP ← API کارگزاری ← بورس</Text>
      </View>

      <View style={styles.checklist}>
        <Check label="ساختار Broker Adapter" done colors={colors} />
        <Check label="محل امن تنظیم API روی سرور" done colors={colors} />
        <Check label="قفل LIVE_TRADING_ENABLED" done colors={colors} />
        <Check label="مستندات رسمی Farabi API" done={false} colors={colors} />
        <Check label="Sandbox / UAT credentials" done={false} colors={colors} />
        <Check label="Hosted funding URL" done={false} colors={colors} />
      </View>

      <Text style={[styles.note, { color: Brand.warning }]}>تا تکمیل سه مورد آخر، خرید واقعی عمداً غیرفعال می‌ماند.</Text>
    </View>
  );
}

function Check({ label, done, colors }: { label: string; done: boolean; colors: ThemeColors }) {
  return (
    <View style={styles.checkRow}>
      <Text style={[styles.checkText, { color: colors.textSecondary }]}>{label}</Text>
      <View style={[styles.dot, { backgroundColor: done ? Brand.positive : Brand.warning }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: Spacing.three, padding: Spacing.four, marginTop: Spacing.three, alignItems: 'flex-end', gap: Spacing.two },
  head: { width: '100%', flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between' },
  title: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '800' },
  liveBadge: { backgroundColor: '#0e7c55', borderRadius: 12, paddingHorizontal: 8, paddingVertical: 4 },
  liveBadgeText: { color: '#fff', fontFamily: Fonts.mono, fontSize: 9, fontWeight: '800' },
  body: { fontFamily: Fonts.sans, fontSize: 11.5, lineHeight: 19, textAlign: 'right' },
  flow: { width: '100%', borderRadius: Spacing.two, padding: Spacing.three },
  flowText: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 18, textAlign: 'right' },
  checklist: { width: '100%', gap: 8, marginTop: 2 },
  checkRow: { flexDirection: 'row-reverse', alignItems: 'center', gap: 8 },
  checkText: { flex: 1, fontFamily: Fonts.sans, fontSize: 10.5, textAlign: 'right' },
  dot: { width: 8, height: 8, borderRadius: 4 },
  note: { fontFamily: Fonts.sans, fontSize: 10.5, fontWeight: '700' },
});
