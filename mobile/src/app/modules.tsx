import { useCallback, useState } from 'react';
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing, ThemeColors } from '@/constants/theme';
import { getBusinessDataset } from '@/lib/business-data';
import { getSelectedGlobalCompany } from '@/lib/global-company-selection';
import { getGlobalMarketSelection, type GlobalMarketSelection } from '@/lib/global-market-selection';
import type { GlobalInstrument } from '@/lib/global-api';

type ModuleItem = { key: string; title: string; subtitle: string; icon: string; href?: '/market' | '/portfolio' | '/kiasha'; privateData?: boolean };
type ModuleGroup = { key: string; title: string; accent: string; items: ModuleItem[] };

const GROUPS: ModuleGroup[] = [
  { key: 'investment', title: 'Investment & Markets', accent: Brand.positive, items: [
    { key: 'market', title: 'Market & Stock Analysis', subtitle: 'Country-specific exchange universe and verified market data', icon: '📈', href: '/market' },
    { key: 'kiasha', title: 'Kiasha AI Agents', subtitle: 'Market scan, agent consensus and evidence-gated ideas', icon: '🧠', href: '/kiasha' },
    { key: 'portfolio', title: 'Portfolio Agent', subtitle: 'Capital allocation, FX, risk and concentration controls', icon: '💼', href: '/portfolio' },
  ]},
  { key: 'data', title: 'Data Analysis', accent: Brand.dataViolet, items: [
    { key: 'eda', title: 'EDA Explorer', subtitle: 'Explore normalized market and financial facts', icon: '🔬' },
    { key: 'sql', title: 'SQL / Data Query', subtitle: 'Query-ready normalized issuer context', icon: '🗄️' },
    { key: 'anomaly', title: 'Anomaly Detection', subtitle: 'Observed outliers, volatility and drawdown', icon: '🚨' },
    { key: 'forecast', title: 'Statistical Forecast', subtitle: 'Observed momentum and time-series readiness', icon: '📉' },
    { key: 'journey', title: 'Journey Map', subtitle: 'Customer journey and friction points', icon: '🗺️', privateData: true },
    { key: 'voc', title: 'VOC + Friction', subtitle: 'Voice of customer and root causes', icon: '💬', privateData: true },
    { key: 'behavior', title: 'User Behavior', subtitle: 'Funnel, churn and usage behavior', icon: '🧭', privateData: true },
  ]},
  { key: 'kpi', title: 'KPI & Dashboard', accent: Brand.primary, items: [
    { key: 'kpi-extract', title: 'KPI Extraction', subtitle: 'KPIs from official filings and market evidence', icon: '🎯' },
    { key: 'dashboard', title: 'BI Dashboard', subtitle: 'Issuer-level financial and market dashboard', icon: '📊' },
    { key: 'governance', title: 'KPI Governance', subtitle: 'Public baseline + optional internal targets/owners', icon: '📏' },
    { key: 'report', title: 'Analytical Report', subtitle: 'Evidence-backed issuer summary', icon: '📋' },
  ]},
  { key: 'business', title: 'Business Development', accent: Brand.secondary, items: [
    { key: 'business-kpi', title: 'Business KPI', subtitle: 'Public baseline + optional private operating data', icon: '🎯' },
    { key: 'swot', title: 'SWOT + Competitors', subtitle: 'Financial strength, risk and valuation signals', icon: '⚔️' },
    { key: 'market-entry', title: 'Market Entry', subtitle: 'Issuer baseline plus target-market inputs', icon: '🌍' },
    { key: 'crm', title: 'CRM + Pipeline', subtitle: 'Lead scoring and pipeline analysis', icon: '👥', privateData: true },
    { key: 'campaign', title: 'Campaign Analysis', subtitle: 'Public baseline + campaign data when connected', icon: '📣' },
    { key: 'pricing', title: 'Smart Pricing', subtitle: 'Product price, cost and volume analysis', icon: '💰', privateData: true },
    { key: 'plan', title: 'Business Plan', subtitle: 'Financial baseline with explicit business assumptions', icon: '📄' },
    { key: 'executive-report', title: 'Executive Report', subtitle: 'KPI, risk, valuation and evidence summary', icon: '🧾' },
  ]},
  { key: 'finance', title: 'Financial Modeling', accent: '#4b8cff', items: [
    { key: 'financial-model', title: 'Financial Model', subtitle: 'Normalized official financial statements', icon: '📈' },
    { key: 'scenario', title: 'Scenario Analysis', subtitle: 'Observed sensitivity inputs; assumptions stay explicit', icon: '🔮' },
    { key: 'unit', title: 'Unit Economics', subtitle: 'CAC, LTV and unit-level economics', icon: '⚙️', privateData: true },
    { key: 'mbr', title: 'Monthly Business Review', subtitle: 'Public baseline + internal monthly data', icon: '🧾' },
  ]},
];

