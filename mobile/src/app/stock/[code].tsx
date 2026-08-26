import { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  useColorScheme,
  SafeAreaView,
  RefreshControl,
} from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, BottomTabInset, ThemeColors } from '@/constants/theme';
import { fetchWatchlist, fetchRecommendation, formatPrice, parsePct, Recommendation, StockItem } from '@/lib/api';
import { StockRowSkeleton } from '@/components/skeleton';
import { RecommendationCard } from '@/components/recommendation-card';

function BackButton({ colors }: { colors: ThemeColors }) {
  return (
    <Pressable
      onPress={() => router.back()}
      style={({ pressed }) => [
        backStyles.btn,
        { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.7 : 1 },
      ]}
    >
      <Text style={[backStyles.arrow, { color: colors.text }]}>←</Text>
      <Text style={[backStyles.label, { color: colors.text }]}>بازگشت</Text>
    </Pressable>
  );
}
const backStyles = StyleSheet.create({
  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: Spacing.two,
    alignSelf: 'flex-end',
  },
  arrow: { fontSize: 18 },
  label: { fontFamily: Fonts.sans, fontSize: 14 },
});

function PriceCard({
  item,
  colors,
}: {
  item: StockItem;
  colors: ThemeColors;
}) {
  const pct = parsePct(item.changePercent);
  const up = pct >= 0;
  const accent = up ? Brand.stockGreen : Brand.negative;
  const diff = (item.closingPrice ?? 0) - (item.yesterdayPrice ?? 0);

  return (
    <View style={[cardStyles.wrap, { backgroundColor: colors.backgroundElement }]}>
      <Text style={[cardStyles.name, { color: colors.text }]}>{item.name}</Text>
      <Text style={[cardStyles.code, { color: colors.textSecondary }]}>{item.code}</Text>

      <View style={cardStyles.priceRow}>
        <Text style={[cardStyles.price, { color: colors.text }]}>
          {formatPrice(item.closingPrice)}
        </Text>
        <Text style={[cardStyles.unit, { color: colors.textSecondary }]}>ریال</Text>
      </View>

      <View style={[cardStyles.badge, { backgroundColor: up ? '#1a3d2b' : '#3d1a1a' }]}>
        <Text style={[cardStyles.pct, { color: accent }]}>
          {up ? '▲' : '▼'} {Math.abs(pct).toFixed(2)}٪
        </Text>
        <Text style={[cardStyles.diffText, { color: accent }]}>
          ({diff >= 0 ? '+' : ''}{formatPrice(diff)} ریال)
        </Text>
      </View>
    </View>
  );
}
const cardStyles = StyleSheet.create({
  wrap: { borderRadius: Spacing.three, padding: Spacing.four, alignItems: 'flex-end', gap: Spacing.two },
  name: { fontSize: 24, fontFamily: Fonts.sans },
  code: { fontSize: 12, fontFamily: Fonts.mono },
  priceRow: { flexDirection: 'row-reverse', alignItems: 'baseline', gap: 6 },
  price: { fontSize: 32, fontFamily: Fonts.mono, fontWeight: '700' },
  unit: { fontSize: 14, fontFamily: Fonts.sans },
  badge: { flexDirection: 'row-reverse', gap: Spacing.two, paddingHorizontal: Spacing.three, paddingVertical: Spacing.one, borderRadius: Spacing.five },
  pct: { fontSize: 16, fontFamily: Fonts.mono, fontWeight: '700' },
  diffText: { fontSize: 14, fontFamily: Fonts.mono },
});

function InfoRow({ label, value, accent, colors }: { label: string; value: string; accent?: string; colors: ThemeColors }) {
  return (
    <View style={[infoStyles.row, { borderBottomColor: colors.backgroundSelected }]}>
      <Text style={[infoStyles.val, { color: accent ?? colors.text }]}>{value}</Text>
      <Text style={[infoStyles.lbl, { color: colors.textSecondary }]}>{label}</Text>
    </View>
  );
}
const infoStyles = StyleSheet.create({
  row: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: Spacing.three,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  lbl: { fontFamily: Fonts.sans, fontSize: 14 },
  val: { fontFamily: Fonts.mono, fontSize: 15, fontWeight: '700' },
});

