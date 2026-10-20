import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, SafeAreaView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { fetchGlobalInstruments, fetchGlobalTiers, GlobalAnalysis, GlobalInstrument, GlobalTierView, scanGlobalMarket, scanGlobalTop10 } from '@/lib/global-api';
import { categoryLabel, gateLines, groupLine, marketListRows } from '@/lib/scan-summary';
import { getGlobalMarketSelection, GlobalMarketSelection } from '@/lib/global-market-selection';
import { setSelectedGlobalCompany } from '@/lib/global-company-selection';
import { isSupportedGlobalEquityInstrument, unsupportedGlobalInstrumentMessage } from '@/lib/global-equity-filter';
import type { GlobalInvestmentDecision } from '@/lib/decision-tier';
import { tierCounts, tierLabel, tierTone } from '@/lib/decision-tier';

const PAGE_SIZE = 80;

type ScanMode = '' | 'live' | 'cached' | 'catalog' | 'global';

function callColor(call: string | undefined, secondary: string) {
  const t = tierTone(call);
  if (t === 'positive') return Brand.positive;
  if (t === 'warning') return Brand.warning;
  if (t === 'negative') return Brand.negative;
  return secondary;
}

function normalizedSearch(value: string | null | undefined) {
  return String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, ' ').replace(/\s+/g, ' ');
}

function searchScore(item: GlobalInstrument, rawQuery: string) {
  const q = normalizedSearch(rawQuery);
  if (!q) return 0;
  const ticker = normalizedSearch(item.ticker).replace(/ /g, '');
  const isin = normalizedSearch(item.isin).replace(/ /g, '');
  const name = normalizedSearch(item.name);
  const words = name.split(' ').filter(Boolean);

  if (ticker === q) return 1000;
  if (ticker.startsWith(q)) return 900;
  if (isin && isin === q) return 850;
  if (isin && isin.startsWith(q)) return 800;
  if (name === q) return 760;
  if (words.some((word) => word === q)) return 700;
  if (words.some((word) => word.startsWith(q))) return 620;
  if (ticker.includes(q.replace(/ /g, ''))) return 580;
  if (name.includes(q)) return 540;

  const queryWords = q.split(' ').filter(Boolean);
  if (queryWords.length > 1 && queryWords.every((part) => words.some((word) => word === part || word.startsWith(part)))) return 560;
  return -1;
}

function appendUnique(existing: GlobalInstrument[], incoming: GlobalInstrument[]) {
  const seen = new Set(existing.map((item) => `${item.country}:${item.exchange}:${item.ticker}:${item.isin || ''}`));
  const merged = [...existing];
  for (const item of incoming) {
    const key = `${item.country}:${item.exchange}:${item.ticker}:${item.isin || ''}`;
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(item);
    }
  }
  return merged;
}

