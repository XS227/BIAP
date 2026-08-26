import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  useColorScheme,
  SafeAreaView,
  Pressable,
} from 'react-native';
import { Colors, Brand, Fonts, Spacing, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { fetchWatchlist, formatPrice, parsePct, StockItem } from '@/lib/api';
import { computeMarketSummary } from '@/lib/market-stats';

type SortKey = 'pct' | 'price' | 'name';
const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'pct', label: 'تغییر٪' },
  { key: 'price', label: 'قیمت' },
  { key: 'name', label: 'نام' },
];

function StatCard({
  label,
  value,
  accent,
  colors,
}: {
  label: string;
  value: string;
  accent?: string;
  colors: ThemeColors;
}) {
  return (
    <View style={[statStyles.card, { backgroundColor: colors.backgroundElement }]}>
      <Text style={[statStyles.value, { color: accent ?? colors.text }]}>{value}</Text>
      <Text style={[statStyles.label, { color: colors.textSecondary }]}>{label}</Text>
    </View>
  );
}

const statStyles = StyleSheet.create({
  card: {
    flex: 1,
    borderRadius: Spacing.two,
    padding: Spacing.three,
    alignItems: 'center',
    gap: 4,
  },
  value: { fontSize: 20, fontFamily: Fonts.mono, fontWeight: '700' },
  label: { fontSize: 12, fontFamily: Fonts.sans, textAlign: 'center' },
});

function SentimentBar({
  gainers,
  losers,
  unchanged,
  total,
  colors,
}: {
  gainers: number;
  losers: number;
  unchanged: number;
  total: number;
  colors: ThemeColors;
}) {
  if (total === 0) return null;
  const gPct = (gainers / total) * 100;
  const lPct = (losers / total) * 100;
  const uPct = (unchanged / total) * 100;

  return (
    <View style={[sentStyles.wrap, { backgroundColor: colors.backgroundElement }]}>
      <Text style={[sentStyles.title, { color: colors.text }]}>احساس بازار</Text>
      <View style={sentStyles.bar}>
        <View style={[sentStyles.seg, { flex: gPct, backgroundColor: Brand.stockGreen }]} />
        <View style={[sentStyles.seg, { flex: uPct, backgroundColor: colors.textSecondary }]} />
        <View style={[sentStyles.seg, { flex: lPct, backgroundColor: Brand.negative }]} />
      </View>
      <View style={sentStyles.legend}>
        <View style={sentStyles.legendItem}>
          <View style={[sentStyles.dot, { backgroundColor: Brand.stockGreen }]} />
          <Text style={[sentStyles.legendText, { color: colors.textSecondary }]}>
            مثبت {gainers}
          </Text>
        </View>
        <View style={sentStyles.legendItem}>
          <View style={[sentStyles.dot, { backgroundColor: colors.textSecondary }]} />
          <Text style={[sentStyles.legendText, { color: colors.textSecondary }]}>
            صفر {unchanged}
          </Text>
        </View>
        <View style={sentStyles.legendItem}>
          <View style={[sentStyles.dot, { backgroundColor: Brand.negative }]} />
          <Text style={[sentStyles.legendText, { color: colors.textSecondary }]}>
            منفی {losers}
          </Text>
        </View>
      </View>
    </View>
  );
}

const sentStyles = StyleSheet.create({
  wrap: { borderRadius: Spacing.two, padding: Spacing.three, gap: Spacing.two },
  title: { fontFamily: Fonts.sans, fontSize: 15, textAlign: 'right' },
  bar: { flexDirection: 'row', height: 10, borderRadius: 5, overflow: 'hidden', gap: 2 },
  seg: { borderRadius: 5 },
  legend: { flexDirection: 'row-reverse', gap: Spacing.three },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  legendText: { fontSize: 12, fontFamily: Fonts.sans },
});

function RankRow({
  item,
  rank,
  colors,
}: {
  item: StockItem;
  rank: number;
  colors: ThemeColors;
}) {
  const pct = parsePct(item.changePercent);
  const up = pct >= 0;
  const accentColor = up ? Brand.stockGreen : Brand.negative;

  return (
    <View style={[rankStyles.row, { backgroundColor: colors.backgroundElement }]}>
      <View style={[rankStyles.rankBadge, { backgroundColor: colors.backgroundSelected }]}>
        <Text style={[rankStyles.rankNum, { color: colors.textSecondary }]}>{rank}</Text>
      </View>
      <View style={rankStyles.info}>
        <Text style={[rankStyles.name, { color: colors.text }]}>{item.name}</Text>
        <Text style={[rankStyles.price, { color: colors.textSecondary }]}>
          {formatPrice(item.closingPrice)} ریال
        </Text>
      </View>
      <View style={[rankStyles.badge, { backgroundColor: up ? '#1a3d2b' : '#3d1a1a' }]}>
        <Text style={[rankStyles.pct, { color: accentColor }]}>
          {up ? '▲' : '▼'} {Math.abs(pct).toFixed(2)}٪
        </Text>
      </View>
    </View>
  );
}

const rankStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: Spacing.two,
    padding: Spacing.two,
    marginBottom: Spacing.two,
    gap: Spacing.two,
  },
  rankBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rankNum: { fontSize: 13, fontFamily: Fonts.mono, fontWeight: '700' },
  info: { flex: 1, alignItems: 'flex-end', gap: 2 },
  name: { fontSize: 15, fontFamily: Fonts.sans },
  price: { fontSize: 12, fontFamily: Fonts.mono },
  badge: { borderRadius: Spacing.one, paddingHorizontal: Spacing.two, paddingVertical: 4 },
  pct: { fontSize: 13, fontFamily: Fonts.mono, fontWeight: '700' },
});

function SectionHeader({ title, colors }: { title: string; colors: ThemeColors }) {
  return (
    <Text style={[sectionStyles.title, { color: colors.text }]}>{title}</Text>
  );
}

const sectionStyles = StyleSheet.create({
  title: { fontSize: 16, fontFamily: Fonts.sans, textAlign: 'right', marginBottom: Spacing.two },
});

export default function BizDevScreen() {
  const scheme = useColorScheme() ?? 'light';
  const colors = Colors[scheme];

  const [stocks, setStocks] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('pct');

  const load = useCallback(async () => {
    try {
      setError(false);
      const data = await fetchWatchlist();
      setStocks(data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, [load]);

  const onRefresh = () => {
    setRefreshing(true);
    load();
  };

  const summary = useMemo(() => computeMarketSummary(stocks), [stocks]);

  const gainers = useMemo(() => {
    const byPct = [...stocks].sort((a, b) => parsePct(b.changePercent) - parsePct(a.changePercent));
    return byPct.filter((s) => parsePct(s.changePercent) > 0);
  }, [stocks]);

  const losers = useMemo(() => {
    const byPct = [...stocks].sort((a, b) => parsePct(a.changePercent) - parsePct(b.changePercent));
    return byPct.filter((s) => parsePct(s.changePercent) < 0);
  }, [stocks]);

  const sortedAll = useMemo(() =>
    [...stocks].sort((a, b) => {
      if (sortKey === 'pct') return parsePct(b.changePercent) - parsePct(a.changePercent);
      if (sortKey === 'price') return (b.closingPrice ?? 0) - (a.closingPrice ?? 0);
      return a.name.localeCompare(b.name, 'fa');
    }),
    [stocks, sortKey]
  );

  const avgUp = summary.avgChange >= 0;

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={[
          styles.content,
          { paddingBottom: BottomTabInset + Spacing.four },
        ]}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={Brand.bizBlue}
          />
        }
      >
        <View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
          {/* Header */}
          <View style={styles.header}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>تحلیل کسب‌وکار</Text>
            <Text style={[styles.headerSub, { color: colors.textSecondary }]}>
              خلاصه وضعیت بازار سرمایه
            </Text>
          </View>

          {error && (
            <View style={[styles.errorBox, { backgroundColor: colors.backgroundElement }]}>
              <Text style={{ color: colors.textSecondary, textAlign: 'right', fontFamily: Fonts.sans }}>
                خطا در دریافت داده. برای تلاش دوباره پایین بکشید.
              </Text>
            </View>
          )}

          {!loading && stocks.length > 0 && (
            <>
              {/* Stats row */}
              <View style={styles.statsRow}>
                <StatCard
                  label="میانگین تغییر"
                  value={`${avgUp ? '▲' : '▼'} ${Math.abs(summary.avgChange).toFixed(2)}٪`}
                  accent={avgUp ? Brand.stockGreen : Brand.negative}
                  colors={colors}
                />
                <StatCard
                  label="تعداد نمادها"
                  value={String(summary.total)}
                  colors={colors}
                />
                <StatCard
                  label="مثبت / منفی"
                  value={`${summary.gainers} / ${summary.losers}`}
                  accent={Brand.bizBlue}
                  colors={colors}
                />
              </View>

              {/* Sentiment bar */}
              <SentimentBar
                gainers={summary.gainers}
                losers={summary.losers}
                unchanged={summary.unchanged}
                total={summary.total}
                colors={colors}
              />

              {/* Top gainer / loser highlight */}
              {(summary.topGainer || summary.topLoser) && (
                <View style={styles.highlightRow}>
                  {summary.topGainer && (
                    <View
                      style={[styles.highlight, { backgroundColor: '#1a3d2b', flex: 1 }]}
                    >
                      <Text style={[styles.highlightLabel, { color: Brand.stockGreen }]}>
                        بیشترین رشد
                      </Text>
                      <Text style={[styles.highlightName, { color: colors.text }]}>
                        {summary.topGainer.name}
                      </Text>
                      <Text style={[styles.highlightPct, { color: Brand.stockGreen }]}>
                        ▲ {Math.abs(parsePct(summary.topGainer.changePercent)).toFixed(2)}٪
                      </Text>
                    </View>
                  )}
                  {summary.topLoser && (
                    <View
                      style={[styles.highlight, { backgroundColor: '#3d1a1a', flex: 1 }]}
                    >
                      <Text style={[styles.highlightLabel, { color: Brand.negative }]}>
                        بیشترین افت
                      </Text>
                      <Text style={[styles.highlightName, { color: colors.text }]}>
                        {summary.topLoser.name}
                      </Text>
                      <Text style={[styles.highlightPct, { color: Brand.negative }]}>
                        ▼ {Math.abs(parsePct(summary.topLoser.changePercent)).toFixed(2)}٪
                      </Text>
                    </View>
                  )}
                </View>
              )}

              {/* Gainers ranking */}
              {gainers.length > 0 && (
                <View style={styles.section}>
                  <SectionHeader title="برترین رشدها" colors={colors} />
                  {gainers.map((s, i) => (
                    <RankRow key={s.code} item={s} rank={i + 1} colors={colors} />
                  ))}
                </View>
              )}

              {/* Losers ranking */}
              {losers.length > 0 && (
                <View style={styles.section}>
                  <SectionHeader title="بیشترین افت‌ها" colors={colors} />
                  {losers.map((s, i) => (
                    <RankRow key={s.code} item={s} rank={i + 1} colors={colors} />
                  ))}
                </View>
              )}

              {/* All stocks — sortable */}
              <View style={styles.section}>
                <View style={sortStyles.row}>
                  <SectionHeader title="همه نمادها" colors={colors} />
                  <View style={sortStyles.pills}>
                    {SORT_OPTIONS.map(({ key, label }) => (
                      <Pressable
                        key={key}
                        onPress={() => setSortKey(key)}
                        style={[
                          sortStyles.pill,
                          { backgroundColor: sortKey === key ? Brand.bizBlue : colors.backgroundElement },
                        ]}
                      >
                        <Text style={[sortStyles.pillText, { color: sortKey === key ? '#fff' : colors.textSecondary }]}>
                          {label}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                </View>
                {sortedAll.map((s, i) => (
                  <RankRow key={s.code} item={s} rank={i + 1} colors={colors} />
                ))}
              </View>
            </>
          )}

          {loading && (
            <View style={styles.loadingWrap}>
              <Text style={{ color: colors.textSecondary, fontFamily: Fonts.sans }}>
                در حال بارگذاری...
              </Text>
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three },
  header: {
    paddingTop: Spacing.four,
    paddingBottom: Spacing.three,
  },
  headerTitle: { fontSize: 22, fontFamily: Fonts.sans, textAlign: 'right' },
  headerSub: { fontSize: 13, fontFamily: Fonts.sans, textAlign: 'right', marginTop: 2 },
  errorBox: { borderRadius: Spacing.two, padding: Spacing.three, marginBottom: Spacing.three },
  statsRow: { flexDirection: 'row-reverse', gap: Spacing.two, marginBottom: Spacing.three },
  highlightRow: { flexDirection: 'row-reverse', gap: Spacing.two, marginVertical: Spacing.three },
  highlight: {
    borderRadius: Spacing.two,
    padding: Spacing.three,
    gap: 4,
    alignItems: 'flex-end',
  },
  highlightLabel: { fontSize: 11, fontFamily: Fonts.sans },
  highlightName: { fontSize: 16, fontFamily: Fonts.sans },
  highlightPct: { fontSize: 15, fontFamily: Fonts.mono, fontWeight: '700' },
  section: { marginTop: Spacing.three },
  loadingWrap: { alignItems: 'center', marginTop: Spacing.six },
});

const sortStyles = StyleSheet.create({
  row: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', marginBottom: Spacing.two },
  pills: { flexDirection: 'row', gap: Spacing.one },
  pill: { paddingHorizontal: Spacing.two, paddingVertical: 4, borderRadius: Spacing.five },
  pillText: { fontFamily: Fonts.sans, fontSize: 12 },
});
