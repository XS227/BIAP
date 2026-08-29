import { useEffect, useState } from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, Pressable, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { clearBusinessDataset, getBusinessDataset, importExcelBusinessDataset, parseBusinessData, saveBusinessDataset } from '@/lib/business-data';

const SOURCES = [
  { key: 'sql', icon: '🗄️', title: 'SQL / Database', body: 'کانکتور Read-only سمت سرور؛ رمز دیتابیس داخل موبایل ذخیره نمی‌شود.', state: 'نیازمند مشخصات دیتابیس' },
  { key: 'crm', icon: '👥', title: 'CRM / ERP', body: 'API رسمی CRM/ERP برای Pipeline، Journey، Pricing و KPI.', state: 'نیازمند API سرویس' },
  { key: 'api', icon: '🔌', title: 'Custom API', body: 'API اختصاصی شرکت با credential سمت سرور.', state: 'نیازمند endpoint و مجوز' },
] as const;

export default function DataConnectScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [raw, setRaw] = useState('');
  const [name, setName] = useState('Company data');
  const [status, setStatus] = useState('');
  const [datasetInfo, setDatasetInfo] = useState('');
  const [importingFile, setImportingFile] = useState(false);

  const refresh = async () => {
    const d = await getBusinessDataset();
    setDatasetInfo(d ? `${d.name} • ${d.rows.length} ردیف • ${d.columns.length} ستون • ${d.source === 'xlsx-file' ? 'Excel' : d.source === 'json-paste' ? 'JSON' : 'CSV'}` : 'هنوز داده شرکت وارد نشده است');
  };
  useEffect(() => { refresh(); }, []);

  const importData = async () => {
    try {
      const dataset = parseBusinessData(raw, name.trim() || 'Company data');
      await saveBusinessDataset(dataset);
      setStatus(`✓ متصل و همگام شد: ${dataset.rows.length} ردیف و ${dataset.columns.length} ستون`);
      setRaw('');
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
});