export default function MarketScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [selection, setSelection] = useState<GlobalMarketSelection | null>(null);
  const [instruments, setInstruments] = useState<GlobalInstrument[]>([]);
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [totalMatched, setTotalMatched] = useState(0);
  const [error, setError] = useState('');
  const [scan, setScan] = useState<GlobalAnalysis[]>([]);
  const [gateInfo, setGateInfo] = useState<string[]>([]);
  const [scanning, setScanning] = useState(false);
  const [scanStatus, setScanStatus] = useState('');
  const [scanMode, setScanMode] = useState<ScanMode>('');
  const [tiers, setTiers] = useState<GlobalTierView | null>(null);
  const tierByTicker = useMemo(() => new Map<string | undefined, GlobalInvestmentDecision>((tiers?.rows || []).map((r) => [r.ticker, r.investment])), [tiers]);

  const loadSeq = useRef(0);

  const load = useCallback(async (forceSearch?: string) => {
    const seq = ++loadSeq.current;
    const selected = await getGlobalMarketSelection();
    setSelection(selected);
    void fetchGlobalTiers(selected.country, selected.exchange).then(setTiers);
    const searchText = typeof forceSearch === 'string' ? forceSearch.trim() : '';
    try {
      setError('');
      const result = await fetchGlobalInstruments(selected.country, selected.exchange, {
        q: searchText || undefined,
        limit: searchText ? 150 : PAGE_SIZE,
        offset: 0,
      });
      if (seq !== loadSeq.current) return;
      setInstruments((result.instruments || []).filter(isSupportedGlobalEquityInstrument));
      setTotalMatched(result.totalMatched || 0);
      setHasMore(Boolean(result.hasMore));
      setNextOffset(result.nextOffset ?? null);
    } catch (err) {
      if (seq !== loadSeq.current) return;
      setInstruments([]);
      setTotalMatched(0);
      setHasMore(false);
      setNextOffset(null);
      setError(err instanceof Error ? err.message.slice(0, 220) : 'Market universe is unavailable.');
    } finally {
      if (seq === loadSeq.current) {
        setLoading(false);
        setRefreshing(false);
        setLoadingSearch(false);
      }
    }
  }, []);

  // Search as you type: debounce the query, then ask the API for the selected exchange (ticker prefix + company name).
  useEffect(() => {
    const text = query.trim();
    if (text === submittedQuery.trim()) return;
    const timer = setTimeout(() => {
      setSubmittedQuery(text);
      setLoadingSearch(true);
      void load(text);
    }, 350);
    return () => clearTimeout(timer);
  }, [query, submittedQuery, load]);

  const loadMore = async () => {
    if (!selection || loading || loadingMore || !hasMore || nextOffset == null) return;
    setLoadingMore(true);
    try {
      const searchText = submittedQuery.trim();
      const result = await fetchGlobalInstruments(selection.country, selection.exchange, {
        q: searchText || undefined,
        limit: searchText ? 150 : PAGE_SIZE,
        offset: nextOffset,
      });
      setInstruments((current) => appendUnique(current, (result.instruments || []).filter(isSupportedGlobalEquityInstrument)));
      setTotalMatched(result.totalMatched || totalMatched);
      setHasMore(Boolean(result.hasMore));
      setNextOffset(result.nextOffset ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message.slice(0, 220) : 'Could not load more instruments.');
    } finally {
      setLoadingMore(false);
    }
  };

  useFocusEffect(useCallback(() => {
    setLoading(true);
    setQuery('');
    setSubmittedQuery('');
    setScan([]);
    setScanStatus('');
    setScanMode('');
    void load();
  }, [load]));

  const filtered = useMemo(() => {
    const q = submittedQuery.trim();
    if (!q) return instruments;
    return instruments
      .map((item) => ({ item, score: searchScore(item, q) }))
      .filter((entry) => entry.score >= 0)
      .sort((a, b) => b.score - a.score || a.item.ticker.localeCompare(b.item.ticker))
      .map((entry) => entry.item);
  }, [instruments, submittedQuery]);

  const searchRemote = async () => {
    const searchText = query.trim();
    setSubmittedQuery(searchText);
    setLoadingSearch(true);
    await load(searchText);
  };

  const runScan = async () => {
    if (!selection) return;
    setScanning(true); setScan([]); setGateInfo([]); setScanStatus(''); setScanMode('');
    try {
      const result = await scanGlobalMarket(selection.country, selection.exchange, 20);
      const extended = result as typeof result & { catalogOnly?: boolean; cachedMarketData?: boolean };
      const rankingEligible = result.rankingEligible === true;
      setScan(marketListRows(result));
      setGateInfo([...(groupLine(result) ? [groupLine(result)] : []), ...gateLines(result)]);
      const marketCoverage = result.screeningCoveragePct == null ? '—' : `${Number(result.screeningCoveragePct).toFixed(1)}%`;
      const fundamentalCoverage = result.fundamentalCoveragePct == null ? '—' : `${Number(result.fundamentalCoveragePct).toFixed(1)}%`;
      const tierView = await fetchGlobalTiers(selection.country, selection.exchange);
      if (tierView) setTiers(tierView);
      if (tierView && tierView.rows.length && !extended.catalogOnly && result.status !== 'MARKET_DATA_REQUIRED') {
        setScanMode('live');
        setScanStatus(`Investment ranking • ${tierCounts(tierView.counts)} • Conservative rule (reference): ${result.qualifiedBuyCount ?? result.recommendationCount ?? 0} qualified BUY`);
      } else if (extended.catalogOnly || result.status === 'MARKET_DATA_REQUIRED') {
        setScanMode('catalog');
        setScanStatus(`Ranking blocked • ${(result.universeDiscovered ?? totalMatched) || instruments.length} eligible equities • fresh market feed unavailable`);
      } else if (extended.cachedMarketData || result.status.startsWith('CACHED_')) {
        setScanMode('cached');
        setScanStatus(`Ranking blocked • stored market records only • market coverage ${marketCoverage} • verified fundamentals ${fundamentalCoverage}`);
      } else if (!rankingEligible) {
        setScanMode('cached');
        setScanStatus(`Ranking blocked • ${result.universeScreened ?? 0}/${result.universeDiscovered ?? 0} equities screened • market coverage ${marketCoverage} • verified fundamentals ${fundamentalCoverage}`);
      } else {
        setScanMode('live');
        setScanStatus(`This market • Market Top ${Math.min(20, (result.marketTop10 || result.recommendations || []).length)} shown • ${result.qualifiedBuyCount ?? result.recommendationCount ?? 0} qualified BUY • ${result.universeScreened ?? 0}/${result.universeDiscovered ?? 0} equities screened • ${marketCoverage} coverage`);
      }
    } catch (err) {
      setScanMode('');
      setScanStatus(err instanceof Error ? err.message.slice(0, 220) : 'Market scan unavailable.');
    } finally { setScanning(false); }
  };

  const runGlobalTop10 = async () => {
    setScanning(true); setScan([]); setScanStatus(''); setScanMode('');
    try {
      const result = await scanGlobalTop10(10, 30);
      const readyMarkets = result.marketsEligible ?? 0;
      const scannedMarkets = result.marketsScanned ?? 0;
      const globallyReady = readyMarkets > 0 && result.status !== 'GLOBAL_DATA_INCOMPLETE';
      const completeGlobalScope = scannedMarkets > 0 && readyMarkets === scannedMarkets;
      setScan(globallyReady ? (result.recommendations || []) : []);
      setScanMode(globallyReady ? 'global' : 'cached');
      const coverage = result.globalCoveragePct == null ? '—' : `${Number(result.globalCoveragePct).toFixed(1)}%`;
      const shown = result.recommendationCount ?? 0;
      const qualifiedLabel = result.qualifiedIssuers != null && result.qualifiedIssuers > shown ? `top ${shown} of ${result.qualifiedIssuers} qualified issuers` : `${shown} qualified`;
      if (!globallyReady) {
        setScanStatus(`Global ranking blocked • ${readyMarkets}/${scannedMarkets} markets ready • ${result.marketsExcluded ?? scannedMarkets} excluded`);
      } else if (!completeGlobalScope) {
        setScanStatus(`Partial global scan • ${readyMarkets}/${scannedMarkets} markets ready • ${qualifiedLabel} in ready markets • ${result.screenedEquities ?? 0}/${result.eligibleEquities ?? 0} screened (price data only) • ${result.deepAnalyzed ?? 0} deep-analyzed • ${coverage} screening coverage`);
      } else {
        setScanStatus(`Global Top 10 • ${qualifiedLabel} • all ${scannedMarkets} markets ready • ${result.screenedEquities ?? 0}/${result.eligibleEquities ?? 0} screened (price data only) • ${result.deepAnalyzed ?? 0} deep-analyzed • ${coverage} screening coverage`);
      }
    } catch (err) {
      setScanMode('');
      setScanStatus(err instanceof Error ? err.message.slice(0, 220) : 'Global Top 10 scan unavailable.');
    } finally { setScanning(false); }
  };

  const openStock = async (item: GlobalInstrument | GlobalAnalysis) => {
    if (!selection) return;
    const ticker = item.ticker || '';
    if (!ticker) return;
    if (!isSupportedGlobalEquityInstrument(item)) {
      setError(unsupportedGlobalInstrumentMessage(item));
      return;
    }
    const instrument: GlobalInstrument = {
      country: item.country || selection.country,
      exchange: item.exchange || selection.exchange,
      currency: item.currency || selection.currency,
      ticker,
      name: item.name || ticker,
      isin: 'isin' in item ? item.isin || null : null,
      lei: 'lei' in item ? item.lei || null : null,
      mic_code: 'mic_code' in item ? item.mic_code || selection.mic || null : selection.mic || null,
      sector: 'sector' in item ? item.sector || null : null,
      industry: 'industry' in item ? item.industry || null : null,
      lot_size: 'lot_size' in item ? item.lot_size || null : null,
    };
    await setSelectedGlobalCompany(instrument);
    router.push({ pathname: '/stock/[code]', params: { code: ticker, country: instrument.country, exchange: instrument.exchange, currency: instrument.currency, name: instrument.name, isin: instrument.isin || '', lei: instrument.lei || '' } } as never);
  };

  const modeColor = scanMode === 'live' ? Brand.positive : scanMode === 'global' ? Brand.primary : scanMode === 'cached' || scanMode === 'catalog' ? Brand.warning : colors.textSecondary;
  const listLabel = submittedQuery.trim()
    ? `Search results${totalMatched ? ` • ${totalMatched}` : ''}`
    : `Ordinary equities${totalMatched ? ` • ${instruments.length} of ${totalMatched}` : ''}`;

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><View style={[styles.container, { backgroundColor: colors.background }]}>
    <View style={styles.header}><View style={styles.headerTop}><View style={{ flex: 1 }}><Text style={[styles.title, { color: colors.text }]}>Market</Text><Text style={[styles.subtitle, { color: colors.textSecondary }]}>{selection ? `${selection.countryName} • ${selection.exchangeLabel}` : 'Loading market context…'}</Text></View><Pressable onPress={() => router.push('/global')} style={[styles.changeButton, { borderColor: Brand.primary }]}><Text style={styles.changeButtonText}>Change market</Text></Pressable></View>{selection ? <Text style={[styles.contextLine, { color: colors.textSecondary }]}>{selection.mic || selection.exchange} • {selection.currency} • one BIAP engine</Text> : null}</View>

    <View style={styles.searchRow}><TextInput value={query} onChangeText={setQuery} onSubmitEditing={() => { void searchRemote(); }} autoCapitalize="characters" placeholder={selection ? `Search ${selection.exchangeLabel} (ticker, company, ISIN)` : 'Search ticker, company or ISIN'} placeholderTextColor={colors.textSecondary} style={[styles.search, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected, color: colors.text }]} /><Pressable disabled={loadingSearch} onPress={() => { void searchRemote(); }} style={[styles.searchButton, { backgroundColor: Brand.primary, opacity: loadingSearch ? .6 : 1 }]}>{loadingSearch ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.searchButtonText}>Search</Text>}</Pressable></View>

    <View style={styles.scanRow}><View style={{ flex: 1 }}><Text style={[styles.scanTitle, { color: colors.text }]}>Kiasha stock selection</Text><Text style={[styles.scanText, { color: colors.textSecondary }]}>Evidence-gated ranking: objective stock score first, investor fit later.</Text></View><View style={styles.scanActions}><Pressable disabled={scanning || !selection} onPress={() => { void runScan(); }} style={[styles.scanButton, { borderColor: Brand.primary }]}>{scanning ? <ActivityIndicator color={Brand.primary} size="small" /> : <Text style={styles.scanButtonText}>This market</Text>}</Pressable><Pressable disabled={scanning} onPress={() => { void runGlobalTop10(); }} style={[styles.scanButton, { borderColor: Brand.primary, backgroundColor: Brand.primary }]}><Text style={[styles.scanButtonText, { color: '#fff' }]}>Global Top 10</Text></Pressable></View></View>
    {scanStatus ? <View style={[styles.statusBox, { backgroundColor: colors.backgroundElement, borderColor: modeColor }]}><Text style={[styles.status, { color: modeColor }]}>{scanStatus}</Text>{scanMode === 'catalog' ? <Text style={[styles.statusHint, { color: colors.textSecondary }]}>The instrument list is real. BIAP will not create BUY candidates until verified market prices are available.</Text> : scanMode === 'cached' ? <Text style={[styles.statusHint, { color: colors.textSecondary }]}>Stored market records are available, but BIAP will not rank this exchange until fresh ordinary-equity coverage and verified fundamental coverage meet the required thresholds.</Text> : scanMode === 'global' ? <Text style={[styles.statusHint, { color: colors.textSecondary }]}>Global Top 10 is one cross-market shortlist, so it stays the same when you change the selected exchange. Use “This market” for a ranking limited to the exchange shown above.</Text> : null}{gateInfo.length ? <View style={{ marginTop: 6 }}><Text style={[styles.statusHint, { color: colors.textSecondary }]}>{tiers ? 'Conservative rule (reference) — a stricter screen, separate from the investment tiers above. Companies rejected at each gate:' : 'Companies rejected at each gate:'}</Text>{gateInfo.map((line) => <Text key={line} style={[styles.statusHint, { color: colors.textSecondary }]}>• {line}</Text>)}</View> : null}</View> : null}
    {scan.length ? <View style={styles.picks}>{scan.slice(0, 20).map((item, index) => <Pressable key={`${item.ticker}-${index}`} onPress={() => { void openStock(item); }} style={[styles.pick, { backgroundColor: colors.backgroundElement }]}><View><Text style={[styles.pickTicker, { color: colors.text }]}>#{index + 1} {item.ticker}</Text><Text numberOfLines={1} style={[styles.pickName, { color: colors.textSecondary }]}>{item.name}</Text></View><View style={{ alignItems: 'flex-end' }}><Text style={[styles.pickCall, { color: callColor(tierByTicker.get(item.ticker)?.tier ?? (item as GlobalAnalysis).investment?.tier ?? item.call, colors.textSecondary) }]}>{(tierByTicker.get(item.ticker) ?? (item as GlobalAnalysis).investment) ? tierLabel((tierByTicker.get(item.ticker) ?? (item as GlobalAnalysis).investment)?.tier) : categoryLabel(item)}</Text><Text style={[styles.pickConfidence, { color: colors.textSecondary }]}>{item.confidence == null ? '—' : `${Math.round(item.confidence * 100)}% conf.`}</Text></View></Pressable>)}</View> : null}
    {tiers ? <View style={styles.picks}>
      <Text style={[styles.tierSummary, { color: colors.textSecondary }]}>{tierCounts(tiers.counts)}</Text>
      {!scan.length ? tiers.rows.slice(0, 20).map((row, index) => <Pressable key={`tier-${row.ticker}-${index}`} onPress={() => { void openStock({ ...(instruments.find((i) => i.ticker === row.ticker) || { country: selection?.country || '', exchange: selection?.exchange || '', currency: '' }), ticker: row.ticker, name: row.name || row.ticker } as GlobalInstrument); }} style={[styles.pick, { backgroundColor: colors.backgroundElement }]}><View><Text style={[styles.pickTicker, { color: colors.text }]}>#{index + 1} {row.ticker}</Text><Text numberOfLines={1} style={[styles.pickName, { color: colors.textSecondary }]}>{row.name}</Text></View><View style={{ alignItems: 'flex-end' }}><Text style={[styles.pickCall, { color: callColor(row.investment.tier, colors.textSecondary) }]}>{tierLabel(row.investment.tier)}</Text><Text style={[styles.pickConfidence, { color: colors.textSecondary }]}>{row.investment.confidence == null ? '—' : `${Math.round(row.investment.confidence * 100)}% conf.`}</Text></View></Pressable>) : null}
    </View> : null}
    {error ? <View style={[styles.errorBox, { borderColor: Brand.warning }]}><Text style={[styles.errorText, { color: colors.textSecondary }]}>{error}</Text></View> : null}

    <FlatList
      data={filtered}
      keyExtractor={(item) => `${item.country}:${item.exchange}:${item.ticker}:${item.isin || ''}`}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(submittedQuery); }} tintColor={Brand.primary} />}
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={styles.list}
      onEndReached={() => { void loadMore(); }}
      onEndReachedThreshold={0.45}
      ListHeaderComponent={<Text style={[styles.listTitle, { color: colors.text }]}>{listLabel}</Text>}
      ListFooterComponent={loadingMore ? <ActivityIndicator color={Brand.primary} style={{ marginVertical: 18 }} /> : (!submittedQuery.trim() && totalMatched > 0 && !hasMore ? <Text style={[styles.endText, { color: colors.textSecondary }]}>All {totalMatched} available instruments loaded.</Text> : null)}
      ListEmptyComponent={loading || loadingSearch ? <ActivityIndicator color={Brand.primary} style={{ marginTop: 30 }} /> : <Text style={[styles.empty, { color: colors.textSecondary }]}>{submittedQuery.trim() ? `No ticker or company-name match on ${selection?.exchangeLabel || 'this exchange'}. Searches cover only the selected market; change market on the Global tab.` : 'No instruments available from the selected market provider.'}</Text>}
      renderItem={({ item }) => <Pressable onPress={() => { void openStock(item); }} style={[styles.row, { backgroundColor: colors.backgroundElement }]}><View style={styles.identity}><Text style={[styles.ticker, { color: colors.text }]}>{item.ticker}</Text><Text numberOfLines={1} style={[styles.name, { color: colors.textSecondary }]}>{item.name}</Text><Text style={[styles.meta, { color: colors.textSecondary }]}>{item.mic_code || selection?.mic || item.exchange} • {item.currency}{item.sector ? ` • ${item.sector}` : ''}</Text></View>{tierByTicker.get(item.ticker) ? <Text style={[styles.tierBadge, { color: callColor(tierByTicker.get(item.ticker)?.tier, colors.textSecondary) }]}>{tierLabel(tierByTicker.get(item.ticker)?.tier)}</Text> : null}<Text style={[styles.chevron, { color: Brand.primary }]}>›</Text></Pressable>}
    />
  </View></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe:{flex:1},container:{flex:1},header:{paddingHorizontal:Spacing.three,paddingTop:Spacing.four,paddingBottom:Spacing.two,maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},headerTop:{flexDirection:'row',alignItems:'center',gap:12},title:{fontFamily:Fonts.sans,fontSize:25,fontWeight:'900'},subtitle:{fontFamily:Fonts.sans,fontSize:12,marginTop:2},contextLine:{fontFamily:Fonts.mono,fontSize:9.5,marginTop:7},changeButton:{borderWidth:1,borderRadius:18,paddingHorizontal:12,paddingVertical:8},changeButtonText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:10,fontWeight:'800'},searchRow:{flexDirection:'row',gap:8,paddingHorizontal:Spacing.three,maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},search:{flex:1,borderWidth:1,borderRadius:Radius.md,paddingHorizontal:13,paddingVertical:11,fontFamily:Fonts.sans,fontSize:12},searchButton:{minWidth:76,borderRadius:Radius.md,alignItems:'center',justifyContent:'center'},searchButtonText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11,fontWeight:'900'},scanRow:{flexDirection:'row',alignItems:'center',gap:10,marginHorizontal:Spacing.three,marginTop:Spacing.three,padding:Spacing.three,borderRadius:Radius.md,maxWidth:MaxContentWidth,alignSelf:'center'},scanTitle:{fontFamily:Fonts.sans,fontSize:12.5,fontWeight:'900'},scanText:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15,marginTop:3},scanActions:{gap:6},scanButton:{borderWidth:1,minWidth:92,minHeight:38,borderRadius:19,alignItems:'center',justifyContent:'center',paddingHorizontal:10},scanButtonText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:9.5,fontWeight:'900'},statusBox:{borderWidth:1,borderRadius:Radius.md,padding:10,marginHorizontal:Spacing.three,marginTop:8,maxWidth:MaxContentWidth,alignSelf:'center',width:'90%'},status:{fontFamily:Fonts.mono,fontSize:9,textAlign:'center'},statusHint:{fontFamily:Fonts.sans,fontSize:9,lineHeight:14,textAlign:'center',marginTop:5},picks:{paddingHorizontal:Spacing.three,paddingTop:Spacing.two,maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},pick:{borderRadius:Radius.md,padding:12,marginBottom:7,flexDirection:'row',justifyContent:'space-between',gap:10},pickTicker:{fontFamily:Fonts.mono,fontSize:12,fontWeight:'900'},pickName:{fontFamily:Fonts.sans,fontSize:9.5,marginTop:2,maxWidth:220},pickCall:{fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},tierBadge:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'900',marginLeft:8,writingDirection:'rtl'},tierSummary:{fontFamily:Fonts.sans,fontSize:10.5,textAlign:'center',marginBottom:6,writingDirection:'rtl'},pickConfidence:{fontFamily:Fonts.mono,fontSize:8.5,marginTop:2},errorBox:{borderWidth:1,borderRadius:Radius.md,padding:10,marginHorizontal:Spacing.three,marginTop:8},errorText:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:17},list:{paddingHorizontal:Spacing.three,paddingBottom:BottomTabInset+Spacing.four,maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},listTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'900',marginTop:Spacing.three,marginBottom:Spacing.two},row:{borderRadius:Radius.md,padding:13,marginBottom:8,flexDirection:'row',alignItems:'center',justifyContent:'space-between'},identity:{flex:1},ticker:{fontFamily:Fonts.mono,fontSize:14,fontWeight:'900'},name:{fontFamily:Fonts.sans,fontSize:10.5,marginTop:2},meta:{fontFamily:Fonts.mono,fontSize:8.5,marginTop:4},chevron:{fontSize:26,marginLeft:10},empty:{fontFamily:Fonts.sans,fontSize:11,textAlign:'center',marginTop:30},endText:{fontFamily:Fonts.sans,fontSize:9.5,textAlign:'center',marginVertical:16},
});