import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { DEMO_MODULES } from '@/demo/demo-data';
import { getDemoMode, setDemoMode } from '@/lib/demo-mode';
import { fetchRealModuleData, RealModulePayload } from '@/lib/real-module-data';

export default function ModuleDetailScreen() {
  const params = useLocalSearchParams<{ key?: string }>();
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [demoMode, setDemoModeState] = useState(false);
  const [real, setReal] = useState<RealModulePayload | null>(null);
  const [loadingReal, setLoadingReal] = useState(true);
  const key = typeof params.key === 'string' ? params.key : '';
  const module = DEMO_MODULES[key];

  useEffect(() => { getDemoMode().then(setDemoModeState); }, []);
  useEffect(() => {
    let mounted = true;
    setLoadingReal(true);
    fetchRealModuleData(key).then((payload) => { if (mounted) setReal(payload); }).finally(() => { if (mounted) setLoadingReal(false); });
    return () => { mounted = false; };
  }, [key]);

  const toggleDemo = async () => {
    const next = !demoMode;
    await setDemoMode(next);
    setDemoModeState(next);
  };

  const renderMetrics = (metrics: { label: string; value: string; delta?: string; tone?: 'positive' | 'negative' | 'neutral' }[]) => (
    <View style={styles.metricsRow}>
      {metrics.map((metric) => {
        const tone = metric.tone === 'positive' ? Brand.positive : metric.tone === 'negative' ? Brand.negative : colors.text;
        return <View key={metric.label} style={[styles.metric, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.metricValue, { color: tone }]}>{metric.value}</Text>{metric.delta ? <Text style={[styles.metricDelta, { color: tone }]}>{metric.delta}</Text> : null}<Text style={[styles.metricLabel, { color: colors.textSecondary }]}>{metric.label}</Text></View>;
      })}
    </View>
  );

  const renderBullets = (title: string, bullets: string[]) => (
    <View style={[styles.insightCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.insightTitle, { color: colors.text }]}>{title}</Text>{bullets.map((bullet) => <View key={bullet} style={styles.bulletRow}><Text style={[styles.bulletText, { color: colors.textSecondary }]}>{bullet}</Text><View style={styles.bulletDot} /></View>)}</View>
  );

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.six }]}><View style={styles.maxWidth}>
    <View style={styles.headerRow}><Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.backText, { color: colors.text }]}>←</Text></Pressable><View style={styles.headerText}><Text style={[styles.title, { color: colors.text }]}>{module?.icon ?? '🧩'} {module?.title ?? 'ماژول BIAP'}</Text><Text style={[styles.subtitle, { color: colors.textSecondary }]}>BIAP Mobile • Real Data First</Text></View></View>

    <View style={[styles.modeCard, { backgroundColor: colors.backgroundElement }]}><View style={{ flex: 1, alignItems: 'flex-end' }}><Text style={[styles.modeTitle, { color: colors.text }]}>{demoMode ? 'Demo Mode' : 'Real Mode'}</Text><Text style={[styles.modeText, { color: colors.textSecondary }]}>{demoMode ? 'داده نمونه کاملاً برچسب‌خورده نمایش داده می‌شود.' : 'فقط داده واقعی متصل نمایش داده می‌شود؛ مقدار ناموجود ساخته نمی‌شود.'}</Text></View><Pressable onPress={toggleDemo} style={[styles.toggle, { backgroundColor: demoMode ? '#7048e8' : Brand.stockGreen }]}><Text style={styles.toggleText}>{demoMode ? 'Demo' : 'واقعی'}</Text></Pressable></View>

    {!module ? <View style={[styles.empty, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.emptyTitle, { color: colors.text }]}>ماژول پیدا نشد</Text></View> : demoMode ? <>
      <View style={styles.demoBadge}><Text style={styles.demoBadgeText}>DEMO • داده نمونه</Text></View>
      <View style={[styles.hero, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.heroText, { color: colors.textSecondary }]}>{module.summary}</Text></View>
      {renderMetrics(module.metrics)}
      {renderBullets('خلاصه Demo', module.bullets)}
      <View style={[styles.disclaimer, { borderColor: '#7c5cff66' }]}><Text style={styles.disclaimerText}>این مقادیر ساختگی و فقط برای نمایش Demo هستند؛ در حساب واقعی جایگزین داده ناموجود نمی‌شوند.</Text></View>
    </> : loadingReal ? <View style={styles.loading}><ActivityIndicator color={Brand.primary} /><Text style={[styles.emptyBody, { color: colors.textSecondary }]}>در حال خواندن منابع واقعی BIAP...</Text></View> : real?.available ? <>
      <View style={styles.realBadge}><Text style={styles.realBadgeText}>LIVE • {real.sourceLabel}</Text></View>
      <View style={[styles.hero, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.heroText, { color: colors.textSecondary }]}>{real.summary}</Text></View>
      {renderMetrics(real.metrics)}
      {renderBullets('خلاصه داده واقعی', real.bullets)}
      {real.note ? <View style={[styles.realNote, { borderColor: Brand.stockGreen + '55' }]}><Text style={[styles.realNoteText, { color: colors.textSecondary }]}>{real.note}</Text></View> : null}
    </> : <View style={[styles.empty, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.emptyTitle, { color: colors.text }]}>برای این ماژول ورودی واقعی لازم است</Text><Text style={[styles.emptyBody, { color: colors.textSecondary }]}>{real?.note ?? 'منبع واقعی متصل در دسترس نیست.'}</Text><Text style={[styles.noFake, { color: Brand.stockGreen }]}>✓ بدون داده ساختگی</Text><Pressable onPress={() => router.push('/data-connect' as never)} style={styles.connectButton}><Text style={styles.connectButtonText}>اتصال منبع داده</Text></Pressable></View>}
  </View></ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingTop:Spacing.three},maxWidth:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},headerRow:{flexDirection:'row-reverse',alignItems:'center',gap:Spacing.three,marginBottom:Spacing.three},headerText:{flex:1,alignItems:'flex-end'},title:{fontFamily:Fonts.sans,fontSize:21,fontWeight:'800',textAlign:'right'},subtitle:{fontFamily:Fonts.sans,fontSize:11,marginTop:2},back:{width:38,height:38,borderRadius:19,alignItems:'center',justifyContent:'center'},backText:{fontSize:19},modeCard:{flexDirection:'row-reverse',alignItems:'center',gap:Spacing.three,borderRadius:Radius.md,padding:Spacing.three,marginBottom:Spacing.three},modeTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'800'},modeText:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:17,textAlign:'right',marginTop:3},toggle:{minWidth:62,paddingHorizontal:12,paddingVertical:8,borderRadius:18,alignItems:'center'},toggleText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},demoBadge:{alignSelf:'flex-end',backgroundColor:'#7048e8',borderRadius:14,paddingHorizontal:10,paddingVertical:5,marginBottom:Spacing.two},demoBadgeText:{color:'#fff',fontFamily:Fonts.mono,fontSize:10,fontWeight:'800'},realBadge:{alignSelf:'flex-end',backgroundColor:'#0f5132',borderRadius:14,paddingHorizontal:10,paddingVertical:5,marginBottom:Spacing.two},realBadgeText:{color:'#7ef7bc',fontFamily:Fonts.mono,fontSize:10,fontWeight:'800'},hero:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.three},heroText:{fontFamily:Fonts.sans,fontSize:13,lineHeight:23,textAlign:'right'},metricsRow:{flexDirection:'row-reverse',gap:Spacing.two,marginBottom:Spacing.three},metric:{flex:1,borderRadius:Radius.md,padding:Spacing.three,alignItems:'center',minHeight:108,justifyContent:'center'},metricValue:{fontFamily:Fonts.mono,fontSize:18,fontWeight:'800'},metricDelta:{fontFamily:Fonts.mono,fontSize:10,marginTop:2},metricLabel:{fontFamily:Fonts.sans,fontSize:10,textAlign:'center',marginTop:5},insightCard:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.three},insightTitle:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'800',textAlign:'right',marginBottom:Spacing.three},bulletRow:{flexDirection:'row-reverse',alignItems:'center',gap:8,marginBottom:9},bulletDot:{width:6,height:6,borderRadius:3,backgroundColor:Brand.primary},bulletText:{flex:1,fontFamily:Fonts.sans,fontSize:12,lineHeight:20,textAlign:'right'},disclaimer:{borderWidth:1,borderRadius:Radius.md,padding:Spacing.three,backgroundColor:'#7048e811'},disclaimerText:{color:'#b6a6ff',fontFamily:Fonts.sans,fontSize:10.5,lineHeight:18,textAlign:'right'},realNote:{borderWidth:1,borderRadius:Radius.md,padding:Spacing.three},realNoteText:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:18,textAlign:'right'},empty:{borderRadius:Radius.lg,padding:Spacing.four,alignItems:'center',marginTop:Spacing.four},emptyTitle:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'800',textAlign:'center'},emptyBody:{fontFamily:Fonts.sans,fontSize:12,lineHeight:21,textAlign:'center',marginTop:Spacing.two},noFake:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'800',marginTop:Spacing.three},connectButton:{backgroundColor:Brand.primary,borderRadius:Radius.md,paddingHorizontal:20,paddingVertical:11,marginTop:Spacing.three},connectButtonText:{color:'#fff',fontFamily:Fonts.sans,fontSize:12,fontWeight:'900'},loading:{paddingVertical:Spacing.six,alignItems:'center',gap:Spacing.two}
});