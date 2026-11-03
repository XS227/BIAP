import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { Brand, Colors, Fonts, Radius, Spacing } from '@/constants/theme';
import { fetchMarketSymbols, instrumentTypeFa } from '@/lib/market-symbols';
import type { MarketSymbolResult } from '@/lib/api';

export type PickedSymbol = { code: string; symbol: string; name: string };

/** Search box that returns the exact TSETMC InsCode; the main stock is listed before bonds/funds/rights. */
export function SymbolPicker({ onPick, current }: { onPick: (s: PickedSymbol) => void; current?: string }) {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [q, setQ] = useState('');
  const [items, setItems] = useState<MarketSymbolResult[]>([]);
  const [searched, setSearched] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (q.trim().length < 2) { setItems([]); setSearched(false); return; }
    timer.current = setTimeout(async () => { setItems((await fetchMarketSymbols({ q: q.trim(), limit: 40 })).slice(0, 8)); setSearched(true); }, 350);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [q]);
  return (
    <View style={styles.wrap}>
      <TextInput value={q} onChangeText={setQ} placeholder={current ? `تغییر نماد (فعلی: ${current})` : 'جست‌وجوی نماد، مثلاً تابان'} placeholderTextColor={colors.textSecondary}
        style={[styles.input, { color: colors.text, backgroundColor: colors.backgroundElement, fontFamily: Fonts.sans }]} textAlign="right" />
      {items.map((s) => (
        <Pressable key={s.code} onPress={() => { onPick({ code: s.code, symbol: s.symbol, name: s.name }); setQ(''); setItems([]); }}
          style={[styles.row, { backgroundColor: colors.backgroundElement }]}>
          <Text style={[styles.sym, { color: colors.text }]}>{s.symbol}</Text>
          <Text style={[styles.sub, { color: colors.textSecondary }]} numberOfLines={1}>{instrumentTypeFa(s as never)} • {s.name}</Text>
        </Pressable>
      ))}
      {searched && !items.length ? <Text style={[styles.sub, { color: colors.textSecondary, textAlign: 'right' }]}>نمادی با این نام پیدا نشد.</Text> : null}
    </View>
  );
}
const styles = StyleSheet.create({
  wrap: { gap: Spacing.two, marginTop: Spacing.three },
  input: { borderRadius: Radius.md, paddingHorizontal: Spacing.three, paddingVertical: Spacing.two, fontSize: 14 },
  row: { borderRadius: Radius.md, padding: Spacing.three, alignItems: 'flex-end' },
  sym: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '800' },
  sub: { fontFamily: Fonts.sans, fontSize: 11 },
});
