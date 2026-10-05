import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { fetchGlobalModuleData, type GlobalModulePayload } from '@/lib/global-module-data';
import { getSelectedGlobalCompany } from '@/lib/global-company-selection';
import type { GlobalInstrument } from '@/lib/global-api';

const META: Record<string, { title: string; icon: string; description: string }> = {
  eda:{title:'EDA Explorer',icon:'🔬',description:'Exploratory analysis over normalized issuer facts and connected private data.'},
  sql:{title:'SQL / Data Query',icon:'🗄️',description:'Query-ready view of the normalized BIAP Global company schema.'},
  anomaly:{title:'Anomaly Detection',icon:'🚨',description:'Observed volatility, drawdown and unusual market behavior without synthetic values.'},
  forecast:{title:'Statistical Forecast',icon:'📉',description:'Time-series readiness, observed momentum and evidence-based forecasting inputs.'},
  'kpi-extract':{title:'KPI Extraction',icon:'🎯',description:'Extract available KPIs from the selected country’s official filings and market feed.'},
  'business-kpi':{title:'Business KPI',icon:'🎯',description:'Public issuer baseline plus optional private operating data.'},
  dashboard:{title:'BI Dashboard',icon:'📊',description:'Financial, market, risk and valuation KPIs for the selected issuer.'},
  governance:{title:'KPI Governance',icon:'📏',description:'KPI baseline with optional internal targets, owners and thresholds.'},
  report:{title:'Analytical Report',icon:'📋',description:'Evidence-backed summary built from the same normalized Global data.'},
  swot:{title:'SWOT + Competitors',icon:'⚔️',description:'Issuer strengths, weaknesses, valuation and risk signals grounded in evidence.'},
  'market-entry':{title:'Market Entry',icon:'🌍',description:'Company baseline from public evidence plus explicit target-market inputs.'},
  journey:{title:'Journey Map',icon:'🗺️',description:'Customer journey analysis requires private customer/process data.'},
  voc:{title:'VOC + Friction',icon:'💬',description:'Voice-of-customer analysis requires private feedback data.'},
  behavior:{title:'User Behavior',icon:'🧭',description:'Funnel, churn and usage behavior require private product/customer data.'},
  crm:{title:'CRM + Pipeline',icon:'👥',description:'Lead scoring and pipeline analysis require CRM or equivalent private data.'},
  campaign:{title:'Campaign Analysis',icon:'📣',description:'Public baseline can be combined with private campaign performance data.'},
  pricing:{title:'Smart Pricing',icon:'💰',description:'Product/service price, unit cost and volume data are required.'},
  plan:{title:'Business Plan',icon:'📄',description:'Financial baseline plus explicit business assumptions and market inputs.'},
  'executive-report':{title:'Executive Report',icon:'🧾',description:'Management-ready summary of financial, market, risk and evidence signals.'},
  'financial-model':{title:'Financial Model',icon:'📈',description:'Normalized official financial statements form the baseline; missing lines stay missing.'},
  scenario:{title:'Scenario Analysis',icon:'🔮',description:'Observed sensitivity inputs with explicit assumptions for forward scenarios.'},
  unit:{title:'Unit Economics',icon:'⚙️',description:'CAC, LTV and contribution economics require internal unit-level data.'},
  mbr:{title:'Monthly Business Review',icon:'🧾',description:'Public company baseline plus optional internal monthly operating data.'},
};

function toneColor(tone: string | undefined, normal: string) {
  if (tone === 'positive') return Brand.positive;
  if (tone === 'negative') return Brand.negative;
  return normal;
}

