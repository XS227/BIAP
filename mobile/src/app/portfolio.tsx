import { useCallback, useMemo, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, useColorScheme, SafeAreaView, Pressable, RefreshControl } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { fetchPaperPortfolio, PaperPortfolio, PaperPosition } from '@/lib/paper-portfolio';
import { fetchPaperEquityHistory, PaperEquitySnapshot } from '@/lib/api';
import { SymbolLogo } from '@/components/symbol-logo';

function money(value:number|null|undefined){return value==null||!Number.isFinite(value)?'—':Math.round(value).toLocaleString('fa-IR')}
function pct(value:number|null|undefined){return value==null||!Number.isFinite(value)?'—':`${value>=0?'+':''}${value.toFixed(2)}٪`}
function signedMoney(value:number|null|undefined){return value==null||!Number.isFinite(value)?'—':`${value>=0?'+':''}${Math.round(value).toLocaleString('fa-IR')}`}

function periodReturn(history:PaperEquitySnapshot[], pointsBack:number){
  if(history.length<2)return {amount:null as number|null,pct:null as number|null};
  const end=history[history.length-1];
  const start=history[Math.max(0,history.length-1-pointsBack)];
  if(!start||!end||!Number.isFinite(start.totalEquity)||!Number.isFinite(end.totalEquity)||start.totalEquity<=0)return {amount:null,pct:null};
  const amount=end.totalEquity-start.totalEquity;
  return {amount,pct:(amount/start.totalEquity)*100};
}

function StatCard({label,value,sub,positive,colors}:{label:string;value:string;sub?:string;positive?:boolean|null;colors:ThemeColors}){
  return <View style={[styles.statCard,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.statLabel,{color:colors.textSecondary}]}>{label}</Text><Text numberOfLines={1} style={[styles.statValue,{color:positive===null||positive===undefined?colors.text:positive?Brand.positive:Brand.negative}]}>{value}</Text>{sub?<Text numberOfLines={1} style={[styles.statSub,{color:colors.textSecondary}]}>{sub}</Text>:null}</View>
}

function CompactPositionCard({position,colors}:{position:PaperPosition;colors:ThemeColors}){
  const positive=(position.unrealizedPnL??0)>=0;
  const label=position.displayName||position.code;
  return <Pressable onPress={()=>router.push(`/stock/${position.code}`)} style={({pressed})=>[styles.assetCard,{backgroundColor:colors.backgroundElement,opacity:pressed?.78:1}]}>
    <SymbolLogo symbol={label} size={38}/>
    <Text numberOfLines={1} style={[styles.assetName,{color:colors.text}]}>{label}</Text>
    <Text numberOfLines={1} style={[styles.assetInvested,{color:colors.textSecondary}]}>{money(position.costBasis)}</Text>
    <Text style={[styles.assetPnl,{color:positive?Brand.positive:Brand.negative}]}>{pct(position.unrealizedPnLPct)}</Text>
    <Text numberOfLines={1} style={[styles.assetPnlMoney,{color:positive?Brand.positive:Brand.negative}]}>{signedMoney(position.unrealizedPnL)}</Text>
  </Pressable>
}

function EquityChart({history,colors}:{history:PaperEquitySnapshot[];colors:ThemeColors}){
  const points=history.slice(-20);
  if(points.length<2)return <View style={[styles.chartEmpty,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.chartEmptyText,{color:colors.textSecondary}]}>پس از ثبت حداقل دو snapshot واقعی، نمودار عملکرد نمایش داده می‌شود.</Text></View>;
  const values=points.map(x=>x.totalEquity).filter(Number.isFinite);
  const min=Math.min(...values),max=Math.max(...values),range=Math.max(1,max-min);
  return <View style={[styles.chartCard,{backgroundColor:colors.backgroundElement}]}>
    <View style={styles.chartHead}><Text style={[styles.chartPeriod,{color:colors.textSecondary}]}>۲۰ snapshot اخیر</Text><Text style={[styles.chartTitle,{color:colors.text}]}>روند ارزش پرتفوی</Text></View>
    <View style={styles.bars}>{points.map((p,i)=>{const h=18+((p.totalEquity-min)/range)*72;const prev=i>0?points[i-1].totalEquity:p.totalEquity;const positive=p.totalEquity>=prev;return <View key={`${p.snapshotDate}-${i}`} style={styles.barSlot}><View style={[styles.bar,{height:h,backgroundColor:positive?Brand.positive:Brand.negative}]} /></View>})}</View>
    <View style={styles.chartFooter}><Text style={[styles.chartFootText,{color:colors.textSecondary}]}>{points[0]?.snapshotDate}</Text><Text style={[styles.chartFootText,{color:colors.textSecondary}]}>{points[points.length-1]?.snapshotDate}</Text></View>
  </View>
}

