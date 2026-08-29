import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, useColorScheme, SafeAreaView, RefreshControl, ActivityIndicator } from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, BottomTabInset, ThemeColors } from '@/constants/theme';
import { fetchRecommendation, formatPrice, parsePct, Recommendation, StockItem, MarketSymbolResult } from '@/lib/api';
import { fetchMarketSymbols } from '@/lib/market-symbols';
import { fetchTsetmcHistory, fetchTsetmcQuote, PricePoint } from '@/lib/market-quote';
import { getDemoMode } from '@/lib/demo-mode';
import { executeDemoTrade, getDemoWallet } from '@/lib/demo-trading';
import { StockRowSkeleton } from '@/components/skeleton';
import { RecommendationCard } from '@/components/recommendation-card';
import { KiashaDecisionCard } from '@/components/kiasha-decision-card';
import { RealTradeGate } from '@/components/real-trade-gate';

function MiniHistoryChart({ points, colors }: { points: PricePoint[]; colors: ThemeColors }) {
  const sample = useMemo(() => {
    if (points.length <= 24) return points;
    const step = Math.ceil(points.length / 24);
    return points.filter((_, index) => index % step === 0).slice(-24);
  }, [points]);
  if (sample.length < 2) return null;
  const values = sample.map((p) => p.close);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const positive = values[values.length - 1] >= values[0];
  const accent = positive ? Brand.stockGreen : Brand.negative;
  return (
    <View style={[styles.chartCard, { backgroundColor: colors.backgroundElement }]}>
      <View style={styles.chartHead}><Text style={[styles.chartMeta, { color: accent }]}>{positive ? '▲' : '▼'} {(((values[values.length - 1] - values[0]) / values[0]) * 100).toFixed(2)}٪</Text><Text style={[styles.chartTitle, { color: colors.text }]}>روند قیمت ۶۰ روز اخیر</Text></View>
      <View style={styles.bars}>{sample.map((point, index) => <View key={`${point.date}-${index}`} style={[styles.bar, { height: 18 + ((point.close - min) / range) * 92, backgroundColor: accent, opacity: 0.35 + (index / sample.length) * 0.65 }]} />)}</View>
      <View style={styles.chartFoot}><Text style={[styles.chartMeta, { color: colors.textSecondary }]}>{formatPrice(min)}</Text><Text style={[styles.chartMeta, { color: colors.textSecondary }]}>{formatPrice(max)} ریال</Text></View>
    </View>
  );
}

function quoteFromRecommendation(rec: Recommendation | null, fallback: MarketSymbolResult): StockItem | null {
  const live = rec?.livePrice;
  if (!live) return null;
  const lastPrice = live.lastPrice == null ? undefined : Number(live.lastPrice);
  const closingPrice = live.closingPrice == null ? undefined : Number(live.closingPrice);
  const yesterdayPrice = live.yesterdayPrice == null ? undefined : Number(live.yesterdayPrice);
  if (!Number.isFinite(lastPrice) && !Number.isFinite(closingPrice)) return null;
  const effective = Number.isFinite(lastPrice) ? lastPrice : closingPrice;
  const change = Number.isFinite(effective) && Number.isFinite(yesterdayPrice) ? Number(effective) - Number(yesterdayPrice) : undefined;
  const changePercent = live.changePercent == null ? (change !== undefined && yesterdayPrice ? (change / yesterdayPrice) * 100 : undefined) : Number(live.changePercent);
  return {
    name: rec?.name || fallback.name,
    code: rec?.code || fallback.code,
    lastPrice: Number.isFinite(lastPrice) ? lastPrice : undefined,
    closingPrice: Number.isFinite(closingPrice) ? closingPrice : undefined,
    yesterdayPrice: Number.isFinite(yesterdayPrice) ? yesterdayPrice : undefined,
    change,
    changePercent,
  };
}

