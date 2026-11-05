import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Brand, Radius, Spacing, ThemeColors } from '@/constants/theme';
import { Block, KpiItem, cellText, formatKpi, formatValue, groupKpis, markerBin, scaleBars, scaleLine } from '@/lib/iran-module-blocks';

type Props = { blocks: Block[]; colors: ThemeColors };
const CHART_H = 110;

function Card({ colors, title, children }: { colors: ThemeColors; title?: string; children: React.ReactNode }) {
  return (
    <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
      {title ? <Text style={[styles.cardTitle, { color: colors.text }]}>{title}</Text> : null}
      {children}
    </View>
  );
}

function KpiBlock({ items, colors }: { items: KpiItem[]; colors: ThemeColors }) {
  return (
    <>
      {groupKpis(items).map(({ group, items: rows }) => (
        <Card key={group} colors={colors} title={group}>
          {rows.map((k) => (
            <View key={k.key} style={styles.kpiRow}>
              <View style={styles.kpiHead}>
                <Text style={[styles.kpiValue, { color: k.value === null ? colors.textSecondary : colors.text }]}>{formatKpi(k)}</Text>
                <Text style={[styles.kpiLabel, { color: colors.text }]}>{k.label}</Text>
              </View>
              <Text style={[styles.kpiMeta, { color: colors.textSecondary }]}>
                {k.value === null ? `ورودی ناموجود: ${(k.missing.length ? k.missing : k.inputs).join('، ')}` : `فرمول: ${k.formula}`}
              </Text>
              <Text style={[styles.kpiMeta, { color: colors.textSecondary }]}>منبع: {k.source}{k.period ? ` • ${k.period}` : ''}</Text>
            </View>
          ))}
        </Card>
      ))}
    </>
  );
}

function Histogram({ block, colors }: { block: Extract<Block, { type: 'histogram' }>; colors: ThemeColors }) {
  const heights = scaleBars(block.bins.map((b) => b.count), CHART_H);
  const mark = markerBin(block.bins, block.marker);
  return (
    <Card colors={colors} title={block.title}>
      <View style={styles.chartRow}>
        {block.bins.map((b, i) => (
          <View key={i} style={styles.colWrap}>
            <View style={[styles.col, { height: heights[i], backgroundColor: i === mark ? Brand.warning : Brand.primary }]} />
          </View>
        ))}
      </View>
      <View style={styles.axis}>
        <Text style={[styles.axisText, { color: colors.textSecondary }]}>{formatValue(block.bins[0]?.from)}</Text>
        <Text style={[styles.axisText, { color: colors.textSecondary }]}>{formatValue(block.bins[block.bins.length - 1]?.to)}</Text>
      </View>
      <Text style={[styles.note, { color: colors.textSecondary }]}>
        {block.marker !== null && block.marker !== undefined ? `مقدار این شرکت: ${formatValue(block.marker)} (ستون نارنجی). ` : ''}
        n={formatValue(block.n)}{block.clipped ? ` • ${formatValue(block.clipped)} مقدار پرت خارج از نمودار` : ''}
      </Text>
      {block.note ? <Text style={[styles.note, { color: colors.textSecondary }]}>{block.note}</Text> : null}
    </Card>
  );
}

function Bars({ block, colors }: { block: Extract<Block, { type: 'bars' }>; colors: ThemeColors }) {
  const widths = scaleBars(block.items.map((i) => i.value), 160);
  return (
    <Card colors={colors} title={block.title}>
      {block.items.map((it, i) => (
        <View key={i} style={styles.hbarRow}>
          <Text style={[styles.hbarValue, { color: colors.text }]}>{formatValue(it.value)}</Text>
          <View style={styles.hbarTrack}><View style={{ width: widths[i], height: 10, borderRadius: 5, backgroundColor: it.value < 0 ? Brand.negative : Brand.primary }} /></View>
          <Text style={[styles.hbarLabel, { color: colors.textSecondary }]} numberOfLines={1}>{it.label}</Text>
        </View>
      ))}
    </Card>
  );
}

function Line({ block, colors }: { block: Extract<Block, { type: 'line' }>; colors: ThemeColors }) {
  const ys = [...block.points.map((p) => p.y), ...(block.forecast ?? []).map((p) => p.y)];
  const W = 280;
  const pts = scaleLine(ys, W, CHART_H);
  const nHist = block.points.length;
  return (
    <Card colors={colors} title={block.title}>
      <View style={{ width: W, height: CHART_H, alignSelf: 'center' }}>
        {pts.map((p, i) => (
          <View key={i} style={{ position: 'absolute', left: p.x - 2, top: p.y - 2, width: 4, height: 4, borderRadius: 2, backgroundColor: i < nHist ? Brand.primary : Brand.warning }} />
        ))}
      </View>
      <Text style={[styles.note, { color: colors.textSecondary }]}>
        {nHist} مشاهده{(block.forecast?.length ?? 0) > 0 ? ` • ${block.forecast!.length} گام پیش‌بینی (نارنجی)` : ''} • از {block.points[0]?.x ?? '—'} تا {block.points[nHist - 1]?.x ?? '—'}
      </Text>
    </Card>
  );
}