export default function PortfolioScreen(){
  const scheme=useColorScheme()==='dark'?'dark':'light';const colors=Colors[scheme];
  const[portfolio,setPortfolio]=useState<PaperPortfolio|null>(null);const[history,setHistory]=useState<PaperEquitySnapshot[]>([]);const[loading,setLoading]=useState(true);const[refreshing,setRefreshing]=useState(false);const[error,setError]=useState(false);
  const load=useCallback(async()=>{const[p,h]=await Promise.all([fetchPaperPortfolio(),fetchPaperEquityHistory(120,12_000)]);if(p===null)setError(true);else{setError(false);setPortfolio(p)};setHistory((h?.items??[]).slice().sort((a,b)=>a.snapshotDate.localeCompare(b.snapshotDate)));setLoading(false);setRefreshing(false)},[]);
  useFocusEffect(useCallback(()=>{load()},[load]));
  const equity=portfolio&&portfolio.totalMarketValue!==null?(portfolio.cash??0)+portfolio.totalMarketValue:null;
  const daily=useMemo(()=>periodReturn(history,1),[history]);
  const weekly=useMemo(()=>periodReturn(history,5),[history]);
  const monthly=useMemo(()=>periodReturn(history,22),[history]);
  return <SafeAreaView style={[styles.safe,{backgroundColor:colors.background}]}><ScrollView contentContainerStyle={[styles.content,{paddingBottom:BottomTabInset+Spacing.four}]} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={()=>{setRefreshing(true);load()}} tintColor={Brand.primary}/>}><View style={{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'}}>
    <View style={styles.header}><Text style={[styles.headerTitle,{color:colors.text}]}>پرتفوی من</Text><Text style={[styles.headerSub,{color:colors.textSecondary}]}>ارزش واقعی ثبت‌شده در BIAP، سرمایه‌گذاری‌ها و سود/زیان شما در یک نگاه</Text></View>
    {loading?<Text style={[styles.stateText,{color:colors.textSecondary}]}>در حال محاسبه پرتفوی...</Text>:null}
    {error?<View style={[styles.stateCard,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.stateTitle,{color:colors.text}]}>دریافت پرتفوی ممکن نشد</Text></View>:null}
    {!loading&&!error&&portfolio?<>
      <View style={[styles.hero,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.heroLabel,{color:colors.textSecondary}]}>ارزش کل حساب</Text><Text style={[styles.heroValue,{color:colors.text}]}>{money(equity)} <Text style={styles.rial}>ریال</Text></Text><Text style={[styles.heroPnl,{color:(portfolio.totalUnrealizedPnL??0)>=0?Brand.positive:Brand.negative}]}>{pct(portfolio.totalUnrealizedPnLPct)} • {signedMoney(portfolio.totalUnrealizedPnL)} ریال</Text></View>
      <View style={styles.statsRow}>
        <StatCard label="امروز" value={pct(daily.pct)} sub={`${signedMoney(daily.amount)} ریال`} positive={daily.amount===null?null:daily.amount>=0} colors={colors}/>
        <StatCard label="هفته" value={pct(weekly.pct)} sub={`${signedMoney(weekly.amount)} ریال`} positive={weekly.amount===null?null:weekly.amount>=0} colors={colors}/>
        <StatCard label="ماه" value={pct(monthly.pct)} sub={`${signedMoney(monthly.amount)} ریال`} positive={monthly.amount===null?null:monthly.amount>=0} colors={colors}/>
      </View>
      <View style={styles.statsRow}>
        <StatCard label="نقد آزاد" value={money(portfolio.manualAvailableCash??portfolio.cash)} sub="ریال" colors={colors}/>
        <StatCard label="سرمایه Kiasha" value={money((portfolio.kiashaReservedCash??0)+(portfolio.kiashaInvestedCost??0))} sub="ریال" colors={colors}/>
        <StatCard label="ارزش سهام" value={money(portfolio.totalMarketValue)} sub="ریال" colors={colors}/>
      </View>
      <EquityChart history={history} colors={colors}/>
      <View style={styles.sectionHead}><Text style={[styles.sectionTitle,{color:colors.text}]}>سرمایه‌گذاری‌های من</Text><Text style={[styles.sectionMeta,{color:colors.textSecondary}]}>{portfolio.positions.length.toLocaleString('fa-IR')} دارایی</Text></View>
      {portfolio.positions.length>0?<View style={styles.assetGrid}>{portfolio.positions.map(p=><CompactPositionCard key={p.code} position={p} colors={colors}/>)}</View>:<View style={[styles.stateCard,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.stateTitle,{color:colors.text}]}>هنوز سرمایه‌گذاری ثبت‌شده ندارید</Text><Pressable onPress={()=>router.push('/market')} style={[styles.primaryBtn,{backgroundColor:Brand.primary}]}><Text style={styles.primaryBtnText}>رفتن به بازار</Text></Pressable></View>}
      <View style={[styles.notice,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.noticeTitle,{color:colors.text}]}>داده بدون عدد ساختگی</Text><Text style={[styles.noticeBody,{color:colors.textSecondary}]}>اگر قیمت یا سابقه کافی برای محاسبه روزانه، هفتگی یا ماهانه وجود نداشته باشد، BIAP خط تیره نشان می‌دهد و بازده را حدس نمی‌زند.</Text></View>
    </>:null}
  </View></ScrollView></SafeAreaView>
}

const styles=StyleSheet.create({safe:{flex:1},content:{paddingHorizontal:Spacing.three},header:{paddingTop:Spacing.four,paddingBottom:Spacing.three,alignItems:'flex-end'},headerTitle:{fontSize:23,fontFamily:Fonts.sans,fontWeight:'800'},headerSub:{fontSize:11.5,lineHeight:19,fontFamily:Fonts.sans,textAlign:'right',marginTop:5},hero:{borderRadius:Radius.lg,padding:Spacing.four,alignItems:'flex-end',marginBottom:Spacing.three},heroLabel:{fontFamily:Fonts.sans,fontSize:12},heroValue:{fontFamily:Fonts.mono,fontSize:29,fontWeight:'800',marginTop:5},heroPnl:{fontFamily:Fonts.mono,fontSize:14,fontWeight:'800',marginTop:7},rial:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'400'},statsRow:{flexDirection:'row-reverse',gap:Spacing.two,marginBottom:Spacing.two},statCard:{flex:1,borderRadius:Radius.md,paddingVertical:Spacing.three,paddingHorizontal:Spacing.two,alignItems:'flex-end',minHeight:78},statLabel:{fontFamily:Fonts.sans,fontSize:9.5},statValue:{fontFamily:Fonts.mono,fontSize:13,fontWeight:'800',marginTop:5},statSub:{fontFamily:Fonts.sans,fontSize:8.5,marginTop:3},chartCard:{borderRadius:Radius.lg,padding:Spacing.three,marginVertical:Spacing.two},chartHead:{flexDirection:'row-reverse',alignItems:'center',justifyContent:'space-between'},chartTitle:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'800'},chartPeriod:{fontFamily:Fonts.sans,fontSize:9.5},bars:{height:100,flexDirection:'row',alignItems:'flex-end',gap:3,marginTop:Spacing.three},barSlot:{flex:1,height:100,justifyContent:'flex-end'},bar:{width:'100%',borderRadius:3,minHeight:4},chartFooter:{flexDirection:'row',justifyContent:'space-between',marginTop:6},chartFootText:{fontFamily:Fonts.mono,fontSize:8},chartEmpty:{borderRadius:Radius.lg,padding:Spacing.four,marginVertical:Spacing.two},chartEmptyText:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:18,textAlign:'right'},sectionHead:{flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center',marginTop:Spacing.four,marginBottom:Spacing.two},sectionTitle:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'800'},sectionMeta:{fontFamily:Fonts.sans,fontSize:10},assetGrid:{flexDirection:'row-reverse',flexWrap:'wrap',gap:Spacing.two},assetCard:{width:'31.5%',borderRadius:Radius.md,paddingVertical:Spacing.three,paddingHorizontal:Spacing.two,alignItems:'center',minHeight:150},assetName:{fontFamily:Fonts.sans,fontSize:11.5,fontWeight:'800',marginTop:8,textAlign:'center',width:'100%'},assetInvested:{fontFamily:Fonts.mono,fontSize:9.5,marginTop:5,textAlign:'center'},assetPnl:{fontFamily:Fonts.mono,fontSize:11,fontWeight:'800',marginTop:8},assetPnlMoney:{fontFamily:Fonts.mono,fontSize:8.5,fontWeight:'700',marginTop:3,textAlign:'center'},stateCard:{borderRadius:Radius.lg,padding:Spacing.four,alignItems:'center',gap:Spacing.two,marginTop:Spacing.three},stateTitle:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'800'},stateText:{fontFamily:Fonts.sans,fontSize:12,textAlign:'center'},primaryBtn:{width:'100%',borderRadius:Radius.sm,paddingVertical:Spacing.three,alignItems:'center'},primaryBtnText:{color:'#fff',fontFamily:Fonts.sans,fontWeight:'800'},notice:{borderRadius:Radius.md,padding:Spacing.three,marginTop:Spacing.four,alignItems:'flex-end'},noticeTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'800'},noticeBody:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:18,textAlign:'right',marginTop:4}});