function DemoTradePanel({ symbol, price, colors }: { symbol: string; price: number; colors: ThemeColors }) {
  const [cash, setCash] = useState<number | null>(null);
  const [quantity, setQuantity] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const load = useCallback(async () => {
    const wallet = await getDemoWallet();
    setCash(wallet.cash);
    setQuantity(wallet.holdings[symbol.toUpperCase()]?.quantity ?? 0);
  }, [symbol]);
  useEffect(() => { load(); }, [load]);
  const trade = async (side: 'BUY' | 'SELL') => {
    setBusy(true); setMessage('');
    const result = await executeDemoTrade({ code: symbol, side, quantity: 10, price });
    if (!result.ok) setMessage(result.message);
    else {
      setCash(result.wallet.cash);
      setQuantity(result.wallet.holdings[symbol.toUpperCase()]?.quantity ?? 0);
      setMessage(`${side === 'BUY' ? 'خرید' : 'فروش'} دمو ۱۰ سهم ثبت شد.`);
    }
    setBusy(false);
  };
  return <View style={[styles.tradeCard, { backgroundColor: colors.backgroundElement }]}>
    <View style={styles.tradeHead}><View style={styles.demoBadge}><Text style={styles.demoBadgeText}>DEMO</Text></View><Text style={[styles.tradeTitle, { color: colors.text }]}>خرید و فروش آزمایشی</Text></View>
    <Text style={[styles.tradeMeta, { color: colors.textSecondary }]}>موجودی نقد: {cash === null ? '—' : Math.round(cash).toLocaleString('fa-IR')} ریال • دارایی {symbol}: {quantity.toLocaleString('fa-IR')} سهم</Text>
    <Text style={[styles.tradeMeta, { color: colors.textSecondary }]}>قیمت مبنا: {formatPrice(price)} ریال • هر سفارش: ۱۰ سهم</Text>
    <View style={styles.tradeButtons}>
      <Pressable disabled={busy} onPress={() => trade('BUY')} style={[styles.tradeBtn, { backgroundColor: Brand.stockGreen }]}><Text style={styles.tradeBtnText}>خرید دمو</Text></Pressable>
      <Pressable disabled={busy} onPress={() => trade('SELL')} style={[styles.tradeBtn, { backgroundColor: Brand.negative }]}><Text style={styles.tradeBtnText}>فروش دمو</Text></Pressable>
    </View>
    {busy ? <ActivityIndicator color={Brand.primary} /> : null}
    {message ? <Text style={[styles.tradeMessage, { color: message.includes('ثبت شد') ? Brand.stockGreen : Brand.negative }]}>{message}</Text> : null}
    <Text style={[styles.tradeNotice, { color: colors.textSecondary }]}>این معامله فقط در کیف پول دمو روی همین دستگاه ذخیره می‌شود و به هیچ کارگزاری ارسال نمی‌شود.</Text>
  </View>;
}

