import { Linking, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, Radius, Spacing } from '@/constants/theme';

// Fixed evidence snapshot from the 2026-10-28 five-issuer CODAL parser regression audit.
// This data is not a live market signal or a backfilled Kiasha evaluation.
type ResearchIssuer = { symbol:string; name:string; code:string; tracing:string; revenue:number; netIncome:number; assets:number; liabilities:number; equity:number; filingUrl:string; oldCall:string|null; oldAt:string|null };
const ISSUERS: ResearchIssuer[] = [{"symbol": "سپیدار", "name": "سپیدار سیستم آسیا", "code": "29590002988360984", "tracing": "1531915", "revenue": 12085377, "netIncome": 8166298, "assets": 27962957, "liabilities": 3136271, "equity": 24826686, "filingUrl": "https://excel.codal.ir/service/Excel/GetAll/jQQQaQQQ13mEO7vjhQhoQS5Kv8vQ%3d%3d/0", "oldCall": null, "oldAt": null}, {"symbol": "مبین", "name": "مبین انرژی خلیج فارس", "code": "19834890400968993", "tracing": "1558868", "revenue": 801264354, "netIncome": 131533844, "assets": 1009985861, "liabilities": 808522157, "equity": 201463704, "filingUrl": "https://excel.codal.ir/service/Excel/GetAll/tJpxQi0biH0na5Mo1XHmOA%3d%3d/0", "oldCall": null, "oldAt": null}, {"symbol": "فخوز", "name": "فولاد خوزستان", "code": "42711713063216333", "tracing": "1584708", "revenue": 1290153813, "netIncome": 87943568, "assets": 1462046402, "liabilities": 1002795175, "equity": 459251227, "filingUrl": "https://excel.codal.ir/service/Excel/GetAll/ig1fMrU6L91kOOObOOOYe6RZLQQQaQQQXg%3d%3d/0", "oldCall": "HOLD", "oldAt": "2026-10-28"}, {"symbol": "دلقما", "name": "دارویی لقمان", "code": "29247915161590165", "tracing": "1524946", "revenue": 23467868, "netIncome": 6373576, "assets": 32946982, "liabilities": 15994754, "equity": 16952228, "filingUrl": "https://excel.codal.ir/service/Excel/GetAll/NZkXA8eyMOGF1CsQQQaQQQ0axHHw%3d%3d/0", "oldCall": "BUY", "oldAt": "2026-09-06"}, {"symbol": "چکاپا", "name": "گروه صنایع کاغذ پارس", "code": "28957320033282870", "tracing": "1504023", "revenue": 15682837, "netIncome": -609980, "assets": 25057957, "liabilities": 14524034, "equity": 10533923, "filingUrl": "https://excel.codal.ir/service/Excel/GetAll/zOrWFaNEieOOObOOOXQQQaQQQzRShS9Wqg%3d%3d/0", "oldCall": "BUY", "oldAt": "2026-10-28"}];
const num=(n:number)=>n.toLocaleString('fa-IR');
export default function ResearchFive() {
 const colors=useColorScheme()==='dark'?Colors.dark:Colors.light;
 return <SafeAreaView style={{flex:1,backgroundColor:colors.background}}>
 <ScrollView contentContainerStyle={{padding:Spacing.three,paddingBottom:BottomTabInset+Spacing.four}}>
 <Pressable onPress={()=>router.back()} style={styles.back}><Text style={{color:Brand.primary,fontFamily:Fonts.sans}}>بازگشت  ←</Text></Pressable>
 <Text style={[styles.title,{color:colors.text}]}>پنج شرکت — آزمایش کدال ایران</Text>
 <Text style={[styles.subtitle,{color:colors.textSecondary}]}>نمونه ثابت پژوهشی ۲۸ اکتبر ۲۰۲۶. این ارقام قیمت لحظه‌ای یا نتیجه تازه کیاشا نیستند. هر دو دوره ترازنامه در استخراج اصلاح‌شده از کنترل اولیه عبور کرده‌اند.</Text>
 <View style={[styles.note,{borderColor:Brand.warning}]}>
  <Text style={[styles.noteText,{color:colors.text}]}>PASS فقط یعنی دارایی = بدهی + حقوق مالکانه در هر دو دوره. تأیید کامل حسابرسی و پیشنهاد خرید یا فروش نیست. رأی‌های تاریخی پیش از اصلاح داده ثبت شده‌اند.</Text>
 </View>
 {ISSUERS.map(item=><View key={item.code} style={[styles.card,{backgroundColor:colors.backgroundElement}]}>
 <View style={styles.head}><Text style={[styles.status,{color:Brand.positive}]}>تراز اولیه: PASS</Text><View style={{alignItems:'flex-end',flex:1}}><Text style={[styles.symbol,{color:colors.text}]}>{item.symbol}</Text><Text style={[styles.name,{color:colors.textSecondary}]}>{item.name}</Text></View></View>
 <Text style={[styles.trace,{color:colors.textSecondary}]}>شناسه گزارش کدال: {item.tracing}  •  دوره: ۱۴۰۴</Text>
 <View style={styles.stats}>
  <View style={styles.stat}><Text style={[styles.value,{color:colors.text}]}>{num(item.revenue)}</Text><Text style={[styles.label,{color:colors.textSecondary}]}>درآمد عملیاتی</Text></View>
  <View style={styles.stat}><Text style={[styles.value,{color:item.netIncome<0?Brand.negative:colors.text}]}>{num(item.netIncome)}</Text><Text style={[styles.label,{color:colors.textSecondary}]}>سود/زیان خالص</Text></View>
 </View>
 <View style={styles.stats}>
  <View style={styles.stat}><Text style={[styles.value,{color:colors.text}]}>{num(item.assets)}</Text><Text style={[styles.label,{color:colors.textSecondary}]}>جمع دارایی‌ها</Text></View>
  <View style={styles.stat}><Text style={[styles.value,{color:colors.text}]}>{num(item.liabilities)}</Text><Text style={[styles.label,{color:colors.textSecondary}]}>جمع بدهی‌ها</Text></View>
 </View>
 <Text style={[styles.label,{color:colors.textSecondary,textAlign:'right',marginTop:8}]}>حقوق مالکانه: {num(item.equity)} • واحد: واحد درج‌شده در خروجی کدال؛ بدون تبدیل ارز</Text>
 <Text style={[styles.history,{color:colors.textSecondary}]}>{item.oldCall ? 'رأی تاریخی کیاشا: '+item.oldCall+' ('+item.oldAt+')؛ پیش از کنترل جدید و غیرقابل اتکا به‌عنوان توصیه امروز' : 'رأی تاریخی کیا‌شا برای این نمونه ثبت نشده است.'}</Text>
 <View style={styles.actions}>
  <Pressable style={[styles.link,{borderColor:Brand.primary}]} onPress={()=>void Linking.openURL(item.filingUrl)}><Text style={[styles.linkText,{color:Brand.primary}]}>گزارش کدال</Text></Pressable>
  <Pressable style={[styles.cta,{backgroundColor:Brand.primary}]} onPress={()=>router.push(('/stock/'+encodeURIComponent(item.code)) as never)}><Text style={styles.ctaText}>تحلیل فعلی</Text></Pressable>
 </View>
 </View>)}
 <Text style={[styles.footer,{color:colors.textSecondary}]}>تحلیل فعلی با اطلاعات دریافتی API در زمان درخواست تولید می‌شود. اگر شواهد معتبر کافی نباشد، کیاشا باید از تصمیم خرید/فروش خودداری کند. این صفحه جایگزین تحلیل زنده نیست.</Text>
 </ScrollView>
 </SafeAreaView>;
}
const styles=StyleSheet.create({
 back:{paddingVertical:14,alignSelf:'flex-end'},title:{fontFamily:Fonts.sans,fontSize:23,fontWeight:'900',textAlign:'right',marginTop:8},subtitle:{fontFamily:Fonts.sans,fontSize:12,lineHeight:22,textAlign:'right',marginTop:10,marginBottom:16},
 note:{borderWidth:1,borderRadius:Radius.md,padding:14,marginBottom:16},noteText:{fontFamily:Fonts.sans,fontSize:11,lineHeight:21,textAlign:'right'},
 card:{borderRadius:Radius.lg,padding:16,marginBottom:12},head:{flexDirection:'row',alignItems:'center',justifyContent:'space-between'},
 symbol:{fontFamily:Fonts.sans,fontSize:20,fontWeight:'900'},name:{fontFamily:Fonts.sans,fontSize:11,marginTop:3},
 status:{fontFamily:Fonts.sans,fontSize:10,fontWeight:'900'},trace:{fontFamily:Fonts.sans,fontSize:10,textAlign:'right',marginTop:12,marginBottom:6},
 stats:{flexDirection:'row-reverse',gap:8,marginTop:8},
 stat:{flex:1,alignItems:'flex-end',minWidth:0},value:{fontFamily:Fonts.mono,fontSize:14,fontWeight:'900'},label:{fontFamily:Fonts.sans,fontSize:10,marginTop:4},
 history:{fontFamily:Fonts.sans,fontSize:11,textAlign:'right',lineHeight:19,marginTop:12},
 actions:{flexDirection:'row-reverse',gap:8,marginTop:15},cta:{flex:1,borderRadius:Radius.sm,padding:12,alignItems:'center'},link:{flex:1,borderWidth:1,borderRadius:Radius.sm,padding:12,alignItems:'center'},ctaText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},linkText:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'800'},footer:{fontFamily:Fonts.sans,fontSize:10,lineHeight:19,textAlign:'right',marginTop:8}
});
