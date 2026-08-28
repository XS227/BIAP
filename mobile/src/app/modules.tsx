import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing, ThemeColors } from '@/constants/theme';

type ModuleItem = {
  key: string;
  title: string;
  subtitle: string;
  icon: string;
  href: '/data' | '/bizdev' | '/market' | '/portfolio' | '/kiasha';
};

type ModuleGroup = {
  key: string;
  title: string;
  accent: string;
  items: ModuleItem[];
};

const GROUPS: ModuleGroup[] = [
  {
    key: 'investment',
    title: 'سرمایه‌گذاری و بورس',
    accent: Brand.positive,
    items: [
      { key: 'market', title: 'بازار و تحلیل نماد', subtitle: 'TSETMC، قیمت و نمادها', icon: '📈', href: '/market' },
      { key: 'kiasha', title: 'کیاشا AI Agents', subtitle: 'پیشنهاد خرید، نگهداری یا فروش', icon: '🤖', href: '/kiasha' },
      { key: 'portfolio', title: 'پرتفوی', subtitle: 'دارایی و عملکرد Paper/Real', icon: '💼', href: '/portfolio' },
    ],
  },
  {
    key: 'data',
    title: 'تحلیل داده',
    accent: Brand.dataViolet,
    items: [
      { key: 'eda', title: 'EDA Explorer', subtitle: 'تحلیل اکتشافی و الگوها', icon: '🔬', href: '/data' },
      { key: 'sql', title: 'SQL Query', subtitle: 'کوئری و تحلیل داده', icon: '🗄️', href: '/data' },
      { key: 'anomaly', title: 'تشخیص ناهنجاری', subtitle: 'Outlier و رفتار غیرعادی', icon: '🚨', href: '/data' },
      { key: 'forecast', title: 'پیش‌بینی آماری', subtitle: 'روند و سری زمانی', icon: '📉', href: '/data' },
    ],
  },
  {
    key: 'kpi',
    title: 'KPI و داشبورد',
    accent: Brand.primary,
    items: [
      { key: 'kpi-extract', title: 'استخراج KPI', subtitle: 'شاخص‌های کلیدی و RAG', icon: '🎯', href: '/data' },
      { key: 'dashboard', title: 'BI Dashboard', subtitle: 'داشبورد مدیریتی', icon: '📊', href: '/data' },
      { key: 'governance', title: 'KPI Governance', subtitle: 'مالک، هدف و چرخه شاخص', icon: '📏', href: '/data' },
      { key: 'report', title: 'گزارش تحلیلی', subtitle: 'خلاصه قابل ارائه', icon: '📋', href: '/data' },
    ],
  },
  {
    key: 'business',
    title: 'توسعه کسب‌وکار',
    accent: Brand.secondary,
    items: [
      { key: 'swot', title: 'SWOT + رقبا', subtitle: 'رقبا و موقعیت بازار', icon: '⚔️', href: '/bizdev' },
      { key: 'journey', title: 'Journey Map', subtitle: 'نقاط تماس و درد مشتری', icon: '🗺️', href: '/bizdev' },
      { key: 'crm', title: 'CRM + Pipeline', subtitle: 'قیف فروش و فرصت‌ها', icon: '👥', href: '/bizdev' },
      { key: 'campaign', title: 'کمپین بازاریابی', subtitle: 'هدف، کانال و پیام', icon: '📣', href: '/bizdev' },
      { key: 'pricing', title: 'قیمت‌گذاری هوشمند', subtitle: 'سناریوهای قیمت', icon: '💰', href: '/bizdev' },
      { key: 'plan', title: 'Business Plan', subtitle: 'طرح کسب‌وکار', icon: '📄', href: '/bizdev' },
    ],
  },
  {
    key: 'finance',
    title: 'مدل مالی',
    accent: '#4b8cff',
    items: [
      { key: 'financial-model', title: 'Financial Modeling', subtitle: 'مدل مالی و سناریو', icon: '📈', href: '/bizdev' },
      { key: 'scenario', title: 'Scenario Analysis', subtitle: 'سناریوی خوش‌بینانه/پایه/بدبینانه', icon: '🔮', href: '/bizdev' },
      { key: 'unit', title: 'Unit Economics', subtitle: 'CAC، LTV و اقتصاد واحد', icon: '⚙️', href: '/bizdev' },
      { key: 'mbr', title: 'گزارش MBR', subtitle: 'گزارش ماهانه مدیریت', icon: '🧾', href: '/bizdev' },
    ],
  },
];

