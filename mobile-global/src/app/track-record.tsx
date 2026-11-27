import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing, type ThemeColors } from '@/constants/theme';
import {
  fetchAccuracyDecisions, fetchAccuracySummary, sessionGlobalStatus,
  type AgentResult, type GlobalAccuracyDecisions, type GlobalAccuracyPooled, type GlobalAccuracySummary,
} from '@/lib/global-api';
import { tr, type Lang, type StrKey } from '@/lib/agent-i18n';
import { agentFlags, HORIZONS, num, pct, pendingLine, pp, signedPct, sortMarkets, toFa } from '@/lib/agent-format';
import { useAgentLang } from '@/lib/agent-lang';
import { LevelChip, Loading, Row, Tag, Unavailable, rtl } from '@/components/agent-ui';

const HKEY: Record<number, StrKey> = { 1: 'horizon1m', 3: 'horizon3m', 6: 'horizon6m', 12: 'horizon12m' };

const spreadColor = (x: number | null | undefined) => (x != null && x < 0 ? Brand.negative : Brand.positive);

function PooledBlock({ p, title, big, lang, colors }: { p: GlobalAccuracyPooled; title: string; big: boolean; lang: Lang; colors: ThemeColors }) {
  const ci = p.spreadCi95Pp ? `${tr(lang, 'ci95')}: ${num(lang, p.spreadCi95Pp[0], 1)} … ${num(lang, p.spreadCi95Pp[1], 1)}` : '';
  return <View style={[st.card, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
    <Text style={[st.small, { color: colors.textSecondary }, rtl(lang)]}>{title}</Text>
    <View style={[st.kpis, lang === 'fa' && { flexDirection: 'row-reverse' }]}>
      <View style={st.kpi}><Text style={[big ? st.kpiBig : st.kpiMid, { color: colors.text }]}>{signedPct(lang, p.buy.meanReturnPct)}</Text><Text style={[st.small, { color: colors.textSecondary }]}>{tr(lang, 'buyMean')} · n={num(lang, p.buy.n, 0)}</Text></View>
      <View style={st.kpi}><Text style={[big ? st.kpiBig : st.kpiMid, { color: colors.text }]}>{signedPct(lang, p.sell.meanReturnPct)}</Text><Text style={[st.small, { color: colors.textSecondary }]}>{tr(lang, 'sellMean')} · n={num(lang, p.sell.n, 0)}</Text></View>
      <View style={st.kpi}><Text style={[big ? st.kpiBig : st.kpiMid, { color: spreadColor(p.spreadMeanPp) }]}>{pp(lang, p.spreadMeanPp)}</Text><Text style={[st.small, { color: colors.textSecondary }]}>{tr(lang, 'spread')}{ci ? `\n${ci}` : ''}</Text></View>
    </View>
    <Text style={[st.small, { color: colors.textSecondary }, rtl(lang)]}>{tr(lang, 'hitRate')}: BUY {pct(lang, p.buy.hitRate == null ? null : p.buy.hitRate * 100, 0)} · SELL {pct(lang, p.sell.hitRate == null ? null : p.sell.hitRate * 100, 0)}</Text>
  </View>;
}

export default function TrackRecordScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const { width } = useWindowDimensions();
  const wide = width >= 900;
  const [lang, setLang] = useAgentLang();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [horizon, setHorizon] = useState<number>(1);
  const [sum, setSum] = useState<AgentResult<GlobalAccuracySummary> | null>(null);
  const [market, setMarket] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [rows, setRows] = useState<GlobalAccuracyDecisions | null>(null);
  const [extra, setExtra] = useState<GlobalAccuracyDecisions['rows']>([]);
  const [worst, setWorst] = useState<GlobalAccuracyDecisions['rows']>([]);

  useEffect(() => { let alive = true; sessionGlobalStatus().then((s) => { if (alive) setEnabled(agentFlags(s).accuracy); }); return () => { alive = false; }; }, []);
  useEffect(() => { if (!enabled) return; setSum(null); fetchAccuracySummary(horizon).then(setSum); }, [enabled, horizon]);

  const matured = sum?.state === 'ok' && sum.data.horizon.status === 'MATURED';
  const loadRows = useCallback(async () => {
    if (!matured) { setRows(null); setWorst([]); return; }
    const best = await fetchAccuracyDecisions({ horizon, market, q: query, limit: 10, sort: 'edge_desc' });
    const bad = await fetchAccuracyDecisions({ horizon, market, q: query, limit: 10, sort: 'edge_asc' });
    setExtra([]);
    setRows(best.state === 'ok' ? best.data : null);
    setWorst(bad.state === 'ok' ? bad.data.rows : []);
  }, [matured, horizon, market, query]);
  useEffect(() => { const t = setTimeout(() => { void loadRows(); }, query ? 350 : 0); return () => clearTimeout(t); }, [loadRows, query]);

  const loadMore = async () => {
    const r = await fetchAccuracyDecisions({ horizon, market, q: query, limit: 20, offset: 10 + extra.length, sort: 'edge_desc' });
    if (r.state === 'ok') setExtra((x) => [...x, ...r.data.rows]);
  };
  const openStock = (r: GlobalAccuracyDecisions['rows'][number]) => router.push({ pathname: '/stock/[code]', params: { code: r.ticker, country: r.country, exchange: r.exchange, name: r.name || r.ticker } } as never);

  const header = <View style={st.header}>
    <View style={{ flexDirection: lang === 'fa' ? 'row-reverse' : 'row', alignItems: 'center', gap: 8 }}>
      <Text style={[st.title, { color: colors.text, flex: 1 }, rtl(lang)]}>{tr(lang, 'trackScreenTitle')}</Text>
      <Pressable onPress={() => setLang(lang === 'fa' ? 'en' : 'fa')} style={[st.lang, { borderColor: colors.backgroundSelected }]}><Text style={[st.small, { color: colors.textSecondary }]}>{tr(lang, 'language')}</Text></Pressable>
    </View>
    <Text style={[st.small, { color: colors.textSecondary }, rtl(lang)]}>{tr(lang, 'trackScreenSub')}</Text>
    <Text style={[st.small, { color: colors.textSecondary }, rtl(lang)]}>{tr(lang, 'advisory')}</Text>
  </View>;

  if (enabled === null) return <SafeAreaView style={[st.safe, { backgroundColor: colors.background }]}><View style={st.pad}><Loading lang={lang} colors={colors} /></View></SafeAreaView>;
  if (!enabled) return <SafeAreaView style={[st.safe, { backgroundColor: colors.background }]}><View style={st.pad}>{header}<Text style={[st.small, { color: colors.textSecondary }]}>—</Text></View></SafeAreaView>;

  const s = sum?.state === 'ok' ? sum.data : null;
  const left = <View style={wide ? { flex: 1 } : undefined}>
    {s ? <View style={[st.card, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
      <Text style={[st.body, { color: colors.text }, rtl(lang)]}>{s.cohortId} · <Text style={{ color: colors.textSecondary }}>{tr(lang, 'frozenCohort')}</Text></Text>
      <Text style={[st.small, { color: colors.textSecondary }, rtl(lang)]}>{tr(lang, 'decisionDate')}: {lang === 'fa' ? toFa(s.decisionDate) : s.decisionDate}</Text>
      <Text style={[st.small, { color: colors.textSecondary }, rtl(lang)]}>{tr(lang, 'returnBasis')}</Text>
      <Text style={[st.small, { color: colors.textSecondary, fontWeight: '800' }, rtl(lang)]}>{tr(lang, 'pastNotForecast')}</Text>
    </View> : null}
    <View style={[st.tabs, lang === 'fa' && { flexDirection: 'row-reverse' }]}>{HORIZONS.map((h) => <Pressable key={h} testID={`horizon-${h}`} onPress={() => { setHorizon(h); setMarket(null); }} style={[st.tab, { borderColor: h === horizon ? Brand.primary : colors.backgroundSelected, backgroundColor: h === horizon ? `${Brand.primary}22` : 'transparent' }]}><Text style={[st.tabText, { color: h === horizon ? Brand.primary : colors.textSecondary }]}>{tr(lang, HKEY[h])}</Text></Pressable>)}</View>
    {sum === null ? <Loading lang={lang} colors={colors} /> : null}
    {sum?.state === 'unavailable' ? <Unavailable lang={lang} colors={colors} onRetry={() => { setSum(null); void fetchAccuracySummary(horizon).then(setSum); }} /> : null}
    {s && s.horizon.status !== 'MATURED' ? <View testID="pending-card" style={[st.card, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}><LevelChip text={`${tr(lang, 'pending')} · ${tr(lang, 'due')} ${s.horizon.matures}`} tone="muted" /><Text style={[st.body, { color: colors.textSecondary }, rtl(lang)]}>{pendingLine(lang, s.horizon.matures)}</Text></View> : null}
    {s?.dataWarnings?.map((w) => <View key={w} testID="data-warning" style={[st.card, { backgroundColor: colors.backgroundElement, borderColor: Brand.negative }]}><Text style={[st.body, { color: colors.text, fontWeight: '800' }]}>{w}</Text></View>)}
    {s?.pooled ? <PooledBlock p={s.pooled} title={tr(lang, 'venueEqual')} big lang={lang} colors={colors} /> : null}
    {s?.pooledStockWeighted ? <PooledBlock p={s.pooledStockWeighted} title={tr(lang, 'stockWeighted')} big={false} lang={lang} colors={colors} /> : null}
    {s?.pooled ? <Text testID="reading-line" style={[st.body, { color: colors.text, marginTop: 10 }, rtl(lang)]}>{tr(lang, (s.pooled.spreadMeanPp ?? 0) < 0 ? 'readingLineNegative' : 'readingLine')}</Text> : null}
    {s?.markets ? <View style={{ marginTop: 14 }}>
      <Text style={[st.section, { color: colors.text }, rtl(lang)]}>{tr(lang, 'perMarket')}</Text>
      {sortMarkets(s.markets).map(([m, v]) => <Pressable key={m} onPress={() => setMarket(market === m ? null : m)} style={[st.card, { backgroundColor: market === m ? `${Brand.primary}14` : colors.backgroundElement, borderColor: market === m ? Brand.primary : colors.backgroundSelected, marginTop: 6 }]}>
        <View style={{ flexDirection: lang === 'fa' ? 'row-reverse' : 'row', gap: 8, alignItems: 'center' }}><Text style={[st.body, { color: colors.text, flex: 1, fontWeight: '800' }, rtl(lang)]}>{m}</Text>{v.tooSmallToInterpret ? <Tag text={tr(lang, 'tooSmall')} /> : null}<Text style={[st.mono, { color: spreadColor(v.spreadMeanPp) }]}>{pp(lang, v.spreadMeanPp, 1)}</Text></View>
        <Text style={[st.small, { color: colors.textSecondary }, rtl(lang)]}>BUY n={num(lang, v.buy.n, 0)} {signedPct(lang, v.buy.meanReturnPct, 1)} · SELL n={num(lang, v.sell.n, 0)} {signedPct(lang, v.sell.meanReturnPct, 1)} · {tr(lang, 'hitRate')} {pct(lang, v.buy.hitRate == null ? null : v.buy.hitRate * 100, 0)}/{pct(lang, v.sell.hitRate == null ? null : v.sell.hitRate * 100, 0)} · {tr(lang, 'benchmark')} {v.benchmark.symbol} {signedPct(lang, v.benchmark.returnPct, 1)}</Text>
      </Pressable>)}
    </View> : null}
  </View>;

  const list = [...(rows?.rows || []), ...extra];
  const right = <View style={wide ? { flex: 1, marginLeft: 16 } : { marginTop: 14 }}>
    {matured ? <>
      <Text style={[st.section, { color: colors.text }, rtl(lang)]}>{tr(lang, 'perStock')}{market ? ` · ${market}` : ` · ${tr(lang, 'allMarkets')}`}</Text>
      <TextInput value={query} onChangeText={setQuery} placeholder={tr(lang, 'search')} placeholderTextColor={colors.textSecondary} style={[st.input, { color: colors.text, borderColor: colors.backgroundSelected }, rtl(lang)]} />
      <Text style={[st.small, { color: colors.textSecondary }, rtl(lang)]}>{tr(lang, 'best10')}{rows ? ` (${num(lang, rows.total, 0)})` : ''}</Text>
      {list.map((r) => <Pressable key={`${r.market}-${r.ticker}-b`} onPress={() => openStock(r)}><Row label={`${r.ticker} · ${r.side}${r.name ? ` · ${r.name}` : ''}`} colors={colors} lang={lang} dot={r.hit ? Brand.positive : Brand.negative} value={`${signedPct(lang, r.returnPct, 1)} · ${tr(lang, 'excess')} ${signedPct(lang, r.excessPct, 1)}`} sub={`${r.market} · ${tr(lang, 'benchmark')} ${signedPct(lang, r.benchmarkPct, 1)} · ${r.hit ? tr(lang, 'hit') : tr(lang, 'miss')}`} /></Pressable>)}
      {worst.length ? <Text style={[st.small, { color: colors.textSecondary, marginTop: 8 }, rtl(lang)]}>{tr(lang, 'worstCalls')}</Text> : null}
      {worst.map((r) => <Pressable key={`${r.market}-${r.ticker}-w`} onPress={() => openStock(r)}><Row label={`${r.ticker} · ${r.side}${r.name ? ` · ${r.name}` : ''}`} colors={colors} lang={lang} dot={r.hit ? Brand.positive : Brand.negative} value={`${signedPct(lang, r.returnPct, 1)} · ${tr(lang, 'excess')} ${signedPct(lang, r.excessPct, 1)}`} sub={`${r.market} · ${tr(lang, 'benchmark')} ${signedPct(lang, r.benchmarkPct, 1)} · ${r.hit ? tr(lang, 'hit') : tr(lang, 'miss')}`} /></Pressable>)}
      {rows && rows.total > 10 + extra.length ? <Pressable onPress={loadMore}><Text style={[st.link]}>{tr(lang, 'loadMore')}</Text></Pressable> : null}
      {rows && !list.length ? <Text style={[st.small, { color: colors.textSecondary }]}>{tr(lang, 'noRows')}</Text> : null}
    </> : null}
    {s?.caveats?.length ? <View style={{ marginTop: 14 }}>
      <Text style={[st.section, { color: colors.text }, rtl(lang)]}>{tr(lang, 'caveats')}</Text>
      {s.caveats.map((c) => <Text key={c} style={[st.small, { color: colors.textSecondary }, rtl(lang)]}>• {c}</Text>)}
      <Text style={[st.small, { color: colors.textSecondary }, rtl(lang)]}>{tr(lang, 'source')}: {s.sourceLabel || s.cohortId}</Text>
    </View> : null}
  </View>;

  return <SafeAreaView style={[st.safe, { backgroundColor: colors.background }]}><ScrollView contentContainerStyle={[st.pad, { paddingBottom: BottomTabInset + Spacing.four }]}><View style={st.max}>
    {header}
    {wide ? <View style={{ flexDirection: 'row' }}>{left}{right}</View> : <>{left}{right}</>}
  </View></ScrollView></SafeAreaView>;
}

const st = StyleSheet.create({
  safe: { flex: 1 }, pad: { paddingHorizontal: Spacing.three }, max: { maxWidth: MaxContentWidth + 400, width: '100%', alignSelf: 'center' },
  header: { paddingTop: Spacing.four, paddingBottom: Spacing.two, gap: 3 },
  title: { fontFamily: Fonts.sans, fontSize: 25, fontWeight: '900' },
  lang: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3 },
  card: { borderWidth: 1, borderRadius: Radius.md, padding: 12, marginTop: 10 },
  tabs: { flexDirection: 'row', gap: 8, marginTop: 12 },
  tab: { borderWidth: 1.5, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 5 },
  tabText: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '900' },
  kpis: { flexDirection: 'row', gap: 8, marginVertical: 8 }, kpi: { flex: 1 },
  kpiBig: { fontFamily: Fonts.sans, fontSize: 20, fontWeight: '900' }, kpiMid: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '800' },
  small: { fontFamily: Fonts.sans, fontSize: 10, lineHeight: 15 }, body: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 18 },
  section: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900', marginTop: 6 }, mono: { fontFamily: Fonts.mono, fontSize: 11, fontWeight: '800' },
  input: { borderWidth: 1, borderRadius: Radius.sm, paddingHorizontal: 10, paddingVertical: 6, marginVertical: 6, fontFamily: Fonts.sans, fontSize: 12 },
  link: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '800', color: Brand.primary, marginTop: 8 },
});
