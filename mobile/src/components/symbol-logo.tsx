import { useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import { Brand, Fonts } from '@/constants/theme';
import { displaySymbol, symbolLogoUrl } from '@/lib/symbol-brand';

export function SymbolLogo({ symbol, size = 42 }: { symbol: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  const display = displaySymbol(symbol);
  const uri = symbolLogoUrl(display);
  const fallback = display.slice(0, 2);
  if (uri && !failed) {
    return <Image source={{ uri }} onError={() => setFailed(true)} style={{ width: size, height: size, borderRadius: Math.round(size * 0.24), backgroundColor: '#fff' }} />;
  }
  return <View style={[styles.fallback, { width: size, height: size, borderRadius: Math.round(size * 0.24) }]}><Text style={[styles.fallbackText, { fontSize: Math.max(10, size * 0.27) }]}>{fallback}</Text></View>;
}

const styles = StyleSheet.create({
  fallback: { alignItems: 'center', justifyContent: 'center', backgroundColor: `${Brand.primary}22`, borderWidth: StyleSheet.hairlineWidth, borderColor: `${Brand.primary}66` },
  fallbackText: { color: '#d9d6ff', fontFamily: Fonts.sans, fontWeight: '900' },
});
