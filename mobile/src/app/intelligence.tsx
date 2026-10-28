import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { Colors, Brand, Fonts, Radius, Spacing, BottomTabInset, MaxContentWidth } from '@/constants/theme';
import { fetchRecommendation, type Recommendation } from '@/lib/api';
import { getSelectedListedCompany, searchListedCompanies, type ListedCompanySummary } from '@/lib/listed-company-selection';
import { answerIranIntelligence, iranCompanyKpis, formatIranKpi } from '@/lib/iran-intelligence';

const PROMPTS = ['درآمد شرکت چقدر رشد داشته؟', 'بدهی شرکت چقدر است؟', 'سودآوری شرکت چگونه است؟', 'ریسک شرکت چیست؟', 'منابع داده کدام است؟'];

export default function IranianIntelligenceScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const params = useLocalSearchParams<{ code?: string }>();
  const incoming = typeof params.code === 'string' ? params.code.trim() : '';
  const [code, setCode] = useState(incoming);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<ListedCompanySummary[]>([]);
  const [name, setName] = useState('');
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');

  const analyze = useCallback(async (target: string, label?: string) => {
    const id = target.trim();
    if (!id) return;
    setCode(id); setName(label || id); setLoading(true); setError(''); setAnswer(''); setRec(null);
    try {
      const result = await fetchRecommendation(id, 30_000);
      if (!result) { setError('تحلیل واقعی برای این نماد در دسترس نیست. ممکن است داده ناقص باشد یا سرور پاسخ نداده باشد.'); return; }
      setRec(result);
    } catch (e) { setError(e instanceof Error ? e.message : 'ارتباط با سرور برقرار نشد'); }
    finally { setLoading(false); }
  }, []);

  useFocusEffect(useCallback(() => {
    let active = true;
    void (async () => {
      if (incoming) { await analyze(incoming); return; }
      const previous = await getSelectedListedCompany();
      if (active && previous?.code) await analyze(previous.code, previous.name || previous.symbol);
    })();
    return () => { active = false; };
  }, [incoming, analyze]));

  const search = async () => {
    if (query.trim().length < 2) return;
    setSearching(true); setError(''); setResults([]);
    try {
      const items = await searchListedCompanies(query.trim(), 35);
      setResults(items);
      if (!items.length) setError('نمادی با این نام در فهرست فعلی پیدا نشد.');
    } finally { setSearching(false); }
  };

  const ask = (value?: string) => {
    if (!rec) return;
    const q = String(value ?? question).trim();
    if (q.length < 3) return;
    setQuestion(q); setAnswer(answerIranIntelligence(rec, q).answer);
  };

  const kpis = iranCompanyKpis(rec);
  const isReal = rec?.dataSource === 'live' || rec?.dataSource === 'codal';
  const hasCodal = Boolean(rec?.dataAvailability?.codal || rec?.dataAvailability?.codal_metadata);
  return <SafeAreaView style={[styles.safe, {backgroundColor:colors.background}]}>
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.max}>
        <Pressable onPress={() => router.back()}><Text style={[styles.back,{color:Brand.primary}]}>→ بازگشت</Text></Pressable>
        <Text style={styles.kicker}>BIAP IRAN / INTELLIGENCE</Text>
        <Text style={[styles.title,{color:colors.text}]}>هوشمندی مالی شرکت‌های ایران</Text>
        <Text style={[styles.sub,{color:colors.textSecondary}]}>داشبورد مالی، داده کدال و TSETMC، پرسش از داده‌ها و تحلیل عوامل کیا‌شا — کاملاً فارسی</Text>

        <View style={[styles.panel,{backgroundColor:colors.backgroundElement,borderColor:colors.backgroundSelected}]}>
          <Text style={[styles.label,{color:colors.text}]}>شرکت بورسی یا فرابورسی</Text>
          <Text style={[styles.muted,{color:colors.textSecondary}]}>{code ? `نماد انتخاب‌شده: ${name} • ${code}` : 'برای شروع یک شرکت را جستجو یا از صفحه بازار انتخاب کنید.'}</Text>
          <View style={styles.searchLine}>
            <Pressable onPress={()=>{void search();}} disabled={searching || query.trim().length<2} style={[styles.action,{backgroundColor:Brand.primary,opacity:query.trim().length < 2 ? .5 : 1}]}><Text style={styles.actionText}>جستجو</Text></Pressable>
            <TextInput value={query} onChangeText={setQuery} onSubmitEditing={()=>{void search();}} placeholder="نام یا نماد شرکت..." placeholderTextColor={colors.textSecondary} textAlign="right" style={[styles.input,{flex:1,backgroundColor:colors.background,borderColor:colors.backgroundSelected,color:colors.text}]} />
          </View>
          {searching ? <ActivityIndicator color={Brand.primary}/> : null}
          {results.map(item=><Pressable key={item.code} onPress={()=>{setResults([]);setQuery('');void analyze(item.code,item.name||item.symbol)}} style={[styles.result,{borderBottomColor:colors.backgroundSelected}]}>
            <Text style={{color:Brand.primary,fontFamily:Fonts.mono}}>{item.symbol}</Text><Text style={{color:colors.text,flex:1,textAlign:'right',fontFamily:Fonts.sans}}>{item.name||item.code}</Text>
          </Pressable>)}
          {code ? <Pressable onPress={()=>{void analyze(code,name)}} disabled={loading} style={[styles.action,{marginTop:12,borderWidth:1,borderColor:Brand.primary}]}><Text style={[styles.actionText,{color:Brand.primary}]}>بروزرسانی تحلیل</Text></Pressable> : null}
        </View>

        {loading ? <View style={styles.loading}><ActivityIndicator color={Brand.primary}/><Text style={{color:colors.textSecondary,fontFamily:Fonts.sans}}>در حال بررسی تحلیل شرکت…</Text></View> : null}
        {error ? <Text style={[styles.warning,{color:Brand.warning}]}>{error}</Text> : null}
        {rec && !loading ? <>
          <View style={[styles.panel,{backgroundColor:colors.backgroundElement,borderColor:colors.backgroundSelected,marginTop:16}]}>
            <Text style={[styles.heading,{color:colors.text}]}>{name || rec.name || code}</Text>
            <View style={styles.badges}><Text style={[styles.pill,{color:isReal?Brand.positive:Brand.warning,borderColor:isReal?Brand.positive:Brand.warning}]}>منبع: {rec.dataSource}</Text><Text style={[styles.pill,{color:hasCodal?Brand.positive:Brand.warning,borderColor:hasCodal?Brand.positive:Brand.warning}]}>کدال: {hasCodal?'در داده‌ها موجود':'ناموجود یا نامشخص'}</Text><Text style={[styles.pill,{color:colors.text,borderColor:colors.backgroundSelected}]}>کیاشا: {rec.call||'نامشخص'}</Text></View>
            <Text style={[styles.muted,{color:colors.textSecondary}]}>آخرین زمان محاسبه: {rec.generatedAt||'نامشخص'} — این زمان به معنی تاریخ گزارش مالی نیست.</Text>
            {!isReal ? <Text style={[styles.warning,{color:Brand.warning}]}>منبع واقعی برای این خروجی تأیید نشده؛ همه KPIهای فاقد داده به‌صورت ناموجود نمایش داده شده‌اند.</Text> : null}
          </View>

          <Text style={[styles.section,{color:colors.text}]}>شاخص‌های شرکت</Text>
          <View style={styles.grid}>
            {kpis.map(metric=><View key={metric.key} style={[styles.metric,{backgroundColor:colors.backgroundElement,borderColor:colors.backgroundSelected}]}>
              <Text style={[styles.metricLabel,{color:colors.textSecondary}]}>{metric.fa}</Text>
              <Text adjustsFontSizeToFit numberOfLines={2} style={[styles.metricValue,{color:metric.value===null?colors.textSecondary:colors.text}]}>{formatIranKpi(metric)}</Text>
              <Text style={[styles.tiny,{color:colors.textSecondary}]}>{metric.source}</Text>
            </View>)}
          </View>

          <View style={[styles.panel,{backgroundColor:colors.backgroundElement,borderColor:Brand.warning,marginTop:15}]}>
            <Text style={[styles.heading,{color:Brand.warning}]}>اعتبار داده‌ها</Text>
            <Text style={[styles.muted,{color:colors.textSecondary}]}>وجود داده در TSETMC یا کدال، تأیید مستقل همه فیلدها نیست. داده ناموجود صفر تلقی نمی‌شود. این صفحه از تحلیل موجود BIAP استفاده می‌کند و BUY/SELL یا داده‌های فریز‌شده را تغییر نمی‌دهد.</Text>
            <Info label="گزارش" value={rec.codalFundamentals?.report_title||'داده موجود نیست'} colors={colors}/>
            <Info label="نوع گزارش" value={rec.codalFundamentals?.report_scope||'نامشخص'} colors={colors}/>
            <Info label="نظر حسابرس" value={rec.codalFundamentals?.audit_opinion||'نامشخص'} colors={colors}/>
            <Info label="پوشش داده کدال" value={hasCodal?'موجود در خروجی':'ناموجود'} colors={colors}/>
          </View>

          <Text style={[styles.section,{color:colors.text}]}>کیاشا و عوامل تحلیلی</Text>
          <View style={[styles.panel,{backgroundColor:colors.backgroundElement,borderColor:colors.backgroundSelected}]}>
            {(rec.breakdown||[]).map((agent,index)=><View key={agent.agent+index} style={[styles.agent,{borderBottomColor:colors.backgroundSelected}]}>
              <Text style={[styles.agentTitle,{color:colors.text}]}>{agent.agent} • {Number.isFinite(agent.vote)?agent.vote.toFixed(3):'—'} • اعتماد {Number.isFinite(agent.confidence)?Math.round(agent.confidence*100).toLocaleString('fa-IR')+'٪':'—'}</Text>
              <Text style={[styles.muted,{color:colors.textSecondary}]}>{agent.reasoning||'توضیح موجود نیست'}</Text>
            </View>)}
            {!(rec.breakdown||[]).length ? <Text style={{color:colors.textSecondary}}>خروجی عامل‌ها موجود نیست.</Text>:null}
          </View>

          <View style={[styles.panel,{backgroundColor:colors.backgroundElement,borderColor:colors.backgroundSelected,marginTop:16}]}>
            <Text style={styles.kicker}>BIAP ANALYST / نسخه پایه</Text>
            <Text style={[styles.heading,{color:colors.text,marginTop:8}]}>از اطلاعات همین شرکت بپرسید</Text>
            <Text style={[styles.muted,{color:colors.textSecondary}]}>پاسخ‌ها فعلاً قاعده‌محور و مبتنی بر داده‌های دریافت‌شده‌اند؛ گفت‌وگوی آزاد هوش مصنوعی نیست.</Text>
            <View style={styles.prompts}>{PROMPTS.map(p=><Pressable key={p} onPress={()=>ask(p)} style={[styles.prompt,{borderColor:colors.backgroundSelected}]}><Text style={{color:colors.textSecondary,fontFamily:Fonts.sans,fontSize:11}}>{p}</Text></Pressable>)}</View>
            <TextInput value={question} onChangeText={setQuestion} onSubmitEditing={()=>ask()} placeholder="سؤال درباره این شرکت..." placeholderTextColor={colors.textSecondary} textAlign="right" style={[styles.input,{backgroundColor:colors.background,borderColor:colors.backgroundSelected,color:colors.text,marginTop:12}]} />
            <Pressable onPress={()=>ask()} disabled={question.trim().length<3} style={[styles.action,{backgroundColor:Brand.primary,marginTop:10,opacity:question.trim().length < 3 ? .5 : 1}]}><Text style={styles.actionText}>تحلیل پرسش</Text></Pressable>
            {answer ? <Text style={[styles.answer,{backgroundColor:colors.background,color:colors.text}]}>{answer}</Text> : null}
          </View>
          <Text style={[styles.muted,{color:colors.textSecondary,marginTop:18,textAlign:'center'}]}>فقط پژوهش و پشتیبانی تصمیم • بدون ارسال سفارش • بدون تغییر مدل کیاشا</Text>
        </>:null}
      </View>
    </ScrollView>
  </SafeAreaView>;
}

