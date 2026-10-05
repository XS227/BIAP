import { useCallback, useMemo, useState } from 'react';
import { Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { fetchWatchlist, parsePct, StockItem } from '@/lib/api';
import { getBusinessDataset, summarizeBusinessDataset } from '@/lib/business-data';
import { getSelectedListedCompany, ListedCompanySummary } from '@/lib/listed-company-selection';

export default function DataScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [stocks, setStocks] = useState<StockItem[]>([]);
  const [dataset, setDataset] = useState<Awaited<ReturnType<typeof getBusinessDataset>>>(null);
  const [selectedCompany, setSelectedCompany] = useState<ListedCompanySummary | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(false);
      const [stockResult, companyDataset, listed] = await Promise.all([
        fetchWatchlist().catch(() => []),
        getBusinessDataset(),
        getSelectedListedCompany(),
      ]);
      setStocks(stockResult);
      setDataset(companyDataset);
      setSelectedCompany(listed);
    } catch {
      setError(true);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const market = useMemo(() => {
    const priced = stocks.filter(s => s.closingPrice != null || s.lastPrice != null);
    const p = priced.map(s => parsePct(s.changePercent));
    const avg = p.length ? p.reduce((a, b) => a + b, 0) / p.length : 0;
    return { priced: priced.length, positive: p.filter(x => x > 0).length, negative: p.filter(x => x < 0).length, avg };
  }, [stocks]);
  const summary = dataset ? summarizeBusinessDataset(dataset) : null;

  const openListed = () => router.push({
    pathname: '/data-connect',
    params: { companyMode: 'listed', ...(selectedCompany ? { code: selectedCompany.code } : {}) },
  } as never);
  const openPrivate = () => router.push({ pathname: '/data-connect', params: { companyMode: 'private' } } as never);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={Brand.dataViolet} />}
        contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}
      >
        <View style={styles.wrap}>
          <View style={styles.header}>
            <Text style={[styles.title, { color: colors.text }]}>تحلیل داده</Text>
            <Text style={[styles.sub, { color: colors.textSecondary }]}>شرکت بورسی → داده پایدار → KPI / SQL / Financial Model</Text>
          </View>

          <View style={styles.actions}>
            <Pressable onPress={openListed} style={[styles.action, { backgroundColor: colors.backgroundElement, borderColor: '#16a34a55' }]}>
              <Text style={styles.icon}>🏢</Text>
              <Text style={[styles.actionTitle, { color: colors.text }]}>شرکت بورسی / فرابورسی</Text>
              <Text style={[styles.actionText, { color: colors.textSecondary }]}>انتخاب نماد و دریافت خودکار Tindex / TSETMC / CODAL</Text>
            </Pressable>
            <Pressable onPress={openPrivate} style={[styles.action, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
              <Text style={styles.icon}>🔌</Text>
              <Text style={[styles.actionTitle, { color: colors.text }]}>داده داخلی شرکت</Text>
              <Text style={[styles.actionText, { color: colors.textSecondary }]}>Excel / CSV فقط برای فیلدهای خصوصی و عملیاتی</Text>
            </Pressable>
          </View>

          <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: selectedCompany ? '#16a34a66' : colors.backgroundSelected }]}>
            <View style={styles.cardHead}>
              <View style={[styles.badge, { backgroundColor: selectedCompany ? '#14532d' : '#374151' }]}><Text style={styles.badgeText}>{selectedCompany ? 'LISTED LIVE' : 'SELECT'}</Text></View>
              <Text style={[styles.cardTitle, { color: colors.text }]}>داده عمومی شرکت بورسی</Text>
            </View>
            {selectedCompany ? (
              <>
                <Text style={[styles.companyName, { color: colors.text }]}>{selectedCompany.symbol} • {selectedCompany.name || selectedCompany.code}</Text>
                <Text style={[styles.source, { color: colors.textSecondary }]}>
                  {selectedCompany.market || 'TSE / IFB'} • دیتابیس پایدار BIAP • حداقل روزانه از Tindex، baseline دوره‌ای از TSETMC/CODAL
                </Text>
                <Text style={[styles.autoNote, { color: Brand.positive }]}>KPI، SQL / Data Query و Financial Model بدون آپلود فایل از همین شرکت خوانده می‌شوند.</Text>
                <View style={styles.buttonRow}>
                  <Pressable onPress={() => router.push('/modules' as never)} style={styles.primarySmall}><Text style={styles.primaryText}>باز کردن ماژول‌ها</Text></Pressable>
                  <Pressable onPress={openListed} style={[styles.secondarySmall, { borderColor: Brand.positive }]}><Text style={[styles.secondaryText, { color: Brand.positive }]}>تغییر شرکت</Text></Pressable>
                </View>
              </>
            ) : (
              <>
                <Text style={[styles.empty, { color: colors.textSecondary }]}>برای شرکت‌های بورس و فرابورس لازم نیست ابتدا فایل وارد کنید. نماد را انتخاب کنید تا BIAP داده‌های عمومی قابل‌تأیید را خودش بردارد و ذخیره کند.</Text>
                <Pressable onPress={openListed} style={styles.primary}><Text style={styles.primaryText}>انتخاب شرکت بورسی / فرابورسی</Text></Pressable>
              </>
            )}
          </View>

          <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
            <View style={styles.cardHead}>
              <View style={[styles.badge, { backgroundColor: dataset ? '#1e3a8a' : '#374151' }]}><Text style={styles.badgeText}>{dataset ? 'PRIVATE SYNC' : 'OPTIONAL'}</Text></View>
              <Text style={[styles.cardTitle, { color: colors.text }]}>داده داخلی / اختصاصی شرکت</Text>
            </View>
            {dataset && summary ? (
              <>
                <Text style={[styles.source, { color: colors.textSecondary }]}>{dataset.name} • {dataset.source}</Text>
                <View style={styles.metrics}>
                  <Metric label="ردیف" value={summary.rows.toLocaleString('fa-IR')} colors={colors} />
                  <Metric label="ستون" value={summary.columns.toLocaleString('fa-IR')} colors={colors} />
                  <Metric label="کامل بودن" value={`${(summary.completeness * 100).toLocaleString('fa-IR', { maximumFractionDigits: 1 })}٪`} colors={colors} />
                </View>
                <Pressable onPress={openPrivate} style={[styles.secondary, { borderColor: Brand.dataViolet }]}><Text style={[styles.secondaryText, { color: Brand.dataViolet }]}>مدیریت داده داخلی</Text></Pressable>
              </>
            ) : (
              <>
                <Text style={[styles.empty, { color: colors.textSecondary }]}>این بخش فقط برای اطلاعاتی است که در منابع عمومی بورس نیست؛ مثل CRM، مشتری، هزینه محصول، Pipeline و داده عملیاتی.</Text>
                <Pressable onPress={openPrivate} style={[styles.secondary, { borderColor: Brand.dataViolet }]}><Text style={[styles.secondaryText, { color: Brand.dataViolet }]}>افزودن داده داخلی (اختیاری)</Text></Pressable>
              </>
            )}
          </View>

          <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
            <View style={styles.cardHead}><View style={[styles.badge, { backgroundColor: '#1e3a8a' }]}><Text style={styles.badgeText}>MARKET</Text></View><Text style={[styles.cardTitle, { color: colors.text }]}>EDA بازار</Text></View>
            <Text style={[styles.source, { color: colors.textSecondary }]}>خلاصه قیمت‌های تأییدشده؛ عدد ناموجود ساخته نمی‌شود.</Text>
            <View style={styles.metrics}>
              <Metric label="قیمت معتبر" value={market.priced.toLocaleString('fa-IR')} colors={colors} />
              <Metric label="مثبت" value={market.positive.toLocaleString('fa-IR')} colors={colors} />
              <Metric label="منفی" value={market.negative.toLocaleString('fa-IR')} colors={colors} />
            </View>
            <Text style={[styles.avg, { color: market.avg >= 0 ? Brand.positive : Brand.negative }]}>میانگین تغییر: {market.avg >= 0 ? '+' : ''}{market.avg.toLocaleString('fa-IR', { maximumFractionDigits: 2 })}٪</Text>
            <Pressable onPress={() => router.push('/market' as never)} style={[styles.secondary, { borderColor: Brand.dataViolet }]}><Text style={[styles.secondaryText, { color: Brand.dataViolet }]}>باز کردن بازار و فیلترها</Text></Pressable>
          </View>

          {error ? <Text style={[styles.error, { color: Brand.warning }]}>بخشی از داده‌ها پاسخ نداد؛ برای تلاش دوباره صفحه را پایین بکشید.</Text> : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function Metric({ label, value, colors }: { label: string; value: string; colors: any }) {
  return <View style={[styles.metric, { backgroundColor: colors.backgroundSelected }]}><Text style={[styles.metricValue, { color: colors.text }]}>{value}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>{label}</Text></View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: Spacing.three },
  wrap: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  header: { alignItems: 'flex-end', paddingVertical: Spacing.three },
  title: { fontFamily: Fonts.sans, fontSize: 24, fontWeight: '900' },
  sub: { fontFamily: Fonts.sans, fontSize: 11, marginTop: 4, textAlign: 'right' },
  actions: { flexDirection: 'row-reverse', gap: Spacing.two, marginBottom: Spacing.three },
  action: { flex: 1, borderRadius: Radius.lg, padding: Spacing.three, alignItems: 'flex-end', borderWidth: 1 },
  icon: { fontSize: 22 },
  actionTitle: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900', marginTop: 5, textAlign: 'right' },
  actionText: { fontFamily: Fonts.sans, fontSize: 9.5, lineHeight: 16, textAlign: 'right', marginTop: 3 },
  card: { borderRadius: Radius.lg, padding: Spacing.four, marginBottom: Spacing.three, borderWidth: 1 },
  cardHead: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center' },
  cardTitle: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '900' },
  badge: { borderRadius: 12, paddingHorizontal: 9, paddingVertical: 4 },
  badgeText: { color: '#fff', fontFamily: Fonts.mono, fontSize: 8.5, fontWeight: '900' },
  companyName: { fontFamily: Fonts.sans, fontSize: 17, fontWeight: '900', textAlign: 'right', marginTop: Spacing.three },
  source: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 18, textAlign: 'right', marginTop: 8 },
  autoNote: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 19, textAlign: 'right', marginTop: Spacing.two, fontWeight: '800' },
  buttonRow: { flexDirection: 'row-reverse', gap: Spacing.two, marginTop: Spacing.three },
  primarySmall: { flex: 1, backgroundColor: Brand.primary, borderRadius: Radius.md, paddingVertical: 11, alignItems: 'center' },
  secondarySmall: { flex: 1, borderWidth: 1, borderRadius: Radius.md, paddingVertical: 11, alignItems: 'center' },
  metrics: { flexDirection: 'row-reverse', gap: Spacing.two, marginTop: Spacing.three },
  metric: { flex: 1, borderRadius: Radius.md, padding: Spacing.three, alignItems: 'center' },
  metricValue: { fontFamily: Fonts.mono, fontSize: 17, fontWeight: '900' },
  metricLabel: { fontFamily: Fonts.sans, fontSize: 9.5, marginTop: 4 },
  empty: { fontFamily: Fonts.sans, fontSize: 11.5, lineHeight: 20, textAlign: 'right', marginTop: Spacing.three },
  avg: { fontFamily: Fonts.mono, fontSize: 12, fontWeight: '800', textAlign: 'right', marginTop: Spacing.three },
  primary: { backgroundColor: Brand.primary, borderRadius: Radius.md, paddingVertical: 12, alignItems: 'center', marginTop: Spacing.three },
  primaryText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 12, fontWeight: '900' },
  secondary: { borderWidth: 1, borderRadius: Radius.md, paddingVertical: 11, alignItems: 'center', marginTop: Spacing.three },
  secondaryText: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '900' },
  error: { fontFamily: Fonts.sans, fontSize: 11, textAlign: 'center' },
});
