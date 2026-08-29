import { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, useColorScheme, SafeAreaView, Pressable, ActivityIndicator, RefreshControl, Switch, Alert } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { router, useFocusEffect } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { AgentPerformance, fetchKiashaPerformanceSummary, formatPrice, KiashaPerformanceSummary } from '@/lib/api';
import { fetchKiashaTopPicks, InvestmentHorizon, KiashaPicksResult } from '@/lib/kiasha-picks';
import { fetchPaperPortfolio, PaperPortfolio } from '@/lib/paper-portfolio';
import { AutoInvestStatus, fetchAutoInvestStatus, updateAutoInvest } from '@/lib/auto-invest';
import { SymbolLogo } from '@/components/symbol-logo';

const AGENT_LABELS: Record<string, { name: string; desc: string }> = {
  fundamental: { name: 'بنیادی', desc: 'رشد درآمد، حاشیه سود و صورت‌های مالی CODAL' },
  risk: { name: 'ریسک', desc: 'نقدشوندگی، نوسان، افت سرمایه و کیفیت داده' },
  forecast: { name: 'پیش‌بینی', desc: 'مومنتوم قیمت، حجم و روند کوتاه‌مدت' },
  comparison: { name: 'مقایسه', desc: 'ارزش‌گذاری نسبی در برابر صنعت و سهام مشابه' },
  technical: { name: 'تکنیکال', desc: 'بازده ۱ هفته، ۱ ماه، ۳ ماه، ۱ سال و جایگاه در بازه ۵۲ هفته' },
  flow: { name: 'جریان پول', desc: 'ورود و خروج پول حقیقی و قدرت خرید/فروش سرانه' },
};

