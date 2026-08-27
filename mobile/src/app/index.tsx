import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  Image,
  StyleSheet,
  ScrollView,
  RefreshControl,
  useColorScheme,
  SafeAreaView,
  Pressable,
} from 'react-native';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors, BiapLogo } from '@/constants/theme';
import { fetchWatchlist, formatPrice, parsePct, StockItem } from '@/lib/api';
import { computeMarketSummary } from '@/lib/market-stats';
import { marketStatusLabel } from '@/lib/market-hours';
import { StockRowSkeleton } from '@/components/skeleton';

function Avatar({ colors }: { colors: ThemeColors }) {
  return (
    <Pressable onPress={() => router.push('/more')} style={[avatarStyles.circle, { backgroundColor: Brand.primary }]}>
      <Text style={avatarStyles.text}>؟</Text>
    </Pressable>
  );
}
const avatarStyles = StyleSheet.create({
  circle: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  text: { color: '#fff', fontSize: 15, fontWeight: '700' },
});

function StatChip({ label, value, accent, colors }: { label: string; value: string; accent?: string; colors: ThemeColors }) {
  return (
    <View style={[chipStyles.wrap, { backgroundColor: colors.backgroundElement }]}>
      <Text style={[chipStyles.value, { color: accent ?? colors.text }]}>{value}</Text>
      <Text style={[chipStyles.label, { color: colors.textSecondary }]}>{label}</Text>
    </View>
  );
}
const chipStyles = StyleSheet.create({
  wrap: { flex: 1, borderRadius: Radius.md, padding: Spacing.three, alignItems: 'center', gap: 4 },
  value: { fontSize: 17, fontFamily: Fonts.mono, fontWeight: '700' },
  label: { fontSize: 11, fontFamily: Fonts.sans, textAlign: 'center' },
});

function WatchRow({ item, colors }: { item: StockItem; colors: ThemeColors }) {
  const pct = parsePct(item.changePercent);
  const up = pct >= 0;
  return (
    <Pressable
      onPress={() => router.push(`/stock/${item.code}`)}
      style={({ pressed }) => [rowStyles.row, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.75 : 1 }]}
    >
      <View style={rowStyles.left}>
        <View style={[rowStyles.dot, { backgroundColor: up ? Brand.positive : Brand.negative }]} />
        <Text style={[rowStyles.name, { color: colors.text }]}>{item.name}</Text>
      </View>
      <View style={rowStyles.right}>
        <Text style={[rowStyles.price, { color: colors.text }]}>{formatPrice(item.closingPrice)}</Text>
        <Text style={{ color: up ? Brand.positive : Brand.negative, fontSize: 12, fontFamily: Fonts.mono }}>
          {up ? '▲' : '▼'} {Math.abs(pct).toFixed(2)}٪
        </Text>
      </View>
    </Pressable>
  );
}
const rowStyles = StyleSheet.create({
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderRadius: Radius.sm, paddingHorizontal: Spacing.three, paddingVertical: Spacing.three, marginBottom: Spacing.two },
  left: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  dot: { width: 8, height: 8, borderRadius: 4 },
  name: { fontFamily: Fonts.sans, fontSize: 15 },
  right: { alignItems: 'flex-end', gap: 3 },
  price: { fontFamily: Fonts.mono, fontSize: 14 },
});

type QuickNavItem = { key: string; title: string; sub: string; icon: string; accent: string; href: '/market' | '/orders' | '/portfolio' | '/kiasha' };

const QUICK_NAV: QuickNavItem[] = [
  { key: 'market', title: 'بازار', sub: 'همه نمادها', icon: '📈', accent: Brand.positive, href: '/market' },
  { key: 'orders', title: 'سفارش‌ها', sub: 'شبیه‌سازی‌های Paper', icon: '🧾', accent: Brand.warning, href: '/orders' },
  { key: 'portfolio', title: 'پرتفوی', sub: 'وضعیت دارایی', icon: '💼', accent: Brand.secondary, href: '/portfolio' },
  { key: 'kiasha', title: 'کیاشا', sub: 'عامل هوشمند', icon: '🤖', accent: Brand.primary, href: '/kiasha' },
];

function QuickNavCard({ item, colors }: { item: QuickNavItem; colors: ThemeColors }) {
  return (
    <Pressable
      onPress={() => router.push(item.href)}
      style={({ pressed }) => [navStyles.card, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.8 : 1 }]}
    >
      <View style={[navStyles.iconWrap, { backgroundColor: `${item.accent}1F` }]}>
        <Text style={{ fontSize: 20 }}>{item.icon}</Text>
      </View>
      <Text style={[navStyles.title, { color: colors.text }]}>{item.title}</Text>
      <Text style={[navStyles.sub, { color: colors.textSecondary }]}>{item.sub}</Text>
    </Pressable>
  );
}
const navStyles = StyleSheet.create({
  card: { flexBasis: '47%', borderRadius: Radius.md, padding: Spacing.three, alignItems: 'flex-end', gap: 4 },
  iconWrap: { width: 40, height: 40, borderRadius: Radius.sm, alignItems: 'center', justifyContent: 'center', marginBottom: 4 },
  title: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '700' },
  sub: { fontFamily: Fonts.sans, fontSize: 11 },
});

