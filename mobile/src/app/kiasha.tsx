import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Dimensions, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, Radius, Spacing } from '@/constants/theme';
import { fetchKiashaPerformanceSummary, formatPrice, KiashaPerformanceSummary } from '@/lib/api';
import { fetchKiashaTopPicks, InvestmentHorizon, KiashaPicksResult } from '@/lib/kiasha-picks';
import { fetchPaperPortfolio, PaperPortfolio } from '@/lib/paper-portfolio';
import { SymbolLogo } from '@/components/symbol-logo';

const screenWidth = Dimensions.get('window').width;
const swipeCardWidth = Math.min(310, Math.max(260, screenWidth - 64));
const money=(v:number|null|undefined)=>v==null||!Number.isFinite(v)?'—':Math.round(v).toLocaleString('fa-IR');
const pct=(v:number|null|undefined)=>v==null||!Number.isFinite(v)?'—':`${v>=0?'+':''}${v.toLocaleString('fa-IR',{maximumFractionDigits:2})}٪`;

function SwipeMetric({label,value,sub,tone,colors}:{label:string;value:string;sub:string;tone?:'positive'|'negative';colors:any}){
  return <View style={[styles.swipeMetric,{backgroundColor:colors.backgroundElement}]}>
    <Text style={[styles.swipeMetricLabel,{color:colors.textSecondary}]}>{label}</Text>
    <Text numberOfLines={1} style={[styles.swipeMetricValue,{color:tone==='positive'?Brand.positive:tone==='negative'?Brand.negative:colors.text}]}>{value}</Text>
    <Text style={[styles.swipeMetricSub,{color:colors.textSecondary}]}>{sub}</Text>
  </View>
}

function pickInfo(pick:KiashaPicksResult['picks'][number]){
  const breakdown=Array.isArray(pick.recommendation?.breakdown)?pick.recommendation.breakdown:[];
  const confidences=breakdown.map((x:any)=>Number(x?.confidence)).filter((x:number)=>Number.isFinite(x)&&x>0);
  const avg=confidences.length?confidences.reduce((s:number,x:number)=>s+x,0)/confidences.length:null;
  const confidence=avg==null?null:Math.round(avg<=1?avg*100:avg);
  const hasCodal=Boolean(pick.recommendation?.dataAvailability?.codal||pick.recommendation?.dataAvailability?.codal_metadata);
  const risk=pick.activeAgents>=4&&pick.score>=0.3?'متوسط':pick.activeAgents>=3?'متوسط رو به بالا':'بالا';
  return {confidence,hasCodal,risk};
}

