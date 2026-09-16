import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { GlobalAnalysis, scanGlobalMarket } from '@/lib/global-api';
import { getGlobalMarketSelection, GlobalMarketSelection } from '@/lib/global-market-selection';

function tone(call: string | undefined, secondary: string) {
  if (call === 'BUY_CANDIDATE') return Brand.positive;
  if (call === 'HOLD_OR_WATCH') return Brand.warning;
  if (call === 'AVOID_OR_REVIEW') return Brand.negative;
  return secondary;
}

function pct(value: number | undefined) {
  return value == null || !Number.isFinite(value) ? '—' : `${Math.round(value * 100)}%`;
}

export default function KiashaGlobalScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [selection, setSelection] = useState<GlobalMarketSelection | null>(null);
  const [picks, setPicks] = useState<GlobalAnalysis[]>([]);
  const [deepResults, setDeepResults] = useState<GlobalAnalysis[]>([]);
  const [status, setStatus] = useState('');
  const [meta, setMeta] = useState({ discovered: 0, screened: 0, deep: 0, coverage: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const selected = await getGlobalMarketSelection();
    setSelection(selected);
    try {
      setError('');
      const result = await scanGlobalMarket(selected.country, selected.exchange, 10);
      setPicks(Array.isArray(result.recommendations) ? result.recommendations : []);
      setDeepResults(Array.isArray(result.deepResults) ? result.deepResults : []);
      setStatus(result.status || '');
      setMeta({
        discovered: Number(result.universeDiscovered || 0),
        screened: Number(result.universeScreened || 0),
        deep: Number(result.deepAnalyzed || 0),
        coverage: Number(result.screeningCoveragePct || 0),
      });
    } catch (err) {
      setPicks([]);
      setDeepResults([]);
      setError(err instanceof Error ? err.message.slice(0, 320) : 'Kiasha market scan is unavailable.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { setLoading(true); void load(); }, [load]));

  const open = (item: GlobalAnalysis) => {
    if (!selection || !item.ticker) return;
    router.push({ pathname: '/stock/[code]', params: {
      code: item.ticker,
      country: item.country || selection.country,
      exchange: item.exchange || selection.exchange,
      currency: item.currency || selection.currency,
      name: item.name || item.ticker,
      isin: item.isin || '',
      lei: item.lei || '',
    }} as never);
  };

  const blocked = deepResults.filter((x) => x.evidence?.status === 'BLOCK').length;
  const warned = deepResults.filter((x) => x.evidence?.status === 'WARN').length;
  const passed = deepResults.filter((x) => x.evidence?.status === 'PASS').length;

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
    <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(); }} tintColor={Brand.primary} />} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.maxWidth}>
        <View style={styles.header}><View style={{ flex: 1 }}><Text style={[styles.title, { color: colors.text }]}>Kiasha Global</Text><Text style={[styles.subtitle, { color: colors.textSecondary }]}>Market selection, deep analysis and evidence-gated ranking</Text></View><Pressable onPress={() => router.push('/global')} style={[styles.marketButton, { borderColor: Brand.primary }]}><Text style={styles.marketButtonText}>Change market</Text></Pressable></View>

        <View style={[styles.hero, { backgroundColor: colors.backgroundElement }]}>
          <Text style={[styles.heroEyebrow, { color: Brand.primary }]}>ACTIVE MARKET</Text>
          <Text style={[styles.heroMarket, { color: colors.text }]}>{selection ? `${selection.countryName} • ${selection.exchangeLabel}` : 'Loading…'}</Text>
          <Text style={[styles.heroText, { color: colors.textSecondary }]}>Kiasha does not pick from raw price momentum alone. The scanner first screens tradability, then runs Fundamental, Risk, Forecast and Comparison agents. Evidence/Verification must PASS before a new BUY candidate can be promoted.</Text>
          <View style={styles.badges}><View style={[styles.badge, { backgroundColor: colors.backgroundSelected }]}><Text style={[styles.badgeText, { color: colors.text }]}>4 core agents</Text></View><View style={[styles.badge, { backgroundColor: colors.backgroundSelected }]}><Text style={[styles.badgeText, { color: colors.text }]}>Evidence gate</Text></View><View style={[styles.badge, { backgroundColor: colors.backgroundSelected }]}><Text style={[styles.badgeText, { color: colors.text }]}>Portfolio agent next</Text></View></View>
        </View>

        {loading ? <ActivityIndicator color={Brand.primary} style={{ marginTop: 36 }} /> : error ? <View style={[styles.empty, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.emptyTitle, { color: colors.text }]}>Scan unavailable</Text><Text style={[styles.emptyText, { color: colors.textSecondary }]}>{error}</Text></View> : <>
          <View style={styles.metrics}><View style={[styles.metric, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.metricValue, { color: colors.text }]}>{meta.discovered || '—'}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>discovered</Text></View><View style={[styles.metric, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.metricValue, { color: colors.text }]}>{meta.deep || deepResults.length || '—'}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>deep analyzed</Text></View><View style={[styles.metric, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.metricValue, { color: colors.text }]}>{picks.length}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>qualified BUY</Text></View></View>

          <View style={[styles.evidenceStrip, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.stripTitle, { color: colors.text }]}>Evidence gate</Text><Text style={[styles.stripText, { color: Brand.positive }]}>PASS {passed}</Text><Text style={[styles.stripText, { color: Brand.warning }]}>WARN {warned}</Text><Text style={[styles.stripText, { color: Brand.negative }]}>BLOCK {blocked}</Text></View>

          <View style={styles.sectionRow}><Text style={[styles.sectionTitle, { color: colors.text }]}>Kiasha picks</Text><Text style={[styles.sectionMeta, { color: colors.textSecondary }]}>{status || 'scan complete'}</Text></View>
          {picks.length ? picks.map((pick, index) => {
            const c = tone(pick.call, colors.textSecondary);
            const signals = Array.isArray(pick.signals) ? pick.signals : [];
            return <Pressable key={`${pick.ticker}-${index}`} onPress={() => open(pick)} style={[styles.pick, { backgroundColor: colors.backgroundElement }]}>
              <View style={styles.pickTop}><View style={[styles.rank, { backgroundColor: Brand.primary }]}><Text style={styles.rankText}>#{index + 1}</Text></View><View style={{ flex: 1 }}><Text style={[styles.ticker, { color: colors.text }]}>{pick.ticker}</Text><Text numberOfLines={1} style={[styles.name, { color: colors.textSecondary }]}>{pick.name}</Text></View><View style={{ alignItems: 'flex-end' }}><Text style={[styles.call, { color: c }]}>{pick.call}</Text><Text style={[styles.conf, { color: colors.textSecondary }]}>{pct(pick.confidence)} confidence</Text></View></View>
              <View style={styles.agentRow}>{signals.map((signal) => <View key={signal.agent} style={[styles.agentChip, { borderColor: colors.backgroundSelected }]}><Text style={[styles.agentChipText, { color: signal.vote >= .25 ? Brand.positive : signal.vote <= -.25 ? Brand.negative : colors.textSecondary }]}>{signal.agent} {signal.vote >= 0 ? '+' : ''}{Number(signal.vote || 0).toFixed(2)}</Text></View>)}</View>
              <Text style={[styles.pickMeta, { color: colors.textSecondary }]}>Score {pick.score == null ? '—' : pick.score.toFixed(3)} • Evidence {pick.evidence?.status || '—'} • tap for full analysis</Text>
            </Pressable>;
          }) : <View style={[styles.empty, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.emptyTitle, { color: colors.text }]}>No qualified BUY candidates</Text><Text style={[styles.emptyText, { color: colors.textSecondary }]}>This is a valid result. Kiasha will not fill a Top 10 list with weaker names when evidence or confidence is insufficient.</Text></View>}

          <View style={[styles.coverage, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.coverageTitle, { color: colors.text }]}>Market coverage</Text><Text style={[styles.coverageText, { color: colors.textSecondary }]}>Universe screened: {meta.screened || '—'} • screening coverage: {meta.coverage ? `${meta.coverage.toFixed(1)}%` : '—'} • deep analyses: {meta.deep || deepResults.length}. Pull down to run again.</Text></View>
        </>}

        <View style={[styles.portfolioCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.portfolioTitle, { color: colors.text }]}>Next: Portfolio Agent</Text><Text style={[styles.portfolioText, { color: colors.textSecondary }]}>Kiasha ranks qualified ideas inside one market. Portfolio Agent can then combine candidates across one or several countries using capital, risk tolerance, FX, cash reserve and concentration limits.</Text><Pressable onPress={() => router.push('/portfolio')} style={[styles.action, { backgroundColor: Brand.primary }]}><Text style={styles.actionText}>Open Portfolio Agent</Text></Pressable></View>

        <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>BIAP Global is research and decision support. Missing or stale evidence can force NO_RECOMMENDATION. Live broker execution remains separate and disabled until the execution/compliance gates are implemented.</Text>
      </View>
    </ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 }, content: { paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.six }, maxWidth: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingTop: Spacing.four, paddingBottom: Spacing.three }, title: { fontFamily: Fonts.sans, fontSize: 26, fontWeight: '900' }, subtitle: { fontFamily: Fonts.sans, fontSize: 10.5, marginTop: 3 }, marketButton: { borderWidth: 1, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 8 }, marketButtonText: { color: Brand.primary, fontFamily: Fonts.sans, fontSize: 10, fontWeight: '900' },
  hero: { borderRadius: Radius.lg, padding: Spacing.four }, heroEyebrow: { fontFamily: Fonts.mono, fontSize: 9, fontWeight: '900' }, heroMarket: { fontFamily: Fonts.sans, fontSize: 20, fontWeight: '900', marginTop: 6 }, heroText: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 17, marginTop: 7 }, badges: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 12 }, badge: { borderRadius: 16, paddingHorizontal: 9, paddingVertical: 6 }, badgeText: { fontFamily: Fonts.sans, fontSize: 9, fontWeight: '800' },
  metrics: { flexDirection: 'row', gap: 8, marginTop: 10 }, metric: { flex: 1, borderRadius: Radius.md, paddingVertical: 14, alignItems: 'center' }, metricValue: { fontFamily: Fonts.mono, fontSize: 17, fontWeight: '900' }, metricLabel: { fontFamily: Fonts.sans, fontSize: 8.5, marginTop: 3 },
  evidenceStrip: { flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: Radius.md, padding: 12, marginTop: 10 }, stripTitle: { fontFamily: Fonts.sans, fontSize: 10.5, fontWeight: '900', flex: 1 }, stripText: { fontFamily: Fonts.mono, fontSize: 9, fontWeight: '900' },
  sectionRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 20, marginBottom: 8 }, sectionTitle: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '900' }, sectionMeta: { fontFamily: Fonts.mono, fontSize: 8.5 },
  pick: { borderRadius: Radius.lg, padding: Spacing.three, marginBottom: 8 }, pickTop: { flexDirection: 'row', alignItems: 'center', gap: 10 }, rank: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' }, rankText: { color: '#fff', fontFamily: Fonts.mono, fontSize: 9, fontWeight: '900' }, ticker: { fontFamily: Fonts.mono, fontSize: 15, fontWeight: '900' }, name: { fontFamily: Fonts.sans, fontSize: 9.5, marginTop: 2 }, call: { fontFamily: Fonts.mono, fontSize: 8.5, fontWeight: '900' }, conf: { fontFamily: Fonts.mono, fontSize: 8, marginTop: 3 }, agentRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 5, marginTop: 10 }, agentChip: { borderWidth: 1, borderRadius: 14, paddingHorizontal: 7, paddingVertical: 4 }, agentChipText: { fontFamily: Fonts.mono, fontSize: 7.5, fontWeight: '800' }, pickMeta: { fontFamily: Fonts.mono, fontSize: 8.5, marginTop: 9 },
  empty: { borderRadius: Radius.lg, padding: Spacing.four, marginTop: 12 }, emptyTitle: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900' }, emptyText: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 17, marginTop: 5 }, coverage: { borderRadius: Radius.lg, padding: Spacing.three, marginTop: 12 }, coverageTitle: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '900' }, coverageText: { fontFamily: Fonts.sans, fontSize: 9.5, lineHeight: 15, marginTop: 4 },
  portfolioCard: { borderRadius: Radius.lg, padding: Spacing.four, marginTop: 18 }, portfolioTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900' }, portfolioText: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 17, marginTop: 6 }, action: { minHeight: 46, borderRadius: Radius.md, alignItems: 'center', justifyContent: 'center', marginTop: 12 }, actionText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 11, fontWeight: '900' }, disclaimer: { fontFamily: Fonts.sans, fontSize: 9.5, lineHeight: 15, textAlign: 'center', marginTop: 22 },
});