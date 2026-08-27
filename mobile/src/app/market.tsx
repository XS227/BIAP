import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  Animated,
  Easing,
  useColorScheme,
  SafeAreaView,
  Pressable,
  TextInput,
} from 'react-native';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { fetchWatchlist, formatPrice, parsePct, StockItem } from '@/lib/api';
import { StockRowSkeleton } from '@/components/skeleton';
import { marketStatusLabel } from '@/lib/market-hours';

function Arrow({ up }: { up: boolean }) {
  return (
    <Text style={{ color: up ? Brand.stockGreen : Brand.negative, fontSize: 11, lineHeight: 14 }}>
      {up ? '▲' : '▼'}
    </Text>
  );
}

function Ticker({ items, colors }: { items: StockItem[]; colors: ThemeColors }) {
  const scrollX = useRef(new Animated.Value(0)).current;
  const [contentWidth, setContentWidth] = useState(0);
  const [containerWidth, setContainerWidth] = useState(0);

  useEffect(() => {
    if (contentWidth <= containerWidth || contentWidth === 0) return;
    scrollX.setValue(containerWidth);
    const anim = Animated.loop(
      Animated.timing(scrollX, {
        toValue: -contentWidth,
        duration: (contentWidth + containerWidth) * 18,
        easing: Easing.linear,
        useNativeDriver: true,
      })
    );
    anim.start();
    return () => anim.stop();
  }, [contentWidth, containerWidth, scrollX]);

  return (
    <View
      style={[styles.tickerWrap, { backgroundColor: colors.backgroundElement }]}
      onLayout={(e) => setContainerWidth(e.nativeEvent.layout.width)}
    >
      <Animated.View
        style={[styles.tickerRow, { transform: [{ translateX: scrollX }] }]}
        onLayout={(e) => setContentWidth(e.nativeEvent.layout.width)}
      >
        {items.concat(items).map((item, idx) => {
          const pct = parsePct(item.changePercent);
          const up = pct >= 0;
          return (
            <View key={idx} style={styles.tickerItem}>
              <Text style={[styles.tickerName, { color: colors.text }]}>{item.name}</Text>
              <Text style={[styles.tickerPrice, { color: colors.text }]}>
                {formatPrice(item.closingPrice)}
              </Text>
              <View style={styles.tickerPctRow}>
                <Arrow up={up} />
                <Text style={{ color: up ? Brand.stockGreen : Brand.negative, fontSize: 12 }}>
                  {Math.abs(pct).toFixed(2)}٪
                </Text>
              </View>
            </View>
          );
        })}
      </Animated.View>
    </View>
  );
}