function ModuleCard({ item, colors, accent }: { item: ModuleItem; colors: ThemeColors; accent: string }) {
  return (
    <Pressable
      onPress={() => router.push(item.href)}
      style={({ pressed }) => [styles.moduleCard, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.75 : 1 }]}
    >
      <View style={[styles.moduleIcon, { backgroundColor: `${accent}22` }]}>
        <Text style={styles.moduleEmoji}>{item.icon}</Text>
      </View>
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
            <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.backText, { color: colors.text }]}>←</Text>
            </Pressable>
            <View style={styles.headerText}>
              <Text style={[styles.title, { color: colors.text }]}>همه ماژول‌های BIAP</Text>
              <Text style={[styles.subtitle, { color: colors.textSecondary }]}>Business & Investment Analysis Platform</Text>
            </View>
          </View>

          <View style={[styles.hero, { backgroundColor: colors.backgroundElement }]}> 
            <Text style={styles.heroMark}>BIAP V2</Text>
            <Text style={[styles.heroTitle, { color: colors.text }]}>یک اپ؛ سرمایه‌گذاری، داده و رشد کسب‌وکار</Text>
            <Text style={[styles.heroBody, { color: colors.textSecondary }]}>داده واقعی همیشه اولویت دارد. داده نمونه فقط در Demo Mode و با برچسب واضح نمایش داده می‌شود.</Text>
            <View style={styles.demoBadge}><Text style={styles.demoBadgeText}>DEMO SAFE • داده نمونه جدا از داده واقعی</Text></View>
          </View>

          {GROUPS.map((group) => (
            <View key={group.key} style={styles.group}>
              <View style={styles.groupHead}>
                <View style={[styles.dot, { backgroundColor: group.accent }]} />
                <Text style={[styles.groupTitle, { color: colors.text }]}>{group.title}</Text>
              </View>
              <View style={styles.grid}>
                {group.items.map((item) => <ModuleCard key={item.key} item={item} colors={colors} accent={group.accent} />)}
              </View>
            </View>
          ))}

          <View style={[styles.demoPanel, { backgroundColor: colors.backgroundElement }]}> 
            <View style={styles.demoPanelHead}>
              <Text style={styles.demoChip}>DEMO</Text>
              <Text style={[styles.demoPanelTitle, { color: colors.text }]}>پیش‌نمایش Demo User</Text>
            </View>
            <View style={styles.demoStats}>
              <View style={styles.demoStat}><Text style={[styles.demoValue, { color: Brand.positive }]}>+12.4٪</Text><Text style={[styles.demoLabel, { color: colors.textSecondary }]}>رشد نمونه</Text></View>
              <View style={styles.demoStat}><Text style={[styles.demoValue, { color: Brand.primary }]}>72</Text><Text style={[styles.demoLabel, { color: colors.textSecondary }]}>امتیاز نمونه</Text></View>
              <View style={styles.demoStat}><Text style={[styles.demoValue, { color: Brand.warning }]}>8</Text><Text style={[styles.demoLabel, { color: colors.textSecondary }]}>KPI نمونه</Text></View>
            </View>
            <Text style={[styles.demoDisclaimer, { color: colors.textSecondary }]}>این اعداد فقط برای نمایش رابط Demo هستند و برای کاربر واقعی هرگز جایگزین داده ناموجود نمی‌شوند.</Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingTop: Spacing.three },
  maxWidth: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  headerRow: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.three, marginBottom: Spacing.three },
  headerText: { flex: 1, alignItems: 'flex-end' },
  title: { fontFamily: Fonts.sans, fontSize: 22, fontWeight: '800' },
  subtitle: { fontFamily: Fonts.sans, fontSize: 11, marginTop: 3 },
  back: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center' },
  backText: { fontSize: 19 },
  hero: { borderRadius: Radius.lg, padding: Spacing.four, marginBottom: Spacing.four, overflow: 'hidden' },
  heroMark: { color: '#8ab4ff', fontFamily: Fonts.mono, fontSize: 12, fontWeight: '800', marginBottom: 8 },
  heroTitle: { fontFamily: Fonts.sans, fontSize: 19, fontWeight: '800', textAlign: 'right', lineHeight: 30 },
  heroBody: { fontFamily: Fonts.sans, fontSize: 12, textAlign: 'right', lineHeight: 21, marginTop: 6 },
  demoBadge: { alignSelf: 'flex-end', marginTop: Spacing.three, borderRadius: 20, paddingHorizontal: 10, paddingVertical: 5, backgroundColor: '#6d4aff22', borderWidth: 1, borderColor: '#7c5cff66' },
  demoBadgeText: { color: '#b6a6ff', fontFamily: Fonts.sans, fontSize: 10, fontWeight: '700' },
  group: { marginBottom: Spacing.four },
  groupHead: { flexDirection: 'row-reverse', alignItems: 'center', gap: 7, marginBottom: Spacing.two },
  dot: { width: 8, height: 8, borderRadius: 4 },
  groupTitle: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '800' },
  grid: { flexDirection: 'row-reverse', flexWrap: 'wrap', gap: Spacing.two },
  moduleCard: { flexBasis: '48%', flexGrow: 1, minHeight: 132, borderRadius: Radius.md, padding: Spacing.three, alignItems: 'flex-end' },
  moduleIcon: { width: 42, height: 42, borderRadius: Radius.sm, alignItems: 'center', justifyContent: 'center', marginBottom: 8 },
  moduleEmoji: { fontSize: 20 },
  moduleTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '800', textAlign: 'right' },
  moduleSubtitle: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 17, textAlign: 'right', marginTop: 4 },
  demoPanel: { borderRadius: Radius.lg, padding: Spacing.four },
  demoPanelHead: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', marginBottom: Spacing.three },
  demoPanelTitle: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '800' },
  demoChip: { color: '#fff', backgroundColor: '#7048e8', paddingHorizontal: 9, paddingVertical: 4, borderRadius: 12, overflow: 'hidden', fontFamily: Fonts.mono, fontSize: 10, fontWeight: '800' },
  demoStats: { flexDirection: 'row-reverse', gap: Spacing.two },
  demoStat: { flex: 1, alignItems: 'center', paddingVertical: Spacing.two },
  demoValue: { fontFamily: Fonts.mono, fontSize: 17, fontWeight: '800' },
  demoLabel: { fontFamily: Fonts.sans, fontSize: 10, marginTop: 3 },
  demoDisclaimer: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 18, textAlign: 'right', marginTop: Spacing.two },
});
