import { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, RefreshControl, useColorScheme, SafeAreaView, Pressable } from 'react-native';
import { useFocusEffect, router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { fetchOrderHistory, OrderReceipt } from '@/lib/api';
import { fetchManualPaperOrders, ManualPaperOrder } from '@/lib/kiasha-paper-trade';
import { fetchTsetmcInstrumentLabel } from '@/lib/market-quote';

const SIDE_LABEL: Record<string, string> = { BUY: 'خرید', SELL: 'فروش' };
const STATUS_LABEL: Record<string, string> = {
  PAPER_FILLED: 'اجرا شد (Paper)',
  PENDING_APPROVAL: 'در انتظار تأیید',
  PENDING_MARKET_OPEN: 'در صف بازگشایی بازار',
  CANCELLED_SIGNAL: 'لغو شد — سیگنال تغییر کرد',
  CANCELLED_RISK: 'لغو شد — کنترل ریسک',
  SIMULATED: 'شبیه‌سازی شد',
};

type DisplayOrder = OrderReceipt | ManualPaperOrder;
function statusColor(status: string) { if (status === 'PAPER_FILLED') return Brand.positive; if (status === 'PENDING_APPROVAL' || status === 'PENDING_MARKET_OPEN') return Brand.warning; if (status.startsWith('CANCELLED')) return Brand.negative; return Brand.secondary; }
function OrderCard({ order, colors, label }: { order: DisplayOrder; colors: ThemeColors; label?: string }) {
  const sideColor = order.side === 'BUY' ? Brand.positive : Brand.negative;
  const rawDate = order.submittedAt || order.created_at; const date = rawDate ? new Date(rawDate) : null;
  const dateLabel = date && !Number.isNaN(date.getTime()) ? date.toLocaleString('fa-IR') : '';
  return <Pressable onPress={() => router.push(`/stock/${order.code}`)} style={({ pressed }) => [orderStyles.card, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.8 : 1 }]}>
    <View style={orderStyles.topRow}><View style={[orderStyles.statusBadge, { backgroundColor: `${statusColor(order.status)}22` }]}><Text style={[orderStyles.statusText, { color: statusColor(order.status) }]}>{STATUS_LABEL[order.status] ?? order.status}</Text></View><View style={[orderStyles.sideBadge, { backgroundColor: `${sideColor}22` }]}><Text style={[orderStyles.sideText, { color: sideColor }]}>{SIDE_LABEL[order.side] ?? order.side}</Text></View></View>
    <Text style={[orderStyles.code, { color: colors.text }]}>{label || (/^\d+$/.test(order.code) ? 'در حال دریافت نام نماد…' : order.code)}</Text>
    {label && label !== order.code ? <Text style={[orderStyles.instrumentId, { color: colors.textSecondary }]}>شناسه بازار: {order.code}</Text> : null}
    <Text style={[orderStyles.meta, { color: colors.textSecondary }]}>{order.quantity} سهم · Paper — بدون معامله واقعی</Text>
    {order.note ? <Text style={[orderStyles.note, { color: colors.textSecondary }]}>{order.note}</Text> : null}{dateLabel ? <Text style={[orderStyles.date, { color: colors.textSecondary }]}>{dateLabel}</Text> : null}
  </Pressable>;
}
const orderStyles = StyleSheet.create({card:{borderRadius:Radius.md,padding:Spacing.three,marginBottom:Spacing.two,alignItems:'flex-end',gap:4},topRow:{flexDirection:'row-reverse',gap:Spacing.one},statusBadge:{paddingHorizontal:Spacing.two,paddingVertical:4,borderRadius:Radius.sm},statusText:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'700'},sideBadge:{paddingHorizontal:Spacing.two,paddingVertical:4,borderRadius:Radius.sm},sideText:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'700'},code:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'800',marginTop:4},instrumentId:{fontFamily:Fonts.mono,fontSize:9},meta:{fontFamily:Fonts.sans,fontSize:12},note:{fontFamily:Fonts.sans,fontSize:12,textAlign:'right',lineHeight:19},date:{fontFamily:Fonts.mono,fontSize:11,marginTop:2}});
function EmptyState({ colors }: { colors: ThemeColors }) { return <View style={emptyStyles.wrap}><Text style={{fontSize:40}}>🧾</Text><Text style={[emptyStyles.title,{color:colors.text}]}>هنوز سفارشی ثبت نشده</Text><Text style={[emptyStyles.body,{color:colors.textSecondary}]}>سفارش Paper در زمان بسته بودن بازار در صف بازگشایی ثبت می‌شود و قبل از اجرا دوباره توسط کیا‌شا و کنترل ریسک بررسی می‌شود.</Text><Pressable onPress={()=>router.push('/market')} style={[emptyStyles.btn,{backgroundColor:Brand.primary}]}><Text style={emptyStyles.btnText}>برو به بازار</Text></Pressable></View>; }
const emptyStyles=StyleSheet.create({wrap:{alignItems:'center',gap:Spacing.two,paddingTop:Spacing.six,paddingHorizontal:Spacing.four},title:{fontFamily:Fonts.sans,fontSize:17,fontWeight:'700'},body:{fontFamily:Fonts.sans,fontSize:13,textAlign:'center',lineHeight:21},btn:{marginTop:Spacing.two,borderRadius:Radius.sm,paddingHorizontal:Spacing.four,paddingVertical:Spacing.three},btnText:{color:'#fff',fontFamily:Fonts.sans,fontSize:14,fontWeight:'700'}});

