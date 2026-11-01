import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Brand, Fonts, Radius, Spacing, ThemeColors } from '@/constants/theme';
import { fetchMarketSymbols } from '@/lib/market-symbols';
import { getSelectedListedCompany, setSelectedListedCompany } from '@/lib/listed-company-selection';

export type PickedCompany = { code: string; symbol: string; name?: string | null };

/** نماد یا کد TSETMC (فارسی/عربی/ارقام فارسی) را جست‌وجو می‌کند؛ فقط نتایج واقعی سرور. */
export function IranCompanyPicker({ colors, selected, onSelect }: { colors: ThemeColors; selected: PickedCompany | null; onSelect: (c: PickedCompany) => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PickedCompany[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [searchedFor, setSearchedFor] = useState('');

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      setLoading(true);
      fetchMarketSymbols({ q: text, limit: 8 })
        .then((items) => { if (!cancelled) { setResults(items.map((i) => ({ code: i.code, symbol: i.symbol, name: i.name }))); setSearchedFor(text); setSearched(true); } })
        .catch(() => { if (!cancelled) { setResults([]); setSearchedFor(text); setSearched(true); } })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 350);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query]);

  const pick = (c: PickedCompany) => {
    void setSelectedListedCompany({ code: c.code, symbol: c.symbol, name: c.name }).catch(() => {});
    setQuery(''); setResults([]); setSearched(false); setSearchedFor('');
    onSelect(c);
  };

  const activeSearch = query.trim().length >= 2 && searchedFor === query.trim();
  const visibleResults = activeSearch ? results : [];
  const visibleSearched = activeSearch && searched;
  const visibleLoading = query.trim().length >= 2 && loading;

  return <View style={[styles.box, { backgroundColor: colors.backgroundElement }]}>
    <Text style={[styles.label, { color: colors.textSecondary }]}>شرکت</Text>
    <Text style={[styles.current, { color: colors.text }]}>{selected ? `${selected.symbol}${selected.name ? ` · ${selected.name}` : ''}` : 'شرکتی انتخاب نشده'}</Text>
    {selected ? <Text style={[styles.meta, { color: colors.textSecondary }]}>کد TSETMC: {selected.code}</Text> : null}
    <TextInput value={query} onChangeText={setQuery} placeholder="نماد یا کد TSETMC (مثلاً پکرمان)" placeholderTextColor={colors.textSecondary}
      autoCapitalize="none" autoCorrect={false} style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected }]} />
    {visibleLoading ? <ActivityIndicator color={Brand.primary} style={{ marginTop: 8 }} /> : null}
    {visibleResults.map((c) => <Pressable key={c.code} onPress={() => pick(c)} style={[styles.result, { borderColor: colors.backgroundSelected }]}>
      <Text style={[styles.resultTitle, { color: colors.text }]}>{c.symbol}</Text><Text style={[styles.meta, { color: colors.textSecondary }]} numberOfLines={1}>{c.name} · {c.code}</Text>
    </Pressable>)}
    {visibleSearched && !visibleLoading && visibleResults.length === 0 ? <Text style={[styles.meta, { color: colors.textSecondary, marginTop: 8 }]}>موردی پیدا نشد.</Text> : null}
  </View>;
}

export function useInitialPickedCompany(set: (c: PickedCompany | null) => void) {
  useEffect(() => {
    void getSelectedListedCompany().then((c) => set(c ? { code: c.code, symbol: c.symbol, name: c.name } : null));
  }, [set]);
}

const styles = StyleSheet.create({
  box: { borderRadius: Radius.lg, padding: Spacing.three, marginBottom: Spacing.three, alignItems: 'flex-end' },
  label: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '800' },
  current: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '900', marginTop: 4, textAlign: 'right' },
  meta: { fontFamily: Fonts.sans, fontSize: 11, marginTop: 2, textAlign: 'right' },
  input: { alignSelf: 'stretch', borderWidth: 1, borderRadius: Radius.sm, paddingHorizontal: 10, paddingVertical: 8, marginTop: 10, fontSize: 13, textAlign: 'right' },
  result: { alignSelf: 'stretch', borderTopWidth: 1, paddingVertical: 8, marginTop: 6, alignItems: 'flex-end' },
  resultTitle: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900' },
});
