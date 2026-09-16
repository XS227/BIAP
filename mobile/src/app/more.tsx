import { useCallback, useState } from 'react';
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import Constants from 'expo-constants';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing, ThemeColors } from '@/constants/theme';
import { getGlobalMarketSelection, type GlobalMarketSelection } from '@/lib/global-market-selection';
import { getSelectedGlobalCompany } from '@/lib/global-company-selection';
import type { GlobalInstrument } from '@/lib/global-api';

type Item = { icon:string; title:string; sub:string; onPress:()=>void; accent?:string };

function Row({item,colors}:{item:Item;colors:ThemeColors}){
  return <Pressable onPress={item.onPress} style={({pressed})=>[styles.row,{backgroundColor:colors.backgroundElement,opacity:pressed?.75:1}]}>
    <View style={[styles.icon,{backgroundColor:`${item.accent||Brand.primary}22`}]}><Text style={styles.emoji}>{item.icon}</Text></View>
    <View style={{flex:1}}><Text style={[styles.rowTitle,{color:colors.text}]}>{item.title}</Text><Text style={[styles.rowSub,{color:colors.textSecondary}]}>{item.sub}</Text></View><Text style={[styles.chevron,{color:colors.textSecondary}]}>›</Text>
  </Pressable>;
}

export default function MoreScreen(){
  const colors=useColorScheme()==='dark'?Colors.dark:Colors.light;
  const[market,setMarket]=useState<GlobalMarketSelection|null>(null);
  const[company,setCompany]=useState<GlobalInstrument|null>(null);
  useFocusEffect(useCallback(()=>{Promise.all([getGlobalMarketSelection(),getSelectedGlobalCompany()]).then(([m,c])=>{setMarket(m);setCompany(c)});},[]));
  const version=Constants.expoConfig?.version||'0.1.0';
  const items:Item[]=[
    {icon:'🧩',title:'BIAP Modules',sub:'Data, KPI, business development and financial modeling on the same Global issuer schema.',onPress:()=>router.push('/modules'),accent:Brand.primary},
    {icon:'🌍',title:'Country & Exchange',sub:market?`${market.countryName} • ${market.exchangeLabel}`:'Choose the market context used across BIAP.',onPress:()=>router.push('/global'),accent:'#0ea5e9'},
    {icon:'📈',title:'Selected Company',sub:company?`${company.ticker} • ${company.name}`:'Open Market and select a listed company for cross-module analysis.',onPress:()=>router.push('/market'),accent:Brand.positive},
    {icon:'🔌',title:'Private Data Connections',sub:'CSV/Excel and company data for CRM, pricing, journey, unit economics and internal KPIs.',onPress:()=>router.push('/data-connect' as never),accent:Brand.dataViolet},
    {icon:'💼',title:'Portfolio Agent',sub:'Capital, FX, cash reserve, risk tolerance and concentration-aware allocation.',onPress:()=>router.push('/portfolio'),accent:Brand.secondary},
    {icon:'🧠',title:'Kiasha',sub:'Evidence-gated market scan and ranked stock ideas for the selected market.',onPress:()=>router.push('/kiasha'),accent:'#7c3aed'},
    {icon:'🧾',title:'Orders / Execution',sub:'Paper-first execution area. Global live brokerage remains disabled until a broker adapter is approved.',onPress:()=>router.push('/orders'),accent:Brand.warning},
    {icon:'👤',title:'Profile & Settings',sub:'Account and app settings.',onPress:()=>router.push('/profile'),accent:'#64748b'},
  ];
  return <SafeAreaView style={[styles.safe,{backgroundColor:colors.background}]}><ScrollView contentContainerStyle={styles.content}><View style={styles.max}>
    <View style={styles.header}><Text style={[styles.title,{color:colors.text}]}>More</Text><Text style={[styles.sub,{color:colors.textSecondary}]}>BIAP Global tools, modules and configuration</Text></View>
    <View style={[styles.hero,{backgroundColor:colors.backgroundElement}]}><Text style={styles.eyebrow}>BIAP GLOBAL • v{version}</Text><Text style={[styles.heroTitle,{color:colors.text}]}>One product, one analysis engine, many markets.</Text><Text style={[styles.heroText,{color:colors.textSecondary}]}>Country adapters normalize exchange, market and filing data before it reaches BIAP modules. Missing official data remains missing; private operational data stays separated from investment evidence.</Text></View>
    {items.map(item=><Row key={item.title} item={item} colors={colors}/>)}
    <View style={[styles.status,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.statusTitle,{color:colors.text}]}>Execution status</Text><Text style={[styles.statusText,{color:colors.textSecondary}]}>Research, market scanning and Portfolio Agent are enabled. Live brokerage is OFF in this build. A future broker adapter must pass market permissions, contract mapping, costs, risk gates and compliance review before orders can be sent.</Text></View>
  </View></ScrollView></SafeAreaView>;
}

const styles=StyleSheet.create({safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingBottom:BottomTabInset+Spacing.four},max:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},header:{paddingTop:Spacing.four,paddingBottom:Spacing.three},title:{fontFamily:Fonts.sans,fontSize:25,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:11,marginTop:3},hero:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.three},eyebrow:{color:Brand.primary,fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},heroTitle:{fontFamily:Fonts.sans,fontSize:18,fontWeight:'900',marginTop:7},heroText:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:17,marginTop:5},row:{borderRadius:Radius.md,padding:Spacing.three,marginBottom:8,flexDirection:'row',alignItems:'center',gap:12},icon:{width:42,height:42,borderRadius:Radius.sm,alignItems:'center',justifyContent:'center'},emoji:{fontSize:20},rowTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900'},rowSub:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15,marginTop:3},chevron:{fontSize:24},status:{borderRadius:Radius.lg,padding:Spacing.four,marginTop:Spacing.three},statusTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900'},statusText:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15,marginTop:5}});