export default function StockDetailScreen() {
  const { code } = useLocalSearchParams<{ code: string }>();
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const activeCodeRef = useRef<string | undefined>(code);
  const [symbol, setSymbol] = useState<MarketSymbolResult | null>(null);
  const [item, setItem] = useState<StockItem | null>(null);
  const [history, setHistory] = useState<PricePoint[]>([]);
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [demo, setDemo] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!code) return;
    const requestedCode = code;
    try {
      const candidates = await fetchMarketSymbols({ q: requestedCode, limit: 30 });
      if (activeCodeRef.current !== requestedCode) return;
      const found = candidates.find((s) => s.code === requestedCode)
        ?? candidates.find((s) => s.symbol === requestedCode)
        ?? { code: requestedCode, symbol: requestedCode, name: requestedCode, market: null };

      const [recommendation, demoMode] = await Promise.all([
        fetchRecommendation(found.symbol || found.code, 55_000),
        getDemoMode(),
      ]);
      if (activeCodeRef.current !== requestedCode) return;
      const fundamentalTicker = String(recommendation?.codalFundamentals?.symbol ?? '').trim();
      const displayTicker = !/^\d+$/.test(found.symbol) ? found.symbol : (!/^\d+$/.test(fundamentalTicker) && fundamentalTicker ? fundamentalTicker : found.symbol);
      const displayName = !/^\d+$/.test(found.name) ? found.name : (recommendation?.name || displayTicker || found.name);
      const resolved: MarketSymbolResult = {
        ...found,
        symbol: displayTicker,
        name: displayName,
        code: recommendation?.code && /^\d+$/.test(recommendation.code) ? recommendation.code : found.code,
      };
      setSymbol(resolved);
      setRec(recommendation);
      setDemo(demoMode);

      const [directQuote, points] = await Promise.all([
        fetchTsetmcQuote(resolved, 6_000, false),
        fetchTsetmcHistory(resolved, 60, 10_000),
      ]);
      if (activeCodeRef.current !== requestedCode) return;
      const fallbackQuote = quoteFromRecommendation(recommendation, resolved);
      setItem(!directQuote.error ? directQuote : (fallbackQuote ?? directQuote));
      setHistory(points);
    } finally {
      if (activeCodeRef.current === requestedCode) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [code]);

  useEffect(() => {
    activeCodeRef.current = code;
    setLoading(true);
    setRefreshing(false);
    setSymbol(null);
    setItem(null);
    setHistory([]);
    setRec(null);
    load();
  }, [code, load]);

  const pct = item?.changePercent !== undefined && !item?.error ? parsePct(item.changePercent) : null;
  const up = (pct ?? 0) >= 0;
  const livePrice = item && !item.error ? (item.lastPrice ?? item.closingPrice ?? null) : null;

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={Brand.stockGreen} />}>
    <View style={styles.header}><Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.backText, { color: colors.text }]}>← بازگشت</Text></Pressable><Text style={[styles.headerLabel, { color: colors.textSecondary }]}>جزئیات نماد</Text></View>
    {loading ? <View>{[1,2,3].map(i => <StockRowSkeleton key={i} />)}</View> : null}
    {!loading && symbol && item ? <>
      <View style={[styles.priceCard, { backgroundColor: colors.backgroundElement }]}><View style={styles.titleLine}><View style={[styles.marketBadge, { backgroundColor: colors.backgroundSelected }]}><Text style={[styles.marketBadgeText, { color: colors.textSecondary }]}>{symbol.market ?? 'TSETMC'}</Text></View><View style={{ alignItems: 'flex-end', flex: 1 }}><Text style={[styles.symbol, { color: colors.text }]}>{symbol.symbol}</Text><Text style={[styles.company, { color: colors.textSecondary }]}>{symbol.name}</Text></View></View><View style={styles.priceLine}><Text style={[styles.price, { color: colors.text }]}>{livePrice === null ? '—' : formatPrice(livePrice)}</Text><Text style={[styles.unit, { color: colors.textSecondary }]}>ریال</Text></View>{pct !== null ? <Text style={[styles.change, { color: up ? Brand.stockGreen : Brand.negative }]}>{up ? '▲' : '▼'} {Math.abs(pct).toFixed(2)}٪</Text> : <Text style={[styles.noQuote, { color: colors.textSecondary }]}>قیمت زنده معتبر فعلاً دریافت نشد.</Text>}</View>
      {history.length >= 2 ? <MiniHistoryChart points={history} colors={colors} /> : <View style={[styles.stateCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.stateText, { color: colors.textSecondary }]}>تاریخچه قیمت TSETMC برای این نماد فعلاً قابل دریافت نیست؛ نمودار ساختگی نمایش داده نمی‌شود.</Text></View>}
      <View style={[styles.table, { backgroundColor: colors.backgroundElement }]}><Row label="آخرین قیمت" value={`${formatPrice(item.lastPrice)} ریال`} colors={colors} /><Row label="قیمت پایانی" value={`${formatPrice(item.closingPrice)} ریال`} colors={colors} /><Row label="قیمت دیروز" value={`${formatPrice(item.yesterdayPrice)} ریال`} colors={colors} /><Row label="شناسه بازار" value={symbol.code} colors={colors} /><Row label="بازار" value={symbol.market ?? 'TSETMC verified resolver'} colors={colors} /></View>
      {rec ? <KiashaDecisionCard rec={rec} colors={colors} demo={demo} /> : null}
      {demo && livePrice ? <DemoTradePanel symbol={symbol.symbol || symbol.code} price={livePrice} colors={colors} /> : demo ? <View style={[styles.stateCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.stateText, { color: colors.textSecondary }]}>برای خرید و فروش دمو باید ابتدا قیمت معتبر TSETMC دریافت شود.</Text></View> : <RealTradeGate colors={colors} />}
      {rec ? <RecommendationCard rec={rec} colors={colors} /> : <View style={[styles.stateCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.stateText, { color: colors.textSecondary }]}>تحلیل کیا‌شا برای این نماد فعلاً دریافت نشد. دکمه اجرای Paper فقط بعد از دریافت تحلیل معتبر نمایش داده می‌شود.</Text><Pressable disabled={refreshing} onPress={() => { setRefreshing(true); load(); }} style={[styles.retryButton, { backgroundColor: Brand.primary, opacity: refreshing ? 0.65 : 1 }]}>{refreshing ? <ActivityIndicator color="#fff" /> : <Text style={styles.retryText}>تلاش دوباره برای تحلیل کیا‌شا</Text>}</Pressable></View>}
      <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>قیمت و تاریخچه از مسیر تأییدشده BIAP/TSETMC؛ مقدار ناموجود ساخته نمی‌شود.</Text>
    </> : null}
  </ScrollView></SafeAreaView>;
}

