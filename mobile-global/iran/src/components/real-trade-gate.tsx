import { View, Text, StyleSheet } from 'react-native';
import { Brand, Fonts, Spacing, ThemeColors } from '@/constants/theme';

/** Compact broker-API placeholder. Real orders remain disabled until an
 * officially authorized broker/order API is connected. */
export function RealTradeGate({ colors }: { colors: ThemeColors }) {
  return (
    <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: `${Brand.primary}55` }]}>
      <View style={styles.head}>
        <View style={styles.badge}><Text style={styles.badgeText}>SOON</Text></View>
        <View style={styles.copy}>
          <Text style={[styles.title, { color: colors.text }]}>اتصال API کارگزاری</Text>
          <Text style={[styles.body, { color: colors.textSecondary }]}>به‌زودی — پس از اتصال منبع مجاز، خرید و فروش مستقیم از همین بخش فعال می‌شود.</Text>
        </View>
        <View style={styles.apiDot}><Text style={styles.apiIcon}>↔</Text></View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: Spacing.three, padding: Spacing.three, marginTop: Spacing.three, borderWidth: 1 },
  head: { width: '100%', flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.two },
  copy: { flex: 1, alignItems: 'flex-end' },
  title: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900' },
  body: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 17, textAlign: 'right', marginTop: 2 },
  badge: { backgroundColor: '#4c1d95', borderRadius: 12, paddingHorizontal: 8, paddingVertical: 4 },
  badgeText: { color: '#ddd6fe', fontFamily: Fonts.mono, fontSize: 9, fontWeight: '900' },
  apiDot: { width: 34, height: 34, borderRadius: 17, backgroundColor: '#26134f', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#7c3aed' },
  apiIcon: { color: '#c4b5fd', fontSize: 17, fontWeight: '900' },
});
