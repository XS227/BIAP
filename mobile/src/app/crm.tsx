import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { BottomTabInset, Brand, Colors, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { formatValue } from '@/lib/iran-module-blocks';
import { Activity, CRM_STAGES, Contact, KpiRow, Lead, Pipeline, crmActivities, crmAddActivity, crmAddContact, crmAddLead, crmContacts, crmDeleteLead, crmLeads, crmMoveLead, crmPipeline, kpiAdd, kpiDelete, kpiList } from '@/lib/iran-modules-api';

const STAGE_FA: Record<string, string> = { lead: 'سرنخ', qualified: 'واجد شرایط', proposal: 'پیشنهاد', negotiation: 'مذاکره', won: 'برنده', lost: 'از دست رفته' };
const ACT_FA: Record<string, string> = { call: 'تماس', meeting: 'جلسه', email: 'ایمیل', note: 'یادداشت', task: 'وظیفه' };
const numOrNull = (t: string) => { const n = Number(t.replace(/,/g, '')); return t.trim() !== '' && Number.isFinite(n) ? n : null; };

export default function CrmScreen() {
  const params = useLocalSearchParams<{ tab?: string }>();
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [tab, setTab] = useState<'pipeline' | 'contacts' | 'kpi'>(params.tab === 'kpi' ? 'kpi' : 'pipeline');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [kpis, setKpis] = useState<KpiRow[]>([]);
  const [acts, setActs] = useState<Activity[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [leadTitle, setLeadTitle] = useState(''); const [leadValue, setLeadValue] = useState(''); const [leadStage, setLeadStage] = useState('lead');
  const [cName, setCName] = useState(''); const [cCompany, setCCompany] = useState(''); const [cEmail, setCEmail] = useState(''); const [cPhone, setCPhone] = useState('');
  const [actText, setActText] = useState(''); const [actType, setActType] = useState('note');
  const [kName, setKName] = useState(''); const [kOwner, setKOwner] = useState(''); const [kTarget, setKTarget] = useState(''); const [kCurrent, setKCurrent] = useState(''); const [kCadence, setKCadence] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    const [p, l, c, k] = await Promise.all([crmPipeline(), crmLeads(), crmContacts(), kpiList()]);
    if (!p.ok) setError(p.message); else { setError(null); setPipeline(p.data); }
    if (l.ok) setLeads(l.data.items);
    if (c.ok) setContacts(c.data.items);
    if (k.ok) setKpis(k.data.items);
    setLoading(false);
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  const loadActs = async (id: number) => { setSelected(id); const r = await crmActivities(id); if (r.ok) setActs(r.data.items); };
  const fail = (m: string) => Alert.alert('خطا', m);

  const addLead = async () => {
    if (!leadTitle.trim()) return fail('عنوان فرصت لازم است.');
    const r = await crmAddLead({ title: leadTitle.trim(), stage: leadStage, value: numOrNull(leadValue) });
    if (!r.ok) return fail(r.message);
    setLeadTitle(''); setLeadValue(''); load();
  };
  const addContact = async () => {
    if (!cName.trim()) return fail('نام مخاطب لازم است.');
    const r = await crmAddContact({ name: cName.trim(), company: cCompany || null, email: cEmail || null, phone: cPhone || null });
    if (!r.ok) return fail(r.message);
    setCName(''); setCCompany(''); setCEmail(''); setCPhone(''); load();
  };
  const addAct = async () => {
    if (selected === null || !actText.trim()) return fail('یک فرصت را انتخاب و شرح فعالیت را بنویسید.');
    const r = await crmAddActivity({ type: actType, summary: actText.trim(), leadId: selected });
    if (!r.ok) return fail(r.message);
    setActText(''); loadActs(selected);
  };
  const addKpi = async () => {
    if (!kName.trim()) return fail('نام شاخص لازم است.');
    const r = await kpiAdd({ name: kName.trim(), owner: kOwner || undefined, target: numOrNull(kTarget), currentValue: numOrNull(kCurrent), cadence: kCadence || undefined });
    if (!r.ok) return fail(r.message);
    setKName(''); setKOwner(''); setKTarget(''); setKCurrent(''); setKCadence(''); load();
  };
  const Input = (p: { v: string; set: (t: string) => void; ph: string; num?: boolean }) => (
    <TextInput value={p.v} onChangeText={p.set} placeholder={p.ph} placeholderTextColor={colors.textSecondary} keyboardType={p.num ? 'numeric' : 'default'} style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected }]} />
  );
  const Chip = ({ label, on, onPress }: { label: string; on: boolean; onPress: () => void }) => (
    <Pressable onPress={onPress} style={[styles.chip, { borderColor: colors.backgroundSelected }, on && { backgroundColor: Brand.primary, borderColor: Brand.primary }]}><Text style={{ color: on ? '#fff' : colors.text, fontSize: 12 }}>{label}</Text></Pressable>
  );
  const Btn = ({ label, onPress }: { label: string; onPress: () => void }) => <Pressable onPress={onPress} style={[styles.btn, { backgroundColor: Brand.primary }]}><Text style={styles.btnText}>{label}</Text></Pressable>;

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.six }]}>
        <View style={styles.maxWidth}>
          <View style={styles.header}>
            <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={{ color: colors.text }}>←</Text></Pressable>
            <View style={{ flex: 1 }}><Text style={[styles.title, { color: colors.text }]}>CRM خصوصی + شاخص‌ها</Text><Text style={[styles.sub, { color: colors.textSecondary }]}>فقط داده‌ی واردشده‌ی خود شما؛ برای شرکت بورسی هیچ مشتری یا فروشی ساخته نمی‌شود.</Text></View>
          </View>
          <View style={styles.row}>
            <Chip label="خط لوله" on={tab === 'pipeline'} onPress={() => setTab('pipeline')} />
            <Chip label="مخاطبین" on={tab === 'contacts'} onPress={() => setTab('contacts')} />
            <Chip label="شاخص‌های سازمانی" on={tab === 'kpi'} onPress={() => setTab('kpi')} />
          </View>
          {loading ? <ActivityIndicator color={Brand.primary} /> : null}
          {error ? <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={{ color: Brand.negative, textAlign: 'right' }}>{error}</Text></View> : null}

          {tab === 'pipeline' && pipeline ? <>
            <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.h, { color: colors.text }]}>خلاصه‌ی خط لوله</Text>
              <Text style={[styles.p, { color: colors.textSecondary }]}>فرصت‌ها {formatValue(pipeline.leads)} • مخاطبین {formatValue(pipeline.contacts)} • فعالیت‌ها {formatValue(pipeline.activities)}</Text>
              <Text style={[styles.p, { color: colors.textSecondary }]}>نرخ برد: {pipeline.winRate === null ? 'هنوز فرصت بسته‌شده‌ای نیست' : `${formatValue(pipeline.winRate * 100, { digits: 0 })}٪`} • ارزش وزنی باز: {formatValue(pipeline.weightedValue)}</Text>
              {pipeline.stages.map((s) => <Text key={s.stage} style={[styles.p, { color: colors.text }]}>{STAGE_FA[s.stage]}: {formatValue(s.count)} فرصت • {formatValue(s.value)} • احتمال {formatValue(s.probability * 100, { digits: 0 })}٪</Text>)}
              <Text style={[styles.hint, { color: colors.textSecondary }]}>{pipeline.probabilityNote}</Text>
              {pipeline.leads === 0 ? <Text style={[styles.hint, { color: Brand.warning }]}>هنوز داده‌ای وارد نشده است. اولین فرصت فروش را از فرم زیر ثبت کنید.</Text> : null}
            </View>
            <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.h, { color: colors.text }]}>فرصت جدید</Text>
              <Input v={leadTitle} set={setLeadTitle} ph="عنوان" /><Input v={leadValue} set={setLeadValue} ph="ارزش (اختیاری)" num />
              <View style={styles.row}>{CRM_STAGES.map((s) => <Chip key={s} label={STAGE_FA[s]} on={leadStage === s} onPress={() => setLeadStage(s)} />)}</View>
              <Btn label="ثبت فرصت" onPress={addLead} />
            </View>
            {leads.map((l) => (
              <View key={l.id} style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: selected === l.id ? Brand.primary : 'transparent', borderWidth: 1 }]}>
                <Pressable onPress={() => loadActs(l.id)}><Text style={[styles.h, { color: colors.text }]}>{l.title}</Text>
                  <Text style={[styles.p, { color: colors.textSecondary }]}>{STAGE_FA[l.stage]} • {l.value === null || l.value === undefined ? 'ارزش ثبت نشده' : formatValue(l.value)}</Text></Pressable>
                <View style={styles.row}>{CRM_STAGES.map((s) => <Chip key={s} label={STAGE_FA[s]} on={l.stage === s} onPress={async () => { const r = await crmMoveLead(l.id, { stage: s }); if (!r.ok) fail(r.message); else load(); }} />)}</View>
                <Pressable onPress={() => Alert.alert('حذف', 'این فرصت حذف شود؟', [{ text: 'خیر' }, { text: 'حذف', style: 'destructive', onPress: async () => { await crmDeleteLead(l.id); setSelected(null); load(); } }])}><Text style={{ color: Brand.negative, fontSize: 12, textAlign: 'right' }}>حذف</Text></Pressable>
                {selected === l.id ? <View style={{ marginTop: 8 }}>
                  {acts.map((a) => <Text key={a.id} style={[styles.p, { color: colors.text }]}>• {ACT_FA[a.type] ?? a.type}: {a.summary}</Text>)}
                  {acts.length === 0 ? <Text style={[styles.hint, { color: colors.textSecondary }]}>فعالیتی ثبت نشده است.</Text> : null}
                  <View style={styles.row}>{Object.keys(ACT_FA).map((t) => <Chip key={t} label={ACT_FA[t]} on={actType === t} onPress={() => setActType(t)} />)}</View>
                  <Input v={actText} set={setActText} ph="شرح فعالیت" /><Btn label="ثبت فعالیت" onPress={addAct} />
                </View> : null}
              </View>
            ))}
          </> : null}

          {tab === 'contacts' ? <>
            <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.h, { color: colors.text }]}>مخاطب جدید</Text>
              <Input v={cName} set={setCName} ph="نام" /><Input v={cCompany} set={setCCompany} ph="شرکت" /><Input v={cEmail} set={setCEmail} ph="ایمیل" /><Input v={cPhone} set={setCPhone} ph="تلفن" />
              <Btn label="ثبت مخاطب" onPress={addContact} />
            </View>
            {contacts.length === 0 && !loading ? <Text style={[styles.hint, { color: Brand.warning }]}>مخاطبی ثبت نشده است.</Text> : null}
            {contacts.map((c) => <View key={c.id} style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.h, { color: colors.text }]}>{c.name}</Text><Text style={[styles.p, { color: colors.textSecondary }]}>{[c.company, c.email, c.phone].filter(Boolean).join(' • ') || 'بدون جزئیات'}</Text></View>)}
          </> : null}

          {tab === 'kpi' ? <>
            <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.h, { color: colors.text }]}>شاخص جدید (ماژول KPI Governance)</Text>
              <Input v={kName} set={setKName} ph="نام شاخص" /><Input v={kOwner} set={setKOwner} ph="مالک" /><Input v={kTarget} set={setKTarget} ph="هدف" num /><Input v={kCurrent} set={setKCurrent} ph="مقدار فعلی" num /><Input v={kCadence} set={setKCadence} ph="چرخه (ماهانه/فصلی)" />
              <Btn label="ثبت شاخص" onPress={addKpi} />
            </View>
            {kpis.length === 0 && !loading ? <Text style={[styles.hint, { color: Brand.warning }]}>شاخصی ثبت نشده است.</Text> : null}
            {kpis.map((k) => (
              <View key={k.id} style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.h, { color: colors.text }]}>{k.name}</Text>
                <Text style={[styles.p, { color: colors.textSecondary }]}>مالک: {k.owner || '—'} • هدف: {formatValue(k.target)} • فعلی: {formatValue(k.current_value)} • تحقق: {k.target && k.current_value !== null && k.current_value !== undefined ? `${formatValue((k.current_value / k.target) * 100, { digits: 0 })}٪` : '—'}</Text>
                <Pressable onPress={async () => { await kpiDelete(k.id); load(); }}><Text style={{ color: Brand.negative, fontSize: 12, textAlign: 'right' }}>حذف</Text></Pressable>
              </View>
            ))}
          </> : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 }, content: { paddingHorizontal: Spacing.three, paddingTop: Spacing.three }, maxWidth: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  header: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.two, marginBottom: Spacing.three }, back: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 20, fontWeight: '800', textAlign: 'right' }, sub: { fontSize: 12, textAlign: 'right', lineHeight: 18 },
  row: { flexDirection: 'row-reverse', flexWrap: 'wrap', gap: 6, marginVertical: 6 }, chip: { borderWidth: 1, borderRadius: 16, paddingHorizontal: 10, paddingVertical: 5 },
  card: { borderRadius: Radius.lg, padding: Spacing.three, marginBottom: Spacing.two }, h: { fontSize: 15, fontWeight: '700', textAlign: 'right', marginBottom: 4 }, p: { fontSize: 12, textAlign: 'right', lineHeight: 20 },
  hint: { fontSize: 11, textAlign: 'right', marginTop: 6, lineHeight: 17 }, input: { borderWidth: 1, borderRadius: 8, padding: 8, textAlign: 'right', marginTop: 6 },
  btn: { borderRadius: 10, padding: 11, alignItems: 'center', marginTop: 8 }, btnText: { color: '#fff', fontWeight: '800' },
});