function Info({label,value,colors}:{label:string;value:string;colors:typeof Colors.light|typeof Colors.dark}) {
  return <View style={styles.info}><Text style={[styles.infoValue,{color:colors.text}]}>{value}</Text><Text style={[styles.infoKey,{color:colors.textSecondary}]}>{label}</Text></View>;
}
const styles=StyleSheet.create({
  safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingBottom:BottomTabInset+Spacing.four},
  max:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},back:{fontFamily:Fonts.sans,marginTop:16,fontSize:13},
  kicker:{color:Brand.primary,fontSize:10,fontWeight:'900',fontFamily:Fonts.mono,letterSpacing:1,marginTop:18},
  title:{fontFamily:Fonts.sans,fontSize:24,fontWeight:'900',marginTop:8,textAlign:'right'},
  sub:{fontFamily:Fonts.sans,fontSize:12,lineHeight:22,marginVertical:12,textAlign:'right'},
  panel:{borderRadius:Radius.lg,borderWidth:1,padding:16},
  label:{fontFamily:Fonts.sans,fontSize:14,textAlign:'right',fontWeight:'700'},
  muted:{fontFamily:Fonts.sans,fontSize:11,lineHeight:20,marginTop:8,textAlign:'right'},
  searchLine:{flexDirection:'row',gap:9,marginTop:13},
  input:{borderWidth:1,borderRadius:Radius.md,fontFamily:Fonts.sans,padding:12,fontSize:12},
  action:{borderRadius:Radius.md,paddingHorizontal:16,minHeight:46,alignItems:'center',justifyContent:'center'},
  actionText:{color:'#fff',fontFamily:Fonts.sans,fontSize:12,fontWeight:'800'},
  result:{flexDirection:'row',gap:14,paddingVertical:11,borderBottomWidth:1,alignItems:'center'},
  loading:{padding:30,alignItems:'center',gap:12},
  warning:{textAlign:'right',fontFamily:Fonts.sans,fontSize:12,lineHeight:21,marginTop:9},
  heading:{fontSize:17,fontFamily:Fonts.sans,fontWeight:'900',textAlign:'right'},
  badges:{flexDirection:'row-reverse',flexWrap:'wrap',gap:8,marginVertical:12},
  pill:{borderWidth:1,borderRadius:20,paddingHorizontal:10,paddingVertical:5,fontFamily:Fonts.sans,fontSize:10},
  section:{fontSize:18,fontFamily:Fonts.sans,textAlign:'right',fontWeight:'900',marginTop:22,marginBottom:12},
  grid:{flexDirection:'row',flexWrap:'wrap',gap:10},
  metric:{width:'48.5%',minHeight:122,padding:13,borderRadius:Radius.md,borderWidth:1,alignItems:'flex-end'},
  metricLabel:{fontFamily:Fonts.sans,fontSize:11,textAlign:'right'},
  metricValue:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900',marginVertical:12,textAlign:'right'},
  tiny:{fontSize:9,fontFamily:Fonts.sans,textAlign:'right'},
  info:{flexDirection:'row',justifyContent:'space-between',paddingVertical:11,gap:12,borderBottomWidth:1},
  infoKey:{fontFamily:Fonts.sans,fontSize:11},infoValue:{fontFamily:Fonts.sans,fontSize:11,flex:1,textAlign:'right'},
  agent:{borderBottomWidth:1,paddingVertical:13},agentTitle:{fontFamily:Fonts.mono,fontSize:12,fontWeight:'800',textAlign:'right'},
  prompts:{flexDirection:'row-reverse',flexWrap:'wrap',gap:7,marginTop:13},
  prompt:{borderWidth:1,padding:9,borderRadius:20},
  answer:{fontFamily:Fonts.sans,lineHeight:25,padding:14,marginTop:14,textAlign:'right',borderRadius:Radius.md,fontSize:12},
});