function MiniBarChart({ item, colors }: { item: StockItem; colors: ThemeColors }) {
  const prices = [
    { label: 'دیروز', value: item.yesterdayPrice ?? 0 },
    { label: 'پایانی', value: item.closingPrice ?? 0 },
    { label: 'آخرین', value: item.lastPrice ?? 0 },
  ];
  const max = Math.max(...prices.map((p) => p.value));
  const pct = parsePct(item.changePercent);
  const up = pct >= 0;

  return (
    <View style={[chartStyles.wrap, { backgroundColor: colors.backgroundElement }]}>
      <Text style={[chartStyles.title, { color: colors.text }]}>مقایسه قیمت</Text>
      <View style={chartStyles.bars}>
        {prices.map((p) => (
          <View key={p.label} style={chartStyles.col}>
            <Text style={[chartStyles.val, { color: colors.textSecondary }]}>
              {(p.value / 1000).toFixed(0)}K
            </Text>
            <View style={chartStyles.track}>
              <View
                style={[
                  chartStyles.bar,
                  {
                    height: `${max > 0 ? (p.value / max) * 100 : 4}%`,
                    backgroundColor: p.label === 'دیروز'
                      ? colors.textSecondary
                      : up ? Brand.stockGreen : Brand.negative,
                  },
                ]}
              />
            </View>
            <Text style={[chartStyles.lbl, { color: colors.text }]}>{p.label}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}
const chartStyles = StyleSheet.create({
  wrap: { borderRadius: Spacing.two, padding: Spacing.three, marginTop: Spacing.three },
  title: { fontFamily: Fonts.sans, fontSize: 15, textAlign: 'right', marginBottom: Spacing.three },
  bars: { flexDirection: 'row-reverse', alignItems: 'flex-end', height: 120, gap: Spacing.three },
  col: { flex: 1, alignItems: 'center', height: '100%' },
  track: { flex: 1, width: '100%', justifyContent: 'flex-end', alignItems: 'center' },
  bar: { width: '60%', borderRadius: 4, minHeight: 4 },
  val: { fontFamily: Fonts.mono, fontSize: 10, marginBottom: 4 },
  lbl: { fontFamily: Fonts.sans, fontSize: 12, marginTop: 6 },
});

export default function StockDetailScreen() {
  const { code } = useLocalSearchParams<{ code: string }>();
  const scheme = useColorScheme() ?? 'light';
  const colors = Colors[scheme];

  const [item, setItem] = useState<StockItem | null>(null);
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const all = await fetchWatchlist();
      const found = all.find((s) => s.code === code) ?? null;
      setItem(found);
      setNotFound(found === null);
      if (found) {
        // Additive and best-effort: the recommendation endpoint may not be
        // deployed yet, fetchRecommendation resolves to null rather than
        // throwing, and the rest of the screen doesn't wait on it.
        fetchRecommendation(found.code).then(setRec);
      } else {
        setRec(null);
      }
    } catch {
      // keep previous item if refresh fails
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [code]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [load]);

  const pct = item ? parsePct(item.changePercent) : 0;
  const up = pct >= 0;
  const accent = up ? Brand.stockGreen : Brand.negative;

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={Brand.stockGreen} />
        }
      >
        <View style={styles.header}>
          <BackButton colors={colors} />
          <Text style={[styles.headerLabel, { color: colors.textSecondary }]}>جزئیات نماد</Text>
        </View>

        {loading ? (
          <View style={{ paddingTop: Spacing.two }}>
            {[1, 2, 3].map((i) => <StockRowSkeleton key={i} />)}
          </View>
        ) : notFound ? (
          <View style={styles.center}>
            <Text style={[styles.notFoundTitle, { color: colors.text }]}>نماد یافت نشد</Text>
            <Text style={[styles.notFoundSub, { color: colors.textSecondary }]}>
              این نماد در watchlist شما وجود ندارد
            </Text>
            <Pressable
              onPress={() => router.back()}
              style={[styles.notFoundBtn, { backgroundColor: colors.backgroundElement }]}
            >
              <Text style={[styles.notFoundBtnText, { color: colors.text }]}>← بازگشت</Text>
            </Pressable>
          </View>
        ) : item ? (
          <>
            <PriceCard item={item} colors={colors} />

            <MiniBarChart item={item} colors={colors} />

            {/* Details table */}
            <View style={[styles.table, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.tableTitle, { color: colors.text }]}>اطلاعات بازار</Text>
              <InfoRow label="قیمت پایانی"   value={`${formatPrice(item.closingPrice)} ریال`}   accent={colors.text} colors={colors} />
              <InfoRow label="آخرین قیمت"    value={`${formatPrice(item.lastPrice)} ریال`}      accent={colors.text} colors={colors} />
              <InfoRow label="قیمت دیروز"    value={`${formatPrice(item.yesterdayPrice)} ریال`} colors={colors} />
              <InfoRow label="تغییر"          value={`${item.change ?? 0}`}                      colors={colors} />
              <InfoRow
                label="درصد تغییر"
                value={`${up ? '▲' : '▼'} ${Math.abs(pct).toFixed(2)}٪`}
                accent={accent}
                colors={colors}
              />
              <InfoRow label="کد نماد" value={item.code} colors={colors} />
            </View>

            {rec ? <RecommendationCard rec={rec} colors={colors} /> : null}

            {/* Disclaimer */}
            <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>
              داده‌ها از TSETMC · هر ۳۰ ثانیه به‌روز می‌شود
            </Text>
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three },
  header: {
    flexDirection: 'row-reverse',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.three,
  },
  headerLabel: { fontFamily: Fonts.sans, fontSize: 13 },
  center: { alignItems: 'center', marginTop: Spacing.six, gap: Spacing.two },
  notFoundTitle: { fontFamily: Fonts.sans, fontSize: 20 },
  notFoundSub: { fontFamily: Fonts.sans, fontSize: 14, textAlign: 'center', paddingHorizontal: Spacing.four },
  notFoundBtn: { marginTop: Spacing.three, paddingHorizontal: Spacing.four, paddingVertical: Spacing.two, borderRadius: Spacing.two },
  notFoundBtnText: { fontFamily: Fonts.sans, fontSize: 15 },
  table: { borderRadius: Spacing.two, padding: Spacing.three, marginTop: Spacing.three },
  tableTitle: { fontFamily: Fonts.sans, fontSize: 15, textAlign: 'right', marginBottom: Spacing.two },
  disclaimer: { fontFamily: Fonts.sans, fontSize: 11, textAlign: 'center', marginTop: Spacing.three },
});
