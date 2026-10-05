import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { Brand, BottomTabInset, Colors, Fonts, MaxContentWidth, Radius, Spacing, ThemeColors } from '@/constants/theme';
import { fetchKiashaPerformanceSummary, fetchPaperEquityHistory, KiashaPerformanceSummary, PaperEquitySnapshot } from '@/lib/api';
import { fetchPaperPortfolio, PaperPortfolio } from '@/lib/paper-portfolio';
import { AutoInvestStatus, fetchAutoInvestStatus, runAutoInvestNow, updateAutoInvest } from '@/lib/auto-invest';
import type { InvestmentHorizon } from '@/lib/kiasha-picks';

function runStatusFa(status?: string) {
  if (status === 'COMPLETED') return 'تکمیل شد';
  if (status === 'RETRYABLE') return 'قابل تلاش مجدد';
  if (status === 'RUNNING') return 'در حال اجرا';
  if (status === 'FAILED') return 'ناموفق';
  return status ?? '—';
}

function money(value: number | null | undefined) { return value == null || !Number.isFinite(value) ? '—' : `${Math.round(value).toLocaleString('fa-IR')} ریال`; }
function percent(value: number | null | undefined) { return value == null || !Number.isFinite(value) ? '—' : `${value >= 0 ? '+' : ''}${value.toLocaleString('fa-IR', { maximumFractionDigits: 2 })}٪`; }

const MS_PER_DAY = 24 * 60 * 60 * 1000;

// Real day-over-day return from the two most recent persisted snapshots.
// Needs at least 2 real points -- never interpolated or estimated.
function dailyReturnPct(snapshots: PaperEquitySnapshot[]): number | null {
  if (snapshots.length < 2) return null;
  const latest = snapshots[snapshots.length - 1];
  const prev = snapshots[snapshots.length - 2];
  if (!prev.totalEquity) return null;
  return ((latest.totalEquity - prev.totalEquity) / prev.totalEquity) * 100;
}

// Real ~30-day return, only once the snapshot history actually spans close
// to a month -- otherwise this would compare against too short a baseline
// and silently mislabel a few days of noise as a "monthly" number.
function monthlyReturnPct(snapshots: PaperEquitySnapshot[]): number | null {
  if (snapshots.length < 2) return null;
  const latest = snapshots[snapshots.length - 1];
  const latestDate = new Date(latest.snapshotDate).getTime();
  const oldest = snapshots[0];
  const oldestDate = new Date(oldest.snapshotDate).getTime();
  if ((latestDate - oldestDate) / MS_PER_DAY < 25) return null;
  const targetTime = latestDate - 30 * MS_PER_DAY;
  let reference = oldest;
  for (const s of snapshots) {
    if (new Date(s.snapshotDate).getTime() <= targetTime) reference = s;
  }
  if (!reference.totalEquity) return null;
  return ((latest.totalEquity - reference.totalEquity) / reference.totalEquity) * 100;
}

function EquityChart({ snapshots, colors }: { snapshots: PaperEquitySnapshot[]; colors: ThemeColors }) {
  const sample = useMemo(() => (snapshots.length <= 30 ? snapshots : snapshots.filter((_, i) => i % Math.ceil(snapshots.length / 30) === 0).slice(-30)), [snapshots]);
  if (sample.length < 2) return null;
  const values = sample.map((s) => s.totalEquity);
  const min = Math.min(...values), max = Math.max(...values), range = Math.max(1, max - min);
  const up = values.at(-1)! >= values[0];
  const accent = up ? Brand.positive : Brand.negative;
  const changePct = ((values.at(-1)! - values[0]) / values[0]) * 100;
  return (
    <View style={[styles.info, { backgroundColor: colors.backgroundElement }]}>
      <View style={styles.autoInvestHead}>
        <Text style={[styles.chartChange, { color: accent }]}>{up ? '▲' : '▼'} {Math.abs(changePct).toLocaleString('fa-IR', { maximumFractionDigits: 2 })}٪</Text>
        <Text style={[styles.infoTitle, { color: colors.text }]}>روند ارزش حساب Paper</Text>
      </View>
      <View style={styles.bars}>{sample.map((s, i) => (
        <View key={`${s.snapshotDate}-${i}`} style={[styles.bar, { height: 12 + ((s.totalEquity - min) / range) * 70, backgroundColor: accent, opacity: 0.35 + (i / sample.length) * 0.65 }]} />
      ))}</View>
    </View>
  );
}

