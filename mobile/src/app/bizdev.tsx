import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { fetchWatchlist } from '@/lib/api';
import { computeMarketSummary } from '@/lib/market-stats';

const BUSINESS_MODULES = [
  { key: 'swot', icon: '⚔️', title: 'SWOT + رقبا', sub: 'جایگاه، نقاط قوت/ضعف و رقبا' },
  { key: 'crm', icon: '👥', title: 'CRM + Pipeline', sub: 'قیف فروش، فرصت‌ها و نرخ برد' },
  { key: 'journey', icon: '🗺️', title: 'Journey Map', sub: 'مسیر مشتری و نقاط اصطکاک' },
  { key: 'pricing', icon: '💰', title: 'قیمت‌گذاری', sub: 'سناریوهای قیمت و اثر روی درآمد' },
  { key: 'financial-model', icon: '📈', title: 'مدل مالی', sub: 'درآمد، هزینه، سود و سناریو' },
  { key: 'unit', icon: '⚙️', title: 'Unit Economics', sub: 'CAC، LTV و کیفیت رشد' },
] as const;

export default function BizDevScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [stocks, setStocks] = useState<Awaited<ReturnType<typeof fetchWatchlist>>>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(false);
      setStocks(await fetchWatchlist());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  const summary = useMemo(() => computeMarketSummary(stocks), [stocks]);
  const avgPositive = summary.avgChange >= 0;

  const openModule = (key: string) => router.push({ pathname: '/module', params: { key } } as never);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={Brand.secondary} />}
        contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}
      >
        <View style={styles.wrap}>
          <View style={styles.header}>
            <Text style={[styles.title, { color: colors.text }]}>تحلیل کسب‌وکار</Text>
            <Text style={[styles.sub, { color: colors.textSecondary }]}>Business Analysis Center</Text>
          </View>

          <View style={[styles.hero, { backgroundColor: colors.backgroundElement }]}>
            <Text style={styles.heroTag}>BUSINESS AI</Text>
            <Text style={[styles.heroTitle, { color: colors.text }]}>داده شرکت → تحلیل → تصمیم مدیریتی</Text>
            <Text style={[styles.heroBody, { color: colors.textSecondary }]}>برای تحلیل واقعی کسب‌وکار، BIAP به داده خود شرکت نیاز دارد. تا قبل از اتصال CSV/Excel، SQL، CRM/ERP یا API، هیچ KPI یا نتیجه ساختگی به‌عنوان داده واقعی نمایش داده نمی‌شود.</Text>
            <Pressable onPress={() => router.push('/data-connections' as never)} style={styles.primaryBtn}><Text style={styles.primaryBtnText}>اتصال داده شرکت</Text></Pressable>
          </View>

          <View style={styles.statusRow}>
            <View style={[styles.statusCard, { backgroundColor: colors.backgroundElement }]}><Text style={styles.live}>LIVE</Text><Text style={[styles.statusTitle, { color: colors.text }]}>بازار / CODAL / Kiasha</Text><Text style={[styles.statusText, { color: colors.textSecondary }]}>منابع مالی متصل BIAP</Text></View>
            <View style={[styles.statusCard, { backgroundColor: colors.backgroundElement }]}><Text style={styles.soon}>SOON</Text><Text style={[styles.statusTitle, { color: colors.text }]}>داده اختصاصی شرکت</Text><Text style={[styles.statusText, { color: colors.textSecondary }]}>CSV • SQL • CRM • API</Text></View>
          </View>

          <Text style={[styles.sectionTitle, { color: colors.text }]}>ابزارهای تحلیل کسب‌وکار</Text>
          <View style={styles.grid}>{BUSINESS_MODULES.map((m) => (
            <Pressable key={m.key} onPress={() => openModule(m.key)} style={[styles.module, { backgroundColor: colors.backgroundElement }]}>
              <Text style={styles.icon}>{m.icon}</Text><Text style={[styles.moduleTitle, { color: colors.text }]}>{m.title}</Text><Text style={[styles.moduleSub, { color: colors.textSecondary }]}>{m.sub}</Text>
            </Pressable>
          ))}</View>

          <View style={styles.sectionHead}><Pressable onPress={() => router.push('/market' as never)}><Text style={styles.link}>باز کردن بازار ←</Text></Pressable><Text style={[styles.sectionTitle, { color: colors.text }]}>نمای بازار متصل</Text></View>
          {loading ? <View style={[styles.marketCard, { backgroundColor: colors.backgroundElement }]}><ActivityIndicator color={Brand.secondary} /></View> : error ? <View style={[styles.marketCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.marketNote, { color: colors.textSecondary }]}>داده بازار فعلاً دریافت نشد. برای تلاش دوباره صفحه را پایین بکشید.</Text></View> : <View style={[styles.marketCard, { backgroundColor: colors.backgroundElement }]}>
            <View style={styles.marketStats}><View style={styles.marketMetric}><Text style={[styles.metricValue, { color: colors.text }]}>{summary.total.toLocaleString('fa-IR')}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>نمادهای متصل</Text></View><View style={styles.marketMetric}><Text style={[styles.metricValue, { color: Brand.stockGreen }]}>{summary.gainers.toLocaleString('fa-IR')}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>مثبت</Text></View><View style={styles.marketMetric}><Text style={[styles.metricValue, { color: Brand.negative }]}>{summary.losers.toLocaleString('fa-IR')}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>منفی</Text></View></View>
            <Text style={[styles.marketAvg, { color: avgPositive ? Brand.stockGreen : Brand.negative }]}>{avgPositive ? '▲' : '▼'} {Math.abs(summary.avgChange).toFixed(2)}٪ میانگین تغییر</Text>
            <Text style={[styles.marketNote, { color: colors.textSecondary }]}>این بخش فقط یک snapshot واقعی از منابع مالی متصل است؛ تحلیل کسب‌وکار شرکت شما پس از اتصال داده اختصاصی فعال می‌شود.</Text>
          </View>}

          <Pressable onPress={() => router.push('/modules' as never)} style={[styles.allModules, { borderColor: colors.backgroundSelected }]}><Text style={[styles.allModulesText, { color: colors.text }]}>مشاهده همه ماژول‌های BIAP</Text></Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:{flex:1},content:{paddingHorizontal:Spacing.three},wrap:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},header:{paddingTop:Spacing.four,paddingBottom:Spacing.three,alignItems:'flex-end'},title:{fontFamily:Fonts.sans,fontSize:24,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:11,marginTop:3},
  hero:{borderRadius:Radius.lg,padding:Spacing.four,alignItems:'flex-end'},heroTag:{fontFamily:Fonts.mono,fontSize:10,fontWeight:'900',color:Brand.secondary},heroTitle:{fontFamily:Fonts.sans,fontSize:19,fontWeight:'900',textAlign:'right',marginTop:7},heroBody:{fontFamily:Fonts.sans,fontSize:11.5,lineHeight:20,textAlign:'right',marginTop:7},primaryBtn:{backgroundColor:Brand.secondary,borderRadius:12,paddingHorizontal:14,paddingVertical:10,marginTop:12},primaryBtnText:{color:'#fff',fontFamily:Fonts.sans,fontSize:12,fontWeight:'900'},
  statusRow:{flexDirection:'row-reverse',gap:Spacing.two,marginTop:Spacing.three},statusCard:{flex:1,borderRadius:Radius.md,padding:Spacing.three,alignItems:'flex-end'},live:{fontFamily:Fonts.mono,fontSize:9,fontWeight:'900',color:Brand.stockGreen},soon:{fontFamily:Fonts.mono,fontSize:9,fontWeight:'900',color:'#f59e0b'},statusTitle:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'900',marginTop:4,textAlign:'right'},statusText:{fontFamily:Fonts.sans,fontSize:9.5,marginTop:3,textAlign:'right'},
  sectionTitle:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900',textAlign:'right',marginTop:Spacing.four,marginBottom:Spacing.two},grid:{flexDirection:'row-reverse',flexWrap:'wrap',gap:Spacing.two},module:{flexBasis:'48%',flexGrow:1,minHeight:128,borderRadius:Radius.md,padding:Spacing.three,alignItems:'flex-end'},icon:{fontSize:22},moduleTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900',textAlign:'right',marginTop:7},moduleSub:{fontFamily:Fonts.sans,fontSize:10,lineHeight:17,textAlign:'right',marginTop:4},
  sectionHead:{flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center'},link:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'800',color:Brand.secondary,marginTop:Spacing.four},marketCard:{borderRadius:Radius.lg,padding:Spacing.four},marketStats:{flexDirection:'row-reverse'},marketMetric:{flex:1,alignItems:'center'},metricValue:{fontFamily:Fonts.mono,fontSize:18,fontWeight:'900'},metricLabel:{fontFamily:Fonts.sans,fontSize:9.5,marginTop:4},marketAvg:{fontFamily:Fonts.mono,fontSize:13,fontWeight:'900',textAlign:'right',marginTop:Spacing.three},marketNote:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:18,textAlign:'right',marginTop:Spacing.two},allModules:{borderWidth:1,borderRadius:Radius.md,paddingVertical:12,alignItems:'center',marginTop:Spacing.three},allModulesText:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'800'}
});
