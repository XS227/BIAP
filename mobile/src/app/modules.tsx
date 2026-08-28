import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing, ThemeColors } from '@/constants/theme';

type ModuleItem = {
  key: string;
  title: string;
  subtitle: string;
  icon: string;
  href?: '/market' | '/portfolio' | '/kiasha';
};

type ModuleGroup = { key: string; title: string; accent: string; items: ModuleItem[] };

const GROUPS: ModuleGroup[] = [
  { key: 'investment', title: 'سرمایه‌گذاری و بورس', accent: Brand.positive, items: [
    { key: 'market', title: 'بازار و تحلیل نماد', subtitle: 'TSETMC، قیمت و نمادها', icon: '📈', href: '/market' },
    { key: 'kiasha', title: 'کیاشا AI Agents', subtitle: 'پیشنهاد خرید، نگهداری یا فروش', icon: '🤖', href: '/kiasha' },
    { key: 'portfolio', title: 'پرتفوی', subtitle: 'دارایی و عملکرد Paper/Real', icon: '💼', href: '/portfolio' },
  ]},
  { key: 'data', title: 'تحلیل داده', accent: Brand.dataViolet, items: [
    { key: 'eda', title: 'EDA Explorer', subtitle: 'تحلیل اکتشافی و الگوها', icon: '🔬' },
    { key: 'sql', title: 'SQL Query', subtitle: 'کوئری و تحلیل داده', icon: '🗄️' },
    { key: 'anomaly', title: 'تشخیص ناهنجاری', subtitle: 'Outlier و رفتار غیرعادی', icon: '🚨' },
    { key: 'forecast', title: 'پیش‌بینی آماری', subtitle: 'روند و سری زمانی', icon: '📉' },
  ]},
  { key: 'kpi', title: 'KPI و داشبورد', accent: Brand.primary, items: [
    { key: 'kpi-extract', title: 'استخراج KPI', subtitle: 'شاخص‌های کلیدی و RAG', icon: '🎯' },
    { key: 'dashboard', title: 'BI Dashboard', subtitle: 'داشبورد مدیریتی', icon: '📊' },
    { key: 'governance', title: 'KPI Governance', subtitle: 'مالک، هدف و چرخه شاخص', icon: '📏' },
    { key: 'report', title: 'گزارش تحلیلی', subtitle: 'خلاصه قابل ارائه', icon: '📋' },
  ]},
  { key: 'business', title: 'توسعه کسب‌وکار', accent: Brand.secondary, items: [
    { key: 'swot', title: 'SWOT + رقبا', subtitle: 'رقبا و موقعیت بازار', icon: '⚔️' },
    { key: 'journey', title: 'Journey Map', subtitle: 'نقاط تماس و درد مشتری', icon: '🗺️' },
    { key: 'crm', title: 'CRM + Pipeline', subtitle: 'قیف فروش و فرصت‌ها', icon: '👥' },
    { key: 'campaign', title: 'کمپین بازاریابی', subtitle: 'هدف، کانال و پیام', icon: '📣' },
    { key: 'pricing', title: 'قیمت‌گذاری هوشمند', subtitle: 'سناریوهای قیمت', icon: '💰' },
    { key: 'plan', title: 'Business Plan', subtitle: 'طرح کسب‌وکار', icon: '📄' },
  ]},
  { key: 'finance', title: 'مدل مالی', accent: '#4b8cff', items: [
    { key: 'financial-model', title: 'Financial Modeling', subtitle: 'مدل مالی و سناریو', icon: '📈' },
    { key: 'scenario', title: 'Scenario Analysis', subtitle: 'خوش‌بینانه، پایه، بدبینانه', icon: '🔮' },
    { key: 'unit', title: 'Unit Economics', subtitle: 'CAC، LTV و اقتصاد واحد', icon: '⚙️' },
    { key: 'mbr', title: 'گزارش MBR', subtitle: 'گزارش ماهانه مدیریت', icon: '🧾' },
  ]},
];

function ModuleCard({ item, colors, accent }: { item: ModuleItem; colors: ThemeColors; accent: string }) {
  const open = () => {
    if (item.href) router.push(item.href);
    else router.push({ pathname: '/module', params: { key: item.key } } as never);
  };
  return (
    <Pressable onPress={open} style={({ pressed }) => [styles.moduleCard, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.75 : 1 }]}>
      <View style={[styles.moduleIcon, { backgroundColor: `${accent}22` }]}><Text style={styles.moduleEmoji}>{item.icon}</Text></View>
      <Text style={[styles.moduleTitle, { color: colors.text }]}>{item.title}</Text>
      <Text style={[styles.moduleSubtitle, { color: colors.textSecondary }]}>{item.subtitle}</Text>
    </Pressable>
  );
}