export default function MarketScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [data, setData] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const [countdown, setCountdown] = useState(30);
  const [query, setQuery] = useState('');
  const marketStatus = marketStatusLabel();

  const filtered = useMemo(() =>
    query.trim()
      ? data.filter((s) => s.name.includes(query) || s.code.includes(query))
      : data,
    [data, query]
  );

  const load = useCallback(async () => {
    try {
      setError(false);
      const symbols = await fetchWatchlist();
      setData(symbols);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(() => { load(); setCountdown(30); }, 30_000);
    const tick = setInterval(() => setCountdown((c) => (c > 0 ? c - 1 : 30)), 1_000);
    return () => { clearInterval(interval); clearInterval(tick); };
  }, [load]);

  const onRefresh = () => {
    setRefreshing(true);
    setCountdown(30);
    load();
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <View style={styles.header}>
          <View style={styles.headerTop}>
            <View style={[styles.marketPill, { backgroundColor: marketStatus.open ? '#1a3d2b' : colors.backgroundElement }]}>
              <View style={[styles.marketDot, { backgroundColor: marketStatus.open ? Brand.stockGreen : colors.textSecondary }]} />
              <Text style={[styles.marketLabel, { color: marketStatus.open ? Brand.stockGreen : colors.textSecondary }]}>
                {marketStatus.label}
              </Text>
            </View>
            <Text style={[styles.headerTitle, { color: colors.text }]}>بورس تهران</Text>
          </View>
          <View style={styles.headerBottom}>
            <Text style={[styles.countdown, { color: colors.textSecondary }]}>بروزرسانی در {countdown}ث</Text>
            <Text style={[styles.headerSub, { color: colors.textSecondary }]}>داده زنده از TSETMC</Text>
          </View>
        </View>

        {data.length > 0 && <Ticker items={data} colors={colors} />}

        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="جستجوی نماد..."
          placeholderTextColor={colors.textSecondary}
          style={[styles.searchBox, { backgroundColor: colors.backgroundElement, color: colors.text, borderColor: colors.backgroundSelected }]}
          textAlign="right"
          returnKeyType="search"
        />

        {error && (
          <View style={styles.errorBox}>
            <Text style={{ color: colors.textSecondary, textAlign: 'right' }}>
              دریافت داده با خطا مواجه شد. برای تلاش دوباره پایین را بکشید.
            </Text>
          </View>
        )}

        <FlatList
          data={filtered}
          keyExtractor={(item) => item.code}
          contentContainerStyle={{
            paddingHorizontal: Spacing.three,
            paddingBottom: BottomTabInset + Spacing.four,
            maxWidth: MaxContentWidth,
            width: '100%',
            alignSelf: 'center',
          }}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={Brand.stockGreen}
            />
          }
          ListEmptyComponent={
            loading ? (
              <View style={{ paddingTop: Spacing.two }}>
                {[1, 2, 3, 4, 5].map((i) => <StockRowSkeleton key={i} />)}
              </View>
            ) : (
              <Text style={{ color: colors.textSecondary, textAlign: 'center', marginTop: Spacing.five, fontFamily: Fonts.sans }}>
                داده‌ای موجود نیست
              </Text>
            )
          }
          renderItem={({ item }) => {
            const pct = parsePct(item.changePercent);
            const up = pct >= 0;
            return (
              <Pressable
                onPress={() => router.push(`/stock/${item.code}`)}
                style={({ pressed }) => ({ opacity: pressed ? 0.75 : 1 })}
              >
              <View style={[styles.row, { backgroundColor: colors.backgroundElement }]}>
                <View style={styles.rowLeft}>
                  <View style={[styles.dot, { backgroundColor: Brand.stockGreen }]} />
                  <Text style={[styles.rowName, { color: colors.text }]}>{item.name}</Text>
                </View>
                <View style={styles.rowRight}>
                  <Text style={[styles.rowPrice, { color: colors.text }]}>
                    {formatPrice(item.closingPrice)}
                  </Text>
                  <View style={styles.pctBadge}>
                    <Arrow up={up} />
                    <Text style={{ color: up ? Brand.stockGreen : Brand.negative, fontSize: 13 }}>
                      {Math.abs(pct).toFixed(2)}٪
                    </Text>
                  </View>
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
  safe: { flex: 1 },
  container: { flex: 1 },
  header: {
    paddingHorizontal: Spacing.three,
    paddingTop: Spacing.four,
    paddingBottom: Spacing.two,
  },
  headerTop: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between' },
  headerBottom: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 },
  headerTitle: { fontSize: 22, fontFamily: Fonts.sans, textAlign: 'right' },
  headerSub: { fontSize: 12, fontFamily: Fonts.sans, textAlign: 'right' },
  marketPill: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20 },
  marketDot: { width: 6, height: 6, borderRadius: 3 },
  marketLabel: { fontSize: 12, fontFamily: Fonts.sans },
  countdown: { fontSize: 12, fontFamily: Fonts.mono },
  tickerWrap: {
    height: 48,
    overflow: 'hidden',
    marginVertical: Spacing.two,
  },
  tickerRow: { flexDirection: 'row', position: 'absolute', top: 0, bottom: 0, alignItems: 'center' },
  tickerItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.three,
    gap: 6,
  },
  tickerName: { fontFamily: Fonts.sans, fontSize: 13 },
  tickerPrice: { fontFamily: Fonts.mono, fontSize: 13 },
  tickerPctRow: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  searchBox: { marginHorizontal: Spacing.three, marginBottom: Spacing.two, borderWidth: 1, borderRadius: Spacing.two, paddingHorizontal: Spacing.three, paddingVertical: 10, fontSize: 14, fontFamily: Fonts.sans },
  errorBox: { paddingHorizontal: Spacing.three, paddingVertical: Spacing.two },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderRadius: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.three,
    marginBottom: Spacing.two,
  },
  rowLeft: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  dot: { width: 8, height: 8, borderRadius: 4 },
  rowName: { fontFamily: Fonts.sans, fontSize: 16 },
  rowRight: { alignItems: 'flex-end', gap: 4 },
  rowPrice: { fontFamily: Fonts.mono, fontSize: 15 },
  pctBadge: { flexDirection: 'row', alignItems: 'center', gap: 2 },
});
