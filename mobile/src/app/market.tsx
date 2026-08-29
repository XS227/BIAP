import { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, FlatList, RefreshControl, useColorScheme, SafeAreaView, Pressable, TextInput, ActivityIndicator, ScrollView } from 'react-native';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, BottomTabInset, MaxContentWidth } from '@/constants/theme';
import { fetchWatchlist, formatPrice, MarketSymbolResult, StockItem } from '@/lib/api';
import { fetchMarketSymbols } from '@/lib/market-symbols';
import { fetchTsetmcQuotes } from '@/lib/market-quote';
import { SymbolLogo } from '@/components/symbol-logo';
import { StockRowSkeleton } from '@/components/skeleton';
import { marketStatusLabel } from '@/lib/market-hours';

const PAGE_SIZE=40;
type Category='ALL'|'TOP'|'LOSERS'|'PRICED'|'TSE'|'IFB'|'IFB_BASE';
const CATEGORIES:{key:Category;label:string}[]=[
  {key:'ALL',label:'همه'},
  {key:'TOP',label:'برترین‌ها'},
  {key:'LOSERS',label:'بیشترین افت'},
  {key:'PRICED',label:'دارای قیمت'},
  {key:'TSE',label:'بورس'},
  {key:'IFB',label:'فرابورس'},
  {key:'IFB_BASE',label:'بازار پایه'},
];

