import { SafeAreaView, ScrollView, StyleSheet, Text, View, Pressable, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';

const SOURCES = [
  {
    key: 'csv',
    icon: '📄',
    title: 'CSV / Excel',
    body: 'برای تحلیل داده شرکت، فایل CSV/Excel به فضای امن حساب متصل می‌شود. آپلود و پردازش واقعی باید روی بک‌اند حساب فعال شود.',
    state: 'آماده اتصال بک‌اند',
  },
  {
    key: 'sql',
    icon: '🗄️',
    title: 'SQL / Database',
    body: 'اتصال فقط با کانکتور سمت سرور و دسترسی محدود Read-only انجام می‌شود؛ رمز دیتابیس داخل اپ موبایل ذخیره نمی‌شود.',
    state: 'آماده اتصال بک‌اند',
  },
  {
    key: 'crm',
    icon: '👥',
    title: 'CRM / ERP',
    body: 'برای KPI، Journey، Pricing و Pipeline می‌توان API رسمی CRM/ERP را به حساب متصل کرد.',
    state: 'آماده اتصال API',
  },
  {
    key: 'api',
    icon: '🔌',
    title: 'Custom API',
    body: 'منبع اختصاصی شرکت از طریق API مجاز به BIAP وصل می‌شود. کلیدها باید فقط سمت سرور نگهداری شوند.',
    state: 'آماده اتصال API',
  },
] as const;

export default function DataConnectScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
    <ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}>
      <View style={styles.wrap}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.backText, { color: colors.text }]}>←</Text></Pressable>
          <View style={styles.headerCopy}><Text style={[styles.title, { color: colors.text }]}>اتصال داده</Text><Text style={[styles.sub, { color: colors.textSecondary }]}>Data Connections • منابع واقعی برای تحلیل</Text></View>
        </View>

        <View style={[styles.activeCard, { backgroundColor: colors.backgroundElement }]}>
          <View style={styles.activeHead}><View style={styles.liveBadge}><Text style={styles.liveBadgeText}>LIVE</Text></View><Text style={[styles.activeTitle, { color: colors.text }]}>منابع فعال BIAP</Text></View>
          <Text style={[styles.body, { color: colors.textSecondary }]}>داده بازار، CODAL و عملکرد Kiasha همین حالا به ماژول‌های سازگار متصل هستند. اگر داده معتبر موجود نباشد، خروجی خالی می‌ماند.</Text>
          <View style={styles.liveRow}><Text style={[styles.liveItem, { color: Brand.positive }]}>● Kiasha Performance</Text><Text style={[styles.liveItem, { color: Brand.positive }]}>● BIAP Market / CODAL</Text></View>
        </View>

        <Text style={[styles.section, { color: colors.text }]}>داده اختصاصی شرکت</Text>
        <Text style={[styles.sectionNote, { color: colors.textSecondary }]}>این اتصال‌ها برای ماژول‌های EDA، KPI، SQL، CRM، Pricing، Journey، Financial Model و سایر ابزارهای کسب‌وکار استفاده می‌شوند.</Text>

        {SOURCES.map((source) => <View key={source.key} style={[styles.sourceCard, { backgroundColor: colors.backgroundElement }]}>
          <View style={styles.sourceTop}><View style={[styles.sourceIcon, { backgroundColor: colors.backgroundSelected }]}><Text style={styles.sourceIconText}>{source.icon}</Text></View><View style={styles.sourceCopy}><Text style={[styles.sourceTitle, { color: colors.text }]}>{source.title}</Text><Text style={[styles.body, { color: colors.textSecondary }]}>{source.body}</Text></View></View>
          <View style={[styles.soonRow, { borderTopColor: colors.backgroundSelected }]}><Text style={[styles.soonText, { color: colors.textSecondary }]}>{source.state}</Text><View style={styles.soonBadge}><Text style={styles.soonBadgeText}>SOON</Text></View></View>
        </View>)}

        <View style={[styles.security, { backgroundColor: colors.backgroundElement }]}>
          <Text style={[styles.securityTitle, { color: colors.text }]}>قانون امنیت اتصال</Text>
          <Text style={[styles.body, { color: colors.textSecondary }]}>رمز دیتابیس، API secret و credential حساس نباید داخل اپ موبایل ذخیره شود. اتصال واقعی از بک‌اند BIAP انجام می‌شود و دسترسی‌ها باید حداقلی و قابل لغو باشند.</Text>
        </View>

        <Pressable onPress={() => router.push('/modules' as never)} style={styles.primary}><Text style={styles.primaryText}>بازگشت به ماژول‌های تحلیل</Text></Pressable>
      </View>
    </ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingTop:Spacing.three},wrap:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},
  headerRow:{flexDirection:'row-reverse',alignItems:'center',gap:Spacing.three,marginBottom:Spacing.three},headerCopy:{flex:1,alignItems:'flex-end'},back:{width:38,height:38,borderRadius:19,alignItems:'center',justifyContent:'center'},backText:{fontSize:19},title:{fontFamily:Fonts.sans,fontSize:23,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:11,marginTop:3},
  activeCard:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.four,borderWidth:1,borderColor:'#166534'},activeHead:{width:'100%',flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center'},activeTitle:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900'},liveBadge:{backgroundColor:'#14532d',paddingHorizontal:9,paddingVertical:4,borderRadius:12},liveBadgeText:{color:'#86efac',fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},body:{fontFamily:Fonts.sans,fontSize:11.5,lineHeight:20,textAlign:'right',marginTop:6},liveRow:{flexDirection:'row-reverse',flexWrap:'wrap',gap:14,marginTop:12},liveItem:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'800'},
  section:{fontFamily:Fonts.sans,fontSize:17,fontWeight:'900',textAlign:'right'},sectionNote:{fontFamily:Fonts.sans,fontSize:11,lineHeight:19,textAlign:'right',marginTop:4,marginBottom:Spacing.three},
  sourceCard:{borderRadius:Radius.md,padding:Spacing.three,marginBottom:Spacing.two},sourceTop:{flexDirection:'row-reverse',gap:Spacing.three,alignItems:'flex-start'},sourceIcon:{width:44,height:44,borderRadius:22,alignItems:'center',justifyContent:'center'},sourceIconText:{fontSize:20},sourceCopy:{flex:1,alignItems:'flex-end'},sourceTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'900'},soonRow:{marginTop:Spacing.three,paddingTop:Spacing.two,borderTopWidth:StyleSheet.hairlineWidth,flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center'},soonText:{fontFamily:Fonts.sans,fontSize:10},soonBadge:{backgroundColor:'#4c1d95',borderRadius:10,paddingHorizontal:8,paddingVertical:4},soonBadgeText:{color:'#ddd6fe',fontFamily:Fonts.mono,fontSize:8.5,fontWeight:'900'},
  security:{borderRadius:Radius.md,padding:Spacing.three,marginTop:Spacing.two,alignItems:'flex-end'},securityTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'900'},primary:{backgroundColor:Brand.primary,borderRadius:Radius.md,paddingVertical:13,alignItems:'center',marginTop:Spacing.three},primaryText:{color:'#fff',fontFamily:Fonts.sans,fontSize:13,fontWeight:'900'},
});