export default function ModulesScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.six }]}>
        <View style={styles.maxWidth}>
          <View style={styles.headerRow}>
            <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.backText, { color: colors.text }]}>←</Text></Pressable>
            <View style={styles.headerText}><Text style={[styles.title, { color: colors.text }]}>همه ماژول‌های BIAP</Text><Text style={[styles.subtitle, { color: colors.textSecondary }]}>Business & Investment Analysis Platform</Text></View>
          </View>
          <View style={[styles.hero, { backgroundColor: colors.backgroundElement }]}>
            <Text style={styles.heroMark}>BIAP V2</Text>
            <Text style={[styles.heroTitle, { color: colors.text }]}>یک اپ؛ سرمایه‌گذاری، داده و رشد کسب‌وکار</Text>
            <Text style={[styles.heroBody, { color: colors.textSecondary }]}>ماژول‌های سرمایه‌گذاری از داده واقعی استفاده می‌کنند. برای ماژول‌های بدون API موبایل، Demo Mode به‌صورت صریح و جداگانه قابل فعال‌سازی است.</Text>
          </View>
          {GROUPS.map((group) => (
            <View key={group.key} style={styles.group}>
              <View style={styles.groupHead}><View style={[styles.dot, { backgroundColor: group.accent }]} /><Text style={[styles.groupTitle, { color: colors.text }]}>{group.title}</Text></View>
              <View style={styles.grid}>{group.items.map((item) => <ModuleCard key={item.key} item={item} colors={colors} accent={group.accent} />)}</View>
            </View>
          ))}
          <View style={[styles.demoPanel, { backgroundColor: colors.backgroundElement }]}>
            <Text style={styles.demoChip}>DEMO SAFE</Text>
            <Text style={[styles.demoPanelTitle, { color: colors.text }]}>داده نمونه داخل هر ماژول</Text>
            <Text style={[styles.demoDisclaimer, { color: colors.textSecondary }]}>روی هر ماژول داده/KPI/کسب‌وکار بزن. داخل صفحه خودش Demo Mode را روشن کن؛ همه اعداد نمونه با برچسب DEMO نمایش داده می‌شوند و به حساب واقعی یا سفارش‌ها نوشته نمی‌شوند.</Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 }, content: { paddingHorizontal: Spacing.three, paddingTop: Spacing.three }, maxWidth: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  headerRow: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.three, marginBottom: Spacing.three }, headerText: { flex: 1, alignItems: 'flex-end' },
  title: { fontFamily: Fonts.sans, fontSize: 22, fontWeight: '800' }, subtitle: { fontFamily: Fonts.sans, fontSize: 11, marginTop: 3 }, back: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center' }, backText: { fontSize: 19 },
  hero: { borderRadius: Radius.lg, padding: Spacing.four, marginBottom: Spacing.four }, heroMark: { color: '#8ab4ff', fontFamily: Fonts.mono, fontSize: 12, fontWeight: '800', marginBottom: 8 }, heroTitle: { fontFamily: Fonts.sans, fontSize: 19, fontWeight: '800', textAlign: 'right', lineHeight: 30 }, heroBody: { fontFamily: Fonts.sans, fontSize: 12, textAlign: 'right', lineHeight: 21, marginTop: 6 },
  group: { marginBottom: Spacing.four }, groupHead: { flexDirection: 'row-reverse', alignItems: 'center', gap: 7, marginBottom: Spacing.two }, dot: { width: 8, height: 8, borderRadius: 4 }, groupTitle: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '800' }, grid: { flexDirection: 'row-reverse', flexWrap: 'wrap', gap: Spacing.two },
  moduleCard: { flexBasis: '48%', flexGrow: 1, minHeight: 132, borderRadius: Radius.md, padding: Spacing.three, alignItems: 'flex-end' }, moduleIcon: { width: 42, height: 42, borderRadius: Radius.sm, alignItems: 'center', justifyContent: 'center', marginBottom: 8 }, moduleEmoji: { fontSize: 20 }, moduleTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '800', textAlign: 'right' }, moduleSubtitle: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 17, textAlign: 'right', marginTop: 4 },
  demoPanel: { borderRadius: Radius.lg, padding: Spacing.four }, demoChip: { alignSelf: 'flex-end', color: '#fff', backgroundColor: '#7048e8', paddingHorizontal: 9, paddingVertical: 4, borderRadius: 12, overflow: 'hidden', fontFamily: Fonts.mono, fontSize: 10, fontWeight: '800' }, demoPanelTitle: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '800', textAlign: 'right', marginTop: Spacing.two }, demoDisclaimer: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 18, textAlign: 'right', marginTop: Spacing.two },
});
