import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Animated, View, Text, StyleSheet, ScrollView, useColorScheme, SafeAreaView, Pressable, ActivityIndicator, RefreshControl } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { router, useFocusEffect } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { AgentPerformance, fetchKiashaPerformanceSummary, formatPrice, KiashaPerformanceSummary } from '@/lib/api';
import { fetchKiashaTopPicks, InvestmentHorizon, KiashaPicksResult } from '@/lib/kiasha-picks';
import { fetchPaperPortfolio, PaperPortfolio } from '@/lib/paper-portfolio';
import { SymbolLogo } from '@/components/symbol-logo';

const AGENT_LABELS: Record<string, { name: string; short: string }> = {
  fundamental: { name: 'بنیادی', short: 'صورت مالی' },
  risk: { name: 'ریسک', short: 'کنترل ریسک' },
  forecast: { name: 'پیش‌بینی', short: 'مومنتوم' },
  comparison: { name: 'مقایسه', short: 'ارزش‌گذاری' },
  technical: { name: 'تکنیکال', short: 'روند قیمت' },
  flow: { name: 'جریان پول', short: 'رفتار بازار' },
};

function money(v: number | null | undefined) { return v == null || !Number.isFinite(v) ? '—' : Math.round(v).toLocaleString('fa-IR'); }
function pct(v: number | null) { return v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toLocaleString('fa-IR', { maximumFractionDigits: 1 })}٪`; }

function KiashaCat() {
  return <LinearGradient colors={['#29105f', '#13152b', '#070b17']} style={styles.catShell}>
    <View style={styles.catEarRow}><View style={[styles.ear, { transform: [{ rotate: '-16deg' }] }]} /><View style={[styles.ear, { transform: [{ rotate: '16deg' }] }]} /></View>
    <LinearGradient colors={['#73717f', '#4f4d58', '#2f3038']} style={styles.catFace}>
      <View style={styles.eyeRow}><View style={styles.eye}><View style={styles.pupil} /></View><View style={styles.eye}><View style={styles.pupil} /></View></View>
      <Text style={styles.nose}>◆</Text><View style={styles.neck}><Text style={styles.ai}>KIASHA AI</Text></View>
    </LinearGradient>
  </LinearGradient>;
}

function HorizonButton({ value, current, onPress }: { value: InvestmentHorizon; current: InvestmentHorizon; onPress: () => void }) {
  const active = value === current;
  return <Pressable onPress={onPress} style={[styles.horizonButton, { backgroundColor: active ? Brand.primary : 'transparent', borderColor: active ? Brand.primary : '#4b5563' }]}><Text style={[styles.horizonText, { color: active ? '#fff' : '#b9c0d0' }]}>{value === 'short' ? 'کوتاه‌مدت' : 'بلندمدت'}</Text></Pressable>;
}

function PickCard({ pick, colors, index }: { pick: KiashaPicksResult['picks'][number]; colors: ThemeColors; index: number }) {
  return <Pressable onPress={() => router.push(`/stock/${encodeURIComponent(pick.code)}`)} style={[styles.pickCard, { backgroundColor: colors.backgroundElement }]}>
    <View style={styles.pickHead}><View style={styles.rank}><Text style={styles.rankText}>{index + 1}</Text></View><View style={styles.pickIdentity}><SymbolLogo symbol={pick.symbol} size={40} /><View style={{ flex: 1, alignItems: 'flex-end' }}><Text style={[styles.pickSymbol, { color: colors.text }]}>{pick.symbol}</Text><Text style={[styles.pickName, { color: colors.textSecondary }]} numberOfLines={1}>{pick.name}</Text></View></View></View>
    <View style={styles.pickMetrics}><Text style={[styles.pickMetric, { color: Brand.positive }]}>امتیاز کیا‌شا {pick.score.toFixed(2)}</Text><Text style={[styles.pickMetric, { color: colors.text }]}>{pick.price == null ? 'قیمت: —' : `${formatPrice(pick.price)} ریال`}</Text><Text style={[styles.source, { color: pick.source === 'live' ? Brand.positive : '#c9b7ff' }]}>{pick.source === 'live' ? 'LIVE + CODAL' : 'CODAL واقعی'}</Text></View>
    <Text style={[styles.reason, { color: colors.textSecondary }]} numberOfLines={3}>{pick.rationale}</Text>
  </Pressable>;
}

function PaperPerformance({ portfolio, colors }: { portfolio: PaperPortfolio | null; colors: ThemeColors }) {
  const pnl = portfolio?.totalUnrealizedPnLPct ?? null;
  const equity = portfolio && portfolio.totalMarketValue !== null ? (portfolio.cash ?? 0) + portfolio.totalMarketValue : null;
  return <View style={[styles.paperCard, { backgroundColor: colors.backgroundElement }]}>
    <View style={styles.paperHead}><Text style={styles.paperBadge}>PAPER</Text><Text style={[styles.paperTitle, { color: colors.text }]}>حساب Paper کیا‌شا</Text></View>
    <View style={styles.paperBalanceRow}><View style={styles.paperBalance}><Text style={[styles.balanceLabel, { color: colors.textSecondary }]}>قدرت خرید / نقد</Text><Text style={[styles.balanceValue, { color: Brand.primary }]}>{money(portfolio?.cash)} ریال</Text></View><View style={styles.paperBalance}><Text style={[styles.balanceLabel, { color: colors.textSecondary }]}>ارزش کل Paper</Text><Text style={[styles.balanceValue, { color: colors.text }]}>{money(equity)} ریال</Text></View></View>
    <Text style={[styles.paperBig, { color: pnl == null ? colors.textSecondary : pnl >= 0 ? Brand.positive : Brand.negative }]}>{pnl == null ? '—' : `${pnl >= 0 ? '+' : ''}${pnl.toLocaleString('fa-IR', { maximumFractionDigits: 2 })}٪`}</Text>
    <Text style={[styles.smallCopy, { color: colors.textSecondary }]}>{portfolio ? `${portfolio.pricedPositions.toLocaleString('fa-IR')} از ${portfolio.totalPositions.toLocaleString('fa-IR')} موقعیت قیمت معتبر دارند.` : 'حساب Paper فعلاً قابل دریافت نیست.'}</Text>
    <Pressable onPress={() => router.push('/portfolio')} style={styles.paperLink}><Text style={styles.paperLinkText}>مشاهده پرتفوی →</Text></Pressable>
  </View>;
}

function ComingSoonBanner({ colors }: { colors: ThemeColors }) {
  return <LinearGradient colors={['#2b174f', '#171a32']} style={styles.soonBanner}>
    <View style={styles.soonBadge}><Text style={styles.soonBadgeText}>SOON</Text></View>
    <View style={{ flex: 1, alignItems: 'flex-end' }}><Text style={[styles.soonTitle, { color: colors.text }]}>Auto Invest</Text><Text style={[styles.soonText, { color: colors.textSecondary }]}>خرید و فروش خودکار پس از تکمیل تست‌های ایمنی فعال می‌شود.</Text></View>
  </LinearGradient>;
}

function EngineNode({ agent, colors, pulse }: { agent: AgentPerformance; colors: ThemeColors; pulse: Animated.Value }) {
  const label = AGENT_LABELS[agent.agent] ?? { name: agent.agent, short: 'عامل کیا‌شا' };
  const active = agent.evaluatedCalls > 0 || agent.trustReady;
  const glow = active ? Brand.positive : '#7c3aed';
  const scale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, active ? 1.06 : 1.02] });
  const opacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [active ? .55 : .28, active ? 1 : .48] });
  return <View style={styles.engineNodeWrap}>
    <Animated.View style={[styles.engineNodeGlow, { borderColor: glow, opacity, transform: [{ scale }] }]} />
    <View style={[styles.engineNode, { backgroundColor: colors.backgroundSelected, borderColor: `${glow}99` }]}>
      <Text style={[styles.engineNodeName, { color: colors.text }]}>{label.name}</Text>
      <Text style={[styles.engineNodeShort, { color: colors.textSecondary }]}>{label.short}</Text>
      <Text style={[styles.engineNodeMetric, { color: active ? Brand.positive : '#a78bfa' }]}>{agent.evaluatedCalls.toLocaleString('fa-IR')} ارزیابی</Text>
    </View>
  </View>;
}

function KiashaEngine({ performance, colors, loading }: { performance: KiashaPerformanceSummary | null; colors: ThemeColors; loading: boolean }) {
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const animation = Animated.loop(Animated.sequence([
      Animated.timing(pulse, { toValue: 1, duration: 1100, useNativeDriver: true }),
      Animated.timing(pulse, { toValue: 0, duration: 1100, useNativeDriver: true }),
    ]));
    animation.start();
    return () => animation.stop();
  }, [pulse]);

  const agents = performance?.agents ?? [];
  const total = agents.reduce((sum, a) => sum + a.evaluatedCalls, 0);
  const activeCount = agents.filter(a => a.evaluatedCalls > 0 || a.trustReady).length;
  const lineOpacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [.24, .9] });

  return <View style={[styles.engineCard, { backgroundColor: colors.backgroundElement }]}>
    <View style={styles.engineHeader}><View style={[styles.liveChip, { backgroundColor: activeCount ? '#103d31' : '#2b2541' }]}><Text style={[styles.liveChipText, { color: activeCount ? Brand.positive : '#a78bfa' }]}>{activeCount ? '● ENGINE LIVE' : '● ENGINE READY'}</Text></View><View style={{ alignItems: 'flex-end' }}><Text style={[styles.engineTitle, { color: colors.text }]}>موتور کیا‌شا</Text><Text style={[styles.engineSubtitle, { color: colors.textSecondary }]}>۶ عامل متصل، یک تصمیم نهایی</Text></View></View>
    {loading ? <ActivityIndicator color={Brand.primary} style={{ marginVertical: 30 }} /> : performance ? <>
      <View style={styles.engineCanvas}>
        <Animated.View style={[styles.busLine, { opacity: lineOpacity }]} />
        <View style={styles.engineGrid}>{agents.map(agent => <EngineNode key={agent.agent} agent={agent} colors={colors} pulse={pulse} />)}</View>
        <View style={[styles.core, { backgroundColor: '#241151', borderColor: Brand.primary }]}><Text style={styles.coreK}>K</Text><Text style={styles.coreText}>KIASHA</Text></View>
        <Animated.View style={[styles.corePulse, { opacity: lineOpacity, transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.16] }) }] }]} />
      </View>
      <View style={styles.engineStats}><View style={styles.engineStat}><Text style={[styles.engineStatValue, { color: colors.text }]}>{total.toLocaleString('fa-IR')}</Text><Text style={[styles.engineStatLabel, { color: colors.textSecondary }]}>کل ارزیابی</Text></View><View style={styles.engineStat}><Text style={[styles.engineStatValue, { color: Brand.positive }]}>{activeCount.toLocaleString('fa-IR')} / ۶</Text><Text style={[styles.engineStatLabel, { color: colors.textSecondary }]}>عامل در تماس</Text></View><View style={styles.engineStat}><Text style={[styles.engineStatValue, { color: performance.observedTrustActive ? Brand.positive : '#a78bfa' }]}>{performance.observedTrustActive ? 'فعال' : 'یادگیری'}</Text><Text style={[styles.engineStatLabel, { color: colors.textSecondary }]}>اعتماد واقعی</Text></View></View>
      <Text style={[styles.engineNote, { color: colors.textSecondary }]}>خط‌های نورانی یعنی عامل‌ها در موتور تصمیم‌گیری کیا‌شا به یک هسته مشترک متصل‌اند. درخشش سبز با داده/ارزیابی واقعی بیشتر می‌شود؛ عامل بدون نمونه واقعی با وزن محافظه‌کارانه باقی می‌ماند.</Text>
    </> : <Text style={[styles.smallCopy, { color: colors.textSecondary }]}>گزارش موتور فعلاً در دسترس نیست.</Text>}
  </View>;
}

export default function KiashaScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [performance, setPerformance] = useState<KiashaPerformanceSummary | null>(null);
  const [paper, setPaper] = useState<PaperPortfolio | null>(null);
  const [horizon, setHorizon] = useState<InvestmentHorizon>('short');
  const [picks, setPicks] = useState<KiashaPicksResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [picksLoading, setPicksLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadBase = useCallback(async () => {
    const [p, portfolio] = await Promise.all([fetchKiashaPerformanceSummary(6_000), fetchPaperPortfolio()]);
    setPerformance(p); setPaper(portfolio); setLoading(false);
  }, []);
  const loadPicks = useCallback(async (force = false) => { setPicksLoading(true); try { setPicks(await fetchKiashaTopPicks(horizon, { force, scanLimit: 72 })); } finally { setPicksLoading(false); } }, [horizon]);
  useFocusEffect(useCallback(() => { loadBase(); }, [loadBase]));
  useEffect(() => { loadPicks(false); }, [loadPicks]);
  const refresh = async () => { setRefreshing(true); await Promise.all([loadBase(), loadPicks(true)]); setRefreshing(false); };

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={Brand.primary} />} contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}><View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
    <View style={styles.header}><Text style={[styles.title, { color: colors.text }]}>کیاشا AI</Text><Text style={[styles.sub, { color: colors.textSecondary }]}>پیشنهادها فقط از داده واقعی قابل‌تأیید ساخته می‌شوند؛ داده ناموجود ساخته نمی‌شود.</Text></View>
    <LinearGradient colors={['#341174', '#22104f', '#14162d']} style={styles.hero}><KiashaCat /><View style={styles.heroCopy}><Text style={styles.heroTitle}>موتور تصمیم‌گیری سرمایه‌گذاری</Text><Text style={styles.heroBody}>کیاشا شش عامل تحلیلی را هم‌زمان وزن می‌دهد و فقط از داده قابل‌تأیید برای رتبه‌بندی استفاده می‌کند.</Text><Pressable onPress={() => router.push('/market')} style={styles.cta}><Text style={styles.ctaText}>باز کردن کل بازار</Text></Pressable></View></LinearGradient>
    <View style={styles.horizonRow}><HorizonButton value="short" current={horizon} onPress={() => setHorizon('short')} /><HorizonButton value="long" current={horizon} onPress={() => setHorizon('long')} /></View>
    {!paper?.demo ? <ComingSoonBanner colors={colors} /> : null}
    <KiashaEngine performance={performance} colors={colors} loading={loading} />
    <View style={styles.sectionHead}><Pressable onPress={() => loadPicks(true)}><Text style={styles.refreshText}>به‌روزرسانی</Text></Pressable><Text style={[styles.section, { color: colors.text }]}>۱۰ پیشنهاد برتر امروز</Text></View>
    {picksLoading ? <View style={[styles.loadingCard, { backgroundColor: colors.backgroundElement }]}><ActivityIndicator color={Brand.primary} /><Text style={[styles.smallCopy, { color: colors.textSecondary }]}>در حال بررسی داده واقعی نمادها…</Text></View> : picks && picks.picks.length ? <>{picks.picks.map((pick, i) => <PickCard key={`${pick.symbol}-${i}`} pick={pick} colors={colors} index={i} />)}<Text style={[styles.coverage, { color: colors.textSecondary }]}>از {picks.scanned.toLocaleString('fa-IR')} نماد بررسی‌شده، {picks.verified.toLocaleString('fa-IR')} نماد داده کافی داشت. کیا‌شا گزینه ساختگی اضافه نمی‌کند.</Text></> : <View style={[styles.loadingCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.smallCopy, { color: colors.textSecondary }]}>فعلاً BUY معتبر کافی پیدا نشد. نتیجه خالی می‌ماند تا داده واقعی شرایط لازم را داشته باشد.</Text></View>}
    <PaperPerformance portfolio={paper} colors={colors} />
  </View></ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe:{flex:1},content:{paddingHorizontal:Spacing.three},header:{paddingTop:Spacing.four,paddingBottom:Spacing.three,alignItems:'flex-end'},title:{fontFamily:Fonts.sans,fontSize:24,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:11.5,marginTop:4,textAlign:'right'},
  hero:{borderRadius:Radius.lg,padding:Spacing.four,flexDirection:'row-reverse',gap:Spacing.three,alignItems:'center',marginBottom:Spacing.three,overflow:'hidden'},catShell:{width:108,height:132,borderRadius:50,alignItems:'center',justifyContent:'center',borderWidth:2,borderColor:'#7c3aed'},catEarRow:{position:'absolute',top:10,width:76,flexDirection:'row',justifyContent:'space-between'},ear:{width:25,height:32,backgroundColor:'#676572',borderTopLeftRadius:4,borderTopRightRadius:18,borderBottomLeftRadius:18,borderWidth:2,borderColor:'#8b5cf6'},catFace:{width:82,height:88,borderRadius:43,alignItems:'center',justifyContent:'center',borderWidth:1,borderColor:'#96939f'},eyeRow:{flexDirection:'row',gap:20,marginTop:7},eye:{width:17,height:17,borderRadius:9,backgroundColor:'#ffb13b',alignItems:'center',justifyContent:'center'},pupil:{width:5,height:10,borderRadius:3,backgroundColor:'#16131b'},nose:{color:'#f6a137',fontSize:11,marginTop:8},neck:{position:'absolute',bottom:7,backgroundColor:'#161827',borderRadius:8,paddingHorizontal:8,paddingVertical:4,borderWidth:1,borderColor:'#5b21b6'},ai:{color:'#d8ccff',fontFamily:Fonts.mono,fontSize:8,fontWeight:'900'},heroCopy:{flex:1,alignItems:'flex-end'},heroTitle:{color:'#fff',fontFamily:Fonts.sans,fontSize:18,fontWeight:'900',textAlign:'right'},heroBody:{color:'#d9d1ef',fontFamily:Fonts.sans,fontSize:11.5,lineHeight:19,textAlign:'right',marginTop:6},cta:{backgroundColor:'#7c3aed',borderRadius:12,paddingHorizontal:12,paddingVertical:9,marginTop:10},ctaText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},
  horizonRow:{flexDirection:'row-reverse',gap:Spacing.two,marginBottom:Spacing.two},horizonButton:{flex:1,borderWidth:1,borderRadius:Radius.sm,paddingVertical:10,alignItems:'center'},horizonText:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'900'},
  soonBanner:{borderRadius:Radius.md,paddingHorizontal:Spacing.three,paddingVertical:Spacing.two,flexDirection:'row',alignItems:'center',gap:Spacing.two,marginBottom:Spacing.three,borderWidth:1,borderColor:'#4c1d95'},soonBadge:{backgroundColor:'#6d28d9',borderRadius:10,paddingHorizontal:8,paddingVertical:4},soonBadgeText:{color:'#fff',fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},soonTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900'},soonText:{fontFamily:Fonts.sans,fontSize:9.5,marginTop:2,textAlign:'right'},
  engineCard:{borderRadius:Radius.lg,padding:Spacing.three,marginBottom:Spacing.three,borderWidth:1,borderColor:'#3b2a65',overflow:'hidden'},engineHeader:{flexDirection:'row',alignItems:'center',justifyContent:'space-between'},engineTitle:{fontFamily:Fonts.sans,fontSize:18,fontWeight:'900'},engineSubtitle:{fontFamily:Fonts.sans,fontSize:10.5,marginTop:2},liveChip:{borderRadius:12,paddingHorizontal:8,paddingVertical:5},liveChipText:{fontFamily:Fonts.mono,fontSize:8.5,fontWeight:'900'},engineCanvas:{marginTop:Spacing.three,minHeight:300,position:'relative',justifyContent:'center'},engineGrid:{flexDirection:'row-reverse',flexWrap:'wrap',justifyContent:'space-between',gap:12,zIndex:2},engineNodeWrap:{width:'30%',aspectRatio:1,alignItems:'center',justifyContent:'center',position:'relative'},engineNodeGlow:{position:'absolute',width:'94%',height:'94%',borderRadius:999,borderWidth:2,shadowColor:'#7c3aed',shadowOpacity:.9,shadowRadius:12,elevation:8},engineNode:{width:'82%',height:'82%',borderRadius:999,borderWidth:1.5,alignItems:'center',justifyContent:'center',padding:5},engineNodeName:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'900',textAlign:'center'},engineNodeShort:{fontFamily:Fonts.sans,fontSize:8.5,textAlign:'center',marginTop:2},engineNodeMetric:{fontFamily:Fonts.mono,fontSize:8,fontWeight:'800',marginTop:4},busLine:{position:'absolute',left:'12%',right:'12%',top:'50%',height:2,backgroundColor:'#7c3aed',shadowColor:'#8b5cf6',shadowOpacity:1,shadowRadius:8,elevation:6,zIndex:1},core:{position:'absolute',width:72,height:72,borderRadius:36,left:'50%',top:'50%',marginLeft:-36,marginTop:-36,zIndex:4,borderWidth:2,alignItems:'center',justifyContent:'center'},corePulse:{position:'absolute',width:86,height:86,borderRadius:43,left:'50%',top:'50%',marginLeft:-43,marginTop:-43,zIndex:3,borderWidth:2,borderColor:'#8b5cf6'},coreK:{color:'#fff',fontFamily:Fonts.mono,fontSize:24,fontWeight:'900'},coreText:{color:'#c4b5fd',fontFamily:Fonts.mono,fontSize:7,fontWeight:'900'},engineStats:{flexDirection:'row-reverse',gap:8,marginTop:Spacing.two},engineStat:{flex:1,backgroundColor:'#11162a',borderRadius:12,padding:9,alignItems:'center'},engineStatValue:{fontFamily:Fonts.mono,fontSize:13,fontWeight:'900'},engineStatLabel:{fontFamily:Fonts.sans,fontSize:8.5,marginTop:3},engineNote:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:17,textAlign:'right',marginTop:Spacing.two},
  sectionHead:{flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center',marginBottom:Spacing.two},section:{fontFamily:Fonts.sans,fontSize:17,fontWeight:'900',textAlign:'right',marginTop:Spacing.three,marginBottom:Spacing.two},refreshText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},loadingCard:{borderRadius:Radius.md,padding:Spacing.four,alignItems:'center',gap:Spacing.two},pickCard:{borderRadius:Radius.md,padding:Spacing.three,marginBottom:Spacing.two},pickHead:{flexDirection:'row-reverse',alignItems:'center',justifyContent:'space-between'},rank:{width:28,height:28,borderRadius:14,backgroundColor:'#6d28d9',alignItems:'center',justifyContent:'center'},rankText:{color:'#fff',fontFamily:Fonts.mono,fontWeight:'900'},pickIdentity:{flex:1,flexDirection:'row-reverse',alignItems:'center',gap:10,marginLeft:10},pickSymbol:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900'},pickName:{fontFamily:Fonts.sans,fontSize:10.5,marginTop:2},pickMetrics:{flexDirection:'row-reverse',flexWrap:'wrap',gap:10,marginTop:10},pickMetric:{fontFamily:Fonts.mono,fontSize:10.5},source:{fontFamily:Fonts.sans,fontSize:9.5,fontWeight:'800'},reason:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:17,textAlign:'right',marginTop:8},coverage:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:16,textAlign:'right',marginBottom:Spacing.two},smallCopy:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:18,textAlign:'right'},
  paperCard:{borderRadius:Radius.lg,padding:Spacing.four,marginTop:Spacing.four,alignItems:'flex-end'},paperHead:{width:'100%',flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center'},paperBadge:{color:'#fff',backgroundColor:'#7048e8',paddingHorizontal:8,paddingVertical:4,borderRadius:10,fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},paperTitle:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'900'},paperBalanceRow:{width:'100%',flexDirection:'row-reverse',gap:Spacing.two,marginTop:Spacing.three},paperBalance:{flex:1,alignItems:'flex-end'},balanceLabel:{fontFamily:Fonts.sans,fontSize:10},balanceValue:{fontFamily:Fonts.mono,fontSize:14,fontWeight:'900',marginTop:4},paperBig:{fontFamily:Fonts.mono,fontSize:30,fontWeight:'900',marginTop:10},paperLink:{marginTop:8},paperLinkText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},
});