function ModuleCard({ item, colors, accent, state }: { item: ModuleItem; colors: ThemeColors; accent: string; state: string }) {
  const open = () => item.href ? router.push(item.href) : router.push({ pathname: '/module', params: { key: item.key } } as never);
  return <Pressable onPress={open} style={({ pressed }) => [styles.moduleCard, { backgroundColor: colors.backgroundElement, opacity: pressed ? .75 : 1 }]}>
    <View style={[styles.moduleIcon, { backgroundColor: `${accent}22` }]}><Text style={styles.moduleEmoji}>{item.icon}</Text></View>
    <Text style={[styles.moduleTitle, { color: colors.text }]}>{item.title}</Text>
    <Text style={[styles.moduleSubtitle, { color: colors.textSecondary }]}>{item.subtitle}</Text>
    <Text style={[styles.state, { color: state.startsWith('LIVE') || state.startsWith('SELECTED') ? Brand.positive : state === 'PRIVATE DATA' ? Brand.dataViolet : colors.textSecondary }]}>{state}</Text>
  </Pressable>;
}

export default function ModulesScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [selected, setSelected] = useState<GlobalInstrument | null>(null);
  const [market, setMarket] = useState<GlobalMarketSelection | null>(null);
  const [hasPrivateData, setHasPrivateData] = useState(false);

  const refresh = useCallback(async () => {
    const [company, marketSelection, dataset] = await Promise.all([getSelectedGlobalCompany(), getGlobalMarketSelection(), getBusinessDataset()]);
    setSelected(company); setMarket(marketSelection); setHasPrivateData(Boolean(dataset?.rows?.length));
  }, []);
  useFocusEffect(useCallback(() => { void refresh(); }, [refresh]));

  const stateFor = (item: ModuleItem, group: string) => {
    if (group === 'investment') return 'LIVE GLOBAL';
    if (item.privateData) return hasPrivateData ? 'PRIVATE DATA' : 'PRIVATE DATA REQUIRED';
    if (selected) return `SELECTED • ${selected.ticker}`;
    if (hasPrivateData) return 'PRIVATE DATA';
    return 'SELECT A STOCK';
  };

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.six }]}><View style={styles.maxWidth}>
    <View style={styles.headerRow}><Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.backText, { color: colors.text }]}>←</Text></Pressable><View style={styles.headerText}><Text style={[styles.title, { color: colors.text }]}>BIAP Modules</Text><Text style={[styles.subtitle, { color: colors.textSecondary }]}>Same modules. Different country data adapters.</Text></View></View>

    <View style={[styles.hero, { backgroundColor: colors.backgroundElement }]}><Text style={styles.heroMark}>GLOBAL MODULE ENGINE</Text><Text style={[styles.heroTitle, { color: colors.text }]}>One module layer for every connected exchange</Text><Text style={[styles.heroBody, { color: colors.textSecondary }]}>Public modules consume the normalized issuer schema, so SEC, ESEF, EDINET, OpenDART, CODAL and other providers feed the same analysis code. Customer/CRM/product modules still require private company data.</Text></View>

    <View style={[styles.context, { backgroundColor: colors.backgroundElement }]}><View style={{ flex: 1 }}><Text style={[styles.contextLabel, { color: colors.textSecondary }]}>MARKET</Text><Text style={[styles.contextValue, { color: colors.text }]}>{market ? `${market.countryName} • ${market.exchangeLabel}` : 'Loading…'}</Text><Text style={[styles.contextLabel, { color: colors.textSecondary, marginTop: 8 }]}>SELECTED COMPANY</Text><Text style={[styles.contextValue, { color: selected ? colors.text : colors.textSecondary }]}>{selected ? `${selected.ticker} • ${selected.name}` : 'Open Market and select a stock'}</Text></View><View style={styles.contextActions}><Pressable onPress={() => router.push('/global')} style={[styles.smallButton, { borderColor: Brand.primary }]}><Text style={styles.smallButtonText}>Market</Text></Pressable><Pressable onPress={() => router.push('/market')} style={[styles.smallButton, { borderColor: Brand.positive }]}><Text style={[styles.smallButtonText, { color: Brand.positive }]}>Stock</Text></Pressable></View></View>

    {GROUPS.map((group) => <View key={group.key} style={styles.group}><View style={styles.groupHead}><View style={[styles.dot, { backgroundColor: group.accent }]} /><Text style={[styles.groupTitle, { color: colors.text }]}>{group.title}</Text></View><View style={styles.grid}>{group.items.map((item) => <ModuleCard key={item.key} item={item} colors={colors} accent={group.accent} state={stateFor(item, group.key)} />)}</View></View>)}

    <View style={[styles.info, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.infoTitle, { color: colors.text }]}>No fake fill-ins</Text><Text style={[styles.infoText, { color: colors.textSecondary }]}>If a country's filing adapter does not provide a field, the module shows it as unavailable. BIAP does not replace missing official data with an estimate unless a future model explicitly labels that estimate.</Text></View>
  </View></ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingTop:Spacing.three},maxWidth:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},headerRow:{flexDirection:'row',alignItems:'center',gap:Spacing.three,marginBottom:Spacing.three},headerText:{flex:1},title:{fontFamily:Fonts.sans,fontSize:22,fontWeight:'900'},subtitle:{fontFamily:Fonts.sans,fontSize:11,marginTop:3},back:{width:38,height:38,borderRadius:19,alignItems:'center',justifyContent:'center'},backText:{fontSize:19},hero:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.three},heroMark:{color:Brand.primary,fontFamily:Fonts.mono,fontSize:10,fontWeight:'900',marginBottom:7},heroTitle:{fontFamily:Fonts.sans,fontSize:19,fontWeight:'900',lineHeight:27},heroBody:{fontFamily:Fonts.sans,fontSize:11,lineHeight:18,marginTop:6},context:{borderRadius:Radius.lg,padding:Spacing.three,flexDirection:'row',gap:12,alignItems:'center'},contextLabel:{fontFamily:Fonts.mono,fontSize:8,fontWeight:'800'},contextValue:{fontFamily:Fonts.sans,fontSize:11.5,fontWeight:'800',marginTop:2},contextActions:{gap:7},smallButton:{borderWidth:1,borderRadius:18,paddingHorizontal:10,paddingVertical:7,alignItems:'center'},smallButtonText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:9,fontWeight:'900'},group:{marginTop:Spacing.four},groupHead:{flexDirection:'row',alignItems:'center',gap:8,marginBottom:Spacing.two},dot:{width:8,height:8,borderRadius:4},groupTitle:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900'},grid:{flexDirection:'row',flexWrap:'wrap',gap:8},moduleCard:{width:'48.5%',minHeight:142,borderRadius:Radius.md,padding:Spacing.three},moduleIcon:{width:38,height:38,borderRadius:Radius.sm,alignItems:'center',justifyContent:'center'},moduleEmoji:{fontSize:19},moduleTitle:{fontFamily:Fonts.sans,fontSize:12.5,fontWeight:'900',marginTop:8},moduleSubtitle:{fontFamily:Fonts.sans,fontSize:9,lineHeight:14,marginTop:3,minHeight:29},state:{fontFamily:Fonts.mono,fontSize:7.5,fontWeight:'800',marginTop:7},info:{borderRadius:Radius.lg,padding:Spacing.four,marginTop:Spacing.four},infoTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900'},infoText:{fontFamily:Fonts.sans,fontSize:10,lineHeight:16,marginTop:5}});