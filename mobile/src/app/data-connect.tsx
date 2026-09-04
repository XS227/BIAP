import { useEffect, useMemo, useState } from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, Pressable, useColorScheme } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { clearBusinessDataset, getBusinessDataset, importExcelBusinessDataset, parseBusinessData, saveBusinessDataset } from '@/lib/business-data';
import { requirementFor, sourceLabel } from '@/lib/module-data-requirements';
import { fetchListedCompanyStatus, getSelectedListedCompany, ListedCompanyStatus, ListedCompanySummary, searchListedCompanies, setSelectedListedCompany } from '@/lib/listed-company-selection';

const SOURCES = [
  { key: 'sql', icon: '🗄️', title: 'SQL / Database', body: 'کانکتور Read-only سمت سرور؛ رمز دیتابیس داخل موبایل ذخیره نمی‌شود.', state: 'نیازمند مشخصات دیتابیس' },
  { key: 'crm', icon: '👥', title: 'CRM / ERP', body: 'API رسمی CRM/ERP برای Pipeline، Journey، Pricing و KPI.', state: 'نیازمند API سرویس' },
  { key: 'api', icon: '🔌', title: 'Custom API', body: 'API اختصاصی شرکت با credential سمت سرور.', state: 'نیازمند endpoint و مجوز' },
] as const;

