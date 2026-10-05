import { View, Text, StyleSheet, ScrollView, useColorScheme, SafeAreaView, Pressable, Alert, Linking } from 'react-native';
import Constants from 'expo-constants';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { useLogout } from '@/lib/logout-context';
import { logoutAndClearAuthSession } from '@/lib/auth-session';
import { API_BASE } from '@/lib/api';

type MenuItem = { icon: string; title: string; sub: string; onPress: () => void; destructive?: boolean; accent?: string };
type MobileRelease = { version: string; versionCode?: number | null; releasedAt?: string | null; changes?: string[]; apkAvailable?: boolean; apkUrl?: string };

const FARABI_TRADING_URL = 'https://m.farabixo.irfarabi.com';
const FARABIZ_PARTNER_URL = 'https://farabiz.irfarabi.com';

function MenuRow({ item, colors }: { item: MenuItem; colors: ThemeColors }) {
  return (
    <Pressable onPress={item.onPress} style={({ pressed }) => [rowStyles.row, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.8 : 1 }]}>
      <Text style={[rowStyles.chevron, { color: colors.textSecondary }]}>‹</Text>
      <View style={rowStyles.textWrap}>
        <Text style={[rowStyles.title, { color: item.destructive ? Brand.negative : colors.text }]}>{item.title}</Text>
        <Text style={[rowStyles.sub, { color: colors.textSecondary }]}>{item.sub}</Text>
      </View>
      <View style={[rowStyles.iconWrap, item.accent ? { backgroundColor: `${item.accent}22` } : null]}><Text style={{ fontSize: 20 }}>{item.icon}</Text></View>
    </Pressable>
  );
}

const rowStyles = StyleSheet.create({
  row: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.three, borderRadius: Radius.md, padding: Spacing.three, marginBottom: Spacing.two },
  textWrap: { flex: 1, alignItems: 'flex-end', gap: 2 }, title: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '700' }, sub: { fontFamily: Fonts.sans, fontSize: 12 }, chevron: { fontSize: 18 }, iconWrap: { width: 40, height: 40, borderRadius: Radius.sm, alignItems: 'center', justifyContent: 'center' },
});

function versionParts(value: string): number[] {
  return value.split('.').map((part) => Number.parseInt(part, 10) || 0);
}

function isNewerVersion(latest: string, current: string): boolean {
  const a = versionParts(latest); const b = versionParts(current); const length = Math.max(a.length, b.length);
  for (let i = 0; i < length; i += 1) {
    const left = a[i] || 0; const right = b[i] || 0;
    if (left !== right) return left > right;
  }
  return false;
}

