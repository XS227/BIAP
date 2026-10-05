import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  FlatList,
  Pressable,
  useColorScheme,
  SafeAreaView,
  ActivityIndicator,
} from 'react-native';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { fetchSymbols, MarketSymbolResult } from '@/lib/api';

const MARKET_LABEL: Record<string, string> = { TSE: 'بورس', IFB: 'فرابورس', IFB_BASE: 'پایه فرابورس' };

function BackButton({ colors }: { colors: ThemeColors }) {
  return (
    <Pressable
      onPress={() => router.back()}
      style={({ pressed }) => [backStyles.btn, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.7 : 1 }]}
    >
      <Text style={[backStyles.arrow, { color: colors.text }]}>←</Text>
    </Pressable>
  );
}
const backStyles = StyleSheet.create({
  btn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  arrow: { fontSize: 18 },
});

function ResultRow({ item, colors }: { item: MarketSymbolResult; colors: ThemeColors }) {
  return (
    <Pressable
      onPress={() => router.push(`/stock/${item.code}`)}
      style={({ pressed }) => [rowStyles.row, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.75 : 1 }]}
    >
      <View style={rowStyles.left}>
        <Text style={[rowStyles.symbol, { color: colors.text }]}>{item.symbol}</Text>
        <Text style={[rowStyles.name, { color: colors.textSecondary }]} numberOfLines={1}>
          {item.name}
        </Text>
      </View>
      {item.market ? (
        <View style={[rowStyles.badge, { backgroundColor: `${Brand.primary}1F` }]}>
          <Text style={[rowStyles.badgeText, { color: Brand.primary }]}>{MARKET_LABEL[item.market] ?? item.market}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}
const rowStyles = StyleSheet.create({
  row: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderRadius: Radius.sm,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.three,
    marginBottom: Spacing.two,
  },
  left: { flex: 1, alignItems: 'flex-end', gap: 2 },
  symbol: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '700' },
  name: { fontFamily: Fonts.sans, fontSize: 12 },
  badge: { paddingHorizontal: Spacing.two, paddingVertical: 4, borderRadius: Radius.sm, marginStart: Spacing.two },
  badgeText: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '600' },
});

export default function SearchScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MarketSymbolResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runSearch = useCallback(async (q: string) => {
    if (q.trim().length < 2) {
      setResults([]);
      setSearched(false);
      return;
    }
    setLoading(true);
    const items = await fetchSymbols({ q: q.trim(), limit: 40 });
    setResults(items);
    setSearched(true);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runSearch(query), 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, runSearch]);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center', flex: 1, paddingHorizontal: Spacing.three }}>
        <View style={styles.header}>
          <BackButton colors={colors} />
          <Text style={[styles.headerLabel, { color: colors.text }]}>جستجوی نماد</Text>
        </View>

        <View style={[styles.inputWrap, { backgroundColor: colors.backgroundElement }]}>
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="نام یا نماد شرکت را وارد کنید…"
            placeholderTextColor={colors.textSecondary}
            style={[styles.input, { color: colors.text }]}
            autoFocus
            textAlign="right"
          />
          {loading ? <ActivityIndicator color={colors.textSecondary} /> : <Text style={{ fontSize: 16 }}>🔍</Text>}
        </View>

        <Text style={[styles.hint, { color: colors.textSecondary }]}>
          جستجو در کل بازار (بورس، فرابورس، پایه) — نه فقط دیده‌بان شما
        </Text>

        {searched && !loading && results.length === 0 ? (
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: colors.textSecondary }]}>نمادی یافت نشد</Text>
          </View>
        ) : (
          <FlatList
            data={results}
            keyExtractor={(item) => item.code}
            renderItem={({ item }) => <ResultRow item={item} colors={colors} />}
            contentContainerStyle={{ paddingTop: Spacing.three, paddingBottom: BottomTabInset + Spacing.four }}
            keyboardShouldPersistTaps="handled"
          />
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  header: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.two, paddingVertical: Spacing.three },
  headerLabel: { fontFamily: Fonts.sans, fontSize: 17, fontWeight: '700' },
  inputWrap: {
    flexDirection: 'row-reverse',
    alignItems: 'center',
    gap: Spacing.two,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.three,
  },
  input: { flex: 1, fontFamily: Fonts.sans, fontSize: 15 },
  hint: { fontFamily: Fonts.sans, fontSize: 12, textAlign: 'right', marginTop: Spacing.two },
  empty: { alignItems: 'center', paddingTop: Spacing.six },
  emptyText: { fontFamily: Fonts.sans, fontSize: 14 },
});
