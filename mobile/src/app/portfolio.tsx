import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { buildGlobalPortfolio, GlobalInstrument, GlobalPortfolioResponse, scanGlobalMarket } from '@/lib/global-api';
import { getGlobalMarketSelection, GlobalMarketSelection } from '@/lib/global-market-selection';

type Risk = 'low' | 'medium' | 'high';

function num(value: number | undefined | null, digits = 2) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return Number(value).toLocaleString('en-US', { maximumFractionDigits: digits });
}

export default function GlobalPortfolioScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [selection, setSelection] = useState<GlobalMarketSelection | null>(null);
  const [capital, setCapital] = useState('50000');
  const [baseCurrency, setBaseCurrency] = useState('EUR');
  const [risk, setRisk] = useState<Risk>('medium');
  const [horizon, setHorizon] = useState('5y');
  const [maxPositions, setMaxPositions] = useState('10');
  const [cashReserve, setCashReserve] = useState('15');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<GlobalPortfolioResponse | null>(null);
  const [candidateCount, setCandidateCount] = useState(0);

  useFocusEffect(useCallback(() => {
    getGlobalMarketSelection().then(setSelection);
  }, []));

  const build = async () => {
    if (!selection) return;
    const amount = Number(capital.replace(/,/g, ''));
    const positions = Math.max(1, Math.min(30, Number(maxPositions) || 10));
    const reserve = Math.max(0, Math.min(80, Number(cashReserve) || 0));
    if (!Number.isFinite(amount) || amount <= 0) { setError('Enter a positive capital amount.'); return; }
    if (!/^[A-Za-z]{3}$/.test(baseCurrency.trim())) { setError('Base currency must be a 3-letter code such as EUR, USD or NOK.'); return; }
    setLoading(true); setError(''); setResult(null); setCandidateCount(0);
    try {
      const scan = await scanGlobalMarket(selection.country, selection.exchange, Math.max(positions, 10));
      const candidates = (scan.recommendations || []).filter((item) => item.ticker).map<GlobalInstrument>((item) => ({
        country: item.country || selection.country,
        exchange: item.exchange || selection.exchange,
        currency: item.currency || selection.currency,
        ticker: item.ticker || '',
        name: item.name || item.ticker || '',
        isin: item.isin || null,
        lei: item.lei || null,
      }));
      setCandidateCount(candidates.length);
      if (!candidates.length) {
        setError('No evidence-qualified BUY candidates are available for this market, so Portfolio Agent will not manufacture a portfolio.');
        return;
      }
      const portfolio = await buildGlobalPortfolio({
        capital: amount,
        baseCurrency: baseCurrency.trim().toUpperCase(),
        riskTolerance: risk,
        horizon: horizon.trim() || '5y',
        allowedCountries: [selection.country],
        allowedExchanges: [selection.exchange],
        maxPositionPct: Math.min(25, Math.max(2, 100 / Math.max(positions, 1) * 1.5)),
        maxCountryPct: 100,
        maxSectorPct: 35,
        minCashReservePct: reserve,
        maxPositions: positions,
      }, candidates);
      setResult(portfolio);
    } catch (err) {
      setError(err instanceof Error ? err.message.slice(0, 360) : 'Portfolio Agent is unavailable.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const proposal = result?.proposal;
  const allocations = proposal?.allocations || [];

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void build(); }} tintColor={Brand.primary} />} contentContainerStyle={styles.content}>
    <View style={styles.maxWidth}>
      <View style={styles.header}><View style={{ flex: 1 }}><Text style={[styles.title, { color: colors.text }]}>Portfolio Agent</Text><Text style={[styles.subtitle, { color: colors.textSecondary }]}>Evidence-qualified portfolio construction with FX, risk and concentration controls</Text></View><Pressable onPress={() => router.push('/global')} style={[styles.marketButton, { borderColor: Brand.primary }]}><Text style={styles.marketButtonText}>Change market</Text></Pressable></View>

      <View style={[styles.marketCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.marketEyebrow, { color: Brand.primary }]}>CURRENT SCOPE</Text><Text style={[styles.marketTitle, { color: colors.text }]}>{selection ? `${selection.countryName} • ${selection.exchangeLabel}` : 'Loading…'}</Text><Text style={[styles.marketText, { color: colors.textSecondary }]}>This first full-parity build constructs from the selected market. The same Portfolio Agent API already supports instruments from multiple countries; multi-market scope selection will be layered on this screen after single-market validation.</Text></View>

      <Text style={[styles.sectionTitle, { color: colors.text }]}>Investor profile</Text>
      <View style={[styles.form, { backgroundColor: colors.backgroundElement }]}>
        <View style={styles.twoCols}><View style={styles.field}><Text style={[styles.label, { color: colors.textSecondary }]}>Capital</Text><TextInput value={capital} onChangeText={setCapital} keyboardType="decimal-pad" style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected }]} /></View><View style={styles.field}><Text style={[styles.label, { color: colors.textSecondary }]}>Base currency</Text><TextInput value={baseCurrency} onChangeText={setBaseCurrency} autoCapitalize="characters" maxLength={3} style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected }]} /></View></View>
        <Text style={[styles.label, { color: colors.textSecondary }]}>Risk tolerance</Text><View style={styles.segment}>{(['low', 'medium', 'high'] as Risk[]).map((item) => <Pressable key={item} onPress={() => setRisk(item)} style={[styles.segmentButton, { backgroundColor: risk === item ? Brand.primary : colors.backgroundSelected }]}><Text style={[styles.segmentText, { color: risk === item ? '#fff' : colors.text }]}>{item}</Text></Pressable>)}</View>
        <View style={styles.twoCols}><View style={styles.field}><Text style={[styles.label, { color: colors.textSecondary }]}>Horizon</Text><TextInput value={horizon} onChangeText={setHorizon} placeholder="5y" placeholderTextColor={colors.textSecondary} style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected }]} /></View><View style={styles.field}><Text style={[styles.label, { color: colors.textSecondary }]}>Max positions</Text><TextInput value={maxPositions} onChangeText={setMaxPositions} keyboardType="number-pad" style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected }]} /></View></View>
        <Text style={[styles.label, { color: colors.textSecondary }]}>Minimum cash reserve (%)</Text><TextInput value={cashReserve} onChangeText={setCashReserve} keyboardType="decimal-pad" style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected }]} />
      </View>

      <Pressable disabled={loading || !selection} onPress={() => { void build(); }} style={[styles.buildButton, { backgroundColor: Brand.primary, opacity: loading ? .65 : 1 }]}>{loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buildText}>Scan market and build paper portfolio</Text>}</Pressable>
      {error ? <View style={[styles.errorBox, { borderColor: Brand.warning }]}><Text style={[styles.errorText, { color: colors.textSecondary }]}>{error}</Text></View> : null}

      {proposal ? <>
        <View style={[styles.summary, { backgroundColor: colors.backgroundElement }]}><View style={styles.summaryTop}><View><Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>Proposal status</Text><Text style={[styles.summaryStatus, { color: proposal.status === 'NO_RECOMMENDATION' ? Brand.warning : Brand.positive }]}>{proposal.status || '—'}</Text></View><View style={{ alignItems: 'flex-end' }}><Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>Qualified inputs</Text><Text style={[styles.summaryNumber, { color: colors.text }]}>{candidateCount}</Text></View></View><View style={styles.summaryMetrics}><View><Text style={[styles.summaryValue, { color: colors.text }]}>{num(proposal.invested_pct)}%</Text><Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>invested</Text></View><View><Text style={[styles.summaryValue, { color: colors.text }]}>{num(proposal.cash_pct)}%</Text><Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>cash</Text></View><View><Text style={[styles.summaryValue, { color: colors.text }]}>{allocations.length}</Text><Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>positions</Text></View></View>{proposal.reasoning ? <Text style={[styles.reasoning, { color: colors.textSecondary }]}>{proposal.reasoning}</Text> : null}</View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>Proposed allocations</Text>
        {allocations.length ? allocations.map((item, index) => <View key={`${item.identity}-${index}`} style={[styles.allocation, { backgroundColor: colors.backgroundElement }]}><View style={styles.allocationTop}><View><Text style={[styles.allocationTicker, { color: colors.text }]}>#{index + 1} {item.ticker}</Text><Text style={[styles.allocationMeta, { color: colors.textSecondary }]}>{item.country} • {item.exchange} • {item.currency}</Text></View><View style={{ alignItems: 'flex-end' }}><Text style={[styles.weight, { color: Brand.primary }]}>{num(item.weight_pct)}%</Text><Text style={[styles.allocationMeta, { color: colors.textSecondary }]}>{num(item.quantity, 0)} shares</Text></View></View><View style={styles.allocationMetrics}><Text style={[styles.allocationMetric, { color: colors.textSecondary }]}>Amount <Text style={{ color: colors.text }}>{num(item.amount_base_currency)} {baseCurrency.toUpperCase()}</Text></Text><Text style={[styles.allocationMetric, { color: colors.textSecondary }]}>Score <Text style={{ color: colors.text }}>{num(item.score, 3)}</Text></Text><Text style={[styles.allocationMetric, { color: colors.textSecondary }]}>Confidence <Text style={{ color: colors.text }}>{item.confidence == null ? '—' : `${Math.round(item.confidence * 100)}%`}</Text></Text></View><Text style={[styles.reasoning, { color: colors.textSecondary }]}>{item.reasoning}</Text></View>) : <View style={[styles.empty, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.emptyText, { color: colors.textSecondary }]}>No allocation cleared all Portfolio Agent gates.</Text></View>}

        {result?.fxErrors && Object.keys(result.fxErrors).length ? <View style={[styles.errorBox, { borderColor: Brand.warning }]}><Text style={[styles.errorText, { color: colors.textSecondary }]}>FX unavailable: {Object.entries(result.fxErrors).map(([k, v]) => `${k}: ${v}`).join(' • ')}</Text></View> : null}
      </> : null}

      <View style={[styles.notice, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.noticeTitle, { color: colors.text }]}>Paper first</Text><Text style={[styles.noticeText, { color: colors.textSecondary }]}>Portfolio Agent proposes weights and quantities only. It does not submit live orders. Live brokerage is a separate adapter and remains disabled until broker permissions, costs, execution risk, compliance and validation are ready.</Text></View>
    </View>
  </ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 }, content: { paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.six }, maxWidth: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingTop: Spacing.four, paddingBottom: Spacing.three }, title: { fontFamily: Fonts.sans, fontSize: 25, fontWeight: '900' }, subtitle: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 16, marginTop: 3 }, marketButton: { borderWidth: 1, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 8 }, marketButtonText: { color: Brand.primary, fontFamily: Fonts.sans, fontSize: 10, fontWeight: '900' },
  marketCard: { borderRadius: Radius.lg, padding: Spacing.four }, marketEyebrow: { fontFamily: Fonts.mono, fontSize: 8.5, fontWeight: '900' }, marketTitle: { fontFamily: Fonts.sans, fontSize: 17, fontWeight: '900', marginTop: 5 }, marketText: { fontFamily: Fonts.sans, fontSize: 9.5, lineHeight: 15, marginTop: 5 }, sectionTitle: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '900', marginTop: 20, marginBottom: 8 },
  form: { borderRadius: Radius.lg, padding: Spacing.three }, twoCols: { flexDirection: 'row', gap: 8 }, field: { flex: 1 }, label: { fontFamily: Fonts.sans, fontSize: 9, marginTop: 8, marginBottom: 4 }, input: { borderWidth: 1, borderRadius: Radius.md, paddingHorizontal: 11, paddingVertical: 10, fontFamily: Fonts.mono, fontSize: 12 }, segment: { flexDirection: 'row', gap: 6 }, segmentButton: { flex: 1, minHeight: 38, borderRadius: 18, alignItems: 'center', justifyContent: 'center' }, segmentText: { fontFamily: Fonts.sans, fontSize: 10, fontWeight: '900', textTransform: 'capitalize' }, buildButton: { minHeight: 50, borderRadius: Radius.md, alignItems: 'center', justifyContent: 'center', marginTop: 12 }, buildText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 11.5, fontWeight: '900' },
  errorBox: { borderWidth: 1, borderRadius: Radius.md, padding: 11, marginTop: 10 }, errorText: { fontFamily: Fonts.sans, fontSize: 9.5, lineHeight: 15 }, summary: { borderRadius: Radius.lg, padding: Spacing.four, marginTop: 14 }, summaryTop: { flexDirection: 'row', justifyContent: 'space-between' }, summaryLabel: { fontFamily: Fonts.sans, fontSize: 8.5 }, summaryStatus: { fontFamily: Fonts.mono, fontSize: 12, fontWeight: '900', marginTop: 3 }, summaryNumber: { fontFamily: Fonts.mono, fontSize: 17, fontWeight: '900', marginTop: 2 }, summaryMetrics: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 16 }, summaryValue: { fontFamily: Fonts.mono, fontSize: 17, fontWeight: '900' }, reasoning: { fontFamily: Fonts.sans, fontSize: 9, lineHeight: 14, marginTop: 8 },
  allocation: { borderRadius: Radius.lg, padding: Spacing.three, marginBottom: 8 }, allocationTop: { flexDirection: 'row', justifyContent: 'space-between' }, allocationTicker: { fontFamily: Fonts.mono, fontSize: 14, fontWeight: '900' }, allocationMeta: { fontFamily: Fonts.mono, fontSize: 8.5, marginTop: 3 }, weight: { fontFamily: Fonts.mono, fontSize: 15, fontWeight: '900' }, allocationMetrics: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 10 }, allocationMetric: { fontFamily: Fonts.mono, fontSize: 8.5 }, empty: { borderRadius: Radius.lg, padding: Spacing.four }, emptyText: { fontFamily: Fonts.sans, fontSize: 10, textAlign: 'center' }, notice: { borderRadius: Radius.lg, padding: Spacing.four, marginTop: 18 }, noticeTitle: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900' }, noticeText: { fontFamily: Fonts.sans, fontSize: 9.5, lineHeight: 15, marginTop: 5 },
});