import { useMemo, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import { Brand, Fonts } from '@/constants/theme';
import { displaySymbol, SYMBOL_BRANDS } from '@/lib/symbol-brand';

export function SymbolLogo({ symbol, size = 42 }: { symbol: string; size?: number }) {
  const display = displaySymbol(symbol);
  const brand = SYMBOL_BRANDS[display];
  const sources = useMemo(() => brand ? [
    `https://www.google.com/s2/favicons?domain_url=https://${brand.domain}&sz=128`,
    `https://${brand.domain}/favicon.ico`,
    `https://icons.duckduckgo.com/ip3/${brand.domain}.ico`,
  ] : [], [brand?.domain]);
  const [sourceIndex, setSourceIndex] = useState(0);
  const fallback = display.slice(0, 2);

  if (sources[sourceIndex]) {
    return <Image
      key={`${display}-${sourceIndex}`}
      source={{ uri: sources[sourceIndex] }}
      onError={() => setSourceIndex((i) => i + 1)}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.24), backgroundColor: '#fff' }}
      resizeMode="contain"
    />;
  }
  return <View style={[styles.fallback, { width: size, height: size, borderRadius: Math.round(size * 0.24) }]}><Text style={[styles.fallbackText, { fontSize: Math.max(10, size * 0.27) }]}>{fallback}</Text></View>;
}

const styles = StyleSheet.create({
  fallback: { alignItems: 'center', justifyContent: 'center', backgroundColor: `${Brand.primary}22`, borderWidth: StyleSheet.hairlineWidth, borderColor: `${Brand.primary}66` },
  fallbackText: { color: '#d9d6ff', fontFamily: Fonts.sans, fontWeight: '900' },
});
