import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { analyzeGlobalInstrument, GlobalAnalysis, GlobalAgentSignal, GlobalInstrument } from '@/lib/global-api';
import { getGlobalMarketSelection } from '@/lib/global-market-selection';

function n(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return Number(value).toLocaleString('en-US', { maximumFractionDigits: digits });
}

function priceN(value: number | null | undefined) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  const x = Math.abs(Number(value));
  const digits = x >= 1 ? 2 : x >= 0.1 ? 3 : x >= 0.01 ? 4 : x >= 0.001 ? 5 : 6;
  return Number(value).toLocaleString('en-US', { maximumFractionDigits: digits });
}

function pct(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return `${Number(value).toLocaleString('en-US', { maximumFractionDigits: digits })}%`;
}

function decisionColor(call: string | undefined, secondary: string) {
  if (call === 'BUY_CANDIDATE') return Brand.positive;
  if (call === 'HOLD_OR_WATCH') return Brand.warning;
  if (call === 'AVOID_OR_REVIEW') return Brand.negative;
  return secondary;
}

function signalColor(signal: GlobalAgentSignal, secondary: string) {
  if (signal.vote >= 0.25) return Brand.positive;
  if (signal.vote <= -0.25) return Brand.negative;
  return secondary;
}

function Metric({ label, value, colors }: { label: string; value: string; colors: typeof Colors.light | typeof Colors.dark }) {
  return <View style={[styles.metric, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.metricValue, { color: colors.text }]}>{value}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>{label}</Text></View>;
}