function pct(v: number | null) { return v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toLocaleString('fa-IR', { maximumFractionDigits: 1 })}٪`; }
function money(v: number | null | undefined) { return v == null || !Number.isFinite(v) ? '—' : Math.round(v).toLocaleString('fa-IR'); }

function AgentRow({ agent, colors }: { agent: AgentPerformance; colors: ThemeColors }) {
  const label = AGENT_LABELS[agent.agent] ?? { name: agent.agent, desc: 'عامل کیا‌شا' };
  return <View style={styles.agent}>
    <View style={styles.agentHead}><Text style={[styles.badge, { color: agent.trustReady ? Brand.positive : colors.textSecondary }]}>{agent.trustReady ? 'عملکرد واقعی فعال' : 'در انتظار نمونه واقعی'}</Text><Text style={[styles.agentName, { color: colors.text }]}>{label.name}</Text></View>
    <Text style={[styles.desc, { color: colors.textSecondary }]}>{label.desc}</Text>
    <View style={styles.metrics}><Text style={[styles.metric, { color: colors.text }]}>{agent.evaluatedCalls.toLocaleString('fa-IR')} ارزیابی</Text><Text style={[styles.metric, { color: colors.text }]}>{pct(agent.directionalAccuracy)} دقت مشاهده‌شده</Text></View>
  </View>;
}

function KiashaCat() {
  return <LinearGradient colors={['#29105f', '#13152b', '#070b17']} style={styles.catShell}>
    <View style={styles.catEarRow}><View style={[styles.ear, { transform: [{ rotate: '-16deg' }] }]} /><View style={[styles.ear, { transform: [{ rotate: '16deg' }] }]} /></View>
    <LinearGradient colors={['#73717f', '#4f4d58', '#2f3038']} style={styles.catFace}>
      <View style={styles.eyeRow}><View style={styles.eye}><View style={styles.pupil} /></View><View style={styles.eye}><View style={styles.pupil} /></View></View>
      <Text style={styles.nose}>◆</Text><View style={styles.mouth}><View style={styles.mouthLine} /><View style={[styles.mouthLine, { transform: [{ rotate: '35deg' }] }]} /><View style={[styles.mouthLine, { transform: [{ rotate: '-35deg' }] }]} /></View>
      <View style={styles.headsetL} /><View style={styles.headsetR} /><View style={styles.neck}><Text style={styles.ai}>KIASHA AI</Text></View>
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
    <Text style={[styles.desc, { color: colors.textSecondary }]}>{portfolio ? `${portfolio.pricedPositions.toLocaleString('fa-IR')} موقعیت قیمت‌گذاری‌شده از ${portfolio.totalPositions.toLocaleString('fa-IR')} موقعیت. موجودی از حساب server-owned Paper همین کاربر خوانده می‌شود.` : 'حساب Paper فعلاً قابل دریافت نیست.'}</Text>
    {portfolio && !portfolio.paperExecutionEnabled && !portfolio.demo ? <Text style={[styles.paperDisabled, { color: colors.textSecondary }]}>اجرای Paper روی سرور فعلاً خاموش است؛ فعال‌سازی Auto Invest به تنهایی این قفل ایمنی را دور نمی‌زند.</Text> : null}
    <Pressable onPress={() => router.push('/portfolio')} style={styles.paperLink}><Text style={styles.paperLinkText}>مشاهده پرتفوی و جزئیات →</Text></Pressable>
  </View>;
}

function AutoInvestCard({ status, colors, busy, onToggle, currentHorizon }: { status: AutoInvestStatus | null; colors: ThemeColors; busy: boolean; onToggle: (enabled: boolean) => void; currentHorizon: InvestmentHorizon }) {
  const ready = Boolean(status?.runnerEnabled && status?.paperExecutionEnabled);
  return <View style={[styles.autoCard, { backgroundColor: colors.backgroundElement }]}>
    <View style={styles.autoHead}>
      <Switch value={Boolean(status?.enabled)} disabled={busy || !status} onValueChange={onToggle} trackColor={{ false: '#4b5563', true: '#6d28d9' }} />
      <View style={{ flex: 1, alignItems: 'flex-end' }}><Text style={[styles.autoTitle, { color: colors.text }]}>Auto Invest — Paper</Text><Text style={[styles.autoBadge, { color: status?.enabled ? Brand.positive : colors.textSecondary }]}>{status?.enabled ? 'فعال برای این حساب' : 'خاموش'}</Text></View>
    </View>
    <Text style={[styles.desc, { color: colors.textSecondary }]}>با فعال‌سازی، کیا‌شا روزهای معاملاتی از موجودی واقعی Paper همین حساب استفاده می‌کند، گزینه‌های BUY را با داده تأییدشده رتبه‌بندی می‌کند، Claude را روی بهترین گزینه‌ها اجرا می‌کند و فقط پس از عبور از کنترل ریسک سفارش Paper می‌زند.</Text>
    <View style={styles.autoFacts}><Text style={[styles.autoFact, { color: colors.text }]}>حداکثر {status?.maxDailyTrades ?? 1} معامله در روز</Text><Text style={[styles.autoFact, { color: colors.text }]}>افق فعال: {(status?.enabled ? status.horizon : currentHorizon) === 'short' ? 'کوتاه‌مدت' : 'بلندمدت'}</Text></View>
    <Text style={[styles.autoState, { color: ready ? Brand.positive : '#f59e0b' }]}>{ready ? 'سرور آماده اجرای روزانه Paper است.' : 'حالت ایمن: Runner/اجرای Paper سرور هنوز فعال نشده است.'}</Text>
    {status?.latestRun ? <Text style={[styles.autoLast, { color: colors.textSecondary }]}>آخرین اجرا: {status.latestRun.tehranDay} · {status.latestRun.status}</Text> : <Text style={[styles.autoLast, { color: colors.textSecondary }]}>هنوز اجرای خودکار ثبت نشده است.</Text>}
  </View>;
}

export default function KiashaScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [performance, setPerformance] = useState<KiashaPerformanceSummary | null>(null);
  const [paper, setPaper] = useState<PaperPortfolio | null>(null);
  const [autoInvest, setAutoInvest] = useState<AutoInvestStatus | null>(null);
  const [autoBusy, setAutoBusy] = useState(false);
  const [horizon, setHorizon] = useState<InvestmentHorizon>('short');
  const [picks, setPicks] = useState<KiashaPicksResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [picksLoading, setPicksLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadBase = useCallback(async () => {
    const [p, portfolio, auto] = await Promise.all([fetchKiashaPerformanceSummary(6_000), fetchPaperPortfolio(), fetchAutoInvestStatus()]);
    setPerformance(p); setPaper(portfolio); setAutoInvest(auto); setLoading(false);
  }, []);
  const loadPicks = useCallback(async (force = false) => { setPicksLoading(true); try { setPicks(await fetchKiashaTopPicks(horizon, { force, scanLimit: 72 })); } finally { setPicksLoading(false); } }, [horizon]);
  useFocusEffect(useCallback(() => { loadBase(); }, [loadBase]));
  useEffect(() => { loadPicks(false); }, [loadPicks]);
  const refresh = async () => { setRefreshing(true); await Promise.all([loadBase(), loadPicks(true)]); setRefreshing(false); };
  const toggleAutoInvest = async (enabled: boolean) => {
    if (paper?.demo) { Alert.alert('Auto Invest', 'Auto Invest فقط روی حساب server-owned Paper اجرا می‌شود، نه کیف پول محلی Demo.'); return; }
    setAutoBusy(true);
    const updated = await updateAutoInvest({ enabled, horizon, maxDailyTrades: autoInvest?.maxDailyTrades ?? 1 });
    setAutoBusy(false);
    if (!updated) { Alert.alert('Auto Invest', 'تنظیمات روی سرور ذخیره نشد. اتصال یا ورود حساب را بررسی کنید.'); return; }
    setAutoInvest(updated);
  };

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={Brand.primary} />} contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}><View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
    <View style={styles.header}><Text style={[styles.title, { color: colors.text }]}>کیاشا AI</Text><Text style={[styles.sub, { color: colors.textSecondary }]}>پیشنهادها فقط از داده واقعی قابل‌تأیید ساخته می‌شوند؛ داده ناموجود ساخته نمی‌شود.</Text></View>
    <LinearGradient colors={['#341174', '#22104f', '#14162d']} style={styles.hero}><KiashaCat /><View style={styles.heroCopy}><Text style={styles.heroTitle}>سرمایه‌گذاری با افق انتخابی</Text><Text style={styles.heroBody}>کوتاه‌مدت روی مومنتوم، تکنیکال، جریان پول و ریسک وزن بیشتری می‌گیرد؛ بلندمدت روی بنیادی و مقایسه. کیا‌شا بازار را برای حداکثر ۱۰ گزینه BUY معتبر رتبه‌بندی می‌کند.</Text><Pressable onPress={() => router.push('/market')} style={styles.cta}><Text style={styles.ctaText}>باز کردن کل بازار</Text></Pressable></View></LinearGradient>
    <View style={styles.horizonRow}><HorizonButton value="short" current={horizon} onPress={() => setHorizon('short')} /><HorizonButton value="long" current={horizon} onPress={() => setHorizon('long')} /></View>
    {!paper?.demo ? <AutoInvestCard status={autoInvest} colors={colors} busy={autoBusy} onToggle={toggleAutoInvest} currentHorizon={horizon} /> : null}
    <View style={styles.sectionHead}><Pressable onPress={() => loadPicks(true)}><Text style={styles.refreshText}>به‌روزرسانی</Text></Pressable><Text style={[styles.section, { color: colors.text }]}>۱۰ پیشنهاد برتر امروز</Text></View>
    {picksLoading ? <View style={[styles.loadingCard, { backgroundColor: colors.backgroundElement }]}><ActivityIndicator color={Brand.primary} /><Text style={[styles.desc, { color: colors.textSecondary }]}>در حال بررسی داده واقعی نمادها…</Text></View> : picks && picks.picks.length ? <>{picks.picks.map((pick, i) => <PickCard key={`${pick.symbol}-${i}`} pick={pick} colors={colors} index={i} />)}<Text style={[styles.coverage, { color: colors.textSecondary }]}>از {picks.scanned.toLocaleString('fa-IR')} نماد بررسی‌شده، {picks.verified.toLocaleString('fa-IR')} نماد داده کافی داشت. اگر کمتر از ۱۰ BUY معتبر باشد، کیا‌شا گزینه ساختگی اضافه نمی‌کند. برای شروع می‌توانید فقط دو رتبه اول کوتاه‌مدت را دستی تست کنید.</Text></> : <View style={[styles.loadingCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.desc, { color: colors.textSecondary }]}>فعلاً BUY معتبر کافی پیدا نشد. نتیجه خالی می‌ماند تا داده واقعی شرایط لازم را داشته باشد.</Text></View>}
    <PaperPerformance portfolio={paper} colors={colors} />
    <Text style={[styles.section, { color: colors.text }]}>عملکرد واقعی ۶ عامل کیا‌شا</Text>
    <View style={[styles.panel, { backgroundColor: colors.backgroundElement }]}>{loading ? <ActivityIndicator color={Brand.primary} /> : performance ? <><View style={[styles.status, { backgroundColor: performance.observedTrustActive ? '#143b31' : '#242938' }]}><Text style={{ color: performance.observedTrustActive ? Brand.positive : colors.textSecondary, fontFamily: Fonts.sans, fontWeight: '800', textAlign: 'center' }}>{performance.observedTrustActive ? 'وزن‌دهی از عملکرد مشاهده‌شده واقعی استفاده می‌کند' : 'عامل‌های جدید تا جمع شدن نمونه واقعی با وزن محافظه‌کارانه شروع می‌کنند'}</Text></View>{performance.agents.map((a) => <AgentRow key={a.agent} agent={a} colors={colors} />)}</> : <Text style={[styles.desc, { color: colors.textSecondary }]}>گزارش عملکرد فعلاً در دسترس نیست.</Text>}</View>
  </View></ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe:{flex:1},content:{paddingHorizontal:Spacing.three},header:{paddingTop:Spacing.four,paddingBottom:Spacing.three,alignItems:'flex-end'},title:{fontFamily:Fonts.sans,fontSize:24,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:11.5,marginTop:4,textAlign:'right'},
  hero:{borderRadius:Radius.lg,padding:Spacing.four,flexDirection:'row-reverse',gap:Spacing.three,alignItems:'center',marginBottom:Spacing.three,overflow:'hidden'},catShell:{width:118,height:146,borderRadius:54,alignItems:'center',justifyContent:'center',borderWidth:2,borderColor:'#7c3aed'},catEarRow:{position:'absolute',top:12,width:82,flexDirection:'row',justifyContent:'space-between'},ear:{width:27,height:36,backgroundColor:'#676572',borderTopLeftRadius:4,borderTopRightRadius:18,borderBottomLeftRadius:18,borderWidth:2,borderColor:'#8b5cf6'},catFace:{width:88,height:96,borderRadius:45,alignItems:'center',justifyContent:'center',borderWidth:1,borderColor:'#96939f'},eyeRow:{flexDirection:'row',gap:22,marginTop:7},eye:{width:18,height:18,borderRadius:9,backgroundColor:'#ffb13b',alignItems:'center',justifyContent:'center'},pupil:{width:5,height:11,borderRadius:3,backgroundColor:'#16131b'},nose:{color:'#f6a137',fontSize:12,marginTop:8},mouth:{height:12,width:26,alignItems:'center'},mouthLine:{position:'absolute',top:2,width:10,height:1.5,backgroundColor:'#ddd6e5'},headsetL:{position:'absolute',left:7,top:54,width:13,height:33,borderRadius:8,backgroundColor:'#6d28d9',borderWidth:2,borderColor:'#a78bfa'},headsetR:{position:'absolute',right:7,top:54,width:13,height:33,borderRadius:8,backgroundColor:'#6d28d9',borderWidth:2,borderColor:'#a78bfa'},neck:{position:'absolute',bottom:7,backgroundColor:'#161827',borderRadius:8,paddingHorizontal:9,paddingVertical:4,borderWidth:1,borderColor:'#5b21b6'},ai:{color:'#d8ccff',fontFamily:Fonts.mono,fontSize:8,fontWeight:'900'},
  heroCopy:{flex:1,alignItems:'flex-end'},heroTitle:{color:'#fff',fontFamily:Fonts.sans,fontSize:18,fontWeight:'900',textAlign:'right'},heroBody:{color:'#d9d1ef',fontFamily:Fonts.sans,fontSize:11.5,lineHeight:19,textAlign:'right',marginTop:6},cta:{backgroundColor:'#7c3aed',borderRadius:12,paddingHorizontal:12,paddingVertical:9,marginTop:10},ctaText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},
  horizonRow:{flexDirection:'row-reverse',gap:Spacing.two,marginBottom:Spacing.three},horizonButton:{flex:1,borderWidth:1,borderRadius:Radius.sm,paddingVertical:10,alignItems:'center'},horizonText:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'900'},sectionHead:{flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center',marginBottom:Spacing.two},section:{fontFamily:Fonts.sans,fontSize:17,fontWeight:'900',textAlign:'right',marginTop:Spacing.three,marginBottom:Spacing.two},refreshText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},
  autoCard:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.three,alignItems:'flex-end',borderWidth:1,borderColor:'#4c1d95'},autoHead:{width:'100%',flexDirection:'row',alignItems:'center',gap:12},autoTitle:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900'},autoBadge:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'800',marginTop:3},autoFacts:{width:'100%',flexDirection:'row-reverse',justifyContent:'space-between',gap:10,marginTop:10},autoFact:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'700'},autoState:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'900',textAlign:'right',marginTop:10},autoLast:{fontFamily:Fonts.mono,fontSize:9.5,textAlign:'right',marginTop:5},
  loadingCard:{borderRadius:Radius.md,padding:Spacing.four,alignItems:'center',gap:Spacing.two},pickCard:{borderRadius:Radius.md,padding:Spacing.three,marginBottom:Spacing.two},pickHead:{flexDirection:'row-reverse',alignItems:'center',justifyContent:'space-between'},rank:{width:28,height:28,borderRadius:14,backgroundColor:'#6d28d9',alignItems:'center',justifyContent:'center'},rankText:{color:'#fff',fontFamily:Fonts.mono,fontWeight:'900'},pickIdentity:{flex:1,flexDirection:'row-reverse',alignItems:'center',gap:10,marginLeft:10},pickSymbol:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900'},pickName:{fontFamily:Fonts.sans,fontSize:10.5,marginTop:2},pickMetrics:{flexDirection:'row-reverse',flexWrap:'wrap',gap:10,marginTop:10},pickMetric:{fontFamily:Fonts.mono,fontSize:10.5},source:{fontFamily:Fonts.sans,fontSize:9.5,fontWeight:'800'},reason:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:17,textAlign:'right',marginTop:8},coverage:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:16,textAlign:'right',marginBottom:Spacing.two},
  paperCard:{borderRadius:Radius.lg,padding:Spacing.four,marginTop:Spacing.four,alignItems:'flex-end'},paperHead:{width:'100%',flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center'},paperBadge:{color:'#fff',backgroundColor:'#7048e8',paddingHorizontal:8,paddingVertical:4,borderRadius:10,fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},paperTitle:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'900'},paperBalanceRow:{width:'100%',flexDirection:'row-reverse',gap:Spacing.two,marginTop:Spacing.three},paperBalance:{flex:1,alignItems:'flex-end'},balanceLabel:{fontFamily:Fonts.sans,fontSize:10},balanceValue:{fontFamily:Fonts.mono,fontSize:14,fontWeight:'900',marginTop:4},paperBig:{fontFamily:Fonts.mono,fontSize:30,fontWeight:'900',marginTop:10},paperDisabled:{fontFamily:Fonts.sans,fontSize:10.5,textAlign:'right',marginTop:6},paperLink:{marginTop:8},paperLinkText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},
  panel:{borderRadius:Radius.lg,padding:Spacing.three},status:{borderRadius:12,padding:10,alignItems:'center',marginBottom:Spacing.two},agent:{paddingVertical:Spacing.three,borderBottomWidth:StyleSheet.hairlineWidth,borderBottomColor:'#313852'},agentHead:{flexDirection:'row-reverse',justifyContent:'space-between'},agentName:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'900'},badge:{fontFamily:Fonts.sans,fontSize:10,fontWeight:'800'},desc:{fontFamily:Fonts.sans,fontSize:11.5,lineHeight:19,textAlign:'right',marginTop:5},metrics:{flexDirection:'row-reverse',gap:18,marginTop:8},metric:{fontFamily:Fonts.mono,fontSize:11},
});