export default function HomeScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [data, setData] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const marketStatus = marketStatusLabel();

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
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [load]);

  const onRefresh = () => {
    setRefreshing(true);
    load();
  };

  const summary = useMemo(() => computeMarketSummary(data), [data]);
  const preview = data.slice(0, 5);
  const avgUp = summary.avgChange >= 0;

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Brand.primary} />}
      >
        <View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
          {/* Header */}
          <View style={styles.header}>
            <Avatar colors={colors} />
            <Image source={BiapLogo} style={styles.logo} resizeMode="contain" />
            <Pressable onPress={() => router.push('/market')} style={[styles.searchBtn, { backgroundColor: colors.backgroundElement }]}>
              <Text style={{ fontSize: 16 }}>🔍</Text>
            </Pressable>
          </View>

          <View style={[styles.marketPill, { backgroundColor: marketStatus.open ? '#123d2b' : colors.backgroundElement, alignSelf: 'flex-end' }]}>
            <View style={[styles.marketDot, { backgroundColor: marketStatus.open ? Brand.positive : colors.textSecondary }]} />
            <Text style={[styles.marketLabel, { color: marketStatus.open ? Brand.positive : colors.textSecondary }]}>
              {marketStatus.label}
            </Text>
          </View>

          {error ? (
            <View style={[styles.errorBox, { backgroundColor: colors.backgroundElement }]}>
              <Text style={{ color: colors.textSecondary, textAlign: 'right', fontFamily: Fonts.sans }}>
                دریافت داده با خطا مواجه شد. برای تلاش دوباره پایین را بکشید.
              </Text>
            </View>
          ) : null}

          {!loading && data.length > 0 ? (
            <>
              {/* Honest watchlist-derived summary -- not the official TSE index */}
              <View style={styles.statsRow}>
                <StatChip
                  label="میانگین تغییر دیده‌بان"
                  value={`${avgUp ? '▲' : '▼'} ${Math.abs(summary.avgChange).toFixed(2)}٪`}
                  accent={avgUp ? Brand.positive : Brand.negative}
                  colors={colors}
                />
                <StatChip label="تعداد نمادها" value={String(summary.total)} colors={colors} />
                <StatChip label="مثبت / منفی" value={`${summary.gainers} / ${summary.losers}`} accent={Brand.primary} colors={colors} />
              </View>

              {/* Watchlist preview */}
              <View style={styles.sectionHead}>
                <Pressable onPress={() => router.push('/market')}>
                  <Text style={[styles.sectionLink, { color: Brand.primary }]}>مشاهده همه ←</Text>
                </Pressable>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>دیده‌بان من</Text>
              </View>
              {preview.map((item) => (
                <WatchRow key={item.code} item={item} colors={colors} />
              ))}
            </>
          ) : null}

          {loading ? (
            <View style={{ marginTop: Spacing.two }}>
              {[1, 2, 3].map((i) => <StockRowSkeleton key={i} />)}
            </View>
          ) : null}

          {/* Quick nav */}
          <Text style={[styles.sectionTitle, { color: colors.text, marginTop: Spacing.four }]}>دسترسی سریع</Text>
          <View style={styles.navGrid}>
            {QUICK_NAV.map((item) => (
              <QuickNavCard key={item.key} item={item} colors={colors} />
            ))}
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingTop: Spacing.three },
  header: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', marginBottom: Spacing.two },
  logo: { width: 84, height: 28 },
  searchBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  marketPill: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20, marginBottom: Spacing.three },
  marketDot: { width: 6, height: 6, borderRadius: 3 },
  marketLabel: { fontSize: 12, fontFamily: Fonts.sans },
  errorBox: { borderRadius: Radius.sm, padding: Spacing.three, marginBottom: Spacing.three },
  statsRow: { flexDirection: 'row-reverse', gap: Spacing.two, marginBottom: Spacing.four },
  sectionHead: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', marginBottom: Spacing.two },
  sectionTitle: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '700', textAlign: 'right' },
  sectionLink: { fontFamily: Fonts.sans, fontSize: 13 },
  navGrid: { flexDirection: 'row-reverse', flexWrap: 'wrap', gap: Spacing.two, marginTop: Spacing.two },
});
