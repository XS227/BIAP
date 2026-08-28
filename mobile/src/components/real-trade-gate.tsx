import { View, Text, StyleSheet } from 'react-native';
import { Brand, Fonts, Spacing, ThemeColors } from '@/constants/theme';

/**
 * Safe production gate for real-money trading.
 *
 * This component deliberately does not collect card credentials and does not
 * submit orders. It becomes actionable only after a licensed broker adapter,
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
        برای فعال‌شدن خرید و فروش واقعی باید حساب یک کارگزاری مجاز به BIAP متصل شود. BIAP اطلاعات کارت بانکی را دریافت یا نگهداری نمی‌کند.
      </Text>
      <View style={[styles.flow, { backgroundColor: colors.backgroundSelected }]}>
        <Text style={[styles.flowText, { color: colors.text }]}>کارت بانکی ← درگاه امن کارگزاری/PSP ← قدرت خرید کارگزاری ← سفارش تأییدشده BIAP ← کارگزاری ← بورس</Text>
      </View>
      <Text style={[styles.note, { color: Brand.warning }]}>در انتظار انتخاب کارگزاری و دریافت API/قرارداد رسمی</Text>
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
  note: { fontFamily: Fonts.sans, fontSize: 10.5, fontWeight: '700' },
});
