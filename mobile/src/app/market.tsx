import { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, FlatList, RefreshControl, useColorScheme, SafeAreaView, Pressable, TextInput, ActivityIndicator } from 'react-native';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, BottomTabInset, MaxContentWidth } from '@/constants/theme';
import { fetchSymbols, formatPrice, MarketSymbolResult, StockItem } from '@/lib/api';
import { fetchTsetmcQuotes } from '@/lib/market-quote';
import { StockRowSkeleton } from '@/components/skeleton';
import { marketStatusLabel } from '@/lib/market-hours';

const PAGE_SIZE = 40;

export default function MarketScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [symbols, setSymbols] = useState<MarketSymbolResult[]>([]);
  const [quotes, setQuotes] = useState<Record<string, StockItem>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState('');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [countdown, setCountdown] = useState(30);
  const marketStatus = marketStatusLabel();

  const filtered = useMemo(() => {
    const q = query.trim();
    if (!q) return symbols;
    return symbols.filter((s) => s.symbol.includes(q) || s.name.includes(q) || s.code.includes(q));
  }, [symbols, query]);

  const visible = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount]);

  const refreshQuotes = useCallback(async (items: MarketSymbolResult[]) => {
    if (!items.length) return;
    const next = await fetchTsetmcQuotes(items);
    setQuotes((current) => ({ ...current, ...next }));
  }, []);

  const loadUniverse = useCallback(async () => {
    try {
      setError(false);
      const items = await fetchSymbols({ limit: 5000 });
      if (!items.length) throw new Error('empty symbol universe');
      setSymbols(items);
      setVisibleCount(PAGE_SIZE);
      await refreshQuotes(items.slice(0, PAGE_SIZE));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [refreshQuotes]);

  useEffect(() => {
    loadUniverse();
  }, [loadUniverse]);

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
    refreshQuotes(filtered.slice(0, PAGE_SIZE));
  }, [query]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const interval = setInterval(() => {
      refreshQuotes(visible);
      setCountdown(30);
    }, 30_000);
    const tick = setInterval(() => setCountdown((c) => (c > 0 ? c - 1 : 30)), 1_000);
    return () => { clearInterval(interval); clearInterval(tick); };
  }, [refreshQuotes, visible]);

  const onRefresh = () => {
    setRefreshing(true);
    setQuotes({});
    setCountdown(30);
    loadUniverse();
  };

  const loadMore = async () => {
    if (loadingMore || visibleCount >= filtered.length) return;
    setLoadingMore(true);
    const nextCount = Math.min(visibleCount + PAGE_SIZE, filtered.length);
    const nextItems = filtered.slice(visibleCount, nextCount);
    setVisibleCount(nextCount);
    await refreshQuotes(nextItems);
    setLoadingMore(false);
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <View style={styles.header}>
          <View style={styles.headerTop}>
            <View style={[styles.marketPill, { backgroundColor: marketStatus.open ? '#1a3d2b' : colors.backgroundElement }]}>
              <View style={[styles.marketDot, { backgroundColor: marketStatus.open ? Brand.stockGreen : colors.textSecondary }]} />
              <Text style={[styles.marketLabel, { color: marketStatus.open ? Brand.stockGreen : colors.textSecondary }]}>{marketStatus.label}</Text>
            </View>
            <Text style={[styles.headerTitle, { color: colors.text }]}>بازار سرمایه ایران</Text>
          </View>
          <View style={styles.headerBottom}>
            <Text style={[styles.countdown, { color: colors.textSecondary }]}>قیمت‌های بازشده: بروزرسانی در {countdown}ث</Text>
            <Text style={[styles.headerSub, { color: colors.textSecondary }]}>{symbols.length.toLocaleString('fa-IR')} نماد TSE / IFB / پایه</Text>
          </View>
        </View>

        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="جستجوی کل بازار؛ نام یا نماد..."
          placeholderTextColor={colors.textSecondary}
          style={[styles.searchBox, { backgroundColor: colors.backgroundElement, color: colors.text, borderColor: colors.backgroundSelected }]}
          textAlign="right"
          returnKeyType="search"
        />

        {error ? <Text style={[styles.errorText, { color: colors.textSecondary }]}>دریافت فهرست کل بازار ممکن نشد. صفحه را پایین بکشید و دوباره تلاش کنید.</Text> : null}

        <FlatList
          data={visible}
          keyExtractor={(item) => item.code}
          onEndReached={loadMore}
          onEndReachedThreshold={0.35}
          contentContainerStyle={{ paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.four, maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Brand.stockGreen} />}
          ListEmptyComponent={loading ? <View style={{ paddingTop: Spacing.two }}>{[1,2,3,4,5].map(i => <StockRowSkeleton key={i} />)}</View> : <Text style={[styles.empty, { color: colors.textSecondary }]}>نمادی پیدا نشد</Text>}
          ListFooterComponent={loadingMore ? <ActivityIndicator color={Brand.primary} style={{ marginVertical: Spacing.three }} /> : visible.length < filtered.length ? <Text style={[styles.footerText, { color: colors.textSecondary }]}>برای نمایش نمادهای بیشتر پایین بروید</Text> : null}
          renderItem={({ item }) => {
            const quote = quotes[item.code];
            const hasPct = quote?.changePercent !== undefined && quote?.changePercent !== null && !quote.error;
            const pct = hasPct ? Number(quote.changePercent) : null;
            const up = (pct ?? 0) >= 0;
            return (
              <Pressable onPress={() => router.push(`/stock/${item.code}`)} style={({ pressed }) => ({ opacity: pressed ? 0.75 : 1 })}>
                <View style={[styles.row, { backgroundColor: colors.backgroundElement }]}>
                  <View style={styles.rowLeft}>
                    <View style={[styles.marketTag, { backgroundColor: colors.backgroundSelected }]}><Text style={[styles.marketTagText, { color: colors.textSecondary }]}>{item.market ?? '—'}</Text></View>
                    <View style={{ alignItems: 'flex-start' }}>
                      <Text style={[styles.rowName, { color: colors.text }]}>{item.symbol}</Text>
                      <Text style={[styles.rowCompany, { color: colors.textSecondary }]} numberOfLines={1}>{item.name}</Text>
                    </View>
                  </View>
                  <View style={styles.rowRight}>
                    <Text style={[styles.rowPrice, { color: colors.text }]}>{quote && !quote.error ? formatPrice(quote.lastPrice ?? quote.closingPrice) : 'در حال دریافت…'}</Text>
                    {hasPct && pct !== null ? <Text style={{ color: up ? Brand.stockGreen : Brand.negative, fontFamily: Fonts.mono, fontSize: 12 }}>{up ? '▲' : '▼'} {Math.abs(pct).toFixed(2)}٪</Text> : <Text style={[styles.quoteState, { color: colors.textSecondary }]}>قیمت زنده TSETMC</Text>}
                  </View>
                </View>
              </Pressable>
            );
          }}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 }, container: { flex: 1 },
  header: { paddingHorizontal: Spacing.three, paddingTop: Spacing.four, paddingBottom: Spacing.two },
  headerTop: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between' },
  headerBottom: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', marginTop: 5 },
  headerTitle: { fontSize: 21, fontFamily: Fonts.sans, fontWeight: '800', textAlign: 'right' },
  headerSub: { fontSize: 11, fontFamily: Fonts.sans },
  marketPill: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20 },
  marketDot: { width: 6, height: 6, borderRadius: 3 }, marketLabel: { fontSize: 11, fontFamily: Fonts.sans }, countdown: { fontSize: 10, fontFamily: Fonts.mono },
  searchBox: { marginHorizontal: Spacing.three, marginBottom: Spacing.two, borderWidth: 1, borderRadius: Spacing.two, paddingHorizontal: Spacing.three, paddingVertical: 11, fontSize: 14, fontFamily: Fonts.sans },
  errorText: { textAlign: 'right', paddingHorizontal: Spacing.three, paddingVertical: Spacing.two, fontFamily: Fonts.sans, fontSize: 12 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderRadius: Spacing.two, paddingHorizontal: Spacing.three, paddingVertical: Spacing.three, marginBottom: Spacing.two },
  rowLeft: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two, flex: 1 },
  marketTag: { minWidth: 39, paddingHorizontal: 6, paddingVertical: 4, borderRadius: 10, alignItems: 'center' }, marketTagText: { fontFamily: Fonts.mono, fontSize: 8 },
  rowName: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '700' }, rowCompany: { fontFamily: Fonts.sans, fontSize: 9.5, maxWidth: 180, marginTop: 2 },
  rowRight: { alignItems: 'flex-end', gap: 4, minWidth: 95 }, rowPrice: { fontFamily: Fonts.mono, fontSize: 13 }, quoteState: { fontFamily: Fonts.sans, fontSize: 9 },
  empty: { textAlign: 'center', marginTop: Spacing.five, fontFamily: Fonts.sans }, footerText: { textAlign: 'center', fontFamily: Fonts.sans, fontSize: 10, marginVertical: Spacing.three },
});