function Row({ label, value, colors }: { label: string; value: string; colors: ThemeColors }) { return <View style={[styles.row, { borderBottomColor: colors.backgroundSelected }]}><Text style={[styles.rowValue, { color: colors.text }]}>{value}</Text><Text style={[styles.rowLabel, { color: colors.textSecondary }]}>{label}</Text></View>; }

const styles = StyleSheet.create({
  safe:{flex:1}, content:{paddingHorizontal:Spacing.three}, header:{flexDirection:'row-reverse',alignItems:'center',justifyContent:'space-between',paddingVertical:Spacing.three}, back:{paddingHorizontal:Spacing.three,paddingVertical:Spacing.two,borderRadius:Spacing.two}, backText:{fontFamily:Fonts.sans,fontSize:13}, headerLabel:{fontFamily:Fonts.sans,fontSize:12},
  priceCard:{borderRadius:Spacing.three,padding:Spacing.four,alignItems:'flex-end'}, titleLine:{width:'100%',flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center',gap:Spacing.two}, marketBadge:{borderRadius:13,paddingHorizontal:9,paddingVertical:5}, marketBadgeText:{fontFamily:Fonts.mono,fontSize:9}, symbol:{fontFamily:Fonts.sans,fontSize:24,fontWeight:'800'}, company:{fontFamily:Fonts.sans,fontSize:11,marginTop:3,textAlign:'right'}, priceLine:{flexDirection:'row-reverse',alignItems:'baseline',gap:6,marginTop:Spacing.three}, price:{fontFamily:Fonts.mono,fontSize:31,fontWeight:'800'}, unit:{fontFamily:Fonts.sans,fontSize:12}, change:{fontFamily:Fonts.mono,fontSize:15,fontWeight:'800',marginTop:5}, noQuote:{fontFamily:Fonts.sans,fontSize:11,marginTop:Spacing.two},
  chartCard:{borderRadius:Spacing.three,padding:Spacing.three,marginTop:Spacing.three}, chartHead:{flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center'}, chartTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'800'}, chartMeta:{fontFamily:Fonts.mono,fontSize:10}, bars:{height:120,flexDirection:'row',alignItems:'flex-end',gap:3,marginTop:Spacing.three}, bar:{flex:1,borderRadius:3,minWidth:2}, chartFoot:{flexDirection:'row',justifyContent:'space-between',marginTop:6},
  table:{borderRadius:Spacing.two,paddingHorizontal:Spacing.three,marginTop:Spacing.three}, row:{flexDirection:'row-reverse',justifyContent:'space-between',paddingVertical:Spacing.three,borderBottomWidth:StyleSheet.hairlineWidth}, rowLabel:{fontFamily:Fonts.sans,fontSize:12}, rowValue:{fontFamily:Fonts.mono,fontSize:12,fontWeight:'700',maxWidth:'65%'},
  tradeCard:{borderRadius:Spacing.three,padding:Spacing.four,marginTop:Spacing.three,alignItems:'flex-end',gap:Spacing.two}, tradeHead:{width:'100%',flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center'}, tradeTitle:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'800'}, demoBadge:{backgroundColor:'#7048e8',borderRadius:12,paddingHorizontal:8,paddingVertical:4}, demoBadgeText:{color:'#fff',fontFamily:Fonts.mono,fontSize:9,fontWeight:'800'}, tradeMeta:{fontFamily:Fonts.sans,fontSize:11,textAlign:'right'}, tradeButtons:{width:'100%',flexDirection:'row-reverse',gap:Spacing.two}, tradeBtn:{flex:1,paddingVertical:Spacing.three,borderRadius:Spacing.two,alignItems:'center'}, tradeBtnText:{color:'#fff',fontFamily:Fonts.sans,fontSize:13,fontWeight:'800'}, tradeMessage:{fontFamily:Fonts.sans,fontSize:11,textAlign:'right'}, tradeNotice:{fontFamily:Fonts.sans,fontSize:10,lineHeight:17,textAlign:'right'},
  stateCard:{borderRadius:Spacing.three,padding:Spacing.four,alignItems:'center',marginTop:Spacing.three}, stateText:{fontFamily:Fonts.sans,fontSize:12,lineHeight:20,textAlign:'center'}, retryButton:{marginTop:Spacing.three,width:'100%',paddingVertical:Spacing.three,borderRadius:Spacing.two,alignItems:'center'},retryText:{color:'#fff',fontFamily:Fonts.sans,fontSize:13,fontWeight:'800'}, disclaimer:{fontFamily:Fonts.sans,fontSize:10.5,textAlign:'center',marginVertical:Spacing.three},
});