function releaseDownloadUrl(release: MobileRelease): string {
  const path = release.apkUrl || '/app/latest.apk';
  return /^https?:\/\//i.test(path) ? path : `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

async function openUrl(url: string, title: string) {
  try {
    await Linking.openURL(url);
  } catch {
    Alert.alert(title, 'باز کردن این صفحه ممکن نشد. اتصال اینترنت را بررسی کنید.');
  }
}

export default function MoreScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light'; const colors = Colors[scheme]; const logout = useLogout();
  const currentVersion = Constants.expoConfig?.version || 'unknown';
  const currentVersionCode = Constants.platform?.android?.versionCode ?? null;
  const openModules = () => router.push('/modules' as never);
  const handleLogout = () => { Alert.alert('خروج از حساب', 'آیا مطمئن هستید که می‌خواهید خارج شوید؟', [{ text: 'انصراف', style: 'cancel' }, { text: 'خروج', style: 'destructive', onPress: async () => { await logoutAndClearAuthSession(); logout(); } }]); };

  const checkForUpdate = async () => {
    try {
      const response = await fetch(`${API_BASE}/app/release`, { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const release = await response.json() as MobileRelease;
      if (!release?.version) throw new Error('invalid release');

      const releaseVersionCode = typeof release.versionCode === 'number' ? release.versionCode : null;
      const currentByNativeBuild = typeof currentVersionCode === 'number' && releaseVersionCode !== null && currentVersionCode >= releaseVersionCode;
      const currentBySemanticVersion = currentVersion !== 'unknown' && !isNewerVersion(release.version, currentVersion);
      if (currentByNativeBuild || currentBySemanticVersion) {
        const installedDisplay = currentByNativeBuild && currentVersion !== release.version ? release.version : currentVersion;
        const buildDisplay = typeof currentVersionCode === 'number' ? `\nBuild نصب‌شده: ${currentVersionCode}` : '';
        Alert.alert('BIAP به‌روز است', `نسخه نصب‌شده: ${installedDisplay}${buildDisplay}\nآخرین نسخه: ${release.version}`);
        return;
      }

      const notes = Array.isArray(release.changes) && release.changes.length
        ? `\n\nتغییرات:\n• ${release.changes.slice(0, 5).join('\n• ')}`
        : '';
      const unavailable = release.apkAvailable === false ? '\n\nفایل APK هنوز روی سرور انتشار قرار نگرفته است.' : '';
      const currentBuild = typeof currentVersionCode === 'number' ? ` (build ${currentVersionCode})` : '';
      Alert.alert(
        'نسخه جدید BIAP',
        `نسخه نصب‌شده: ${currentVersion}${currentBuild}\nنسخه جدید: ${release.version}${notes}${unavailable}`,
        [
          { text: 'بعداً', style: 'cancel' },
          ...(release.apkAvailable === false ? [] : [{ text: 'دانلود و نصب', onPress: () => { void openUrl(releaseDownloadUrl(release), 'به‌روزرسانی BIAP'); } }]),
        ],
      );
    } catch {
      Alert.alert('بررسی به‌روزرسانی', 'در حال حاضر ارتباط با مرکز به‌روزرسانی برقرار نشد. کمی بعد دوباره امتحان کنید.');
    }
  };

  const openFarabiTrading = () => {
    Alert.alert(
      'معاملات آنلاین فارابی',
      'برای خرید و فروش واقعی وارد سامانه رسمی فارابیکسو می‌شوید. BIAP فعلاً API معاملاتی فارابی ندارد و هیچ سفارش یا رمز کارگزاری را دریافت نمی‌کند.',
      [
        { text: 'انصراف', style: 'cancel' },
        { text: 'ورود به فارابیکسو', onPress: () => { void openUrl(FARABI_TRADING_URL, 'فارابیکسو'); } },
      ],
    );
  };

  const items: MenuItem[] = [
    { icon: '🔄', title: 'به‌روزرسانی BIAP', sub: `بررسی نسخه جدید و دانلود APK • نسخه فعلی ${currentVersion}`, onPress: () => { void checkForUpdate(); }, accent: Brand.primary },
    { icon: '📈', title: 'معاملات آنلاین فارابی', sub: 'ورود امن به سامانه رسمی فارابیکسو برای خرید و فروش واقعی', onPress: openFarabiTrading, accent: Brand.positive },
    { icon: '🤝', title: 'همکاری با فارابی (فارابیز پلاس)', sub: 'برنامه رسمی معرفی صندوق‌های ETF و درآمد مشارکتی فارابی', onPress: () => { void openUrl(FARABIZ_PARTNER_URL, 'فارابیز پلاس'); }, accent: '#0ea5e9' },
    { icon: '🧾', title: 'سفارش‌ها', sub: 'سفارش‌های Paper و تاریخچه اجرای کیا‌شا', onPress: () => router.push('/orders'), accent: Brand.warning },
    { icon: '💼', title: 'پرتفوی', sub: 'موقعیت‌ها، تخصیص سرمایه و بازده Paper', onPress: () => router.push('/portfolio'), accent: Brand.secondary },
    { icon: '⭐', title: 'علاقه‌مندی‌ها', sub: 'نمادهایی که برای بررسی بعدی ذخیره کرده‌اید', onPress: () => router.push('/favorites' as never), accent: '#f59e0b' },
    { icon: '❓', title: 'چطور از BIAP استفاده کنم؟', sub: 'How to do it • راهنمای بازار، کیا‌شا، Paper و ماژول‌ها', onPress: () => router.push('/how-to' as never), accent: Brand.primary },
    { icon: '🤖', title: 'پروفایل سرمایه‌گذاری کیا‌شا', sub: 'سرمایه Paper، بازده، دقت و Track Record ایجنت', onPress: () => router.push('/kiasha-profile' as never), accent: '#7c3aed' },
    { icon: '🧩', title: 'همه ماژول‌های BIAP', sub: 'سرمایه‌گذاری، داده، KPI، کسب‌وکار و مدل مالی', onPress: openModules, accent: Brand.primary },
    { icon: '💼', title: 'توسعه کسب‌وکار', sub: 'SWOT، CRM، Journey، کمپین و مدل مالی', onPress: () => router.push('/bizdev'), accent: Brand.secondary },
    { icon: '📊', title: 'تحلیل داده', sub: 'EDA، آمار، نمودار و خروجی CSV', onPress: () => router.push('/data'), accent: Brand.dataViolet },
    { icon: '🔌', title: 'اتصال داده', sub: 'داده شرکت برای ماژول‌های تحلیل و کسب‌وکار', onPress: () => router.push('/data-connect' as never), accent: Brand.dataViolet },
    { icon: '👤', title: 'حساب کاربری', sub: 'اطلاعات، تغییر رمز و تنظیمات حساب', onPress: () => router.push('/profile') },
  ];

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}><View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
    <View style={styles.header}><Text style={[styles.headerTitle, { color: colors.text }]}>بیشتر</Text><Text style={[styles.headerSub, { color: colors.textSecondary }]}>مرکز ماژول‌ها، معاملات، به‌روزرسانی، راهنما و تنظیمات BIAP</Text></View>
    <Pressable onPress={() => router.push('/how-to' as never)} style={[styles.hero, { backgroundColor: colors.backgroundElement }]}><Text style={styles.heroEyebrow}>START HERE</Text><Text style={[styles.heroTitle, { color: colors.text }]}>اولین بار است؟ از اینجا شروع کن</Text><Text style={[styles.heroBody, { color: colors.textSecondary }]}>راهنمای قدم‌به‌قدم بازار، کیا‌شا، Paper Trade، تحلیل داده و مسیر معاملات واقعی.</Text><Text style={styles.heroLink}>مشاهده راهنما ←</Text></Pressable>
    {items.map((item) => <MenuRow key={item.title} item={item} colors={colors} />)}
    <View style={{ height: Spacing.three }} /><MenuRow item={{ icon: '🚪', title: 'خروج از حساب', sub: 'خروج از حساب کاربری فعلی', onPress: handleLogout, destructive: true }} colors={colors} />
  </View></ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({ safe:{flex:1},content:{paddingHorizontal:Spacing.three},header:{paddingTop:Spacing.four,paddingBottom:Spacing.three,alignItems:'flex-end'},headerTitle:{fontSize:22,fontFamily:Fonts.sans,textAlign:'right',fontWeight:'800'},headerSub:{fontSize:12,fontFamily:Fonts.sans,textAlign:'right',marginTop:3},hero:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.three,alignItems:'flex-end'},heroEyebrow:{color:'#8ab4ff',fontFamily:Fonts.mono,fontSize:11,fontWeight:'800'},heroTitle:{fontFamily:Fonts.sans,fontSize:18,fontWeight:'800',marginTop:6},heroBody:{fontFamily:Fonts.sans,fontSize:12,lineHeight:20,textAlign:'right',marginTop:5},heroLink:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:12,fontWeight:'700',marginTop:Spacing.two} });
