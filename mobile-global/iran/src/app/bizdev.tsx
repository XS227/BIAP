import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { fetchWatchlist } from '@/lib/api';
import { computeMarketSummary } from '@/lib/market-stats';
import { getBusinessDataset } from '@/lib/business-data';
import { getDemoMode } from '@/lib/demo-mode';
import { getSelectedListedCompany, ListedCompanySummary } from '@/lib/listed-company-selection';

const BUSINESS_MODULES = [
  { key: 'business-kpi', icon: '🎯', title: 'داشبورد KPI', sub: 'شاخص‌های عمومی شرکت + داده داخلی در صورت اتصال' },
  { key: 'swot', icon: '⚔️', title: 'رقبا + SWOT', sub: 'جایگاه، قوت/ضعف و شواهد بازار عمومی' },
  { key: 'market-entry', icon: '🌍', title: 'فرصت و ورود به بازار', sub: 'شواهد عمومی بازار و نیازهای داده‌ای تکمیلی' },
  { key: 'crm', icon: '👥', title: 'CRM + Pipeline', sub: 'نیازمند داده مشتری و Pipeline داخلی' },
  { key: 'campaign', icon: '📣', title: 'کمپین بازاریابی', sub: 'زمینه عمومی + داده کمپین در صورت اتصال' },
  { key: 'pricing', icon: '💰', title: 'قیمت‌گذاری هوشمند', sub: 'نیازمند قیمت محصول، هزینه و حجم فروش داخلی' },
  { key: 'plan', icon: '📄', title: 'Business Plan', sub: 'زمینه بازار، مالی و نقشه راه داده‌محور' },
  { key: 'executive-report', icon: '🧾', title: 'گزارش مدیریتی', sub: 'KPI، شواهد عمومی و اقدام بعدی' },
] as const;

const INTERNAL_ONLY = new Set(['crm', 'pricing']);