function PickCard({pick,totalVerified,colors}:{pick:KiashaPicksResult['picks'][number];totalVerified:number;colors:any}){
  const info=pickInfo(pick);
  return <Pressable onPress={()=>router.push(`/stock/${encodeURIComponent(pick.code)}`)} style={({pressed})=>[styles.pickCard,{width:swipeCardWidth,backgroundColor:colors.backgroundElement,opacity:pressed?0.82:1}]}>
    <View style={styles.pickTop}>
      <View style={styles.rankBubble}><Text style={styles.rankBubbleText}>#{pick.rank.toLocaleString('fa-IR')}</Text></View>
      <View style={styles.pickIdentity}>
        <SymbolLogo symbol={pick.symbol} size={44}/>
        <View style={styles.pickNames}><Text style={[styles.pickSymbol,{color:colors.text}]}>{pick.symbol}</Text><Text numberOfLines={1} style={[styles.pickName,{color:colors.textSecondary}]}>{pick.name}</Text></View>
      </View>
    </View>
    <View style={styles.pickMainRow}>
      <View style={styles.pickMainCell}><Text style={[styles.pickMainValue,{color:Brand.primary}]}>{pick.score>=0?'+':''}{pick.score.toFixed(3)}</Text><Text style={[styles.pickMainLabel,{color:colors.textSecondary}]}>امتیاز کیا‌شا</Text></View>
      <View style={styles.pickMainCell}><Text style={[styles.pickMainValue,{color:colors.text}]}>{info.confidence==null?'—':`${info.confidence.toLocaleString('fa-IR')}٪`}</Text><Text style={[styles.pickMainLabel,{color:colors.textSecondary}]}>اعتماد</Text></View>
      <View style={styles.pickMainCell}><Text style={[styles.pickMainValue,{color:colors.text}]}>{pick.price==null?'—':formatPrice(pick.price)}</Text><Text style={[styles.pickMainLabel,{color:colors.textSecondary}]}>قیمت</Text></View>
    </View>
    <View style={styles.pickChips}>
      <View style={[styles.chip,{backgroundColor:colors.backgroundSelected}]}><Text style={[styles.chipText,{color:colors.textSecondary}]}>{info.hasCodal?'بازار + کدال':'داده بازار'}</Text></View>
      <View style={[styles.chip,{backgroundColor:colors.backgroundSelected}]}><Text style={[styles.chipText,{color:colors.textSecondary}]}>ریسک {info.risk}</Text></View>
      <View style={[styles.chip,{backgroundColor:colors.backgroundSelected}]}><Text style={[styles.chipText,{color:colors.textSecondary}]}>{pick.activeAgents.toLocaleString('fa-IR')} / ۶ عامل</Text></View>
    </View>
    <Text style={[styles.pickReason,{color:colors.textSecondary}]}>رتبه {pick.rank.toLocaleString('fa-IR')} از {totalVerified.toLocaleString('fa-IR')} تحلیل عمیق. برای دیدن جزئیات کامل لمس کنید.</Text>
  </Pressable>
}

