import { View, Text, StyleSheet } from 'react-native';
import { Brand, Fonts, Spacing, ThemeColors } from '@/constants/theme';

/** Broker-neutral production boundary. Real orders stay outside BIAP until an
 * officially authorized broker adapter is connected. */
export function RealTradeGate({ colors }: { colors: ThemeColors }) {
  return (
    <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
      <View style={styles.head}>
        <View style={styles.manualBadge}><Text style={styles.manualBadgeText}>MANUAL</Text></View>
        <Text style={[styles.title, { color: colors.text }]}>اجرای واقعی فعلاً دستی است</Text>
      </View>
      <Text style={[styles.body, { color: colors.textSecondary }]}>
        BIAP به کارگزاری خاصی وابسته نیست. کیا‌شا تحلیل، نماد، اندازه پیشنهادی و زمان تصمیم را ارائه می‌کند؛ خرید یا فروش واقعی را شما در کارگزاری دلخواه انجام می‌دهید و سپس داخل BIAP تأیید می‌کنید تا موقعیت برای پیگیری بعدی ثبت شود.
      </Text>
      <View style={[styles.flow, { backgroundColor: colors.backgroundSelected }]}>
        <Text style={[styles.flowText, { color: colors.text }]}>داده بازار + CODAL ← کیا‌شا ← کنترل ریسک ← پیشنهاد اندازه/زمان ← اجرای دستی در کارگزاری دلخواه ← تأیید خرید/فروش در BIAP</Text>
      </View>
      <Text style={[styles.note, { color: Brand.warning }]}>ارسال مستقیم سفارش از BIAP تا زمان اتصال رسمی یک Broker Adapter مجاز، غیرفعال می‌ماند.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: Spacing.three, padding: Spacing.four, marginTop: Spacing.three, alignItems: 'flex-end', gap: Spacing.two },
  head: { width: '100%', flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between' },
  title: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '800' },
  manualBadge: { backgroundColor: '#365314', borderRadius: 12, paddingHorizontal: 8, paddingVertical: 4 },
  manualBadgeText: { color: '#fff', fontFamily: Fonts.mono, fontSize: 9, fontWeight: '800' },
  body: { fontFamily: Fonts.sans, fontSize: 11.5, lineHeight: 19, textAlign: 'right' },
  flow: { width: '100%', borderRadius: Spacing.two, padding: Spacing.three },
  flowText: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 18, textAlign: 'right' },
  note: { fontFamily: Fonts.sans, fontSize: 10.5, fontWeight: '700', textAlign: 'right' },
});
