import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { BottomTabInset, Brand, Colors, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { SQL_ROW_LIMITS, cellText, csvFileName, formatValue } from '@/lib/iran-module-blocks';
import { SqlRequest, SqlResult, fetchModule, sqlExport, sqlQuery, sqlSchema } from '@/lib/iran-modules-api';

type Schema = Record<string, { name: string; type: string }[]>;
type Example = { title: string; sql: string; params: unknown[] };
const OPS: [string, string][] = [['=', '='], ['>', '>'], ['<', '<'], ['>=', '≥'], ['<=', '≤'], ['!=', '≠'], ['like', 'شامل']];
const DEFAULT_EXAMPLES: Example[] = [
  { title: 'پوشش داده به تفکیک سطح', sql: 'SELECT tier, COUNT(*) AS n FROM companies WHERE is_primary = 1 GROUP BY tier ORDER BY n DESC', params: [] },
  { title: 'پرسودترین شرکت‌ها', sql: 'SELECT symbol, sector, net_margin, roe FROM companies WHERE net_margin IS NOT NULL AND is_primary = 1 ORDER BY net_margin DESC', params: [] },
];

export default function SqlScreen() {
  const params = useLocalSearchParams<{ code?: string }>();
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [mode, setMode] = useState<'builder' | 'sql'>('builder');
  const [schema, setSchema] = useState<Schema | null>(null);
  const [examples, setExamples] = useState<Example[]>(DEFAULT_EXAMPLES);
  const [table, setTable] = useState('companies');
  const [cols, setCols] = useState<string[]>(['symbol', 'tier', 'net_margin', 'roe']);
  const [fCol, setFCol] = useState('');
  const [fOp, setFOp] = useState('>');
  const [fVal, setFVal] = useState('');
  const [orderCol, setOrderCol] = useState('');
  const [orderDir, setOrderDir] = useState<'asc' | 'desc'>('desc');
  const [sql, setSql] = useState(DEFAULT_EXAMPLES[0].sql);
  const [sqlParams, setSqlParams] = useState<unknown[]>([]);
  const [limit, setLimit] = useState(50);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SqlResult | null>(null);

  useEffect(() => {
    (async () => {
      const s = await sqlSchema();
      if (s.ok) setSchema(s.data.schema); else setError(s.message);
      if (typeof params.code === 'string' && params.code) {
        const m = await fetchModule(params.code, 'sql');
        if (m.ok && m.data.examples?.length) setExamples(m.data.examples);
      }
    })();
  }, [params.code]);

  const columns = useMemo(() => (schema?.[table] ?? []).map((c) => c.name), [schema, table]);
  const request = useCallback((offset: number): SqlRequest => {
    if (mode === 'sql') return { sql, params: sqlParams, limit, offset };
    const spec: Record<string, unknown> = { table, columns: cols.length ? cols : undefined };
    if (fCol && fVal.trim() !== '') {
      const num = Number(fVal);
      spec.where = [{ column: fCol, op: fOp, value: fOp !== 'like' && Number.isFinite(num) && fVal.trim() !== '' ? num : fOp === 'like' ? `%${fVal}%` : fVal }];
    }
    if (orderCol) spec.orderBy = [{ column: orderCol, dir: orderDir }];
    return { spec, limit, offset };
  }, [mode, sql, sqlParams, limit, table, cols, fCol, fOp, fVal, orderCol, orderDir]);

  const run = async (nextPage = 0) => {
    setBusy(true); setError(null);
    const res = await sqlQuery(request(nextPage * limit));
    setBusy(false);
    if (res.ok) { setResult(res.data); setPage(nextPage); } else { setResult(null); setError(res.message); }
  };
  const exportCsv = async () => {
    const res = await sqlExport(request(0));
    if (!res.ok) { setError(res.message); return; }
    try {
      const uri = `${FileSystem.cacheDirectory}${csvFileName()}`;
      await FileSystem.writeAsStringAsync(uri, '﻿' + res.data, { encoding: FileSystem.EncodingType.UTF8 });
      if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(uri, { mimeType: 'text/csv', dialogTitle: 'خروجی CSV' });
      else Alert.alert('خروجی ساخته شد', uri);
    } catch { setError('ذخیره‌ی فایل CSV ممکن نشد.'); }
  };
  const toggleCol = (c: string) => setCols((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  const Chip = ({ label, on, onPress }: { label: string; on: boolean; onPress: () => void }) => (
    <Pressable onPress={onPress} style={[styles.chip, { borderColor: colors.backgroundSelected }, on && { backgroundColor: Brand.primary, borderColor: Brand.primary }]}><Text style={[styles.chipText, { color: on ? '#fff' : colors.text }]}>{label}</Text></Pressable>
  );

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.six }]}>
        <View style={styles.maxWidth}>
          <View style={styles.header}>
            <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={{ color: colors.text }}>←</Text></Pressable>
            <View style={{ flex: 1 }}><Text style={[styles.title, { color: colors.text }]}>SQL / پرس‌وجوی داده</Text><Text style={[styles.sub, { color: colors.textSecondary }]}>فقط‌خواندنی • حداکثر ۱۰۰۰ ردیف • محدودیت زمانی ۳ ثانیه</Text></View>
          </View>

          <View style={styles.tabs}>
            <Chip label="سازنده‌ی پرس‌وجو" on={mode === 'builder'} onPress={() => setMode('builder')} />
            <Chip label="SQL" on={mode === 'sql'} onPress={() => setMode('sql')} />
          </View>

          {mode === 'builder' ? (
            <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.label, { color: colors.text }]}>جدول</Text>
              <View style={styles.wrap}>{Object.keys(schema ?? { companies: [] }).map((t) => <Chip key={t} label={t} on={table === t} onPress={() => { setTable(t); setCols([]); setFCol(''); setOrderCol(''); }} />)}</View>
              <Text style={[styles.label, { color: colors.text }]}>ستون‌ها</Text>
              <View style={styles.wrap}>{columns.map((c) => <Chip key={c} label={c} on={cols.includes(c)} onPress={() => toggleCol(c)} />)}</View>
              <Text style={[styles.label, { color: colors.text }]}>فیلتر</Text>
              <View style={styles.wrap}>{columns.map((c) => <Chip key={c} label={c} on={fCol === c} onPress={() => setFCol(fCol === c ? '' : c)} />)}</View>
              <View style={styles.wrap}>{OPS.map(([v, l]) => <Chip key={v} label={l} on={fOp === v} onPress={() => setFOp(v)} />)}</View>
              <TextInput value={fVal} onChangeText={setFVal} placeholder="مقدار" placeholderTextColor={colors.textSecondary} style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected }]} />
              <Text style={[styles.label, { color: colors.text }]}>مرتب‌سازی</Text>
              <View style={styles.wrap}>{columns.map((c) => <Chip key={c} label={c} on={orderCol === c} onPress={() => setOrderCol(orderCol === c ? '' : c)} />)}</View>
              <View style={styles.wrap}><Chip label="نزولی" on={orderDir === 'desc'} onPress={() => setOrderDir('desc')} /><Chip label="صعودی" on={orderDir === 'asc'} onPress={() => setOrderDir('asc')} /></View>
            </View>
          ) : (
            <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
              <TextInput value={sql} onChangeText={(t) => { setSql(t); setSqlParams([]); }} multiline autoCapitalize="none" autoCorrect={false} style={[styles.editor, { color: colors.text, borderColor: colors.backgroundSelected }]} />
              <Text style={[styles.label, { color: colors.text }]}>نمونه‌ها</Text>
              <View style={styles.wrap}>{examples.map((e) => <Chip key={e.title} label={e.title} on={false} onPress={() => { setSql(e.sql); setSqlParams(e.params); }} />)}</View>
              {schema ? <Text style={[styles.hint, { color: colors.textSecondary }]}>{Object.entries(schema).map(([t, c]) => `${t}(${c.map((x) => x.name).join(', ')})`).join('\n')}</Text> : null}
            </View>
          )}

          <View style={styles.wrap}>
            <Text style={[styles.label, { color: colors.text }]}>تعداد ردیف:</Text>
            {SQL_ROW_LIMITS.map((n) => <Chip key={n} label={formatValue(n)} on={limit === n} onPress={() => setLimit(n)} />)}
          </View>
          <View style={styles.actions}>
            <Pressable onPress={() => run(0)} disabled={busy} style={[styles.primary, { backgroundColor: Brand.primary }]}>{busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>اجرا</Text>}</Pressable>
            <Pressable onPress={exportCsv} style={[styles.secondary, { borderColor: Brand.primary }]}><Text style={{ color: Brand.primary, fontWeight: '700' }}>خروجی CSV</Text></Pressable>
          </View>

          {error ? <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: Brand.negative, borderWidth: 1 }]}><Text style={{ color: Brand.negative, textAlign: 'right' }}>{error}</Text></View> : null}
          {result ? (
            <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.hint, { color: colors.textSecondary }]}>{formatValue(result.rowCount)} ردیف • {formatValue(result.elapsedMs, { digits: 1 })} میلی‌ثانیه{result.truncated ? ' • نتیجه بیشتر است' : ''}</Text>
              <ScrollView horizontal>
                <View>
                  <View style={styles.tr}>{result.columns.map((c) => <Text key={c} style={[styles.th, { color: colors.textSecondary }]}>{c}</Text>)}</View>
                  {result.rows.map((r, i) => <View key={i} style={[styles.tr, { borderTopColor: colors.backgroundSelected }]}>{r.map((v, j) => <Text key={j} style={[styles.td, { color: colors.text }]}>{cellText(v)}</Text>)}</View>)}
                </View>
              </ScrollView>
              <View style={styles.actions}>
                <Pressable disabled={page === 0 || busy} onPress={() => run(page - 1)} style={[styles.secondary, { borderColor: colors.backgroundSelected, opacity: page === 0 ? 0.4 : 1 }]}><Text style={{ color: colors.text }}>قبلی</Text></Pressable>
                <Text style={{ color: colors.textSecondary }}>صفحه {formatValue(page + 1)}</Text>
                <Pressable disabled={!result.truncated || busy} onPress={() => run(page + 1)} style={[styles.secondary, { borderColor: colors.backgroundSelected, opacity: result.truncated ? 1 : 0.4 }]}><Text style={{ color: colors.text }}>بعدی</Text></Pressable>
              </View>
            </View>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 }, content: { paddingHorizontal: Spacing.three, paddingTop: Spacing.three }, maxWidth: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  header: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.two, marginBottom: Spacing.three }, back: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 20, fontWeight: '800', textAlign: 'right' }, sub: { fontSize: 12, textAlign: 'right' },
  tabs: { flexDirection: 'row-reverse', gap: 8, marginBottom: Spacing.two }, wrap: { flexDirection: 'row-reverse', flexWrap: 'wrap', gap: 6, marginBottom: 8, alignItems: 'center' },
  chip: { borderWidth: 1, borderRadius: 16, paddingHorizontal: 10, paddingVertical: 5 }, chipText: { fontSize: 12 },
  card: { borderRadius: Radius.lg, padding: Spacing.three, marginBottom: Spacing.two }, label: { fontSize: 13, fontWeight: '700', textAlign: 'right', marginBottom: 6, marginTop: 6 },
  input: { borderWidth: 1, borderRadius: 8, padding: 8, textAlign: 'right' }, editor: { borderWidth: 1, borderRadius: 8, padding: 10, minHeight: 110, textAlign: 'left', fontFamily: 'monospace', fontSize: 13 },
  hint: { fontSize: 11, textAlign: 'left', marginTop: 6, lineHeight: 17 }, actions: { flexDirection: 'row-reverse', gap: 10, alignItems: 'center', justifyContent: 'space-between', marginVertical: Spacing.two },
  primary: { flex: 1, borderRadius: 10, padding: 12, alignItems: 'center' }, primaryText: { color: '#fff', fontWeight: '800' }, secondary: { borderWidth: 1, borderRadius: 10, paddingVertical: 11, paddingHorizontal: 16, alignItems: 'center' },
  tr: { flexDirection: 'row', borderTopWidth: StyleSheet.hairlineWidth, paddingVertical: 6 }, th: { width: 110, fontSize: 11, fontWeight: '700', textAlign: 'left' }, td: { width: 110, fontSize: 12, textAlign: 'left' },
});