export default function KiashaScreen(){
  const colors=useColorScheme()==='dark'?Colors.dark:Colors.light;
  const[performance,setPerformance]=useState<KiashaPerformanceSummary|null>(null);
  const[portfolio,setPortfolio]=useState<PaperPortfolio|null>(null);
  const[picks,setPicks]=useState<KiashaPicksResult|null>(null);
  const[horizon,setHorizon]=useState<InvestmentHorizon>('short');
  const[loading,setLoading]=useState(true);
  const[refreshing,setRefreshing]=useState(false);

  const loadBase=useCallback(async()=>{const[p,a]=await Promise.all([fetchKiashaPerformanceSummary(8000),fetchPaperPortfolio()]);setPerformance(p);setPortfolio(a);setLoading(false)},[]);
  const loadPicks=useCallback(async(force=false)=>{setPicks(await fetchKiashaTopPicks(horizon,{force,scanLimit:72}))},[horizon]);
  useFocusEffect(useCallback(()=>{loadBase()},[loadBase]));
  useEffect(()=>{loadPicks(false)},[loadPicks]);
  const refresh=async()=>{setRefreshing(true);await Promise.all([loadBase(),loadPicks(true)]);setRefreshing(false)};

  const agents=performance?.agents??[];
  const evaluated=agents.reduce((s,a)=>s+a.evaluatedCalls,0);
  const active=agents.filter(a=>a.evaluatedCalls>0||a.trustReady).length;
  const equity=portfolio&&portfolio.totalMarketValue!==null?(portfolio.cash??0)+portfolio.totalMarketValue:null;
  const pnl=portfolio?.totalUnrealizedPnLPct??null;
  const statusLabel=!performance?'نامشخص':evaluated>0?'فعال و در حال یادگیری':active>0?'آماده تحلیل':'منتظر داده';
  const statusTone=evaluated>0?Brand.positive:Brand.primary;
  const topPick=useMemo(()=>picks?.picks?.[0]??null,[picks]);

  return <SafeAreaView style={[styles.safe,{backgroundColor:colors.background}]}>
    <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={Brand.primary}/>} contentContainerStyle={[styles.content,{paddingBottom:BottomTabInset+Spacing.four}]} showsVerticalScrollIndicator={false}>
      <View style={styles.header}>
        <Text style={[styles.title,{color:colors.text}]}>کیاشا</Text>
        <Text style={[styles.sub,{color:colors.textSecondary}]}>تحلیل و سرمایه‌گذاری هوشمند با داده قابل‌تأیید</Text>
      </View>

      <View style={[styles.hero,{backgroundColor:colors.backgroundElement}]}>
        <View style={styles.heroTop}><View style={[styles.liveDot,{backgroundColor:statusTone}]}/><Text style={[styles.heroStatus,{color:statusTone}]}>{statusLabel}</Text></View>
        <Text style={[styles.heroLabel,{color:colors.textSecondary}]}>ارزش حساب تحت نظر</Text>
        <Text style={[styles.heroValue,{color:colors.text}]}>{money(equity)} <Text style={styles.rial}>ریال</Text></Text>
        <Text style={[styles.heroPnl,{color:pnl==null?colors.textSecondary:pnl>=0?Brand.positive:Brand.negative}]}>{pct(pnl)}</Text>
        <Pressable onPress={()=>router.push('/portfolio')} style={[styles.primaryAction,{backgroundColor:Brand.primary}]}><Text style={styles.primaryActionText}>مشاهده پرتفوی</Text></Pressable>
      </View>

      <View style={styles.sectionRow}><Text style={[styles.sectionHint,{color:colors.textSecondary}]}>برای دیدن بقیه ← بکشید</Text><Text style={[styles.sectionTitle,{color:colors.text}]}>خلاصه</Text></View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalContent} snapToInterval={swipeCardWidth+Spacing.two} decelerationRate="fast">
        <SwipeMetric label="بازده فعلی" value={pct(pnl)} sub="کل حساب" tone={pnl==null?undefined:pnl>=0?'positive':'negative'} colors={colors}/>
        <SwipeMetric label="عامل‌های فعال" value={`${active.toLocaleString('fa-IR')} / ۶`} sub="موتور تحلیل" colors={colors}/>
        <SwipeMetric label="ارزیابی واقعی" value={evaluated.toLocaleString('fa-IR')} sub="برای یادگیری عملکرد" colors={colors}/>
        <SwipeMetric label="سهام قیمت‌گذاری‌شده" value={`${(portfolio?.pricedPositions??0).toLocaleString('fa-IR')} / ${(portfolio?.totalPositions??0).toLocaleString('fa-IR')}`} sub="داده معتبر" colors={colors}/>
      </ScrollView>

      <View style={styles.sectionRow}><View style={styles.segment}><Pressable onPress={()=>setHorizon('short')} style={[styles.segmentBtn,horizon==='short'&&styles.segmentActive]}><Text style={[styles.segmentText,{color:horizon==='short'?'#fff':colors.textSecondary}]}>کوتاه‌مدت</Text></Pressable><Pressable onPress={()=>setHorizon('long')} style={[styles.segmentBtn,horizon==='long'&&styles.segmentActive]}><Text style={[styles.segmentText,{color:horizon==='long'?'#fff':colors.textSecondary}]}>بلندمدت</Text></Pressable></View><Text style={[styles.sectionTitle,{color:colors.text}]}>انتخاب‌های کیا‌شا</Text></View>

      {!picks?<ActivityIndicator color={Brand.primary} style={{marginVertical:24}}/>:picks.picks.length?
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalContent} snapToInterval={swipeCardWidth+Spacing.two} decelerationRate="fast">
          {picks.picks.map(p=><PickCard key={`${p.code}-${p.rank}`} pick={p} totalVerified={picks.verified} colors={colors}/>) }
        </ScrollView>
      :<View style={[styles.empty,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.emptyText,{color:colors.textSecondary}]}>فعلاً نمادی با داده کافی برای پیشنهاد تأییدشده پیدا نشد.</Text></View>}

      {topPick?<View style={[styles.focusCard,{backgroundColor:colors.backgroundElement}]}>
        <Text style={[styles.focusEyebrow,{color:Brand.primary}]}>تمرکز امروز</Text>
        <View style={styles.focusHead}><SymbolLogo symbol={topPick.symbol} size={46}/><View style={styles.focusCopy}><Text style={[styles.focusTitle,{color:colors.text}]}>{topPick.symbol}</Text><Text style={[styles.focusName,{color:colors.textSecondary}]} numberOfLines={1}>{topPick.name}</Text></View></View>
        <Text style={[styles.focusText,{color:colors.textSecondary}]}>کیاشا این نماد را در رتبه اول غربال فعلی قرار داده. جزئیات قیمت، ریسک، داده CODAL و نظر عامل‌ها داخل صفحه سهم در دسترس است.</Text>
        <Pressable onPress={()=>router.push(`/stock/${encodeURIComponent(topPick.code)}`)} style={[styles.secondaryAction,{borderColor:Brand.primary}]}><Text style={[styles.secondaryActionText,{color:Brand.primary}]}>باز کردن تحلیل کامل</Text></Pressable>
      </View>:null}

      <View style={[styles.statusCard,{backgroundColor:colors.backgroundElement}]}>
        <View style={styles.statusTop}><Text style={[styles.statusValue,{color:colors.text}]}>{picks?`${picks.eligible.toLocaleString('fa-IR')} سهم`: '—'}</Text><Text style={[styles.statusTitle,{color:colors.text}]}>پوشش بازار</Text></View>
        <Text style={[styles.statusText,{color:colors.textSecondary}]}>{picks?`${picks.verified.toLocaleString('fa-IR')} نماد تحلیل عمیق و رتبه‌بندی شده‌اند. برای تازه‌سازی، صفحه را به پایین بکشید.`:'اطلاعات غربال بازار هنوز دریافت نشده است.'}</Text>
      </View>

      <Text style={[styles.disclaimer,{color:colors.textSecondary}]}>هیچ عددی در این صفحه حدس زده نمی‌شود. وقتی داده یا قیمت معتبر کافی نباشد، مقدار «—» نمایش داده می‌شود. اجرای واقعی سفارش فقط پس از اتصال مجاز کارگزاری فعال خواهد شد.</Text>
    </ScrollView>
  </SafeAreaView>
}

