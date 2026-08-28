import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { Brand, BottomTabInset, Colors, Fonts, MaxContentWidth, Radius, Spacing, ThemeColors } from '@/constants/theme';
import { fetchKiashaPerformanceSummary, KiashaPerformanceSummary } from '@/lib/api';
import { fetchPaperPortfolio, PaperPortfolio } from '@/lib/paper-portfolio';

function money(value: number | null | undefined) { return value == null || !Number.isFinite(value) ? '—' : `${Math.round(value).toLocaleString('fa-IR')} ریال`; }
function percent(value: number | null | undefined) { return value == null || !Number.isFinite(value) ? '—' : `${value >= 0 ? '+' : ''}${value.toLocaleString('fa-IR', { maximumFractionDigits: 2 })}٪`; }

export default function KiashaProfileScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [portfolio, setPortfolio] = useState<PaperPortfolio | null>(null);
  const [performance, setPerformance] = useState<KiashaPerformanceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const [p, perf] = await Promise.all([fetchPaperPortfolio(), fetchKiashaPerformanceSummary(6_000)]);
    setPortfolio(p); setPerformance(perf); setLoading(false); setRefreshing(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const managed = useMemo(() => {
    if (!portfolio) return null;
    return portfolio.totalCostBasis ?? portfolio.totalMarketValue;
  }, [portfolio]);
  const returnPct = portfolio?.totalUnrealizedPnLPct ?? null;
  const evaluated = performance?.evaluatedRecommendationsLowerBound ?? 0;
  const accuracyValues = performance?.agents.map((a) => a.directionalAccuracy).filter((x): x is number => x != null) ?? [];
  const avgAccuracy = accuracyValues.length ? accuracyValues.reduce((a, b) => a + b, 0) / accuracyValues.length : null;

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={Brand.primary} />} contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}><View style={styles.wrap}>
    <View style={styles.header}><Pressable onPress={() => router.back()}><Text style={styles.back}>← بازگشت</Text></Pressable><View style={{ alignItems: 'flex-end' }}><Text style={[styles.title, { color: colors.text }]}>پروفایل سرمایه‌گذاری کیا‌شا</Text><Text style={[styles.sub, { color: colors.textSecondary }]}>AI Agent • Track record شفاف قبل از سرمایه واقعی</Text></View></View>

    <View style={[styles.agentHero, { backgroundColor: colors.backgroundElement }]}><View style={styles.avatar}><Text style={styles.avatarText}>K</Text></View><View style={styles.identity}><Text style={[styles.agentName, { color: colors.text }]}>Kiasha Investment Agent</Text><Text style={[styles.role, { color: colors.textSecondary }]}>تحلیل بنیادی + ریسک + پیش‌بینی + مقایسه</Text><View style={styles.badges}><Text style={styles.paperBadge}>PAPER TRACK RECORD</Text><Text style={[styles.liveBadge, { color: Brand.positive }]}>REAL DATA</Text></View></View></View>

    {loading ? <ActivityIndicator color={Brand.primary} /> : <>
      <Text style={[styles.section, { color: colors.text }]}>سرمایه و عملکرد</Text>
      <View style={styles.grid}>
        <Metric title="سرمایه تحت مدیریت Paper" value={money(managed)} colors={colors} />
        <Metric title="ارزش فعلی Paper" value={money(portfolio?.totalMarketValue)} colors={colors} />
        <Metric title="بازده فعلی Paper" value={percent(returnPct)} colors={colors} accent={returnPct == null ? undefined : returnPct >= 0 ? Brand.positive : Brand.negative} />
        <Metric title="موقعیت‌های قیمت‌گذاری‌شده" value={portfolio ? `${portfolio.pricedPositions.toLocaleString('fa-IR')} / ${portfolio.totalPositions.toLocaleString('fa-IR')}` : '—'} colors={colors} />
      </View>

      <Text style={[styles.section, { color: colors.text }]}>اعتبار تصمیم‌ها</Text>
      <View style={styles.grid}>
        <Metric title="پیشنهادهای ارزیابی‌شده" value={evaluated.toLocaleString('fa-IR')} colors={colors} />
        <Metric title="میانگین دقت مشاهده‌شده" value={avgAccuracy == null ? '—' : `${(avgAccuracy * 100).toLocaleString('fa-IR', { maximumFractionDigits: 1 })}٪`} colors={colors} />
        <Metric title="بازده روزانه" value="در حال جمع‌آوری" colors={colors} />
        <Metric title="بازده ماهانه" value="در حال جمع‌آوری" colors={colors} />
      </View>

      <View style={[styles.info, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.infoTitle, { color: colors.text }]}>چرا روزانه و ماهانه هنوز عدد ندارد؟</Text><Text style={[styles.body, { color: colors.textSecondary }]}>برای این دو شاخص باید snapshotهای واقعی روزانه Paper ذخیره شوند. تا وقتی تاریخچه کافی جمع نشده، BIAP به‌جای تخمین یا fallback ساختگی «در حال جمع‌آوری» نشان می‌دهد.</Text></View>

      <View style={[styles.info, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.infoTitle, { color: colors.text }]}>مسیر اعتماد به Agent</Text><Text style={[styles.body, { color: colors.textSecondary }]}>اول عملکرد کیا‌شا را در Paper Trade می‌بینی، بعد افق سرمایه‌گذاری را انتخاب می‌کنی، و فقط پس از اتصال رسمی کارگزاری و تأیید خود کاربر امکان واگذاری سفارش واقعی اضافه می‌شود. Auto-trading فعلاً قفل است.</Text><Pressable onPress={() => router.push('/kiasha')} style={styles.cta}><Text style={styles.ctaText}>دیدن پیشنهادهای کیا‌شا ←</Text></Pressable></View>
    </>}
  </View></ScrollView></SafeAreaView>;
}