export default function BizDevScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [stocks, setStocks] = useState<Awaited<ReturnType<typeof fetchWatchlist>>>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const [companyConnected, setCompanyConnected] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState<ListedCompanySummary | null>(null);
  const [demoMode, setDemoModeState] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(false);
      const [watchlist, dataset, listed, demo] = await Promise.all([
        fetchWatchlist().catch(() => []),
        getBusinessDataset(),
        getSelectedListedCompany(),
        getDemoMode(),
      ]);
      setStocks(watchlist);
      setCompanyConnected(Boolean(dataset?.rows.length));
      setSelectedCompany(listed);
      setDemoModeState(demo);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  const summary = useMemo(() => computeMarketSummary(stocks), [stocks]);
  const avgPositive = summary.avgChange >= 0;

  const openListed = () => router.push({
    pathname: '/data-connect',
    params: { companyMode: 'listed', ...(selectedCompany ? { code: selectedCompany.code } : {}) },
  } as never);
  const openPrivate = () => router.push({ pathname: '/data-connect', params: { companyMode: 'private' } } as never);
  const openModule = (key: string) => router.push({
    pathname: '/module',
    params: selectedCompany
      ? { key, companyMode: 'listed', code: selectedCompany.code }
      : { key, companyMode: 'private' },
  } as never);

  const stateFor = (key: string) => {
    if (demoMode) return 'DEMO';
    if (selectedCompany && !INTERNAL_ONLY.has(key)) return `LISTED • ${selectedCompany.symbol}`;
    if (companyConnected) return 'PRIVATE DATA LIVE';
    if (selectedCompany && INTERNAL_ONLY.has(key)) return 'NEEDS INTERNAL DATA';
    return 'SELECT COMPANY';
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={Brand.secondary} />}
        contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}
      >
        <View style={styles.wrap}>
          <View style={styles.header}><Text style={[styles.title, { color: colors.text }]}>تحلیل کسب‌وکار</Text><Text style={[styles.sub, { color: colors.textSecondary }]}>Listed Company → Public Data → Business Analysis</Text></View>

          <View style={[styles.hero, { backgroundColor: colors.backgroundElement, borderColor: selectedCompany ? '#16a34a66' : colors.backgroundSelected }]}>
            <Text style={styles.heroTag}>BUSINESS AI</Text>
            <Text style={[styles.heroTitle, { color: colors.text }]}>اول شرکت را انتخاب کنید؛ داده بورسی را BIAP خودش می‌آورد</Text>
            {selectedCompany ? (
              <>
                <Text style={[styles.selectedCompany, { color: colors.text }]}>{selectedCompany.symbol} • {selectedCompany.name || selectedCompany.code}</Text>
                <Text style={[styles.heroBody, { color: colors.textSecondary }]}>KPI، SWOT/رقبا، فرصت بازار، گزارش مدیریتی و مدل‌های عمومی از دیتابیس پایدار BIAP و منابع Tindex / TSETMC / CODAL شروع می‌شوند. فقط بخش‌هایی مثل CRM، قیمت محصول و Pipeline به داده داخلی نیاز دارند.</Text>
              </>
            ) : (
              <Text style={[styles.heroBody, { color: colors.textSecondary }]}>برای شرکت بورسی یا فرابورسی لازم نیست CSV/Excel وارد کنید. نماد را انتخاب کنید؛ داده عمومی قابل‌تأیید به‌صورت خودکار بارگذاری و ذخیره می‌شود. داده داخلی فقط مکمل است.</Text>
            )}
            <View style={styles.heroButtons}>
              <Pressable onPress={openListed} style={styles.primaryBtn}><Text style={styles.primaryBtnText}>{selectedCompany ? 'تغییر شرکت بورسی' : 'انتخاب شرکت بورسی / فرابورسی'}</Text></Pressable>
              <Pressable onPress={openPrivate} style={[styles.outlineBtn, { borderColor: colors.backgroundSelected }]}><Text style={[styles.outlineBtnText, { color: colors.textSecondary }]}>افزودن داده داخلی</Text></Pressable>
            </View>
          </View>

          <View style={styles.statusRow}>
            <View style={[styles.statusCard, { backgroundColor: colors.backgroundElement }]}>
              <Text style={{ fontFamily: Fonts.mono, fontSize: 9, fontWeight: '900', color: selectedCompany ? Brand.stockGreen : '#f59e0b' }}>{selectedCompany ? 'LISTED ACTIVE' : 'SELECT'}</Text>
              <Text style={[styles.statusTitle, { color: colors.text }]}>شرکت بورسی</Text>
              <Text style={[styles.statusText, { color: colors.textSecondary }]}>{selectedCompany ? `${selectedCompany.symbol} • Tindex/TSETMC/CODAL` : 'یک نماد انتخاب کنید'}</Text>
            </View>
            <View style={[styles.statusCard, { backgroundColor: colors.backgroundElement }]}>
              <Text style={{ fontFamily: Fonts.mono, fontSize: 9, fontWeight: '900', color: companyConnected ? Brand.stockGreen : colors.textSecondary }}>{companyConnected ? 'CONNECTED' : 'OPTIONAL'}</Text>
              <Text style={[styles.statusTitle, { color: colors.text }]}>داده داخلی شرکت</Text>
              <Text style={[styles.statusText, { color: colors.textSecondary }]}>{companyConnected ? 'CSV / JSON / Excel همگام' : 'برای CRM/Pricing و فیلدهای خصوصی'}</Text>
            </View>
          </View>

          <View style={[styles.modeStrip, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.modeText, { color: colors.textSecondary }]}>حالت فعلی ماژول‌ها</Text><Text style={[styles.modeValue, { color: demoMode ? '#a78bfa' : Brand.stockGreen }]}>{demoMode ? 'DEMO • داده نمونه' : selectedCompany ? `REAL • ${selectedCompany.symbol}` : 'REAL • انتخاب شرکت'}</Text></View>

          <Text style={[styles.sectionTitle, { color: colors.text }]}>۸ ماژول توسعه کسب‌وکار</Text>
          <View style={styles.grid}>{BUSINESS_MODULES.map(m => {
            const state = stateFor(m.key);
            const stateColor = state.startsWith('LISTED') || state === 'PRIVATE DATA LIVE' ? Brand.stockGreen : state === 'DEMO' ? '#a78bfa' : colors.textSecondary;
            return (
              <Pressable key={m.key} onPress={() => openModule(m.key)} style={[styles.module, { backgroundColor: colors.backgroundElement }]}>
                <Text style={styles.icon}>{m.icon}</Text>
                <Text style={[styles.moduleTitle, { color: colors.text }]}>{m.title}</Text>
                <Text style={[styles.moduleSub, { color: colors.textSecondary }]}>{m.sub}</Text>
                <Text style={[styles.moduleState, { color: stateColor }]}>{state}</Text>
              </Pressable>
            );
          })}</View>

          <View style={styles.sectionHead}><Pressable onPress={() => router.push('/market' as never)}><Text style={styles.link}>باز کردن بازار ←</Text></Pressable><Text style={[styles.sectionTitle, { color: colors.text }]}>نمای بازار متصل</Text></View>
          {loading ? (
            <View style={[styles.marketCard, { backgroundColor: colors.backgroundElement }]}><ActivityIndicator color={Brand.secondary} /></View>
          ) : error ? (
            <View style={[styles.marketCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.marketNote, { color: colors.textSecondary }]}>داده بازار فعلاً دریافت نشد. برای تلاش دوباره صفحه را پایین بکشید.</Text></View>
          ) : (
            <View style={[styles.marketCard, { backgroundColor: colors.backgroundElement }]}>
              <View style={styles.marketStats}>
                <View style={styles.marketMetric}><Text style={[styles.metricValue, { color: colors.text }]}>{summary.total.toLocaleString('fa-IR')}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>نمادهای متصل</Text></View>
                <View style={styles.marketMetric}><Text style={[styles.metricValue, { color: Brand.stockGreen }]}>{summary.gainers.toLocaleString('fa-IR')}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>مثبت</Text></View>
                <View style={styles.marketMetric}><Text style={[styles.metricValue, { color: Brand.negative }]}>{summary.losers.toLocaleString('fa-IR')}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>منفی</Text></View>
              </View>
              <Text style={[styles.marketAvg, { color: avgPositive ? Brand.stockGreen : Brand.negative }]}>{avgPositive ? '▲' : '▼'} {Math.abs(summary.avgChange).toFixed(2)}٪ میانگین تغییر</Text>
              <Text style={[styles.marketNote, { color: colors.textSecondary }]}>این snapshot واقعی بازار است و از داده Demo برای پر کردن مقادیر استفاده نمی‌کند.</Text>
            </View>
          )}

          <Pressable onPress={() => router.push('/modules' as never)} style={[styles.allModules, { borderColor: colors.backgroundSelected }]}><Text style={[styles.allModulesText, { color: colors.text }]}>مشاهده همه ماژول‌های BIAP</Text></Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three },
  wrap: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  header: { paddingTop: Spacing.four, paddingBottom: Spacing.three, alignItems: 'flex-end' },
  title: { fontFamily: Fonts.sans, fontSize: 24, fontWeight: '900' },
  sub: { fontFamily: Fonts.sans, fontSize: 11, marginTop: 3 },
  hero: { borderRadius: Radius.lg, padding: Spacing.four, alignItems: 'flex-end', borderWidth: 1 },
  heroTag: { fontFamily: Fonts.mono, fontSize: 10, fontWeight: '900', color: Brand.secondary },
  heroTitle: { fontFamily: Fonts.sans, fontSize: 19, fontWeight: '900', textAlign: 'right', marginTop: 7 },
  selectedCompany: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '900', textAlign: 'right', marginTop: 10 },
  heroBody: { fontFamily: Fonts.sans, fontSize: 11.5, lineHeight: 20, textAlign: 'right', marginTop: 7 },
  heroButtons: { flexDirection: 'row-reverse', gap: Spacing.two, width: '100%', marginTop: 12 },
  primaryBtn: { flex: 1, backgroundColor: Brand.secondary, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 11, alignItems: 'center' },
  primaryBtnText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 11.5, fontWeight: '900', textAlign: 'center' },
  outlineBtn: { flex: 1, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 11, alignItems: 'center', borderWidth: 1 },
  outlineBtnText: { fontFamily: Fonts.sans, fontSize: 11.5, fontWeight: '800' },
  statusRow: { flexDirection: 'row-reverse', gap: Spacing.two, marginTop: Spacing.three },
  statusCard: { flex: 1, borderRadius: Radius.md, padding: Spacing.three, alignItems: 'flex-end' },
  statusTitle: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '900', marginTop: 4, textAlign: 'right' },
  statusText: { fontFamily: Fonts.sans, fontSize: 9.5, marginTop: 3, textAlign: 'right', lineHeight: 16 },
  modeStrip: { marginTop: Spacing.two, borderRadius: Radius.md, padding: Spacing.three, flexDirection: 'row-reverse', justifyContent: 'space-between' },
  modeText: { fontFamily: Fonts.sans, fontSize: 10.5 },
  modeValue: { fontFamily: Fonts.mono, fontSize: 10, fontWeight: '900' },
  sectionTitle: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '900', textAlign: 'right', marginTop: Spacing.four, marginBottom: Spacing.two },
  grid: { flexDirection: 'row-reverse', flexWrap: 'wrap', gap: Spacing.two },
  module: { flexBasis: '48%', flexGrow: 1, minHeight: 142, borderRadius: Radius.md, padding: Spacing.three, alignItems: 'flex-end' },
  icon: { fontSize: 22 },
  moduleTitle: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900', textAlign: 'right', marginTop: 7 },
  moduleSub: { fontFamily: Fonts.sans, fontSize: 10, lineHeight: 17, textAlign: 'right', marginTop: 4 },
  moduleState: { fontFamily: Fonts.mono, fontSize: 8.5, fontWeight: '900', marginTop: 8 },
  sectionHead: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center' },
  link: { fontFamily: Fonts.sans, fontSize: 10.5, fontWeight: '800', color: Brand.secondary, marginTop: Spacing.four },
  marketCard: { borderRadius: Radius.lg, padding: Spacing.four },
  marketStats: { flexDirection: 'row-reverse' },
  marketMetric: { flex: 1, alignItems: 'center' },
  metricValue: { fontFamily: Fonts.mono, fontSize: 18, fontWeight: '900' },
  metricLabel: { fontFamily: Fonts.sans, fontSize: 9.5, marginTop: 4 },
  marketAvg: { fontFamily: Fonts.mono, fontSize: 13, fontWeight: '900', textAlign: 'right', marginTop: Spacing.three },
  marketNote: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 18, textAlign: 'right', marginTop: Spacing.two },
  allModules: { borderWidth: 1, borderRadius: Radius.md, paddingVertical: 12, alignItems: 'center', marginTop: Spacing.three },
  allModulesText: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '800' },
});