const styles=StyleSheet.create({
  safe:{flex:1},
  content:{paddingHorizontal:Spacing.three},
  header:{alignItems:'flex-end',paddingTop:Spacing.four,paddingBottom:Spacing.three},
  title:{fontFamily:Fonts.sans,fontSize:26,fontWeight:'900'},
  sub:{fontFamily:Fonts.sans,fontSize:11.5,marginTop:4,textAlign:'right'},
  hero:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.four,alignItems:'flex-end'},
  heroTop:{flexDirection:'row-reverse',alignItems:'center',gap:7,marginBottom:Spacing.three},
  liveDot:{width:8,height:8,borderRadius:4},
  heroStatus:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'800'},
  heroLabel:{fontFamily:Fonts.sans,fontSize:11},
  heroValue:{fontFamily:Fonts.mono,fontSize:28,fontWeight:'900',marginTop:4,textAlign:'right'},
  rial:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'400'},
  heroPnl:{fontFamily:Fonts.mono,fontSize:14,fontWeight:'900',marginTop:5},
  primaryAction:{minHeight:48,borderRadius:Radius.md,alignItems:'center',justifyContent:'center',alignSelf:'stretch',marginTop:Spacing.four},
  primaryActionText:{color:'#fff',fontFamily:Fonts.sans,fontSize:13,fontWeight:'900'},
  sectionRow:{flexDirection:'row-reverse',alignItems:'center',justifyContent:'space-between',marginBottom:Spacing.two,marginTop:Spacing.two},
  sectionTitle:{fontFamily:Fonts.sans,fontSize:17,fontWeight:'900'},
  sectionHint:{fontFamily:Fonts.sans,fontSize:9.5},
  horizontalContent:{gap:Spacing.two,paddingBottom:Spacing.four,paddingLeft:Spacing.one},
  swipeMetric:{width:swipeCardWidth,borderRadius:Radius.lg,padding:Spacing.four,alignItems:'flex-end',minHeight:122},
  swipeMetricLabel:{fontFamily:Fonts.sans,fontSize:10.5},
  swipeMetricValue:{fontFamily:Fonts.mono,fontSize:24,fontWeight:'900',marginTop:8},
  swipeMetricSub:{fontFamily:Fonts.sans,fontSize:10,marginTop:5},
  segment:{flexDirection:'row',backgroundColor:'transparent',gap:5},
  segmentBtn:{minHeight:38,paddingHorizontal:12,borderRadius:18,justifyContent:'center',borderWidth:1,borderColor:'#4b5563'},
  segmentActive:{backgroundColor:Brand.primary,borderColor:Brand.primary},
  segmentText:{fontFamily:Fonts.sans,fontSize:10,fontWeight:'800'},
  pickCard:{borderRadius:Radius.lg,padding:Spacing.four,minHeight:270},
  pickTop:{flexDirection:'row-reverse',alignItems:'center',justifyContent:'space-between'},
  pickIdentity:{flexDirection:'row-reverse',alignItems:'center',gap:Spacing.two,flex:1},
  pickNames:{alignItems:'flex-end',flex:1,minWidth:0},
  pickSymbol:{fontFamily:Fonts.sans,fontSize:17,fontWeight:'900'},
  pickName:{fontFamily:Fonts.sans,fontSize:10.5,marginTop:2,maxWidth:'100%'},
  rankBubble:{minWidth:42,height:34,borderRadius:17,backgroundColor:Brand.primary,alignItems:'center',justifyContent:'center'},
  rankBubbleText:{color:'#fff',fontFamily:Fonts.mono,fontSize:11,fontWeight:'900'},
  pickMainRow:{flexDirection:'row-reverse',gap:Spacing.two,marginTop:Spacing.four},
  pickMainCell:{flex:1,alignItems:'center'},
  pickMainValue:{fontFamily:Fonts.mono,fontSize:13,fontWeight:'900',textAlign:'center'},
  pickMainLabel:{fontFamily:Fonts.sans,fontSize:9,marginTop:4,textAlign:'center'},
  pickChips:{flexDirection:'row-reverse',flexWrap:'wrap',gap:6,marginTop:Spacing.four},
  chip:{borderRadius:14,paddingHorizontal:9,paddingVertical:6},
  chipText:{fontFamily:Fonts.sans,fontSize:9,fontWeight:'700'},
  pickReason:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:18,textAlign:'right',marginTop:Spacing.three},
  empty:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.four},
  emptyText:{fontFamily:Fonts.sans,fontSize:11,lineHeight:19,textAlign:'right'},
  focusCard:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.three},
  focusEyebrow:{fontFamily:Fonts.sans,fontSize:10,fontWeight:'900',textAlign:'right'},
  focusHead:{flexDirection:'row-reverse',alignItems:'center',gap:Spacing.two,marginTop:Spacing.three},
  focusCopy:{alignItems:'flex-end',flex:1},
  focusTitle:{fontFamily:Fonts.sans,fontSize:18,fontWeight:'900'},
  focusName:{fontFamily:Fonts.sans,fontSize:10.5,marginTop:2},
  focusText:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:19,textAlign:'right',marginTop:Spacing.three},
  secondaryAction:{minHeight:46,borderWidth:1,borderRadius:Radius.md,alignItems:'center',justifyContent:'center',marginTop:Spacing.three},
  secondaryActionText:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'900'},
  statusCard:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.three},
  statusTop:{flexDirection:'row-reverse',alignItems:'center',justifyContent:'space-between'},
  statusTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'900'},
  statusValue:{fontFamily:Fonts.mono,fontSize:14,fontWeight:'900'},
  statusText:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:19,textAlign:'right',marginTop:Spacing.two},
  disclaimer:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:17,textAlign:'right',paddingHorizontal:Spacing.one,paddingVertical:Spacing.three}
});