export default function ModuleDetailScreen() {
  const { key: rawKey } = useLocalSearchParams<{ key?: string }>();
  const key = String(rawKey || '');
  const info = META[key] || { title: 'BIAP Module', icon: '🧩', description: 'Global BIAP analysis module.' };
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [company, setCompany] = useState<GlobalInstrument | null>(null);
  const [payload, setPayload] = useState<GlobalModulePayload | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const selected = await getSelectedGlobalCompany();
    setCompany(selected);
    setPayload(await fetchGlobalModuleData(key, selected));
    setLoading(false);
  }, [key]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView contentContainerStyle={styles.content}><View style={styles.maxWidth}>
    <View style={styles.header}><Pressable onPress={() => router.back()} style={[styles.back,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.backText,{color:colors.text}]}>← Back</Text></Pressable><View style={styles.headerText}><Text style={[styles.title,{color:colors.text}]}>{info.icon} {info.title}</Text><Text style={[styles.subtitle,{color:colors.textSecondary}]}>{info.description}</Text></View></View>

    <View style={[styles.context,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.contextLabel,{color:Brand.primary}]}>ANALYSIS CONTEXT</Text><Text style={[styles.contextValue,{color:colors.text}]}>{company ? `${company.ticker} • ${company.name}` : 'No listed company selected'}</Text><Text style={[styles.contextSub,{color:colors.textSecondary}]}>{company ? `${company.country} • ${company.exchange} • ${company.currency}` : 'Select a stock from Market, or connect private company data for modules that require it.'}</Text><View style={styles.actions}><Pressable onPress={() => router.push('/market')} style={[styles.smallButton,{borderColor:Brand.positive}]}><Text style={[styles.smallButtonText,{color:Brand.positive}]}>Select stock</Text></Pressable><Pressable onPress={() => router.push({pathname:'/data-connect',params:{key}} as never)} style={[styles.smallButton,{borderColor:Brand.dataViolet}]}><Text style={[styles.smallButtonText,{color:Brand.dataViolet}]}>Connect private data</Text></Pressable></View></View>

    {loading ? <ActivityIndicator color={Brand.primary} style={{marginTop:40}}/> : payload ? <>
      <View style={[styles.sourceCard,{backgroundColor:colors.backgroundElement,borderColor:payload.evidenceStatus==='PASS'?Brand.positive:colors.backgroundSelected}]}><View style={styles.sourceHead}><Text style={[styles.sourceTitle,{color:colors.text}]}>{payload.available ? 'LIVE / VERIFIED INPUT' : payload.analysis ? 'PUBLIC BASELINE • PRIVATE INPUT REQUIRED' : 'INPUT REQUIRED'}</Text>{payload.evidenceStatus?<Text style={[styles.evidence,{color:payload.evidenceStatus==='PASS'?Brand.positive:payload.evidenceStatus==='WARN'?Brand.warning:Brand.negative}]}>{payload.evidenceStatus}</Text>:null}</View><Text style={[styles.sourceLabel,{color:colors.textSecondary}]}>{payload.sourceLabel}</Text><Text style={[styles.summary,{color:colors.textSecondary}]}>{payload.summary}</Text></View>

      {payload.metrics.length ? <View style={styles.metrics}>{payload.metrics.map((metric) => <View key={metric.label} style={[styles.metric,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.metricValue,{color:toneColor(metric.tone,colors.text)}]}>{metric.value}</Text><Text style={[styles.metricLabel,{color:colors.textSecondary}]}>{metric.label}</Text></View>)}</View> : null}

      {payload.bullets.length ? <View style={[styles.card,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.cardTitle,{color:colors.text}]}>Analysis evidence</Text>{payload.bullets.map((bullet,index)=><View key={`${index}-${bullet}`} style={styles.bullet}><View style={styles.dot}/><Text style={[styles.bulletText,{color:colors.textSecondary}]}>{bullet}</Text></View>)}</View> : null}

      {payload.note ? <View style={[styles.note,{borderColor:payload.available?colors.backgroundSelected:Brand.warning}]}><Text style={[styles.noteText,{color:colors.textSecondary}]}>{payload.note}</Text></View> : null}

      {!payload.available ? <Pressable onPress={() => router.push({pathname:'/data-connect',params:{key}} as never)} style={[styles.primary,{backgroundColor:Brand.primary}]}><Text style={styles.primaryText}>Connect required data</Text></Pressable> : null}

      {payload.analysis ? <View style={[styles.card,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.cardTitle,{color:colors.text}]}>Shared investment context</Text><Text style={[styles.summary,{color:colors.textSecondary}]}>This business/data module reads the same normalized issuer evidence as the investment engine. It does not silently write its private-company inputs back into Kiasha stock recommendations.</Text><Pressable onPress={() => router.push({pathname:'/stock/[code]',params:{code:payload.analysis?.ticker||company?.ticker||'',country:payload.analysis?.country||company?.country||'',exchange:payload.analysis?.exchange||company?.exchange||'',currency:payload.analysis?.currency||company?.currency||'',name:payload.analysis?.name||company?.name||''}} as never)} style={[styles.linkButton,{borderColor:Brand.primary}]}><Text style={styles.linkText}>Open full stock analysis</Text></Pressable></View> : null}
    </> : null}

    <Text style={[styles.disclaimer,{color:colors.textSecondary}]}>BIAP Global never fills missing official fields with invented production values. Private business data is kept separate from market recommendation evidence unless an explicit future model defines that integration.</Text>
  </View></ScrollView></SafeAreaView>;
}

