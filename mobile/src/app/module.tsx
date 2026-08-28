import { useEffect, useState } from 'react';
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { DEMO_MODULES } from '@/demo/demo-data';
import { getDemoMode, setDemoMode } from '@/lib/demo-mode';

export default function ModuleDetailScreen() {
  const params = useLocalSearchParams<{ key?: string }>();
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [demoMode, setDemoModeState] = useState(false);
  const key = typeof params.key === 'string' ? params.key : '';
  const module = DEMO_MODULES[key];

  useEffect(() => {
    getDemoMode().then(setDemoModeState);
  }, []);

  const toggleDemo = async () => {
    const next = !demoMode;
    await setDemoMode(next);
    setDemoModeState(next);
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.six }]}>
        <View style={styles.maxWidth}>
          <View style={styles.headerRow}>
            <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.backText, { color: colors.text }]}>←</Text>
            </Pressable>
            <View style={styles.headerText}>
              <Text style={[styles.title, { color: colors.text }]}>{module?.icon ?? '🧩'} {module?.title ?? 'ماژول BIAP'}</Text>
              <Text style={[styles.subtitle, { color: colors.textSecondary }]}>BIAP Mobile V2</Text>
            </View>
          </View>

          <View style={[styles.modeCard, { backgroundColor: colors.backgroundElement }]}>
            <View style={{ flex: 1, alignItems: 'flex-end' }}>
              <Text style={[styles.modeTitle, { color: colors.text }]}>Demo Mode</Text>
              <Text style={[styles.modeText, { color: colors.textSecondary }]}>داده نمونه فقط وقتی خودت Demo Mode را روشن کنی نمایش داده می‌شود.</Text>
            </View>
            <Pressable onPress={toggleDemo} style={[styles.toggle, { backgroundColor: demoMode ? '#7048e8' : colors.backgroundSelected }]}>
              <Text style={styles.toggleText}>{demoMode ? 'روشن' : 'خاموش'}</Text>
            </Pressable>
          </View>

          {!module ? (
            <View style={[styles.empty, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.emptyTitle, { color: colors.text }]}>ماژول پیدا نشد</Text>
            </View>
          ) : demoMode ? (
            <>
              <View style={styles.demoBadge}><Text style={styles.demoBadgeText}>DEMO • داده نمونه</Text></View>
              <View style={[styles.hero, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.heroText, { color: colors.textSecondary }]}>{module.summary}</Text>
              </View>

              <View style={styles.metricsRow}>
                {module.metrics.map((metric) => {
                  const tone = metric.tone === 'positive' ? Brand.positive : metric.tone === 'negative' ? Brand.negative : colors.text;
                  return (
                    <View key={metric.label} style={[styles.metric, { backgroundColor: colors.backgroundElement }]}>
                      <Text style={[styles.metricValue, { color: tone }]}>{metric.value}</Text>
                      {metric.delta ? <Text style={[styles.metricDelta, { color: tone }]}>{metric.delta}</Text> : null}
                      <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>{metric.label}</Text>
                    </View>
                  );
                })}
              </View>

              <View style={[styles.insightCard, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.insightTitle, { color: colors.text }]}>خلاصه Demo</Text>
                {module.bullets.map((bullet) => (
                  <View key={bullet} style={styles.bulletRow}>
                    <Text style={[styles.bulletText, { color: colors.textSecondary }]}>{bullet}</Text>
                    <View style={styles.bulletDot} />
                  </View>
                ))}
              </View>

              <View style={[styles.disclaimer, { borderColor: '#7c5cff66' }]}>
                <Text style={styles.disclaimerText}>این مقادیر ساختگی و فقط برای نمایش Demo هستند؛ در حساب واقعی هرگز جایگزین داده ناموجود نمی‌شوند.</Text>
              </View>
            </>
          ) : (
            <View style={[styles.empty, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.emptyTitle, { color: colors.text }]}>داده واقعی این ماژول هنوز به API موبایل متصل نیست</Text>
              <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>برای کاربر واقعی عدد ساختگی نمایش نمی‌دهیم. برای دیدن تجربه کامل محصول، Demo Mode را بالا روشن کن.</Text>
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingTop: Spacing.three },
  maxWidth: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  headerRow: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.three, marginBottom: Spacing.three },
  headerText: { flex: 1, alignItems: 'flex-end' },
  title: { fontFamily: Fonts.sans, fontSize: 21, fontWeight: '800', textAlign: 'right' },
  subtitle: { fontFamily: Fonts.sans, fontSize: 11, marginTop: 2 },
  back: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center' },
  backText: { fontSize: 19 },
  modeCard: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.three, borderRadius: Radius.md, padding: Spacing.three, marginBottom: Spacing.three },
  modeTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '800' },
  modeText: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 17, textAlign: 'right', marginTop: 3 },
  toggle: { minWidth: 62, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 18, alignItems: 'center' },
  toggleText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 11, fontWeight: '800' },
  demoBadge: { alignSelf: 'flex-end', backgroundColor: '#7048e8', borderRadius: 14, paddingHorizontal: 10, paddingVertical: 5, marginBottom: Spacing.two },
  demoBadgeText: { color: '#fff', fontFamily: Fonts.mono, fontSize: 10, fontWeight: '800' },
  hero: { borderRadius: Radius.lg, padding: Spacing.four, marginBottom: Spacing.three },
  heroText: { fontFamily: Fonts.sans, fontSize: 13, lineHeight: 23, textAlign: 'right' },
  metricsRow: { flexDirection: 'row-reverse', gap: Spacing.two, marginBottom: Spacing.three },
  metric: { flex: 1, borderRadius: Radius.md, padding: Spacing.three, alignItems: 'center', minHeight: 108, justifyContent: 'center' },
  metricValue: { fontFamily: Fonts.mono, fontSize: 18, fontWeight: '800' },
  metricDelta: { fontFamily: Fonts.mono, fontSize: 10, marginTop: 2 },
  metricLabel: { fontFamily: Fonts.sans, fontSize: 10, textAlign: 'center', marginTop: 5 },
  insightCard: { borderRadius: Radius.lg, padding: Spacing.four, marginBottom: Spacing.three },
  insightTitle: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '800', textAlign: 'right', marginBottom: Spacing.three },
  bulletRow: { flexDirection: 'row-reverse', alignItems: 'center', gap: 8, marginBottom: 9 },
  bulletDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: Brand.primary },
  bulletText: { flex: 1, fontFamily: Fonts.sans, fontSize: 12, lineHeight: 20, textAlign: 'right' },
  disclaimer: { borderWidth: 1, borderRadius: Radius.md, padding: Spacing.three, backgroundColor: '#7048e811' },
  disclaimerText: { color: '#b6a6ff', fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 18, textAlign: 'right' },
  empty: { borderRadius: Radius.lg, padding: Spacing.four, alignItems: 'center', marginTop: Spacing.four },
  emptyTitle: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '800', textAlign: 'center' },
  emptyBody: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 21, textAlign: 'center', marginTop: Spacing.two },
});
