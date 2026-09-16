import { Image, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { BiapLogo, Brand, Colors, Fonts, Radius, Spacing } from '@/constants/theme';

const markets = [
  ['🇳🇴', 'Norway', 'Euronext Oslo + ESEF'],
  ['🇺🇸', 'United States', 'NYSE / Nasdaq + SEC EDGAR'],
  ['🇬🇧', 'United Kingdom', 'LSE + UKSEF / Companies House'],
  ['🇯🇵', 'Japan', 'Tokyo Stock Exchange + EDINET'],
  ['🇦🇺', 'Australia', 'ASX + official issuer evidence'],
  ['🇸🇪', 'Sweden', 'Nasdaq Stockholm + ESEF'],
];

export default function HomeScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Image source={BiapLogo} style={styles.logo} resizeMode="contain" />
          <View style={[styles.globalPill, { borderColor: Brand.primary }]}><Text style={styles.globalPillText}>GLOBAL</Text></View>
        </View>

        <View style={[styles.hero, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
          <Text style={styles.kicker}>BUSINESS & INVESTMENT ANALYSIS PLATFORM</Text>
          <Text style={[styles.title, { color: colors.text }]}>BIAP Global</Text>
          <Text style={[styles.body, { color: colors.textSecondary }]}>A multi-market research and portfolio decision-support system. Six agents combine fundamentals, risk, forecasting, comparison, evidence verification and portfolio construction.</Text>
          <Pressable onPress={() => router.push('/global')} style={styles.primaryButton}><Text style={styles.primaryButtonText}>Open Global Markets</Text></Pressable>
        </View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>Priority markets</Text>
        <View style={styles.grid}>
          {markets.map(([icon, name, source]) => (
            <Pressable key={name} onPress={() => router.push('/global')} style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
              <Text style={styles.icon}>{icon}</Text>
              <Text style={[styles.cardTitle, { color: colors.text }]}>{name}</Text>
              <Text style={[styles.cardText, { color: colors.textSecondary }]}>{source}</Text>
            </Pressable>
          ))}
        </View>

        <View style={[styles.systemCard, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
          <Text style={[styles.systemTitle, { color: colors.text }]}>Evidence before recommendation</Text>
          <Text style={[styles.systemText, { color: colors.textSecondary }]}>BIAP Global can return NO RECOMMENDATION when price data is stale, filings are missing, identity is ambiguous or the agents materially disagree. Live broker execution remains disabled in this preview.</Text>
        </View>

        <View style={styles.featureRow}>
          <View style={[styles.feature, { backgroundColor: colors.backgroundElement }]}><Text style={styles.featureNumber}>6</Text><Text style={[styles.featureLabel, { color: colors.textSecondary }]}>agents</Text></View>
          <View style={[styles.feature, { backgroundColor: colors.backgroundElement }]}><Text style={styles.featureNumber}>30+</Text><Text style={[styles.featureLabel, { color: colors.textSecondary }]}>country packs</Text></View>
          <View style={[styles.feature, { backgroundColor: colors.backgroundElement }]}><Text style={styles.featureNumber}>0</Text><Text style={[styles.featureLabel, { color: colors.textSecondary }]}>forced buys</Text></View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: Spacing.three, paddingBottom: 110 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 },
  logo: { width: 104, height: 38 },
  globalPill: { borderWidth: 1, borderRadius: 30, paddingHorizontal: 12, paddingVertical: 6 },
  globalPillText: { color: Brand.primary, fontFamily: Fonts.mono, fontWeight: '900', fontSize: 10, letterSpacing: 1.2 },
  hero: { borderWidth: 1, borderRadius: Radius.lg, padding: 22 },
  kicker: { color: Brand.primary, fontFamily: Fonts.mono, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  title: { fontFamily: Fonts.sans, fontSize: 32, fontWeight: '900', marginTop: 8 },
  body: { fontFamily: Fonts.sans, fontSize: 13, lineHeight: 22, marginTop: 6 },
  primaryButton: { marginTop: 18, backgroundColor: Brand.primary, minHeight: 50, borderRadius: Radius.md, alignItems: 'center', justifyContent: 'center' },
  primaryButtonText: { color: '#fff', fontFamily: Fonts.sans, fontWeight: '900', fontSize: 14 },
  sectionTitle: { fontFamily: Fonts.sans, fontSize: 17, fontWeight: '900', marginTop: 24, marginBottom: 10 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  card: { width: '48%', minHeight: 120, borderWidth: 1, borderRadius: Radius.md, padding: 13 },
  icon: { fontSize: 24 },
  cardTitle: { fontFamily: Fonts.sans, fontWeight: '900', fontSize: 14, marginTop: 6 },
  cardText: { fontFamily: Fonts.sans, fontSize: 10, lineHeight: 16, marginTop: 4 },
  systemCard: { borderWidth: 1, borderRadius: Radius.md, padding: 16, marginTop: 20 },
  systemTitle: { fontFamily: Fonts.sans, fontWeight: '900', fontSize: 14 },
  systemText: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 18, marginTop: 5 },
  featureRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  feature: { flex: 1, borderRadius: Radius.md, paddingVertical: 14, alignItems: 'center' },
  featureNumber: { color: Brand.primary, fontFamily: Fonts.mono, fontWeight: '900', fontSize: 18 },
  featureLabel: { fontFamily: Fonts.sans, fontSize: 9, marginTop: 3 },
});
