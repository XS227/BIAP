import { useMemo, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import { Fonts } from '@/constants/theme';
import { displaySymbol, SYMBOL_BRANDS } from '@/lib/symbol-brand';

// Most TSE/IFB symbols have no verified official domain (SYMBOL_BRANDS only
// lists a small, manually confirmed set — see its own comment: we never guess
// a company's domain, since a wrong favicon is worse than no logo). For every
// other symbol this renders a deterministic, distinctly colored initials tile
// instead of one flat generic color, so the market/portfolio lists still read
// as a row of distinguishable "logos" rather than identical placeholders.
function fallbackHue(seed: string): number {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  return hash % 360;
}

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
  const hue = useMemo(() => fallbackHue(display), [display]);

  if (sources[sourceIndex]) {
    return <Image
      key={`${display}-${sourceIndex}`}
      source={{ uri: sources[sourceIndex] }}
      onError={() => setSourceIndex((i) => i + 1)}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.24), backgroundColor: '#fff' }}
      resizeMode="contain"
    />;
  }
  return <View style={[styles.fallback, { width: size, height: size, borderRadius: Math.round(size * 0.24), backgroundColor: `hsl(${hue},58%,42%)`, borderColor: `hsl(${hue},58%,62%)` }]}><Text style={[styles.fallbackText, { fontSize: Math.max(10, size * 0.27) }]}>{fallback}</Text></View>;
}

const styles = StyleSheet.create({
  fallback: { alignItems: 'center', justifyContent: 'center', borderWidth: StyleSheet.hairlineWidth },
  fallbackText: { color: '#fff', fontFamily: Fonts.sans, fontWeight: '900' },
});
