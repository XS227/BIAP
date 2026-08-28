import { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, useColorScheme, SafeAreaView, RefreshControl } from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, BottomTabInset } from '@/constants/theme';
import { fetchSymbols, fetchRecommendation, formatPrice, parsePct, Recommendation, StockItem, MarketSymbolResult } from '@/lib/api';
import { fetchTsetmcQuote } from '@/lib/market-quote';
import { StockRowSkeleton } from '@/components/skeleton';
import { RecommendationCard } from '@/components/recommendation-card';

export default function StockDetailScreen() {
  const { code } = useLocalSearchParams<{ code: string }>();
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [symbol, setSymbol] = useState<MarketSymbolResult | null>(null);
  const [item, setItem] = useState<StockItem | null>(null);
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(async () => {
    if (!code) return;
    try {
      const candidates = await fetchSymbols({ q: code, limit: 30 });
      const found = candidates.find((s) => s.code === code) ?? candidates.find((s) => s.symbol === code) ?? null;
      setSymbol(found);
      if (!found) {
        setNotFound(true);
        setItem(null);
        setRec(null);
        return;
      }
      setNotFound(false);
      const [quote, recommendation] = await Promise.all([
        fetchTsetmcQuote(found),
        fetchRecommendation(found.code),
      ]);
      setItem(quote.error ? { name: found.symbol || found.name, code: found.code } : quote);
      setRec(recommendation);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [code]);

  useEffect(() => { load(); }, [load]);

  const pct = item?.changePercent !== undefined ? parsePct(item.changePercent) : null;
  const up = (pct ?? 0) >= 0;

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={Brand.stockGreen} />}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.backText, { color: colors.text }]}>← بازگشت</Text></Pressable>
          <Text style={[styles.headerLabel, { color: colors.textSecondary }]}>جزئیات نماد</Text>
        </View>

        {loading ? <View>{[1,2,3].map(i => <StockRowSkeleton key={i} />)}</View> : null}

        {!loading && notFound ? <View style={[styles.stateCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.stateTitle, { color: colors.text }]}>نماد یافت نشد</Text><Text style={[styles.stateText, { color: colors.textSecondary }]}>این نماد در فهرست کل بازار TSE/IFB پیدا نشد.</Text></View> : null}

        {!loading && symbol && item ? <>
          <View style={[styles.priceCard, { backgroundColor: colors.backgroundElement }]}>
            <View style={styles.titleLine}><View style={[styles.marketBadge, { backgroundColor: colors.backgroundSelected }]}><Text style={[styles.marketBadgeText, { color: colors.textSecondary }]}>{symbol.market ?? '—'}</Text></View><View style={{ alignItems: 'flex-end' }}><Text style={[styles.symbol, { color: colors.text }]}>{symbol.symbol}</Text><Text style={[styles.company, { color: colors.textSecondary }]}>{symbol.name}</Text></View></View>
            <View style={styles.priceLine}><Text style={[styles.price, { color: colors.text }]}>{formatPrice(item.lastPrice ?? item.closingPrice)}</Text><Text style={[styles.unit, { color: colors.textSecondary }]}>ریال</Text></View>
            {pct !== null ? <Text style={[styles.change, { color: up ? Brand.stockGreen : Brand.negative }]}>{up ? '▲' : '▼'} {Math.abs(pct).toFixed(2)}٪</Text> : <Text style={[styles.noQuote, { color: colors.textSecondary }]}>قیمت زنده برای این نماد در این لحظه در دسترس نیست.</Text>}
          </View>

          <View style={[styles.table, { backgroundColor: colors.backgroundElement }]}>
            <Row label="آخرین قیمت" value={`${formatPrice(item.lastPrice)} ریال`} colors={colors} />
            <Row label="قیمت پایانی" value={`${formatPrice(item.closingPrice)} ریال`} colors={colors} />
            <Row label="قیمت دیروز" value={`${formatPrice(item.yesterdayPrice)} ریال`} colors={colors} />
            <Row label="کد TSETMC" value={symbol.code} colors={colors} />
            <Row label="بازار" value={symbol.market ?? '—'} colors={colors} />
          </View>

          {rec ? <RecommendationCard rec={rec} colors={colors} /> : <View style={[styles.stateCard, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.stateText, { color: colors.textSecondary }]}>تحلیل کیا‌شا برای این نماد فعلاً دریافت نشد؛ قیمت بازار مستقل از تحلیل نمایش داده می‌شود.</Text></View>}
          <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>فهرست بازار و قیمت از TSETMC؛ مقدار ناموجود ساخته نمی‌شود.</Text>
        </> : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({ label, value, colors }: { label: string; value: string; colors: typeof Colors.dark }) {
  return <View style={[styles.row, { borderBottomColor: colors.backgroundSelected }]}><Text style={[styles.rowValue, { color: colors.text }]}>{value}</Text><Text style={[styles.rowLabel, { color: colors.textSecondary }]}>{label}</Text></View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 }, content: { paddingHorizontal: Spacing.three },
  header: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', paddingVertical: Spacing.three },
  back: { paddingHorizontal: Spacing.three, paddingVertical: Spacing.two, borderRadius: Spacing.two }, backText: { fontFamily: Fonts.sans, fontSize: 13 }, headerLabel: { fontFamily: Fonts.sans, fontSize: 12 },
  priceCard: { borderRadius: Spacing.three, padding: Spacing.four, alignItems: 'flex-end' }, titleLine: { width: '100%', flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center' },
  marketBadge: { borderRadius: 13, paddingHorizontal: 9, paddingVertical: 5 }, marketBadgeText: { fontFamily: Fonts.mono, fontSize: 9 }, symbol: { fontFamily: Fonts.sans, fontSize: 24, fontWeight: '800' }, company: { fontFamily: Fonts.sans, fontSize: 11, marginTop: 3, textAlign: 'right' },
  priceLine: { flexDirection: 'row-reverse', alignItems: 'baseline', gap: 6, marginTop: Spacing.three }, price: { fontFamily: Fonts.mono, fontSize: 31, fontWeight: '800' }, unit: { fontFamily: Fonts.sans, fontSize: 12 }, change: { fontFamily: Fonts.mono, fontSize: 15, fontWeight: '800', marginTop: 5 }, noQuote: { fontFamily: Fonts.sans, fontSize: 11, marginTop: Spacing.two },
  table: { borderRadius: Spacing.two, paddingHorizontal: Spacing.three, marginTop: Spacing.three }, row: { flexDirection: 'row-reverse', justifyContent: 'space-between', paddingVertical: Spacing.three, borderBottomWidth: StyleSheet.hairlineWidth }, rowLabel: { fontFamily: Fonts.sans, fontSize: 12 }, rowValue: { fontFamily: Fonts.mono, fontSize: 12, fontWeight: '700', maxWidth: '65%' },
  stateCard: { borderRadius: Spacing.three, padding: Spacing.four, alignItems: 'center', marginTop: Spacing.three }, stateTitle: { fontFamily: Fonts.sans, fontSize: 17, fontWeight: '800' }, stateText: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 20, textAlign: 'center' }, disclaimer: { fontFamily: Fonts.sans, fontSize: 10.5, textAlign: 'center', marginVertical: Spacing.three },
});
