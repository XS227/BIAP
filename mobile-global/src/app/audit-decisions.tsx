import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { fetchGlobalAuditLedger, type GlobalAuditLedgerResponse } from '@/lib/global-api';
import { getGlobalMarketSelection } from '@/lib/global-market-selection';

export default function AuditDecisionsScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [data, setData] = useState<GlobalAuditLedgerResponse | null>(null);
  const [market, setMarket] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    setData(null);
    try {
      const selected = await getGlobalMarketSelection();
      setMarket(selected.country + ' • ' + selected.exchange);
      const result = await fetchGlobalAuditLedger(selected.country, selected.exchange);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Stored audit data is unavailable.');
    } finally {
      setLoading(false);
    }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
    <ScrollView contentContainerStyle={styles.content}><View style={styles.max}>
      <Text style={[styles.title, { color: colors.text }]}>Audit Decisions</Text>
      <Text style={[styles.subtitle, { color: colors.textSecondary }]}>{market || 'Selected Global market'} · stored evidence only</Text>
      <Text style={[styles.notice, { color: colors.textSecondary }]}>
        Evidence PASS is not an audited financial statement, a complete financial model or a BUY recommendation.
        Missing figures remain missing. AI Company Analysis requires a separately verified proxy.
      </Text>
      <Pressable onPress={() => { void load(); }} style={[styles.refresh, { backgroundColor: colors.backgroundElement }]}>
        <Text style={{ color: colors.text, fontWeight: '700' }}>Refresh stored audit</Text>
      </Pressable>
      {loading ? <ActivityIndicator color={Brand.primary} /> : null}
      {error ? <Text style={{ color: Brand.negative }}>{error}</Text> : null}
      {!loading && data?.note ? <Text style={{ color: colors.textSecondary }}>{data.note}</Text> : null}
      {!loading && data?.rows.length === 0 ? <Text style={{ color: colors.textSecondary }}>No stored company analyses for this market.</Text> : null}
      {data?.rows.map((item, index) => {
        const evidence = item.evidence;
        const ledger = item.ledger;
        const financial = ledger?.financial;
        const missing = financial?.missing ?? [];
        const source = ledger?.source || 'SOURCE UNAVAILABLE';
        return <View key={item.ticker + '-' + index} style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
          <Text style={[styles.company, { color: colors.text }]}>{item.ticker} · {item.name || 'Unknown company'}</Text>
          <Text style={[styles.meta, { color: colors.textSecondary }]}>Ledger: {ledger?.status || 'UNVERIFIED'} · Evidence: {evidence?.status || 'UNVERIFIED'}</Text>
          <Text style={[styles.meta, { color: colors.textSecondary }]}>Source: {source}</Text>
          <Text style={[styles.meta, { color: colors.textSecondary }]}>
            Financial coverage: {typeof financial?.coveragePct === 'number' ? financial.coveragePct.toFixed(1) + '%' : 'UNAVAILABLE'}
            {' · '}Core statements: {financial?.coreComplete === true ? 'PRESENT' : 'INCOMPLETE / UNVERIFIED'}
          </Text>
          <Text style={[styles.meta, { color: colors.textSecondary }]}>
            Full financial completeness: {financial?.complete === true ? 'REPORTED COMPLETE' : 'NOT COMPLETE / UNVERIFIED'}
          </Text>
          {missing.length > 0 ? <Text style={[styles.meta, { color: Brand.warning }]}>Missing: {missing.slice(0, 8).join(', ')}</Text> : null}
          {ledger?.reason ? <Text style={[styles.reason, { color: colors.textSecondary }]} numberOfLines={3}>{ledger.reason}</Text> : null}
        </View>;
      })}
    </View></ScrollView>
  </SafeAreaView>;
}
const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingTop: Spacing.four, paddingBottom: BottomTabInset + Spacing.four },
  max: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  title: { fontFamily: Fonts.sans, fontSize: 25, fontWeight: '900' },
  subtitle: { fontFamily: Fonts.sans, fontSize: 12, marginTop: 4 },
  notice: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 17, marginVertical: Spacing.three },
  refresh: { padding: Spacing.three, borderRadius: Radius.md, marginBottom: Spacing.three, alignItems: 'center' },
  card: { padding: Spacing.three, borderRadius: Radius.md, marginBottom: Spacing.two },
  company: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '800' },
  meta: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 18, marginTop: 4 },
  reason: { fontFamily: Fonts.sans, fontSize: 10, lineHeight: 16, marginTop: 6 },
});