export default function DataConnectScreen() {
  const params = useLocalSearchParams<{ key?: string; companyMode?: string; code?: string }>();
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const moduleKey = typeof params.key === 'string' ? params.key : '';
  const companyMode = params.companyMode === 'listed' ? 'listed' : params.companyMode === 'hybrid' ? 'hybrid' : 'private';
  const code = typeof params.code === 'string' ? params.code : '';
  const requirement = useMemo(() => requirementFor(moduleKey), [moduleKey]);
  const [raw, setRaw] = useState('');
  const [name, setName] = useState(code ? `${code} • company data` : 'Company data');
  const [status, setStatus] = useState('');
  const [datasetInfo, setDatasetInfo] = useState('');
  const [importingFile, setImportingFile] = useState(false);
  const [companyQuery, setCompanyQuery] = useState('');
  const [companyResults, setCompanyResults] = useState<ListedCompanySummary[]>([]);
  const [selectedCompany, setSelectedCompanyState] = useState<ListedCompanySummary | null>(null);
  const [companyLoading, setCompanyLoading] = useState(false);
  const [companyStoreStatus, setCompanyStoreStatus] = useState<ListedCompanyStatus | null>(null);

  const refresh = async () => {
    const d = await getBusinessDataset();
    setDatasetInfo(d ? `${d.name} • ${d.rows.length} ردیف • ${d.columns.length} ستون • ${d.source === 'xlsx-file' ? 'Excel' : d.source === 'json-paste' ? 'JSON' : 'CSV'}` : 'هنوز داده شرکت وارد نشده است');
  };

  const refreshListedCompanies = async (query = companyQuery) => {
    setCompanyLoading(true);
    try {
      const [items, storeStatus] = await Promise.all([searchListedCompanies(query, 80), fetchListedCompanyStatus()]);
      setCompanyResults(items);
      setCompanyStoreStatus(storeStatus);
    } finally {
      setCompanyLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);
  useEffect(() => {
    if (requirement && !raw.trim()) setRaw(requirement.csvTemplate);
  }, [requirement]);
  useEffect(() => {
    if (companyMode !== 'listed') return;
    let active = true;
    (async () => {
      const saved = await getSelectedListedCompany();
      if (!active) return;
      setSelectedCompanyState(saved);
      if (saved && !code) {
        router.setParams({ code: saved.code, companyMode: 'listed' } as never);
        setName(`${saved.code} • company data`);
      }
      await refreshListedCompanies('');
    })();
    return () => { active = false; };
  }, [companyMode]);

  const selectCompany = async (company: ListedCompanySummary) => {
    await setSelectedListedCompany(company);
    setSelectedCompanyState(company);
    setName(`${company.code} • company data`);
    router.setParams({ code: company.code, companyMode: 'listed' } as never);
    setStatus(`✓ شرکت بورسی انتخاب شد: ${company.symbol}${company.name ? ` • ${company.name}` : ''}`);
  };

  const importData = async () => {
    try {
      const dataset = parseBusinessData(raw, name.trim() || 'Company data');
      await saveBusinessDataset(dataset);
      setStatus(`✓ متصل و همگام شد: ${dataset.rows.length} ردیف و ${dataset.columns.length} ستون`);
      setRaw(requirement?.csvTemplate ?? '');
      await refresh();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'خطا در خواندن یا همگام‌سازی داده');
    }
  };

  const importExcel = async () => {
    setImportingFile(true);
    setStatus('');
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (result.canceled) return;
      const asset = result.assets[0];
      if (!asset.name.toLowerCase().endsWith('.xlsx')) throw new Error('فقط فایل واقعی .xlsx پشتیبانی می‌شود');
      const base64Data = await FileSystem.readAsStringAsync(asset.uri, { encoding: FileSystem.EncodingType.Base64 });
      const cleanName = (name.trim() && name.trim() !== 'Company data') ? name.trim() : asset.name.replace(/\.xlsx$/i, '');
      const dataset = await importExcelBusinessDataset({ filename: asset.name, name: cleanName, base64Data });
      setStatus(`✓ Excel خوانده و با حساب همگام شد: ${dataset.rows.length} ردیف و ${dataset.columns.length} ستون`);
      await refresh();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'خطا در خواندن فایل Excel');
    } finally {
      setImportingFile(false);
    }
  };

  const clear = async () => {
    try {
      await clearBusinessDataset();
      setStatus('✓ داده شرکت از حساب و دستگاه حذف شد');
      await refresh();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'خطا در حذف داده');
    }
  };

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}>
      <View style={styles.wrap}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.backText, { color: colors.text }]}>←</Text></Pressable>
          <View style={styles.headerCopy}><Text style={[styles.title, { color: colors.text }]}>اتصال داده</Text><Text style={[styles.sub, { color: colors.textSecondary }]}>Data Connections • منابع واقعی برای تحلیل</Text></View>
        </View>

        {companyMode === 'listed' ? <View style={[styles.companyCard, { backgroundColor: colors.backgroundElement, borderColor: '#16a34a66' }]}>
          <View style={styles.activeHead}><View style={styles.liveBadge}><Text style={styles.liveBadgeText}>LISTED</Text></View><Text style={[styles.activeTitle, { color: colors.text }]}>انتخاب شرکت بورسی</Text></View>
          <Text style={[styles.body, { color: colors.textSecondary }]}>شرکت انتخاب‌شده برای ماژول‌های تحلیل و توسعه کسب‌وکار ذخیره می‌شود. جست‌وجو از دیتابیس پایدار BIAP انجام می‌شود.</Text>
          {selectedCompany ? <View style={[styles.selectedBox, { borderColor: Brand.positive }]}><Text style={[styles.selectedName, { color: colors.text }]}>{selectedCompany.symbol} • {selectedCompany.name || selectedCompany.code}</Text><Text style={[styles.selectedMeta, { color: colors.textSecondary }]}>{selectedCompany.market || 'بازار نامشخص'} • {selectedCompany.sourceUniverse || 'منبع ثبت نشده'}</Text></View> : null}
          <View style={styles.searchRow}>
            <Pressable onPress={() => refreshListedCompanies()} style={styles.searchButton}><Text style={styles.searchButtonText}>{companyLoading ? '…' : 'جست‌وجو'}</Text></Pressable>
            <TextInput value={companyQuery} onChangeText={setCompanyQuery} onSubmitEditing={() => refreshListedCompanies()} placeholder="نماد یا نام شرکت" placeholderTextColor={colors.textSecondary} style={[styles.companySearch, { color: colors.text, borderColor: colors.backgroundSelected }]} />
          </View>
          {companyStoreStatus ? <Text style={[styles.storeStatus, { color: colors.textSecondary }]}>ثبت‌شده: {companyStoreStatus.total.toLocaleString('fa-IR')} • غنی‌شده: {companyStoreStatus.enriched.toLocaleString('fa-IR')}{companyStoreStatus.tindexConfigured === false ? ' • Tindex: توکن production موجود نیست' : ''}</Text> : null}
          <View style={styles.companyResults}>{companyResults.slice(0, 20).map(item => <Pressable key={item.code} onPress={() => selectCompany(item)} style={[styles.companyRow, { borderBottomColor: colors.backgroundSelected }]}><View style={{ flex: 1, alignItems: 'flex-end' }}><Text style={[styles.companyName, { color: colors.text }]}>{item.symbol} • {item.name || item.code}</Text><Text style={[styles.companyMeta, { color: colors.textSecondary }]}>{item.market || 'بازار نامشخص'} • {item.sourceUniverse || 'منبع نامشخص'}{item.enrichedAt ? ' • داده تکمیلی موجود' : ''}</Text></View><Text style={[styles.pickText, { color: Brand.positive }]}>{selectedCompany?.code === item.code ? '✓' : 'انتخاب'}</Text></Pressable>)}</View>
          {!companyLoading && companyResults.length === 0 ? <Text style={[styles.helpText, { color: colors.textSecondary }]}>نتیجه‌ای در دیتابیس فعلی پیدا نشد. اگر ingestion هنوز کامل نشده باشد، وضعیت سرور اینجا نمایش داده می‌شود.</Text> : null}
        </View> : null}

        {requirement ? <View style={[styles.requirementCard,{backgroundColor:colors.backgroundElement,borderColor:companyMode==='listed'?'#166534':'#2563eb55'}]}>
          <View style={styles.activeHead}><View style={[styles.modeBadge,{backgroundColor:companyMode==='listed'?'#14532d':'#1e3a8a'}]}><Text style={styles.modeBadgeText}>{companyMode==='listed'?'بورسی':'خصوصی / خدماتی'}</Text></View><Text style={[styles.activeTitle,{color:colors.text}]}>{requirement.title}</Text></View>
          {(selectedCompany?.code || code) ? <Text style={[styles.codeText,{color:Brand.positive}]}>نماد: {selectedCompany?.code || code}</Text> : null}
          <Text style={[styles.body,{color:colors.textSecondary}]}>{requirement.description}</Text>
          {companyMode==='listed' ? <>
            <Text style={[styles.reqTitle,{color:colors.text}]}>ابتدا خودکار از این منابع بررسی می‌شود:</Text>
            <View style={styles.chips}>{requirement.listedAutoSources.length ? requirement.listedAutoSources.map(s=><View key={s} style={styles.greenChip}><Text style={styles.greenChipText}>{sourceLabel(s)}</Text></View>) : <Text style={[styles.body,{color:Brand.warning}]}>برای این تحلیل منبع بورسی کافی نیست و داده داخلی لازم است.</Text>}</View>
          </> : <Text style={[styles.reqTitle,{color:colors.text}]}>قالب زیر دقیقاً برای همین ماژول آماده شده است.</Text>}
          <Text style={[styles.reqTitle,{color:colors.text}]}>فیلدهای مورد نیاز</Text>
          {requirement.fields.map(field=><View key={field.key} style={styles.fieldRow}><Text style={[styles.fieldState,{color:field.required?Brand.warning:colors.textSecondary}]}>{field.required?'لازم':'اختیاری'}</Text><Text style={[styles.fieldName,{color:colors.text}]}>{field.label}</Text></View>)}
          {companyMode==='listed' ? <Text style={[styles.helpText,{color:colors.textSecondary}]}>BIAP داده‌های قابل دریافت از TSETMC/Tindex/CODAL را خودش می‌گیرد. فقط فیلدهایی که در منابع عمومی وجود ندارند باید با Excel/CSV/CRM تکمیل شوند.</Text> : null}
        </View> : null}

        <View style={[styles.activeCard, { backgroundColor: colors.backgroundElement }]}>
          <View style={styles.activeHead}><View style={styles.liveBadge}><Text style={styles.liveBadgeText}>SYNC</Text></View><Text style={[styles.activeTitle, { color: colors.text }]}>منابع فعال BIAP</Text></View>
          <Text style={[styles.body, { color: colors.textSecondary }]}>Market/CODAL/Kiasha فعال هستند. داده اختصاصی شرکت به حساب کاربر همگام می‌شود و روی دستگاه نیز cache محلی دارد.</Text>
          <View style={styles.liveRow}><Text style={[styles.liveItem, { color: Brand.positive }]}>● Company Dataset Sync</Text><Text style={[styles.liveItem, { color: Brand.positive }]}>● Market / CODAL / Kiasha</Text></View>
        </View>

        <View style={[styles.importCard, { backgroundColor: colors.backgroundElement }]}>
          <View style={styles.activeHead}><View style={styles.liveBadge}><Text style={styles.liveBadgeText}>READY</Text></View><Text style={[styles.activeTitle, { color: colors.text }]}>CSV / JSON / Excel</Text></View>
          <Text style={[styles.body, { color: colors.textSecondary }]}>CSV یا JSON را paste کنید، یا فایل واقعی Excel با پسوند .xlsx انتخاب کنید. فایل Excel در backend امن خوانده می‌شود و dataset نرمال‌شده در حساب شما ذخیره می‌شود.</Text>
          <TextInput value={name} onChangeText={setName} placeholder="نام منبع داده" placeholderTextColor={colors.textSecondary} style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected }]} />
          <Pressable disabled={importingFile} onPress={importExcel} style={[styles.excelButton, { borderColor: Brand.primary, opacity: importingFile ? .6 : 1 }]}><Text style={[styles.excelButtonText, { color: Brand.primary }]}>{importingFile ? 'در حال خواندن Excel…' : 'انتخاب فایل Excel (.xlsx)'}</Text></Pressable>
          <TextInput value={raw} onChangeText={setRaw} multiline textAlignVertical="top" placeholder={'یا paste کنید:\nmonth,revenue,cost,customers\n1405-01,1200000,700000,240'} placeholderTextColor={colors.textSecondary} style={[styles.area, { color: colors.text, borderColor: colors.backgroundSelected }]} />
          {requirement ? <Pressable onPress={()=>setRaw(requirement.csvTemplate)} style={[styles.templateBtn,{borderColor:colors.backgroundSelected}]}><Text style={[styles.templateText,{color:colors.textSecondary}]}>بازگرداندن قالب پیشنهادی {requirement.title}</Text></Pressable> : null}
          <Pressable onPress={importData} style={styles.primary}><Text style={styles.primaryText}>اتصال CSV / JSON</Text></Pressable>
          <Text style={[styles.dataset, { color: colors.textSecondary }]}>{datasetInfo}</Text>
          {status ? <Text style={[styles.status, { color: status.startsWith('✓') ? Brand.positive : Brand.warning }]}>{status}</Text> : null}
          <Pressable onPress={clear} style={styles.clearBtn}><Text style={styles.clearText}>حذف داده متصل</Text></Pressable>
        </View>

        <Text style={[styles.section, { color: colors.text }]}>اتصال‌های سازمانی</Text>
        <Text style={[styles.sectionNote, { color: colors.textSecondary }]}>SQL، CRM/ERP و Custom API آماده اتصال امن سمت سرور هستند و با دریافت endpoint/credential واقعی سازمان فعال می‌شوند.</Text>
        {SOURCES.map((source) => <View key={source.key} style={[styles.sourceCard, { backgroundColor: colors.backgroundElement }]}>
          <View style={styles.sourceTop}><View style={[styles.sourceIcon, { backgroundColor: colors.backgroundSelected }]}><Text style={styles.sourceIconText}>{source.icon}</Text></View><View style={styles.sourceCopy}><Text style={[styles.sourceTitle, { color: colors.text }]}>{source.title}</Text><Text style={[styles.body, { color: colors.textSecondary }]}>{source.body}</Text></View></View>
          <View style={[styles.soonRow, { borderTopColor: colors.backgroundSelected }]}><Text style={[styles.soonText, { color: colors.textSecondary }]}>{source.state}</Text><View style={styles.soonBadge}><Text style={styles.soonBadgeText}>SETUP</Text></View></View>
        </View>)}

        <View style={[styles.security, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.securityTitle, { color: colors.text }]}>امنیت</Text><Text style={[styles.body, { color: colors.textSecondary }]}>برای SQL، CRM و API، secret فقط سمت سرور نگهداری می‌شود. هیچ رمز سازمانی داخل اپ ذخیره نمی‌شود.</Text></View>
        <Pressable onPress={() => router.push('/modules' as never)} style={styles.primary}><Text style={styles.primaryText}>رفتن به ماژول‌های تحلیل</Text></Pressable>
      </View>
    </ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingTop:Spacing.three},wrap:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},headerRow:{flexDirection:'row-reverse',alignItems:'center',gap:Spacing.three,marginBottom:Spacing.three},headerCopy:{flex:1,alignItems:'flex-end'},back:{width:38,height:38,borderRadius:19,alignItems:'center',justifyContent:'center'},backText:{fontSize:19},title:{fontFamily:Fonts.sans,fontSize:23,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:11,marginTop:3},activeCard:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.three,borderWidth:1,borderColor:'#166534'},importCard:{borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.four},activeHead:{width:'100%',flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center'},activeTitle:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900'},liveBadge:{backgroundColor:'#14532d',paddingHorizontal:9,paddingVertical:4,borderRadius:12},liveBadgeText:{color:'#86efac',fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},body:{fontFamily:Fonts.sans,fontSize:11.5,lineHeight:20,textAlign:'right',marginTop:6},liveRow:{flexDirection:'row-reverse',flexWrap:'wrap',gap:14,marginTop:12},liveItem:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'800'},input:{borderWidth:1,borderRadius:Radius.sm,padding:10,marginTop:Spacing.three,fontFamily:Fonts.sans,textAlign:'right'},excelButton:{borderWidth:1,borderRadius:Radius.md,paddingVertical:12,alignItems:'center',marginTop:Spacing.two},excelButtonText:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'900'},area:{borderWidth:1,borderRadius:Radius.sm,padding:10,marginTop:Spacing.two,minHeight:150,fontFamily:Fonts.mono,fontSize:11},dataset:{fontFamily:Fonts.sans,fontSize:10.5,textAlign:'right',marginTop:10},status:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'800',textAlign:'right',marginTop:6},clearBtn:{alignSelf:'flex-end',paddingVertical:8},clearText:{color:Brand.negative,fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'800'},section:{fontFamily:Fonts.sans,fontSize:17,fontWeight:'900',textAlign:'right'},sectionNote:{fontFamily:Fonts.sans,fontSize:11,lineHeight:19,textAlign:'right',marginTop:4,marginBottom:Spacing.three},sourceCard:{borderRadius:Radius.md,padding:Spacing.three,marginBottom:Spacing.two},sourceTop:{flexDirection:'row-reverse',gap:Spacing.three,alignItems:'flex-start'},sourceIcon:{width:44,height:44,borderRadius:22,alignItems:'center',justifyContent:'center'},sourceIconText:{fontSize:20},sourceCopy:{flex:1,alignItems:'flex-end'},sourceTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'900'},soonRow:{marginTop:Spacing.three,paddingTop:Spacing.two,borderTopWidth:StyleSheet.hairlineWidth,flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center'},soonText:{fontFamily:Fonts.sans,fontSize:10},soonBadge:{backgroundColor:'#1e3a8a',borderRadius:10,paddingHorizontal:8,paddingVertical:4},soonBadgeText:{color:'#bfdbfe',fontFamily:Fonts.mono,fontSize:8.5,fontWeight:'900'},security:{borderRadius:Radius.md,padding:Spacing.three,marginTop:Spacing.two,alignItems:'flex-end'},securityTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'900'},primary:{backgroundColor:Brand.primary,borderRadius:Radius.md,paddingVertical:13,alignItems:'center',marginTop:Spacing.three},primaryText:{color:'#fff',fontFamily:Fonts.sans,fontSize:13,fontWeight:'900'},
  requirementCard:{borderWidth:1,borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.three},modeBadge:{borderRadius:12,paddingHorizontal:8,paddingVertical:4},modeBadgeText:{color:'#dbeafe',fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},codeText:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'900',textAlign:'right',marginTop:8},reqTitle:{fontFamily:Fonts.sans,fontSize:11.5,fontWeight:'900',textAlign:'right',marginTop:12},chips:{flexDirection:'row-reverse',flexWrap:'wrap',gap:6,marginTop:7},greenChip:{backgroundColor:'#14532d22',borderWidth:1,borderColor:'#16a34a66',borderRadius:12,paddingHorizontal:8,paddingVertical:5},greenChipText:{color:Brand.positive,fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},fieldRow:{flexDirection:'row-reverse',justifyContent:'space-between',alignItems:'center',paddingVertical:7,borderBottomWidth:StyleSheet.hairlineWidth,borderBottomColor:'#94a3b833'},fieldName:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'700'},fieldState:{fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},helpText:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:18,textAlign:'right',marginTop:10},templateBtn:{borderWidth:1,borderRadius:Radius.sm,paddingVertical:9,alignItems:'center',marginTop:8},templateText:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'800'},
  companyCard:{borderWidth:1,borderRadius:Radius.lg,padding:Spacing.four,marginBottom:Spacing.three},selectedBox:{borderWidth:1,borderRadius:Radius.md,padding:Spacing.three,marginTop:Spacing.three,alignItems:'flex-end'},selectedName:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900',textAlign:'right'},selectedMeta:{fontFamily:Fonts.sans,fontSize:10,marginTop:4,textAlign:'right'},searchRow:{flexDirection:'row',gap:8,marginTop:Spacing.three},companySearch:{flex:1,borderWidth:1,borderRadius:Radius.sm,paddingHorizontal:10,paddingVertical:9,fontFamily:Fonts.sans,textAlign:'right'},searchButton:{backgroundColor:Brand.primary,borderRadius:Radius.sm,paddingHorizontal:14,justifyContent:'center'},searchButtonText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11,fontWeight:'900'},storeStatus:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:16,textAlign:'right',marginTop:8},companyResults:{marginTop:8},companyRow:{flexDirection:'row-reverse',alignItems:'center',gap:10,borderBottomWidth:StyleSheet.hairlineWidth,paddingVertical:10},companyName:{fontFamily:Fonts.sans,fontSize:11.5,fontWeight:'800',textAlign:'right'},companyMeta:{fontFamily:Fonts.sans,fontSize:9.5,marginTop:3,textAlign:'right'},pickText:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'900'}
});