export default function MarketScreen(){
  const scheme=useColorScheme()==='dark'?'dark':'light';const colors=Colors[scheme];
  const[symbols,setSymbols]=useState<MarketSymbolResult[]>([]);const[quotes,setQuotes]=useState<Record<string,StockItem>>({});
  const[loading,setLoading]=useState(true);const[refreshing,setRefreshing]=useState(false);const[loadingMore,setLoadingMore]=useState(false);const[error,setError]=useState(false);
  const[query,setQuery]=useState('');const[category,setCategory]=useState<Category>('ALL');const[visibleCount,setVisibleCount]=useState(PAGE_SIZE);const[countdown,setCountdown]=useState(30);const marketStatus=marketStatusLabel();

  const filtered=useMemo(()=>{
    const q=query.trim();
    let items=q?symbols.filter(s=>s.symbol.includes(q)||s.name.includes(q)||s.code.includes(q)):symbols;
    if(category==='TSE'||category==='IFB'||category==='IFB_BASE')items=items.filter(s=>(s.market??'').toUpperCase()===category);
    if(category==='PRICED')items=items.filter(s=>{const x=quotes[s.code];return Boolean(x&&!x.error&&(x.lastPrice!=null||x.closingPrice!=null))});
    if(category==='TOP'||category==='LOSERS'){
      items=[...items].sort((a,b)=>{
        const qa=quotes[a.code],qb=quotes[b.code];
        const pa=qa?.changePercent!=null&&!qa.error?Number(qa.changePercent):null;
        const pb=qb?.changePercent!=null&&!qb.error?Number(qb.changePercent):null;
        if(pa===null&&pb===null)return a.symbol.localeCompare(b.symbol,'fa');
        if(pa===null)return 1;if(pb===null)return -1;
        return category==='TOP'?pb-pa:pa-pb;
      });
    }
    return items;
  },[symbols,query,category,quotes]);
  const visible=useMemo(()=>filtered.slice(0,visibleCount),[filtered,visibleCount]);

  const mergeWatchlist=useCallback(async(items:MarketSymbolResult[])=>{try{const watch=await fetchWatchlist();setQuotes(cur=>{const next={...cur};for(const w of watch){const match=items.find(s=>s.symbol===w.name||s.symbol===w.code||s.code===w.code||s.name===w.name);if(match)next[match.code]={...w,code:match.code,name:match.symbol};}return next})}catch{}},[]);
  const refreshQuotes=useCallback(async(items:MarketSymbolResult[])=>{if(!items.length)return;const next=await fetchTsetmcQuotes(items);setQuotes(cur=>({...cur,...next}));await mergeWatchlist(items)},[mergeWatchlist]);
  const loadUniverse=useCallback(async()=>{try{setError(false);const items=await fetchMarketSymbols({limit:5000});if(!items.length)throw new Error('empty');setSymbols(items);setVisibleCount(PAGE_SIZE);await refreshQuotes(items.slice(0,PAGE_SIZE))}catch{setError(true)}finally{setLoading(false);setRefreshing(false)}},[refreshQuotes]);

  useEffect(()=>{loadUniverse()},[loadUniverse]);
  useEffect(()=>{setVisibleCount(PAGE_SIZE);refreshQuotes(filtered.slice(0,PAGE_SIZE))},[query]);
  useEffect(()=>{if(category==='TOP'||category==='LOSERS'||category==='PRICED')refreshQuotes(symbols.slice(0,120));setVisibleCount(PAGE_SIZE)},[category]);
  useEffect(()=>{const interval=setInterval(()=>{refreshQuotes(visible);setCountdown(30)},30000);const tick=setInterval(()=>setCountdown(c=>c>0?c-1:30),1000);return()=>{clearInterval(interval);clearInterval(tick)}},[refreshQuotes,visible]);
  const loadMore=async()=>{if(loadingMore||visibleCount>=filtered.length)return;setLoadingMore(true);const n=Math.min(visibleCount+PAGE_SIZE,filtered.length);const more=filtered.slice(visibleCount,n);setVisibleCount(n);await refreshQuotes(more);setLoadingMore(false)};

  return <SafeAreaView style={[styles.safe,{backgroundColor:colors.background}]}><View style={[styles.container,{backgroundColor:colors.background}]}>
    <View style={styles.header}><View style={styles.headerTop}><View style={[styles.marketPill,{backgroundColor:marketStatus.open?'#1a3d2b':colors.backgroundElement}]}><View style={[styles.marketDot,{backgroundColor:marketStatus.open?Brand.stockGreen:colors.textSecondary}]}/><Text style={[styles.marketLabel,{color:marketStatus.open?Brand.stockGreen:colors.textSecondary}]}>{marketStatus.label}</Text></View><Text style={[styles.headerTitle,{color:colors.text}]}>بازار سرمایه ایران</Text></View><View style={styles.headerBottom}><Text style={[styles.countdown,{color:colors.textSecondary}]}>داده موجود: تازه‌سازی {countdown}ث</Text><Text style={[styles.headerSub,{color:colors.textSecondary}]}>{symbols.length.toLocaleString('fa-IR')} نماد</Text></View></View>
    <TextInput value={query} onChangeText={setQuery} placeholder="جستجوی نام، نماد یا شرکت..." placeholderTextColor={colors.textSecondary} style={[styles.searchBox,{backgroundColor:colors.backgroundElement,color:colors.text,borderColor:colors.backgroundSelected}]} textAlign="right"/>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>{CATEGORIES.map(c=><Pressable key={c.key} onPress={()=>setCategory(c.key)} style={[styles.filterChip,{backgroundColor:category===c.key?Brand.primary:colors.backgroundElement,borderColor:category===c.key?Brand.primary:colors.backgroundSelected}]}><Text style={[styles.filterText,{color:category===c.key?'#fff':colors.textSecondary}]}>{c.label}</Text></Pressable>)}</ScrollView>
    {(category==='TOP'||category==='LOSERS')?<Text style={[styles.rankingNote,{color:colors.textSecondary}]}>رتبه‌بندی فقط بر پایه قیمت/درصد تغییر تأییدشده‌ای است که دریافت شده؛ داده ناموجود رتبه‌سازی نمی‌شود.</Text>:null}
    {error?<Text style={[styles.errorText,{color:colors.textSecondary}]}>فهرست بازار فعلاً در دسترس نیست؛ دوباره پایین بکشید.</Text>:null}
    <FlatList data={visible} keyExtractor={i=>i.code} onEndReached={loadMore} onEndReachedThreshold={.35} contentContainerStyle={{paddingHorizontal:Spacing.three,paddingBottom:BottomTabInset+Spacing.four,maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'}} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={()=>{setRefreshing(true);setQuotes({});setCountdown(30);loadUniverse()}} tintColor={Brand.stockGreen}/>} ListEmptyComponent={loading?<View>{[1,2,3,4].map(i=><StockRowSkeleton key={i}/>)}</View>:<Text style={[styles.empty,{color:colors.textSecondary}]}>نمادی پیدا نشد</Text>} ListFooterComponent={loadingMore?<ActivityIndicator color={Brand.primary}/>:null} renderItem={({item,index})=>{const quote=quotes[item.code];const hasPct=quote?.changePercent!=null&&!quote.error;const p=hasPct?Number(quote.changePercent):null;const up=(p??0)>=0;const ranked=(category==='TOP'||category==='LOSERS')&&p!==null;return <Pressable onPress={()=>router.push(`/stock/${item.code}`)}><View style={[styles.row,{backgroundColor:colors.backgroundElement}]}><View style={styles.rowLeft}>{ranked?<Text style={[styles.rank,{color:colors.textSecondary}]}>{index+1}</Text>:null}<SymbolLogo symbol={item.symbol} size={42}/><View style={{alignItems:'flex-start',flex:1}}><Text style={[styles.rowName,{color:colors.text}]}>{item.symbol}</Text><Text style={[styles.rowCompany,{color:colors.textSecondary}]} numberOfLines={1}>{item.name}</Text><Text style={[styles.marketTagText,{color:colors.textSecondary}]}>{item.market??'CODAL'}</Text></View></View><View style={styles.rowRight}><Text style={[styles.rowPrice,{color:colors.text}]}>{quote&&!quote.error?formatPrice(quote.lastPrice??quote.closingPrice):'—'}</Text>{hasPct&&p!==null?<Text style={{color:up?Brand.stockGreen:Brand.negative,fontFamily:Fonts.mono,fontSize:12}}>{up?'▲':'▼'} {Math.abs(p).toFixed(2)}٪</Text>:<Text style={[styles.quoteState,{color:colors.textSecondary}]}>قیمت در دسترس نیست</Text>}</View></View></Pressable>}}/>
  </View></SafeAreaView>;
}

const styles=StyleSheet.create({safe:{flex:1},container:{flex:1},header:{paddingHorizontal:Spacing.three,paddingTop:Spacing.four,paddingBottom:Spacing.two},headerTop:{flexDirection:'row-reverse',alignItems:'center',justifyContent:'space-between'},headerBottom:{flexDirection:'row-reverse',justifyContent:'space-between',marginTop:5},headerTitle:{fontSize:21,fontFamily:Fonts.sans,fontWeight:'800'},headerSub:{fontSize:11,fontFamily:Fonts.sans},marketPill:{flexDirection:'row',alignItems:'center',gap:5,paddingHorizontal:10,paddingVertical:4,borderRadius:20},marketDot:{width:6,height:6,borderRadius:3},marketLabel:{fontSize:11,fontFamily:Fonts.sans},countdown:{fontSize:10,fontFamily:Fonts.mono},searchBox:{marginHorizontal:Spacing.three,marginBottom:Spacing.two,borderWidth:1,borderRadius:Spacing.two,paddingHorizontal:Spacing.three,paddingVertical:11,fontSize:14,fontFamily:Fonts.sans},filters:{paddingHorizontal:Spacing.three,paddingBottom:Spacing.two,gap:8,flexDirection:'row-reverse'},filterChip:{borderWidth:1,borderRadius:18,paddingHorizontal:12,paddingVertical:7},filterText:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'700'},rankingNote:{fontFamily:Fonts.sans,fontSize:9.5,textAlign:'right',paddingHorizontal:Spacing.three,paddingBottom:Spacing.two},errorText:{textAlign:'right',paddingHorizontal:Spacing.three,paddingVertical:Spacing.two,fontFamily:Fonts.sans,fontSize:12},row:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',borderRadius:Spacing.two,padding:Spacing.three,marginBottom:Spacing.two},rowLeft:{flexDirection:'row',alignItems:'center',gap:Spacing.two,flex:1},rank:{fontFamily:Fonts.mono,fontSize:10,minWidth:18,textAlign:'center'},marketTagText:{fontFamily:Fonts.mono,fontSize:8,marginTop:3},rowName:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'800'},rowCompany:{fontFamily:Fonts.sans,fontSize:9.5,maxWidth:190,marginTop:2},rowRight:{alignItems:'flex-end',gap:4,minWidth:95},rowPrice:{fontFamily:Fonts.mono,fontSize:13},quoteState:{fontFamily:Fonts.sans,fontSize:9},empty:{textAlign:'center',marginTop:Spacing.five,fontFamily:Fonts.sans}});