export default function KiashaProfileScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [portfolio, setPortfolio] = useState<PaperPortfolio | null>(null);
  const [performance, setPerformance] = useState<KiashaPerformanceSummary | null>(null);
  const [autoInvest, setAutoInvest] = useState<AutoInvestStatus | null>(null);
  const [equityHistory, setEquityHistory] = useState<PaperEquitySnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [savingAutoInvest, setSavingAutoInvest] = useState(false);
  const [runningNow, setRunningNow] = useState(false);

  const load = useCallback(async () => {
    const [p, perf, ai, history] = await Promise.all([fetchPaperPortfolio(), fetchKiashaPerformanceSummary(6_000), fetchAutoInvestStatus(), fetchPaperEquityHistory(400, 8_000)]);
    setPortfolio(p); setPerformance(perf); setAutoInvest(ai); setEquityHistory(history?.items ?? []); setLoading(false); setRefreshing(false);
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const toggleAutoInvest = async () => {
    if (!autoInvest || autoInvest.authRequired || savingAutoInvest) return;
    setSavingAutoInvest(true);
    const next = await updateAutoInvest({ enabled: !autoInvest.enabled, horizon: autoInvest.horizon });
    if (next) setAutoInvest(next);
    setSavingAutoInvest(false);
  };
  const setAutoInvestHorizon = async (horizon: InvestmentHorizon) => {
    if (!autoInvest || autoInvest.authRequired || savingAutoInvest || horizon === autoInvest.horizon) return;
    setSavingAutoInvest(true);
    const next = await updateAutoInvest({ enabled: autoInvest.enabled, horizon });
    if (next) setAutoInvest(next);
    setSavingAutoInvest(false);
  };
  const runNow = async () => {
    if (runningNow) return;
    setRunningNow(true);
    await runAutoInvestNow();
    setAutoInvest(await fetchAutoInvestStatus());
    setRunningNow(false);
  };

  const managed = useMemo(() => {
    if (!portfolio) return null;
    return portfolio.totalCostBasis ?? portfolio.totalMarketValue;
  }, [portfolio]);
  const equity = portfolio && portfolio.totalMarketValue !== null ? (portfolio.cash ?? 0) + portfolio.totalMarketValue : null;
  const returnPct = portfolio?.totalUnrealizedPnLPct ?? null;
  const evaluated = performance?.evaluatedRecommendationsLowerBound ?? 0;
  const accuracyValues = performance?.agents.map((a) => a.directionalAccuracy).filter((x): x is number => x != null) ?? [];
  const avgAccuracy = accuracyValues.length ? accuracyValues.reduce((a, b) => a + b, 0) / accuracyValues.length : null;
  const dailyReturn = useMemo(() => dailyReturnPct(equityHistory), [equityHistory]);
  const monthlyReturn = useMemo(() => monthlyReturnPct(equityHistory), [equityHistory]);

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={Brand.primary} />} contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}><View style={styles.wrap}>
    <View style={styles.header}><Pressable onPress={() => router.back()}><Text style={styles.back}>← بازگشت</Text></Pressable><View style={{ alignItems: 'flex-end' }}><Text style={[styles.title, { color: colors.text }]}>پروفایل سرمایه‌گذاری کیا‌شا</Text><Text style={[styles.sub, { color: colors.textSecondary }]}>AI Agent • Track record شفاف قبل از سرمایه واقعی</Text></View></View>

    <View style={[styles.agentHero, { backgroundColor: colors.backgroundElement }]}><View style={styles.avatar}><Text style={styles.avatarText}>K</Text></View><View style={styles.identity}><Text style={[styles.agentName, { color: colors.text }]}>Kiasha Investment Agent</Text><Text style={[styles.role, { color: colors.textSecondary }]}>تحلیل بنیادی + ریسک + پیش‌بینی + مقایسه</Text><View style={styles.badges}><Text style={styles.paperBadge}>PAPER TRACK RECORD</Text><Text style={[styles.liveBadge, { color: Brand.positive }]}>REAL DATA</Text></View></View></View>

    {loading ? <ActivityIndicator color={Brand.primary} /> : <>
      <Text style={[styles.section, { color: colors.text }]}>سرمایه و عملکرد</Text>
      <View style={styles.grid}>
        <Metric title="سرمایه تحت مدیریت Paper" value={money(managed)} colors={colors} />
        <Metric title="ارزش کل حساب Paper" value={money(equity)} colors={colors} />
        <Metric title="قدرت خرید / نقد" value={money(portfolio?.cash)} colors={colors} />
        <Metric title="ارزش سهام" value={money(portfolio?.totalMarketValue)} colors={colors} />
        <Metric title="بازده فعلی Paper" value={percent(returnPct)} colors={colors} accent={returnPct == null ? undefined : returnPct >= 0 ? Brand.positive : Brand.negative} />
        <Metric title="موقعیت‌های قیمت‌گذاری‌شده" value={portfolio ? `${portfolio.pricedPositions.toLocaleString('fa-IR')} / ${portfolio.totalPositions.toLocaleString('fa-IR')}` : '—'} colors={colors} />
      </View>

      <Text style={[styles.section, { color: colors.text }]}>اعتبار تصمیم‌ها</Text>
      <View style={styles.grid}>
        <Metric title="پیشنهادهای ارزیابی‌شده" value={evaluated.toLocaleString('fa-IR')} colors={colors} />
        <Metric title="میانگین دقت مشاهده‌شده" value={avgAccuracy == null ? '—' : `${(avgAccuracy * 100).toLocaleString('fa-IR', { maximumFractionDigits: 1 })}٪`} colors={colors} />
        <Metric title="بازده روزانه" value={dailyReturn == null ? 'در حال جمع‌آوری' : percent(dailyReturn)} colors={colors} accent={dailyReturn == null ? undefined : dailyReturn >= 0 ? Brand.positive : Brand.negative} />
        <Metric title="بازده ماهانه" value={monthlyReturn == null ? 'در حال جمع‌آوری' : percent(monthlyReturn)} colors={colors} accent={monthlyReturn == null ? undefined : monthlyReturn >= 0 ? Brand.positive : Brand.negative} />
      </View>

      {equityHistory.length >= 2
        ? <EquityChart snapshots={equityHistory} colors={colors} />
        : <View style={[styles.info, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.infoTitle, { color: colors.text }]}>چرا روزانه و ماهانه هنوز عدد ندارد؟</Text><Text style={[styles.body, { color: colors.textSecondary }]}>برای این دو شاخص باید snapshotهای واقعی روزانه Paper ذخیره شوند. تا وقتی تاریخچه کافی جمع نشده (حداقل ۲ روز برای بازده روزانه، حدود یک ماه برای بازده ماهانه)، BIAP به‌جای تخمین یا نمودار ساختگی «در حال جمع‌آوری» نشان می‌دهد.</Text></View>}

      <Text style={[styles.section, { color: colors.text }]}>Auto Invest — Paper</Text>
      <View style={[styles.info, { backgroundColor: colors.backgroundElement }]}>
        <View style={styles.autoInvestHead}>
          <Pressable disabled={!autoInvest || autoInvest.authRequired || savingAutoInvest} onPress={toggleAutoInvest} style={[styles.autoInvestSwitch, { backgroundColor: autoInvest?.enabled ? Brand.positive : colors.backgroundSelected, opacity: !autoInvest || autoInvest.authRequired ? 0.5 : 1 }]}>
            <Text style={styles.autoInvestSwitchText}>{autoInvest?.enabled ? 'روشن' : 'خاموش'}</Text>
          </Pressable>
          <Text style={[styles.infoTitle, { color: colors.text }]}>اجرای خودکار Paper</Text>
        </View>
        <Text style={[styles.body, { color: colors.textSecondary }]}>
          {autoInvest?.authRequired
            ? 'برای فعال‌سازی Auto Invest ابتدا وارد حساب کاربری شوید.'
            : autoInvest && !(autoInvest.runnerEnabled && autoInvest.paperExecutionEnabled)
            ? 'Auto Invest فعلاً روی سرور غیرفعال است.'
            : 'هر روز معاملاتی تهران، کیا‌شا در پنجره بازگشایی، حساب Paper سرور شما را با پیشنهادهای تأییدشده و ریسک‌گیت قطعی، خودکار می‌چرخاند. حداکثر ۳ معامله Paper در روز، حداکثر ۱۵٪ سرمایه جدید در روز، حداکثر ۵٪ روی هر نماد. هیچ سفارشی به کارگزاری واقعی ارسال نمی‌شود.'}
        </Text>
        {autoInvest && !autoInvest.authRequired ? <>
          <View style={styles.horizonRow}>
            <Pressable onPress={() => setAutoInvestHorizon('short')} style={[styles.horizonChip, autoInvest.horizon === 'short' && styles.horizonChipActive]}><Text style={styles.horizonChipText}>کوتاه‌مدت</Text></Pressable>
            <Pressable onPress={() => setAutoInvestHorizon('long')} style={[styles.horizonChip, autoInvest.horizon === 'long' && styles.horizonChipActive]}><Text style={styles.horizonChipText}>بلندمدت</Text></Pressable>
          </View>
          {autoInvest.latestRun ? <Text style={[styles.body, { color: colors.textSecondary, marginTop: 8 }]}>آخرین اجرا ({autoInvest.latestRun.tehranDay}): {runStatusFa(autoInvest.latestRun.status)}</Text> : null}
          {autoInvest.enabled ? <Pressable disabled={runningNow} onPress={runNow} style={[styles.cta, { marginTop: 10 }]}><Text style={styles.ctaText}>{runningNow ? 'در حال اجرا…' : 'اجرای همین حالا'}</Text></Pressable> : null}
        </> : null}
      </View>

      <View style={[styles.info, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.infoTitle, { color: colors.text }]}>مسیر اعتماد به Agent</Text><Text style={[styles.body, { color: colors.textSecondary }]}>اول عملکرد کیا‌شا را در Paper Trade می‌بینی، بعد افق سرمایه‌گذاری را انتخاب می‌کنی، و فقط پس از اتصال رسمی کارگزاری و تأیید خود کاربر امکان واگذاری سفارش واقعی اضافه می‌شود. Paper Auto Invest اختیاری است و امروز هم قابل استفاده است؛ اجرای سفارش واقعی نزد کارگزاری همچنان قفل است.</Text><Pressable onPress={() => router.push('/kiasha')} style={styles.cta}><Text style={styles.ctaText}>دیدن پیشنهادهای کیا‌شا ←</Text></Pressable></View>
    </>}
  </View></ScrollView></SafeAreaView>;
}