export default function OrdersScreen(){
  const scheme=useColorScheme()==='dark'?'dark':'light'; const colors=Colors[scheme];
  const[orders,setOrders]=useState<DisplayOrder[]>([]); const[names,setNames]=useState<Record<string,string>>({}); const[refreshing,setRefreshing]=useState(false); const[error,setError]=useState(false);
  const load=useCallback(async()=>{const[legacy,queued]=await Promise.all([fetchOrderHistory(),fetchManualPaperOrders()]);if(legacy===null&&queued===null)setError(true);else{setError(false);const combined=[...(queued??[]),...(legacy??[])];const seen=new Set<string>();const unique=combined.filter(item=>{if(seen.has(item.id))return false;seen.add(item.id);return true});unique.sort((a,b)=>String(b.submittedAt||b.created_at).localeCompare(String(a.submittedAt||a.created_at)));setOrders(unique)}setRefreshing(false)},[]);
  useFocusEffect(useCallback(()=>{load()},[load]));
  useEffect(()=>{let cancelled=false;const numeric=[...new Set(orders.map(o=>o.code).filter(c=>/^\d+$/.test(c)))].filter(c=>!names[c]);if(!numeric.length)return;Promise.all(numeric.map(async code=>[code,await fetchTsetmcInstrumentLabel(code,2200)] as const)).then(rows=>{if(cancelled)return;setNames(cur=>{const next={...cur};for(const[code,label]of rows)if(label)next[code]=label;return next})});return()=>{cancelled=true}},[orders,names]);
  const onRefresh=()=>{setRefreshing(true);load()};
  return <SafeAreaView style={[styles.safe,{backgroundColor:colors.background}]}><ScrollView contentContainerStyle={[styles.content,{paddingBottom:BottomTabInset+Spacing.four}]} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Brand.primary}/>}><View style={{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'}}><View style={styles.header}><Text style={[styles.headerTitle,{color:colors.text}]}>سفارش‌ها</Text><Text style={[styles.headerSub,{color:colors.textSecondary}]}>Paper شما — سفارش خارج از ساعت بازار در صف می‌ماند و هنگام بازگشایی دوباره کنترل می‌شود.</Text></View>{error?<View style={[styles.errorBox,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.errorText,{color:colors.textSecondary}]}>دریافت سفارش‌ها با خطا مواجه شد. برای تلاش دوباره پایین را بکشید.</Text></View>:orders.length===0?<EmptyState colors={colors}/>:orders.map(o=><OrderCard key={o.id} order={o} colors={colors} label={names[o.code]}/>)}</View></ScrollView></SafeAreaView>;
}
const styles=StyleSheet.create({safe:{flex:1},content:{paddingHorizontal:Spacing.three},header:{paddingTop:Spacing.four,paddingBottom:Spacing.three},headerTitle:{fontSize:22,fontFamily:Fonts.sans,textAlign:'right',fontWeight:'700'},headerSub:{fontSize:13,fontFamily:Fonts.sans,textAlign:'right',marginTop:4,lineHeight:21},errorBox:{borderRadius:Radius.md,padding:Spacing.three,marginTop:Spacing.two},errorText:{fontFamily:Fonts.sans,fontSize:13,textAlign:'right'}});