function AgentCard({ signal, colors }: { signal: GlobalAgentSignal; colors: typeof Colors.light | typeof Colors.dark }) {
  const tone = signalColor(signal, colors.textSecondary);
  const name = signal.agent.charAt(0).toUpperCase() + signal.agent.slice(1);
  return <View style={[styles.agentCard, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
    <View style={styles.rowBetween}><Text style={[styles.agentName, { color: colors.text }]}>{name} Agent</Text><Text style={[styles.agentVote, { color: tone }]}>{signal.vote >= 0 ? '+' : ''}{n(signal.vote, 3)}</Text></View>
    <Text style={[styles.agentConfidence, { color: colors.textSecondary }]}>Confidence {Math.round((signal.confidence || 0) * 100)}%</Text>
    <Text style={[styles.agentReason, { color: colors.textSecondary }]}>{signal.reasoning || 'No verified signal.'}</Text>
  </View>;
}

export default function GlobalStockDetailScreen() {
  const params = useLocalSearchParams<{ code?: string; country?: string; exchange?: string; currency?: string; name?: string; isin?: string; lei?: string }>();
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [analysis, setAnalysis] = useState<GlobalAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const ticker = String(params.code || '').trim();
    if (!ticker) { setError('Ticker is missing.'); setLoading(false); return; }
    try {
      setError('');
      const selected = await getGlobalMarketSelection();
      const instrument: GlobalInstrument = {
        country: String(params.country || selected.country).toUpperCase(),
        exchange: String(params.exchange || selected.exchange),
        currency: String(params.currency || selected.currency).toUpperCase(),
        ticker,
        name: String(params.name || ticker),
        isin: params.isin ? String(params.isin) : null,
        lei: params.lei ? String(params.lei) : null,
      };
      setAnalysis(await analyzeGlobalInstrument(instrument));
    } catch (err) {
      setAnalysis(null);
      setError(err instanceof Error ? err.message.slice(0, 320) : 'Analysis is unavailable.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [params.code, params.country, params.exchange, params.currency, params.name, params.isin, params.lei]);

  useEffect(() => { setLoading(true); void load(); }, [load]);
  const company = analysis?.company;
  const signals = Array.isArray(analysis?.signals) ? analysis!.signals! : [];
  const sources = Array.isArray(company?.sources) ? company!.sources! : [];
  const callTone = decisionColor(analysis?.call, colors.textSecondary);
  const price = company?.price;
  const priceTimestamp = company?.price_observed_at;
  const lowPriceWarning = price != null && Number.isFinite(Number(price)) && Number(price) > 0 && Number(price) < 0.1;
  const extremeVolatilityWarning = company?.volatility_annualized_pct != null && Number(company.volatility_annualized_pct) >= 250;
  const marketRows = useMemo(() => [
    ['Price', price == null ? '—' : `${priceN(price)} ${analysis?.currency || ''}`],
    ['52-week range', company?.price_52w_low == null || company?.price_52w_high == null ? '—' : `${priceN(company.price_52w_low)} – ${priceN(company.price_52w_high)}`],
    ['1M / 3M / 6M', `${pct(company?.return_1m_pct)} / ${pct(company?.return_3m_pct)} / ${pct(company?.return_6m_pct)}`],
    ['Annualized volatility', pct(company?.volatility_annualized_pct)],
    ['Max drawdown', pct(company?.max_drawdown_pct)],
    ['Volume / 30d avg.', `${n(company?.volume_today, 0)} / ${n(company?.avg_volume_30d, 0)}`],
  ], [company, price, analysis?.currency]);
  const valuationRows = useMemo(() => [
    ['Market cap', n(company?.market_cap, 0)], ['P/E', n(company?.pe)], ['P/B', n(company?.pb)], ['EV/EBITDA', n(company?.ev_ebitda)], ['Peer / sector P/E', n(company?.sector_pe)],
  ], [company]);
  const financialRows = useMemo(() => [
    ['Revenue', n(company?.revenue, 0)], ['Revenue YoY', pct(company?.revenue_yoy_pct)], ['Net income', n(company?.net_income, 0)], ['Net margin', pct(company?.net_margin_pct)],
    ['Assets', n(company?.total_assets, 0)], ['Liabilities', n(company?.total_liabilities, 0)], ['Equity', n(company?.total_equity, 0)], ['Operating cash flow', n(company?.operating_cash_flow, 0)], ['Free cash flow', n(company?.free_cash_flow, 0)], ['Debt', n(company?.total_debt, 0)],
  ], [company]);

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(); }} tintColor={Brand.primary} />} contentContainerStyle={styles.content}>
    <View style={styles.maxWidth}>
      <View style={styles.header}><Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.backText, { color: colors.text }]}>← Back</Text></Pressable><Text style={[styles.headerMeta, { color: colors.textSecondary }]}>Global stock analysis</Text></View>
      {loading ? <ActivityIndicator color={Brand.primary} style={{ marginTop: 50 }} /> : error ? <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.cardTitle, { color: colors.text }]}>Analysis unavailable</Text><Text style={[styles.body, { color: colors.textSecondary }]}>{error}</Text></View> : analysis ? <>
        <View style={[styles.hero, { backgroundColor: colors.backgroundElement }]}>
          <View style={styles.rowBetween}><View style={{ flex: 1 }}><Text style={[styles.ticker, { color: colors.text }]}>{analysis.ticker}</Text><Text style={[styles.companyName, { color: colors.textSecondary }]}>{analysis.name}</Text><Text style={[styles.identity, { color: colors.textSecondary }]}>{analysis.country} • {analysis.exchange} • {analysis.mic || 'MIC n/a'} • {analysis.currency}</Text></View><View style={[styles.callPill, { borderColor: callTone }]}><Text style={[styles.callText, { color: callTone }]}>{analysis.call}</Text></View></View>
          <View style={styles.priceRow}><Text style={[styles.price, { color: colors.text }]}>{price == null ? '—' : priceN(price)}</Text><Text style={[styles.currency, { color: colors.textSecondary }]}>{analysis.currency}</Text></View>
          <Text style={[styles.timestamp, { color: colors.textSecondary }]}>{priceTimestamp ? `Price observed ${priceTimestamp}` : 'Verified price timestamp unavailable'}</Text>
        </View>

        {(lowPriceWarning || extremeVolatilityWarning) ? <View style={[styles.caution, { backgroundColor: colors.backgroundElement, borderColor: Brand.warning }]}><Text style={[styles.cautionTitle, { color: Brand.warning }]}>Market-data caution</Text><Text style={[styles.body, { color: colors.textSecondary }]}>{lowPriceWarning ? 'This is a very low-priced instrument; BIAP preserves extra decimal precision instead of rounding it to zero. ' : ''}{extremeVolatilityWarning ? 'Observed volatility is extreme, so risk metrics should be interpreted with extra caution and remain subject to the Evidence gate.' : ''}</Text></View> : null}

        <View style={styles.metrics}><Metric label="Kiasha score" value={analysis.score == null ? '—' : n(analysis.score, 3)} colors={colors}/><Metric label="Decision confidence" value={analysis.confidence == null ? '—' : `${Math.round(analysis.confidence * 100)}%`} colors={colors}/><Metric label="Evidence" value={analysis.evidence?.status || '—'} colors={colors}/></View>

        <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.cardTitle, { color: colors.text }]}>Kiasha decision</Text><Text style={[styles.body, { color: colors.textSecondary }]}>Kiasha combines the six scoring agent signals after provider normalization, then applies the Evidence/Verification gate. A new BUY candidate is allowed only when evidence status is PASS and confidence clears the threshold.</Text></View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>Core analysis agents</Text>
        {signals.map((signal) => <AgentCard key={signal.agent} signal={signal} colors={colors} />)}

        <View style={[styles.agentCard, { backgroundColor: colors.backgroundElement, borderColor: analysis.evidence?.status === 'PASS' ? Brand.positive : analysis.evidence?.status === 'WARN' ? Brand.warning : Brand.negative }]}>
          <View style={styles.rowBetween}><Text style={[styles.agentName, { color: colors.text }]}>Evidence / Verification Agent</Text><Text style={[styles.agentVote, { color: analysis.evidence?.status === 'PASS' ? Brand.positive : analysis.evidence?.status === 'WARN' ? Brand.warning : Brand.negative }]}>{analysis.evidence?.status || '—'}</Text></View>
          <Text style={[styles.agentConfidence, { color: colors.textSecondary }]}>Coverage {analysis.evidence?.coverage == null ? '—' : `${Math.round(analysis.evidence.coverage * 100)}%`} • Freshness {analysis.evidence?.freshness_score == null ? '—' : n(analysis.evidence.freshness_score, 2)}</Text>
          <Text style={[styles.agentReason, { color: colors.textSecondary }]}>{analysis.evidence?.reasoning || 'Evidence assessment unavailable.'}</Text>
          {analysis.evidence?.missing_critical?.length ? <Text style={[styles.warning, { color: Brand.warning }]}>Missing critical: {analysis.evidence.missing_critical.join(', ')}</Text> : null}
        </View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>Market & risk</Text>
        <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>{marketRows.map(([label, value]) => <View key={label} style={[styles.dataRow, { borderBottomColor: colors.backgroundSelected }]}><Text style={[styles.dataLabel, { color: colors.textSecondary }]}>{label}</Text><Text style={[styles.dataValue, { color: colors.text }]}>{value}</Text></View>)}</View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>Valuation</Text>
        <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>{valuationRows.map(([label, value]) => <View key={label} style={[styles.dataRow, { borderBottomColor: colors.backgroundSelected }]}><Text style={[styles.dataLabel, { color: colors.textSecondary }]}>{label}</Text><Text style={[styles.dataValue, { color: colors.text }]}>{value}</Text></View>)}</View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>Fundamentals</Text>
        <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>{financialRows.map(([label, value]) => <View key={label} style={[styles.dataRow, { borderBottomColor: colors.backgroundSelected }]}><Text style={[styles.dataLabel, { color: colors.textSecondary }]}>{label}</Text><Text style={[styles.dataValue, { color: colors.text }]}>{value}</Text></View>)}</View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>Evidence sources</Text>
        <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>{sources.length ? sources.map((source, index) => <View key={`${source.provider}-${index}`} style={[styles.sourceRow, { borderBottomColor: colors.backgroundSelected }]}><Text style={[styles.sourceProvider, { color: colors.text }]}>{source.provider || 'source'}</Text><Text style={[styles.sourceMeta, { color: colors.textSecondary }]}>{source.source_type || 'evidence'} • quality {source.quality == null ? '—' : n(source.quality, 2)}{source.observed_at ? ` • ${source.observed_at}` : ''}</Text></View>) : <Text style={[styles.body, { color: colors.textSecondary }]}>No verified provenance records were returned. Evidence Agent should block a directional recommendation.</Text>}</View>

        <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.cardTitle, { color: colors.text }]}>Portfolio Agent</Text><Text style={[styles.body, { color: colors.textSecondary }]}>Portfolio construction is intentionally separate from single-stock analysis. Open the Portfolio tab to combine qualified candidates using capital, base currency, risk tolerance, concentration caps, FX and cash reserve.</Text><Pressable onPress={() => router.push('/portfolio')} style={[styles.action, { backgroundColor: Brand.primary }]}><Text style={styles.actionText}>Open Portfolio Agent</Text></Pressable></View>

        <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>No missing market or filing value is fabricated. NO_RECOMMENDATION is a valid result when sources are missing, stale, ambiguous or conflicting.</Text>
      </> : null}
    </View>
  </ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 }, content: { paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.six }, maxWidth: { width: '100%', maxWidth: MaxContentWidth, alignSelf: 'center' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: Spacing.three }, back: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 18 }, backText: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '700' }, headerMeta: { fontFamily: Fonts.sans, fontSize: 10.5 },
  hero: { borderRadius: Radius.lg, padding: Spacing.four }, rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }, ticker: { fontFamily: Fonts.mono, fontSize: 26, fontWeight: '900' }, companyName: { fontFamily: Fonts.sans, fontSize: 12, marginTop: 3 }, identity: { fontFamily: Fonts.mono, fontSize: 9, marginTop: 5 }, callPill: { borderWidth: 1, borderRadius: 20, paddingHorizontal: 10, paddingVertical: 6 }, callText: { fontFamily: Fonts.mono, fontSize: 8.5, fontWeight: '900' }, priceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 6, marginTop: 18 }, price: { fontFamily: Fonts.mono, fontSize: 31, fontWeight: '900' }, currency: { fontFamily: Fonts.mono, fontSize: 11 }, timestamp: { fontFamily: Fonts.mono, fontSize: 8.5, marginTop: 4 },
  caution: { borderWidth: 1, borderRadius: Radius.md, padding: Spacing.three, marginTop: 10 }, cautionTitle: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '900' },
  metrics: { flexDirection: 'row', gap: 8, marginTop: 10 }, metric: { flex: 1, borderRadius: Radius.md, paddingVertical: 14, paddingHorizontal: 8, alignItems: 'center' }, metricValue: { fontFamily: Fonts.mono, fontSize: 15, fontWeight: '900', textAlign: 'center' }, metricLabel: { fontFamily: Fonts.sans, fontSize: 8.5, marginTop: 4, textAlign: 'center' },
  sectionTitle: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '900', marginTop: 20, marginBottom: 8 }, card: { borderRadius: Radius.lg, padding: Spacing.three, marginTop: 10 }, cardTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900' }, body: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 17, marginTop: 5 },
  agentCard: { borderWidth: 1, borderRadius: Radius.lg, padding: Spacing.three, marginBottom: 8 }, agentName: { fontFamily: Fonts.sans, fontSize: 12.5, fontWeight: '900' }, agentVote: { fontFamily: Fonts.mono, fontSize: 12, fontWeight: '900' }, agentConfidence: { fontFamily: Fonts.mono, fontSize: 9, marginTop: 5 }, agentReason: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 17, marginTop: 6 }, warning: { fontFamily: Fonts.sans, fontSize: 9.5, lineHeight: 15, marginTop: 6 },
  dataRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 9, borderBottomWidth: StyleSheet.hairlineWidth }, dataLabel: { fontFamily: Fonts.sans, fontSize: 10, flex: 1 }, dataValue: { fontFamily: Fonts.mono, fontSize: 10, fontWeight: '800', flex: 1, textAlign: 'right' }, sourceRow: { paddingVertical: 9, borderBottomWidth: StyleSheet.hairlineWidth }, sourceProvider: { fontFamily: Fonts.mono, fontSize: 10, fontWeight: '900' }, sourceMeta: { fontFamily: Fonts.mono, fontSize: 8.5, marginTop: 3 },
  action: { minHeight: 46, borderRadius: Radius.md, alignItems: 'center', justifyContent: 'center', marginTop: 12 }, actionText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 11, fontWeight: '900' }, disclaimer: { fontFamily: Fonts.sans, fontSize: 9.5, lineHeight: 15, textAlign: 'center', marginTop: 22 },
});