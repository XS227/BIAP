import { useCallback, useState } from 'react';
import { Image, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BiapLogo, Brand, Colors, Fonts, Radius, Spacing, BottomTabInset, MaxContentWidth } from '@/constants/theme';
import { fetchGlobalStatus, type GlobalInstrument } from '@/lib/global-api';
import { getGlobalMarketSelection, type GlobalMarketSelection } from '@/lib/global-market-selection';
import { getSelectedGlobalCompany } from '@/lib/global-company-selection';

const shortcuts=[
  ['📈','Market','Browse the selected exchange and run Kiasha scan','/market'],
  ['🧠','Kiasha','Evidence-gated ranked stock ideas','/kiasha'],
  ['💼','Portfolio','Compare markets and build a global paper portfolio','/portfolio'],
  ['🧩','Modules','KPI, data, business and financial modules','/modules'],
] as const;

export default function HomeScreen(){
  const colors=useColorScheme()==='dark'?Colors.dark:Colors.light;
  const[market,setMarket]=useState<GlobalMarketSelection|null>(null);
  const[company,setCompany]=useState<GlobalInstrument|null>(null);
  const[status,setStatus]=useState<Record<string,unknown>|null>(null);
  useFocusEffect(useCallback(()=>{Promise.all([getGlobalMarketSelection(),getSelectedGlobalCompany(),fetchGlobalStatus()]).then(([m,c,s])=>{setMarket(m);setCompany(c);setStatus(s)});},[]));
  const apiOk=Boolean(status);
  const marketConfigured=Boolean(status?.marketProviderConfigured);
  const liveTrading=Boolean(status?.liveTrading);
  return <SafeAreaView style={[styles.safe,{backgroundColor:colors.background}]}><ScrollView contentContainerStyle={styles.content}><View style={styles.max}>
    <View style={styles.header}><Image source={BiapLogo} style={styles.logo} resizeMode="contain"/><View style={[styles.globalPill,{borderColor:Brand.primary}]}><Text style={styles.globalPillText}>GLOBAL</Text></View></View>

    <View style={[styles.hero,{backgroundColor:colors.backgroundElement,borderColor:colors.backgroundSelected}]}><Text style={styles.kicker}>BUSINESS & INVESTMENT ANALYSIS PLATFORM</Text><Text style={[styles.title,{color:colors.text}]}>BIAP Global</Text><Text style={[styles.body,{color:colors.textSecondary}]}>One BIAP engine across connected markets: six scoring agents — Fundamental, Risk, Forecast, Comparison, Quality and Liquidity — plus Evidence/Verification and Portfolio construction.</Text><View style={styles.heroActions}><Pressable onPress={()=>router.push('/market')} style={[styles.primary,{backgroundColor:Brand.primary}]}><Text style={styles.primaryText}>Open Market</Text></Pressable><Pressable onPress={()=>router.push('/global')} style={[styles.secondary,{borderColor:Brand.primary}]}><Text style={styles.secondaryText}>Change country</Text></Pressable></View></View>

    <Text style={[styles.section,{color:colors.text}]}>Current context</Text>
    <View style={[styles.context,{backgroundColor:colors.backgroundElement}]}><View style={styles.contextBlock}><Text style={[styles.label,{color:colors.textSecondary}]}>COUNTRY / EXCHANGE</Text><Text style={[styles.value,{color:colors.text}]}>{market?`${market.countryName} • ${market.exchangeLabel}`:'Loading…'}</Text><Text style={[styles.meta,{color:colors.textSecondary}]}>{market?`${market.mic||market.exchange} • ${market.currency}`:''}</Text></View><View style={[styles.divider,{backgroundColor:colors.backgroundSelected}]}/><View style={styles.contextBlock}><Text style={[styles.label,{color:colors.textSecondary}]}>SELECTED COMPANY</Text><Text style={[styles.value,{color:company?colors.text:colors.textSecondary}]}>{company?`${company.ticker} • ${company.name}`:'No stock selected'}</Text><Text style={[styles.meta,{color:colors.textSecondary}]}>{company?`${company.country} • ${company.exchange}`:'Choose a stock from Market or Kiasha for cross-module analysis.'}</Text></View></View>

    <Text style={[styles.section,{color:colors.text}]}>Core workflows</Text>
    <View style={styles.grid}>{shortcuts.map(([icon,title,sub,href])=><Pressable key={title} onPress={()=>router.push(href as never)} style={[styles.card,{backgroundColor:colors.backgroundElement}]}><Text style={styles.icon}>{icon}</Text><Text style={[styles.cardTitle,{color:colors.text}]}>{title}</Text><Text style={[styles.cardText,{color:colors.textSecondary}]}>{sub}</Text></Pressable>)}</View>

    <Text style={[styles.section,{color:colors.text}]}>System status</Text>
    <View style={styles.statusRow}><View style={[styles.status,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.statusValue,{color:apiOk?Brand.positive:Brand.warning}]}>{apiOk?'ONLINE':'CHECK'}</Text><Text style={[styles.statusLabel,{color:colors.textSecondary}]}>Global API</Text></View><View style={[styles.status,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.statusValue,{color:marketConfigured?Brand.positive:Brand.warning}]}>{marketConfigured?'READY':'KEY'}</Text><Text style={[styles.statusLabel,{color:colors.textSecondary}]}>Market feed</Text></View><View style={[styles.status,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.statusValue,{color:liveTrading?Brand.positive:colors.textSecondary}]}>{liveTrading?'ON':'OFF'}</Text><Text style={[styles.statusLabel,{color:colors.textSecondary}]}>Live broker</Text></View></View>

    <View style={[styles.notice,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.noticeTitle,{color:colors.text}]}>Evidence before recommendation</Text><Text style={[styles.noticeText,{color:colors.textSecondary}]}>A missing filing, stale price, ambiguous entity, poor liquidity or high-confidence agent conflict can force NO_RECOMMENDATION. BIAP Global is designed to abstain rather than fill gaps with invented values.</Text></View>
  </View></ScrollView></SafeAreaView>;
}