function Metric({ title, value, colors, accent }: { title: string; value: string; colors: ThemeColors; accent?: string }) {
  return <View style={[styles.metric, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.metricValue, { color: accent ?? colors.text }]}>{value}</Text><Text style={[styles.metricTitle, { color: colors.textSecondary }]}>{title}</Text></View>;
}

const styles = StyleSheet.create({ safe:{flex:1},content:{paddingHorizontal:Spacing.three},wrap:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},header:{paddingTop:Spacing.four,paddingBottom:Spacing.three,flexDirection:'row',justifyContent:'space-between',alignItems:'center'},back:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},title:{fontFamily:Fonts.sans,fontSize:22,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:10.5,marginTop:3},agentHero:{borderRadius:Radius.lg,padding:Spacing.four,flexDirection:'row-reverse',alignItems:'center',gap:Spacing.three},avatar:{width:76,height:76,borderRadius:24,backgroundColor:'#6d28d9',alignItems:'center',justifyContent:'center'},avatarText:{color:'#fff',fontFamily:Fonts.mono,fontSize:34,fontWeight:'900'},identity:{flex:1,alignItems:'flex-end'},agentName:{fontFamily:Fonts.sans,fontSize:18,fontWeight:'900',textAlign:'right'},role:{fontFamily:Fonts.sans,fontSize:11,textAlign:'right',marginTop:4},badges:{flexDirection:'row-reverse',gap:7,marginTop:9},paperBadge:{color:'#fff',backgroundColor:'#7048e8',paddingHorizontal:7,paddingVertical:4,borderRadius:9,fontFamily:Fonts.mono,fontSize:8,fontWeight:'900'},liveBadge:{fontFamily:Fonts.mono,fontSize:8,fontWeight:'900',paddingVertical:4},section:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900',textAlign:'right',marginTop:Spacing.four,marginBottom:Spacing.two},grid:{flexDirection:'row-reverse',flexWrap:'wrap',gap:Spacing.two},metric:{width:'48%',minHeight:92,borderRadius:Radius.md,padding:Spacing.three,alignItems:'flex-end',justifyContent:'space-between'},metricValue:{fontFamily:Fonts.mono,fontSize:16,fontWeight:'900',textAlign:'right'},metricTitle:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:17,textAlign:'right'},info:{borderRadius:Radius.md,padding:Spacing.three,alignItems:'flex-end',marginTop:Spacing.three},infoTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'900'},body:{fontFamily:Fonts.sans,fontSize:11.5,lineHeight:20,textAlign:'right',marginTop:5},cta:{marginTop:Spacing.two},ctaText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'} });