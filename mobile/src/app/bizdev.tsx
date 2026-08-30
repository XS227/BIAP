import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { fetchWatchlist } from '@/lib/api';
import { computeMarketSummary } from '@/lib/market-stats';
import { getBusinessDataset } from '@/lib/business-data';
import { getDemoMode } from '@/lib/demo-mode';

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
  const [companyConnected, setCompanyConnected] = useState(false);
  const [demoMode, setDemoModeState] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(false);
      const [watchlist, dataset, demo] = await Promise.all([fetchWatchlist(), getBusinessDataset(), getDemoMode()]);
      setStocks(watchlist);
      setCompanyConnected(Boolean(dataset?.rows.length));
      setDemoModeState(demo);
    } catch {
      setError(true);
      const [dataset, demo] = await Promise.all([getBusinessDataset(), getDemoMode()]);
      setCompanyConnected(Boolean(dataset?.rows.length));
      setDemoModeState(demo);
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
      <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={Brand.secondary} />} contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}>
        <View style={styles.wrap}>
          <View style={styles.header}><Text style={[styles.title, { color: colors.text }]}>تحلیل کسب‌وکار</Text><Text style={[styles.sub, { color: colors.textSecondary }]}>Business Analysis Center</Text></View>

          <View style={[styles.hero, { backgroundColor: colors.backgroundElement }]}>
            <Text style={styles.heroTag}>BUSINESS AI</Text>
            <Text style={[styles.heroTitle, { color: colors.text }]}>داده شرکت → تحلیل → تصمیم مدیریتی</Text>
            <Text style={[styles.heroBody, { color: colors.textSecondary }]}>{companyConnected ? 'داده اختصاصی شرکت متصل است و ماژول‌های کسب‌وکار می‌توانند در Real Mode روی همان dataset اجرا شوند.' : 'برای تحلیل واقعی کسب‌وکار، داده شرکت را از CSV/JSON/Excel وارد کنید. بدون داده واقعی، نتیجه ساختگی به‌عنوان LIVE نمایش داده نمی‌شود.'}</Text>
            <Pressable onPress={() => router.push('/data-connect' as never)} style={styles.primaryBtn}><Text style={styles.primaryBtnText}>{companyConnected ? 'مدیریت داده متصل' : 'اتصال داده شرکت'}</Text></Pressable>
          </View>

          <View style={styles.statusRow}>
            <View style={[styles.statusCard, { backgroundColor: colors.backgroundElement }]}><Text style={styles.live}>LIVE</Text><Text style={[styles.statusTitle, { color: colors.text }]}>بازار / CODAL / Kiasha</Text><Text style={[styles.statusText, { color: colors.textSecondary }]}>منابع مالی متصل BIAP</Text></View>
            <View style={[styles.statusCard, { backgroundColor: colors.backgroundElement }]}><Text style={{fontFamily:Fonts.mono,fontSize:9,fontWeight:'900',color:companyConnected?Brand.stockGreen:'#f59e0b'}}>{companyConnected ? 'CONNECTED' : 'NEEDS DATA'}</Text><Text style={[styles.statusTitle, { color: colors.text }]}>داده اختصاصی شرکت</Text><Text style={[styles.statusText, { color: colors.textSecondary }]}>{companyConnected ? 'CSV / JSON / Excel متصل' : 'برای Real Mode وارد کنید'}</Text></View>
          </View>
          <View style={[styles.modeStrip,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.modeText,{color:colors.textSecondary}]}>حالت فعلی ماژول‌ها</Text><Text style={[styles.modeValue,{color:demoMode?'#a78bfa':Brand.stockGreen}]}>{demoMode?'DEMO • داده نمونه':'REAL • فقط داده واقعی'}</Text></View>

          <Text style={[styles.sectionTitle, { color: colors.text }]}>ابزارهای تحلیل کسب‌وکار</Text>
          <View style={styles.grid}>{BUSINESS_MODULES.map((m) => (
            <Pressable key={m.key} onPress={() => openModule(m.key)} style={[styles.module, { backgroundColor: colors.backgroundElement }]}>
              <Text style={styles.icon}>{m.icon}</Text><Text style={[styles.moduleTitle, { color: colors.text }]}>{m.title}</Text><Text style={[styles.moduleSub, { color: colors.textSecondary }]}>{m.sub}</Text><Text style={[styles.moduleState,{color:demoMode?'#a78bfa':companyConnected?Brand.stockGreen:colors.textSecondary}]}>{demoMode?'DEMO':companyConnected?'LIVE DATA':'نیازمند داده'}</Text>
            </Pressable>
          ))}</View>

          <View style={styles.sectionHead}><Pressable onPress={() => router.push('/market' as never)}><Text style={styles.link}>باز کردن بازار ←</Text></Pressable><Text style={[styles.sectionTitle, { color: colors.text }]}>نمای بازار متصل</Text></View>
          {loading ? <View style={[styles.marketCard, { backgroundColor: colors.backgroundElement }]}><ActivityIndicator color={Brand.secondary} /></View> : error ? <View style={[styles.marketCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.marketNote, { color: colors.textSecondary }]}>داده بازار فعلاً دریافت نشد. برای تلاش دوباره صفحه را پایین بکشید.</Text></View> : <View style={[styles.marketCard, { backgroundColor: colors.backgroundElement }]}>
            <View style={styles.marketStats}><View style={styles.marketMetric}><Text style={[styles.metricValue, { color: colors.text }]}>{summary.total.toLocaleString('fa-IR')}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>نمادهای متصل</Text></View><View style={styles.marketMetric}><Text style={[styles.metricValue, { color: Brand.stockGreen }]}>{summary.gainers.toLocaleString('fa-IR')}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>مثبت</Text></View><View style={styles.marketMetric}><Text style={[styles.metricValue, { color: Brand.negative }]}>{summary.losers.toLocaleString('fa-IR')}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>منفی</Text></View></View>
            <Text style={[styles.marketAvg, { color: avgPositive ? Brand.stockGreen : Brand.negative }]}>{avgPositive ? '▲' : '▼'} {Math.abs(summary.avgChange).toFixed(2)}٪ میانگین تغییر</Text>
            <Text style={[styles.marketNote, { color: colors.textSecondary }]}>این بخش snapshot واقعی بازار است و از داده Demo برای پر کردن مقادیر استفاده نمی‌کند.</Text>
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
  statusRow:{flexDirection:'row-reverse',gap:Spacing.two,marginTop:Spacing.three},statusCard:{flex:1,borderRadius:Radius.md,padding:Spacing.three,alignItems:'flex-end'},live:{fontFamily:Fonts.mono,fontSize:9,fontWeight:'900',color:Brand.stockGreen},statusTitle:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'900',marginTop:4,textAlign:'right'},statusText:{fontFamily:Fonts.sans,fontSize:9.5,marginTop:3,textAlign:'right'},modeStrip:{marginTop:Spacing.two,borderRadius:Radius.md,padding:Spacing.three,flexDirection:'row-reverse',justifyContent:'space-between'},modeText:{fontFamily:Fonts.sans,fontSize:10.5},modeValue:{fontFamily:Fonts.mono,fontSize:10,fontWeight:'900'},
  sectionTitle:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900',textAlign:'right',marginTop:Spacing.four,marginBottom:Spacing.two},grid:{flexDirection:'row-reverse',flexWrap:'wrap',gap:Spacing.two},module:{flexBasis:'48%',flexGrow:1,minHeight:142,borderRadius:Radius.md,padding:Spacing.three,alignItems:'flex-end'},icon:{fontSize:22},moduleTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900',textAlign:'right',marginTop:7},moduleSub:{fontFamily:Fonts.sans,fontSize:10,lineHeight:17,textAlign:'right',marginTop:4},moduleState:{fontFamily:Fonts.mono,fontSize:8.5,fontWeight:'900',marginTop:8},
  sectionHead:{flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center'},link:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'800',color:Brand.secondary,marginTop:Spacing.four},marketCard:{borderRadius:Radius.lg,padding:Spacing.four},marketStats:{flexDirection:'row-reverse'},marketMetric:{flex:1,alignItems:'center'},metricValue:{fontFamily:Fonts.mono,fontSize:18,fontWeight:'900'},metricLabel:{fontFamily:Fonts.sans,fontSize:9.5,marginTop:4},marketAvg:{fontFamily:Fonts.mono,fontSize:13,fontWeight:'900',textAlign:'right',marginTop:Spacing.three},marketNote:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:18,textAlign:'right',marginTop:Spacing.two},allModules:{borderWidth:1,borderRadius:Radius.md,paddingVertical:12,alignItems:'center',marginTop:Spacing.three},allModulesText:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'800'}
});
