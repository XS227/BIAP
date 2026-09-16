import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, SafeAreaView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { fetchGlobalInstruments, GlobalAnalysis, GlobalInstrument, scanGlobalMarket } from '@/lib/global-api';
import { getGlobalMarketSelection, GlobalMarketSelection } from '@/lib/global-market-selection';
import { setSelectedGlobalCompany } from '@/lib/global-company-selection';

const PAGE_SIZE = 80;

function callColor(call: string | undefined, secondary: string) {
  if (call === 'BUY_CANDIDATE') return Brand.positive;
  if (call === 'HOLD_OR_WATCH') return Brand.warning;
  if (call === 'AVOID_OR_REVIEW') return Brand.negative;
  return secondary;
}

export default function MarketScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [selection, setSelection] = useState<GlobalMarketSelection | null>(null);
  const [instruments, setInstruments] = useState<GlobalInstrument[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [error, setError] = useState('');
  const [scan, setScan] = useState<GlobalAnalysis[]>([]);
  const [scanning, setScanning] = useState(false);
  const [scanStatus, setScanStatus] = useState('');

  const load = useCallback(async (forceSearch?: string) => {
    const selected = await getGlobalMarketSelection();
    setSelection(selected);
    const searchText = typeof forceSearch === 'string' ? forceSearch.trim() : '';
    try {
      setError('');
      const result = await fetchGlobalInstruments(selected.country, selected.exchange, {
        q: searchText || undefined,
        limit: searchText ? 150 : PAGE_SIZE,
      });
      setInstruments(result.instruments || []);
    } catch (err) {
      setInstruments([]);
      setError(err instanceof Error ? err.message.slice(0, 220) : 'Market universe is unavailable.');
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLoadingSearch(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    setLoading(true);
    setScan([]);
    setScanStatus('');
    void load();
  }, [load]));

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return instruments;
    return instruments.filter((item) => item.ticker.toLowerCase().includes(q) || item.name.toLowerCase().includes(q) || String(item.isin || '').toLowerCase().includes(q));
  }, [instruments, query]);

  const searchRemote = async () => {
    if (!query.trim()) return load('');
    setLoadingSearch(true);
    await load(query);
  };

  const runScan = async () => {
    if (!selection) return;
    setScanning(true); setScan([]); setScanStatus('');
    try {
      const result = await scanGlobalMarket(selection.country, selection.exchange, 10);
      setScan(result.recommendations || []);
      setScanStatus(`${result.status} • ${result.recommendationCount ?? 0} qualified • ${result.deepAnalyzed ?? 0} deep analyses`);
    } catch (err) {
      setScanStatus(err instanceof Error ? err.message.slice(0, 220) : 'Market scan unavailable.');
    } finally { setScanning(false); }
  };

  const openStock = async (item: GlobalInstrument | GlobalAnalysis) => {
    if (!selection) return;
    const ticker = item.ticker || '';
    if (!ticker) return;
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

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><View style={[styles.container, { backgroundColor: colors.background }]}>
    <View style={styles.header}><View style={styles.headerTop}><View style={{ flex: 1 }}><Text style={[styles.title, { color: colors.text }]}>Market</Text><Text style={[styles.subtitle, { color: colors.textSecondary }]}>{selection ? `${selection.countryName} • ${selection.exchangeLabel}` : 'Loading market context…'}</Text></View><Pressable onPress={() => router.push('/global')} style={[styles.changeButton, { borderColor: Brand.primary }]}><Text style={styles.changeButtonText}>Change market</Text></Pressable></View>{selection ? <Text style={[styles.contextLine, { color: colors.textSecondary }]}>{selection.mic || selection.exchange} • {selection.currency} • one BIAP engine</Text> : null}</View>

    <View style={styles.searchRow}><TextInput value={query} onChangeText={setQuery} onSubmitEditing={() => { void searchRemote(); }} autoCapitalize="characters" placeholder="Search ticker, company or ISIN" placeholderTextColor={colors.textSecondary} style={[styles.search, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected, color: colors.text }]} /><Pressable disabled={loadingSearch} onPress={() => { void searchRemote(); }} style={[styles.searchButton, { backgroundColor: Brand.primary, opacity: loadingSearch ? .6 : 1 }]}>{loadingSearch ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.searchButtonText}>Search</Text>}</Pressable></View>

    <View style={styles.scanRow}><View style={{ flex: 1 }}><Text style={[styles.scanTitle, { color: colors.text }]}>Kiasha market selection</Text><Text style={[styles.scanText, { color: colors.textSecondary }]}>Universe → liquidity screen → six-agent deep analysis → evidence gate.</Text></View><Pressable disabled={scanning || !selection} onPress={() => { void runScan(); }} style={[styles.scanButton, { borderColor: Brand.primary }]}>{scanning ? <ActivityIndicator color={Brand.primary} size="small" /> : <Text style={styles.scanButtonText}>Run scan</Text>}</Pressable></View>
    {scanStatus ? <Text style={[styles.status, { color: colors.textSecondary }]}>{scanStatus}</Text> : null}
    {scan.length ? <View style={styles.picks}>{scan.slice(0, 5).map((item, index) => <Pressable key={`${item.ticker}-${index}`} onPress={() => { void openStock(item); }} style={[styles.pick, { backgroundColor: colors.backgroundElement }]}><View><Text style={[styles.pickTicker, { color: colors.text }]}>#{index + 1} {item.ticker}</Text><Text numberOfLines={1} style={[styles.pickName, { color: colors.textSecondary }]}>{item.name}</Text></View><View style={{ alignItems: 'flex-end' }}><Text style={[styles.pickCall, { color: callColor(item.call, colors.textSecondary) }]}>{item.call}</Text><Text style={[styles.pickConfidence, { color: colors.textSecondary }]}>{item.confidence == null ? '—' : `${Math.round(item.confidence * 100)}% conf.`}</Text></View></Pressable>)}</View> : null}
    {error ? <View style={[styles.errorBox, { borderColor: Brand.warning }]}><Text style={[styles.errorText, { color: colors.textSecondary }]}>{error}</Text></View> : null}

    <FlatList data={filtered} keyExtractor={(item) => `${item.country}:${item.exchange}:${item.ticker}:${item.isin || ''}`} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(query); }} tintColor={Brand.primary} />} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.list} ListHeaderComponent={<Text style={[styles.listTitle, { color: colors.text }]}>{query.trim() ? 'Search results' : 'Exchange instruments'}</Text>} ListEmptyComponent={loading ? <ActivityIndicator color={Brand.primary} style={{ marginTop: 30 }} /> : <Text style={[styles.empty, { color: colors.textSecondary }]}>No instruments available from the selected market provider.</Text>} renderItem={({ item }) => <Pressable onPress={() => { void openStock(item); }} style={[styles.row, { backgroundColor: colors.backgroundElement }]}><View style={styles.identity}><Text style={[styles.ticker, { color: colors.text }]}>{item.ticker}</Text><Text numberOfLines={1} style={[styles.name, { color: colors.textSecondary }]}>{item.name}</Text><Text style={[styles.meta, { color: colors.textSecondary }]}>{item.mic_code || selection?.mic || item.exchange} • {item.currency}{item.sector ? ` • ${item.sector}` : ''}</Text></View><Text style={[styles.chevron, { color: Brand.primary }]}>›</Text></Pressable>} />
  </View></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe:{flex:1},container:{flex:1},header:{paddingHorizontal:Spacing.three,paddingTop:Spacing.four,paddingBottom:Spacing.two,maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},headerTop:{flexDirection:'row',alignItems:'center',gap:12},title:{fontFamily:Fonts.sans,fontSize:25,fontWeight:'900'},subtitle:{fontFamily:Fonts.sans,fontSize:12,marginTop:2},contextLine:{fontFamily:Fonts.mono,fontSize:9.5,marginTop:7},changeButton:{borderWidth:1,borderRadius:18,paddingHorizontal:12,paddingVertical:8},changeButtonText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:10,fontWeight:'800'},searchRow:{flexDirection:'row',gap:8,paddingHorizontal:Spacing.three,maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},search:{flex:1,borderWidth:1,borderRadius:Radius.md,paddingHorizontal:13,paddingVertical:11,fontFamily:Fonts.sans,fontSize:12},searchButton:{minWidth:76,borderRadius:Radius.md,alignItems:'center',justifyContent:'center'},searchButtonText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11,fontWeight:'900'},scanRow:{flexDirection:'row',alignItems:'center',gap:10,marginHorizontal:Spacing.three,marginTop:Spacing.three,padding:Spacing.three,borderRadius:Radius.md,maxWidth:MaxContentWidth,alignSelf:'center'},scanTitle:{fontFamily:Fonts.sans,fontSize:12.5,fontWeight:'900'},scanText:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15,marginTop:3},scanButton:{borderWidth:1,minWidth:76,minHeight:40,borderRadius:20,alignItems:'center',justifyContent:'center',paddingHorizontal:10},scanButtonText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:10,fontWeight:'900'},status:{fontFamily:Fonts.mono,fontSize:9,textAlign:'center',marginTop:7,paddingHorizontal:Spacing.three},picks:{paddingHorizontal:Spacing.three,paddingTop:Spacing.two,maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},pick:{borderRadius:Radius.md,padding:12,marginBottom:7,flexDirection:'row',justifyContent:'space-between',gap:10},pickTicker:{fontFamily:Fonts.mono,fontSize:12,fontWeight:'900'},pickName:{fontFamily:Fonts.sans,fontSize:9.5,marginTop:2,maxWidth:220},pickCall:{fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},pickConfidence:{fontFamily:Fonts.mono,fontSize:8.5,marginTop:2},errorBox:{borderWidth:1,borderRadius:Radius.md,padding:10,marginHorizontal:Spacing.three,marginTop:8},errorText:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:17},list:{paddingHorizontal:Spacing.three,paddingBottom:BottomTabInset+Spacing.four,maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},listTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'900',marginTop:Spacing.three,marginBottom:Spacing.two},row:{borderRadius:Radius.md,padding:13,marginBottom:8,flexDirection:'row',alignItems:'center',justifyContent:'space-between'},identity:{flex:1},ticker:{fontFamily:Fonts.mono,fontSize:14,fontWeight:'900'},name:{fontFamily:Fonts.sans,fontSize:10.5,marginTop:2},meta:{fontFamily:Fonts.mono,fontSize:8.5,marginTop:4},chevron:{fontSize:26,marginLeft:10},empty:{fontFamily:Fonts.sans,fontSize:11,textAlign:'center',marginTop:30},
});