function Table({ block, colors }: { block: Extract<Block, { type: 'table' }>; colors: ThemeColors }) {
  if (!block.rows.length) return <Card colors={colors} title={block.title}><Text style={[styles.note, { color: colors.textSecondary }]}>موردی برای نمایش نیست.</Text></Card>;
  return (
    <Card colors={colors} title={block.title}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View>
          <View style={styles.tr}>{block.columns.map((c) => <Text key={c} style={[styles.th, { color: colors.textSecondary }]}>{c}</Text>)}</View>
          {block.rows.map((r, i) => (
            <View key={i} style={[styles.tr, { borderTopColor: colors.backgroundSelected }]}>
              {block.columns.map((c) => <Text key={c} style={[styles.td, { color: colors.text }]}>{cellText(r[c])}</Text>)}
            </View>
          ))}
        </View>
      </ScrollView>
    </Card>
  );
}

function Swot({ block, colors }: { block: Extract<Block, { type: 'swot' }>; colors: ThemeColors }) {
  const sections: [string, string[], string][] = [['نقاط قوت', block.strengths, Brand.positive], ['نقاط ضعف', block.weaknesses, Brand.negative], ['فرصت‌ها', block.opportunities, Brand.primary], ['تهدیدها', block.threats, Brand.warning]];
  return (
    <>
      {sections.map(([title, items, color]) => (
        <Card key={title} colors={colors} title={title}>
          {items.length ? items.map((t, i) => <Text key={i} style={[styles.bullet, { color: colors.text, borderRightColor: color }]}>{t}</Text>)
            : <Text style={[styles.note, { color: colors.textSecondary }]}>شاهد عددی کافی برای این بخش وجود ندارد.</Text>}
        </Card>
      ))}
    </>
  );
}

function BlockView({ block, colors }: { block: Block; colors: ThemeColors }) {
  switch (block.type) {
    case 'metrics':
      return (
        <View style={styles.metricsRow}>
          {block.items.map((m, i) => (
            <View key={i} style={[styles.metric, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.metricValue, { color: colors.text }]}>{formatValue(m.value, { unit: m.unit })}</Text>
              <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>{m.label}</Text>
            </View>
          ))}
        </View>
      );
    case 'kpi_table': return <KpiBlock items={block.items} colors={colors} />;
    case 'table': return <Table block={block} colors={colors} />;
    case 'histogram': return <Histogram block={block} colors={colors} />;
    case 'bars': return <Bars block={block} colors={colors} />;
    case 'line': return <Line block={block} colors={colors} />;
    case 'swot': return <Swot block={block} colors={colors} />;
    case 'bullets': return <Card colors={colors} title={block.title}>{block.items.map((t, i) => <Text key={i} style={[styles.bullet, { color: colors.text, borderRightColor: Brand.primary }]}>{t}</Text>)}</Card>;
    case 'notice':
      return (
        <Card colors={colors}>
          <Text style={[styles.note, { color: colors.text }]}>{block.text}</Text>
          {block.missing?.length ? <Text style={[styles.note, { color: Brand.warning }]}>لازم است: {block.missing.join('، ')}</Text> : null}
        </Card>
      );
    default: return null;
  }
}

export function ModuleBlocks({ blocks, colors }: Props) {
  return <>{blocks.map((b, i) => <BlockView key={i} block={b} colors={colors} />)}</>;
}

const styles = StyleSheet.create({
  card: { borderRadius: Radius.lg, padding: Spacing.three, marginBottom: Spacing.two },
  cardTitle: { fontSize: 15, fontWeight: '700', textAlign: 'right', marginBottom: Spacing.two },
  note: { fontSize: 12, textAlign: 'right', marginTop: 6, lineHeight: 19 },
  bullet: { fontSize: 13, textAlign: 'right', lineHeight: 21, borderRightWidth: 3, paddingRight: 8, marginBottom: 6 },
  metricsRow: { flexDirection: 'row-reverse', flexWrap: 'wrap', gap: Spacing.two, marginBottom: Spacing.two },
  metric: { flexGrow: 1, minWidth: 96, borderRadius: Radius.lg, padding: Spacing.three, alignItems: 'center' },
  metricValue: { fontSize: 18, fontWeight: '800' },
  metricLabel: { fontSize: 11, marginTop: 4, textAlign: 'center' },
  kpiRow: { marginBottom: Spacing.two },
  kpiHead: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'baseline' },
  kpiLabel: { fontSize: 14, fontWeight: '600', flexShrink: 1, textAlign: 'right' },
  kpiValue: { fontSize: 16, fontWeight: '800' },
  kpiMeta: { fontSize: 11, textAlign: 'right', lineHeight: 17 },
  chartRow: { flexDirection: 'row', alignItems: 'flex-end', height: CHART_H, gap: 3 },
  colWrap: { flex: 1, justifyContent: 'flex-end', height: CHART_H },
  col: { borderTopLeftRadius: 3, borderTopRightRadius: 3 },
  axis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 },
  axisText: { fontSize: 10 },
  hbarRow: { flexDirection: 'row-reverse', alignItems: 'center', gap: 8, marginBottom: 6 },
  hbarLabel: { width: 70, fontSize: 11, textAlign: 'right' },
  hbarTrack: { flex: 1, alignItems: 'flex-end' },
  hbarValue: { width: 70, fontSize: 11, textAlign: 'left' },
  tr: { flexDirection: 'row-reverse', borderTopWidth: StyleSheet.hairlineWidth, paddingVertical: 6 },
  th: { width: 96, fontSize: 11, fontWeight: '700', textAlign: 'right' },
  td: { width: 96, fontSize: 12, textAlign: 'right' },
});