const styles=StyleSheet.create({safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingTop:Spacing.three,paddingBottom:BottomTabInset+Spacing.six},maxWidth:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},header:{flexDirection:'row',alignItems:'flex-start',gap:12,marginBottom:Spacing.three},back:{paddingHorizontal:11,paddingVertical:8,borderRadius:18},backText:{fontFamily:Fonts.sans,fontSize:10,fontWeight:'800'},headerText:{flex:1},title:{fontFamily:Fonts.sans,fontSize:20,fontWeight:'900'},subtitle:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:16,marginTop:4},context:{borderRadius:Radius.lg,padding:Spacing.three},contextLabel:{fontFamily:Fonts.mono,fontSize:8,fontWeight:'900'},contextValue:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'900',marginTop:5},contextSub:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15,marginTop:3},actions:{flexDirection:'row',gap:8,marginTop:12},smallButton:{borderWidth:1,borderRadius:18,paddingHorizontal:10,paddingVertical:7},smallButtonText:{fontFamily:Fonts.sans,fontSize:9,fontWeight:'900'},sourceCard:{borderWidth:1,borderRadius:Radius.lg,padding:Spacing.four,marginTop:Spacing.three},sourceHead:{flexDirection:'row',justifyContent:'space-between',alignItems:'center'},sourceTitle:{fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},evidence:{fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},sourceLabel:{fontFamily:Fonts.mono,fontSize:8.5,marginTop:5},summary:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:17,marginTop:7},metrics:{flexDirection:'row',flexWrap:'wrap',gap:8,marginTop:Spacing.three},metric:{width:'31.5%',minHeight:92,borderRadius:Radius.md,padding:10,justifyContent:'center',alignItems:'center'},metricValue:{fontFamily:Fonts.mono,fontSize:14,fontWeight:'900',textAlign:'center'},metricLabel:{fontFamily:Fonts.sans,fontSize:8.5,textAlign:'center',marginTop:5},card:{borderRadius:Radius.lg,padding:Spacing.four,marginTop:Spacing.three},cardTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900'},bullet:{flexDirection:'row',gap:8,alignItems:'flex-start',marginTop:9},dot:{width:5,height:5,borderRadius:3,backgroundColor:Brand.primary,marginTop:5},bulletText:{flex:1,fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15},note:{borderWidth:1,borderRadius:Radius.md,padding:12,marginTop:Spacing.three},noteText:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15},primary:{minHeight:48,borderRadius:Radius.md,alignItems:'center',justifyContent:'center',marginTop:Spacing.three},primaryText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11,fontWeight:'900'},linkButton:{borderWidth:1,borderRadius:18,alignSelf:'flex-start',paddingHorizontal:11,paddingVertical:7,marginTop:10},linkText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:9,fontWeight:'900'},disclaimer:{fontFamily:Fonts.sans,fontSize:8.5,lineHeight:14,textAlign:'center',marginTop:Spacing.four}});