const styles=StyleSheet.create({safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingBottom:BottomTabInset+Spacing.four},max:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},header:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',paddingTop:Spacing.three,marginBottom:14},logo:{width:104,height:38},globalPill:{borderWidth:1,borderRadius:30,paddingHorizontal:12,paddingVertical:6},globalPillText:{color:Brand.primary,fontFamily:Fonts.mono,fontWeight:'900',fontSize:10,letterSpacing:1.2},hero:{borderWidth:1,borderRadius:Radius.lg,padding:20},kicker:{color:Brand.primary,fontFamily:Fonts.mono,fontSize:8.5,fontWeight:'900',letterSpacing:1},title:{fontFamily:Fonts.sans,fontSize:30,fontWeight:'900',marginTop:7},body:{fontFamily:Fonts.sans,fontSize:11.5,lineHeight:19,marginTop:5},heroActions:{flexDirection:'row',gap:8,marginTop:16},primary:{flex:1,minHeight:46,borderRadius:Radius.md,alignItems:'center',justifyContent:'center'},primaryText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11,fontWeight:'900'},secondary:{flex:1,minHeight:46,borderRadius:Radius.md,borderWidth:1,alignItems:'center',justifyContent:'center'},secondaryText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:11,fontWeight:'900'},section:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'900',marginTop:20,marginBottom:8},context:{borderRadius:Radius.lg,padding:Spacing.three},contextBlock:{paddingVertical:4},label:{fontFamily:Fonts.mono,fontSize:8,fontWeight:'900'},value:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900',marginTop:4},meta:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:14,marginTop:3},divider:{height:1,marginVertical:10},grid:{flexDirection:'row',flexWrap:'wrap',gap:8},card:{width:'48.5%',minHeight:126,borderRadius:Radius.md,padding:Spacing.three},icon:{fontSize:22},cardTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900',marginTop:6},cardText:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15,marginTop:3},statusRow:{flexDirection:'row',gap:8},status:{flex:1,borderRadius:Radius.md,paddingVertical:14,alignItems:'center'},statusValue:{fontFamily:Fonts.mono,fontSize:13,fontWeight:'900'},statusLabel:{fontFamily:Fonts.sans,fontSize:8.5,marginTop:4},notice:{borderRadius:Radius.lg,padding:Spacing.four,marginTop:16},noticeTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900'},noticeText:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15,marginTop:5}});