function Metric({ title, value, colors, accent }: { title: string; value: string; colors: ThemeColors; accent?: string }) {
  return <View style={[styles.metric, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.metricValue, { color: accent ?? colors.text }]}>{value}</Text><Text style={[styles.metricTitle, { color: colors.textSecondary }]}>{title}</Text></View>;
}

const styles = StyleSheet.create({ safe:{flex:1},content:{paddingHorizontal:Spacing.three},wrap:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},header:{paddingTop:Spacing.four,paddingBottom:Spacing.three,flexDirection:'row',justifyContent:'space-between',alignItems:'center'},back:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},title:{fontFamily:Fonts.sans,fontSize:22,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:10.5,marginTop:3},agentHero:{borderRadius:Radius.lg,padding:Spacing.four,flexDirection:'row-reverse',alignItems:'center',gap:Spacing.three},avatar:{width:76,height:76,borderRadius:24,backgroundColor:'#6d28d9',alignItems:'center',justifyContent:'center'},avatarText:{color:'#fff',fontFamily:Fonts.mono,fontSize:34,fontWeight:'900'},identity:{flex:1,alignItems:'flex-end'},agentName:{fontFamily:Fonts.sans,fontSize:18,fontWeight:'900',textAlign:'right'},role:{fontFamily:Fonts.sans,fontSize:11,textAlign:'right',marginTop:4},badges:{flexDirection:'row-reverse',gap:7,marginTop:9},paperBadge:{color:'#fff',backgroundColor:'#7048e8',paddingHorizontal:7,paddingVertical:4,borderRadius:9,fontFamily:Fonts.mono,fontSize:8,fontWeight:'900'},liveBadge:{fontFamily:Fonts.mono,fontSize:8,fontWeight:'900',paddingVertical:4},section:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900',textAlign:'right',marginTop:Spacing.four,marginBottom:Spacing.two},grid:{flexDirection:'row-reverse',flexWrap:'wrap',gap:Spacing.two},metric:{width:'48%',minHeight:92,borderRadius:Radius.md,padding:Spacing.three,alignItems:'flex-end',justifyContent:'space-between'},metricValue:{fontFamily:Fonts.mono,fontSize:16,fontWeight:'900',textAlign:'right'},metricTitle:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:17,textAlign:'right'},info:{borderRadius:Radius.md,padding:Spacing.three,alignItems:'flex-end',marginTop:Spacing.three},infoTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'900'},body:{fontFamily:Fonts.sans,fontSize:11.5,lineHeight:20,textAlign:'right',marginTop:5},cta:{marginTop:Spacing.two},ctaText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},
  autoInvestHead:{width:'100%',flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center'},autoInvestSwitch:{paddingHorizontal:14,paddingVertical:8,borderRadius:16},autoInvestSwitchText:{color:'#fff',fontFamily:Fonts.mono,fontSize:10,fontWeight:'900'},horizonRow:{flexDirection:'row',gap:6,marginTop:10},horizonChip:{borderWidth:1,borderColor:'#4b5563',borderRadius:14,paddingHorizontal:10,paddingVertical:6},horizonChipActive:{backgroundColor:Brand.primary,borderColor:Brand.primary},horizonChipText:{color:'#fff',fontFamily:Fonts.sans,fontSize:9,fontWeight:'800'},
  chartChange:{fontFamily:Fonts.mono,fontSize:11,fontWeight:'900'},bars:{width:'100%',height:90,flexDirection:'row',alignItems:'flex-end',gap:3,marginTop:Spacing.three},bar:{flex:1,borderRadius:3,minWidth:2} });