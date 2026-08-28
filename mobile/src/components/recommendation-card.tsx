import { useEffect, useState } from 'react';
import { View, Text, Pressable, StyleSheet, ActivityIndicator } from 'react-native';
import { Brand, Fonts, Spacing, ThemeColors } from '@/constants/theme';
import { Recommendation, previewPaperOrder, submitPaperOrder } from '@/lib/api';
import { getDemoMode } from '@/lib/demo-mode';
import { executeDemoTrade, getDemoWallet } from '@/lib/demo-trading';

const CALL_LABEL: Record<string, string> = { BUY: 'خرید', SELL: 'فروش', HOLD: 'نگهداری' };
const AGENT_LABEL: Record<string, string> = { fundamental: 'بنیادی', risk: 'ریسک', forecast: 'پیش‌بینی', comparison: 'مقایسه' };
function callColor(call: string) { if (call === 'BUY') return Brand.stockGreen; if (call === 'SELL') return Brand.negative; return Brand.dataViolet; }
type SimState = { status: 'idle' } | { status: 'loading' } | { status: 'filled'; note: string } | { status: 'pending'; note: string } | { status: 'rejected'; reasons: string[] } | { status: 'error'; message: string };

export function RecommendationCard({ rec, colors }: { rec: Recommendation; colors: ThemeColors }) {
  const [sim, setSim] = useState<SimState>({ status: 'idle' }); const [expanded, setExpanded] = useState(false); const [demo, setDemo] = useState(false); const [demoCash, setDemoCash] = useState<number | null>(null);
  const accent = callColor(rec.call); const directional = rec.call === 'BUY' || rec.call === 'SELL'; const top = [...rec.breakdown].sort((a,b)=>(b.weight_normalized??0)-(a.weight_normalized??0))[0]; const sourceLabel = rec.dataSource === 'live' ? 'TSETMC + CODAL' : rec.dataSource === 'codal' ? 'CODAL' : 'نمونه';
  useEffect(() => { getDemoMode().then(async (enabled) => { setDemo(enabled); if (enabled) setDemoCash((await getDemoWallet()).cash); }); }, []);

  const runDemoTrade = async (side: 'BUY' | 'SELL') => {
    const price = rec.livePrice?.lastPrice ?? rec.livePrice?.closingPrice ?? null;
    if (!price) { setSim({ status: 'error', message: 'قیمت زنده برای معامله دمو در دسترس نیست.' }); return; }
    setSim({ status: 'loading' }); const result = await executeDemoTrade({ code: rec.code, side, quantity: 10, price });
    if (!result.ok) setSim({ status: 'error', message: result.message }); else { setDemoCash(result.wallet.cash); setSim({ status: 'filled', note: `${side === 'BUY' ? 'خرید' : 'فروش'} دمو ۱۰ سهم با موفقیت ثبت شد.` }); }
  };

  const runPaperSim = async () => {
    if (!directional) return; setSim({ status: 'loading' }); const preview = await previewPaperOrder({ code: rec.code, side: rec.call as 'BUY' | 'SELL', quantity: 10 });
    if (!preview.ok) { if (preview.riskRejected) setSim({ status: 'rejected', reasons: preview.risk.reasons }); else setSim({ status: 'error', message: preview.message }); return; }
    const submitted = await submitPaperOrder(preview.intent.id); if (!submitted.ok) { setSim({ status: 'error', message: submitted.message }); return; }
    if (submitted.receipt.status === 'PAPER_FILLED') setSim({ status: 'filled', note: submitted.receipt.note ?? 'شبیه‌سازی انجام شد' }); else setSim({ status: 'pending', note: submitted.receipt.note ?? 'در انتظار تأیید' });
  };

  return <View style={[styles.wrap, { backgroundColor: colors.backgroundElement }]}>
    <View style={styles.header}><View style={[styles.badge,{backgroundColor:`${accent}22`}]}><Text style={[styles.badgeText,{color:accent}]}>{CALL_LABEL[rec.call]??rec.call}</Text></View><View style={styles.titleWrap}><Text style={[styles.title,{color:colors.text}]}>تحلیل کیا‌شا</Text><Text style={[styles.source,{color:colors.textSecondary}]}>منبع: {sourceLabel}</Text></View></View>
    <Text style={[styles.score,{color:colors.textSecondary}]}>امتیاز نهایی: {rec.score>=0?'+':''}{rec.score.toFixed(3)}</Text>
    {top ? <Text style={[styles.reasoning,{color:colors.textSecondary}]} numberOfLines={expanded?undefined:2}>{top.reasoning}</Text> : null}
    {rec.breakdown.length>0 ? <Pressable onPress={()=>setExpanded(e=>!e)}><Text style={[styles.toggle,{color:accent}]}>{expanded?'بستن جزئیات تیم':'مشاهده جزئیات تیم'}</Text></Pressable> : null}
    {expanded ? <View style={styles.breakdown}>{rec.breakdown.map(b=><View key={b.agent} style={styles.breakdownRow}><Text style={[styles.breakdownAgent,{color:colors.text}]}>{AGENT_LABEL[b.agent]??b.agent}</Text><Text style={[styles.breakdownDetail,{color:colors.textSecondary}]}>رأی {b.vote>=0?'+':''}{b.vote.toFixed(2)} · اطمینان {(b.confidence*100).toFixed(0)}٪ · وزن {((b.weight_normalized??0)*100).toFixed(0)}٪</Text><Text style={[styles.breakdownDetail,{color:colors.textSecondary}]}>{b.reasoning}</Text></View>)}</View> : null}
    {rec.codalFundamentals ? <View style={styles.fundamentals}><Text style={[styles.fundTitle,{color:colors.text}]}>بنیادی از CODAL</Text>{typeof rec.codalFundamentals.revenue_yoy_pct==='number'?<Text style={[styles.fact,{color:colors.textSecondary}]}>رشد درآمد سالانه: {rec.codalFundamentals.revenue_yoy_pct.toFixed(1)}٪</Text>:null}{typeof rec.codalFundamentals.net_margin_pct==='number'?<Text style={[styles.fact,{color:colors.textSecondary}]}>حاشیه سود خالص: {rec.codalFundamentals.net_margin_pct.toFixed(1)}٪</Text>:null}</View> : null}
    <View style={styles.simSection}>
      <Text style={[styles.simLabel,{color:colors.textSecondary}]}>{demo ? `DEMO WALLET • موجودی ${demoCash===null?'—':Math.round(demoCash).toLocaleString('fa-IR')} ریال` : 'Paper — فقط شبیه‌سازی، بدون معامله واقعی'}</Text>
      {demo ? <View style={styles.demoButtons}><Pressable disabled={sim.status==='loading'} onPress={()=>runDemoTrade('BUY')} style={[styles.demoBtn,{backgroundColor:Brand.stockGreen}]}><Text style={styles.simBtnText}>خرید دمو ۱۰ سهم</Text></Pressable><Pressable disabled={sim.status==='loading'} onPress={()=>runDemoTrade('SELL')} style={[styles.demoBtn,{backgroundColor:Brand.negative}]}><Text style={styles.simBtnText}>فروش دمو ۱۰ سهم</Text></Pressable></View> : <Pressable disabled={!directional||sim.status==='loading'} onPress={runPaperSim} style={[styles.simBtn,{backgroundColor:directional?accent:colors.backgroundSelected,opacity:directional?1:.7}]}>{sim.status==='loading'?<ActivityIndicator color="#fff"/>:<Text style={[styles.simBtnText,{color:directional?'#fff':colors.textSecondary}]}>{directional?`شبیه‌سازی ${CALL_LABEL[rec.call]} (۱۰ سهم)`:'بدون سیگنال جهت‌دار'}</Text>}</Pressable>}
      {sim.status==='filled'?<Text style={[styles.simResult,{color:Brand.stockGreen}]}>✓ {sim.note}</Text>:null}{sim.status==='pending'?<Text style={[styles.simResult,{color:colors.textSecondary}]}>{sim.note}</Text>:null}{sim.status==='rejected'?<Text style={[styles.simResult,{color:Brand.negative}]}>رد شد توسط ریسک: {sim.reasons.join('؛ ')}</Text>:null}{sim.status==='error'?<Text style={[styles.simResult,{color:Brand.negative}]}>{sim.message}</Text>:null}
    </View>
  </View>;
}

const styles = StyleSheet.create({ wrap:{borderRadius:Spacing.three,padding:Spacing.four,marginTop:Spacing.three,gap:Spacing.two,alignItems:'flex-end'}, header:{flexDirection:'row-reverse',alignItems:'center',gap:Spacing.two,width:'100%',justifyContent:'space-between'}, titleWrap:{alignItems:'flex-end',flex:1}, badge:{paddingHorizontal:Spacing.three,paddingVertical:Spacing.one,borderRadius:Spacing.five}, badgeText:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'700'}, title:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'700'}, source:{fontFamily:Fonts.sans,fontSize:10,marginTop:2}, score:{fontFamily:Fonts.mono,fontSize:13,alignSelf:'flex-end'}, reasoning:{fontFamily:Fonts.sans,fontSize:13,textAlign:'right',lineHeight:20,alignSelf:'flex-end'}, toggle:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'600'}, breakdown:{width:'100%',gap:Spacing.two,marginTop:Spacing.one}, breakdownRow:{alignItems:'flex-end'}, breakdownAgent:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'700'}, breakdownDetail:{fontFamily:Fonts.sans,fontSize:11,textAlign:'right',lineHeight:17}, fundamentals:{width:'100%',alignItems:'flex-end',gap:4,marginTop:Spacing.one}, fundTitle:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'700'}, fact:{fontFamily:Fonts.sans,fontSize:11,textAlign:'right'}, simSection:{width:'100%',marginTop:Spacing.two,gap:Spacing.two,alignItems:'flex-end'}, simLabel:{fontFamily:Fonts.sans,fontSize:11}, simBtn:{width:'100%',paddingVertical:Spacing.three,borderRadius:Spacing.two,alignItems:'center',justifyContent:'center'}, demoButtons:{width:'100%',flexDirection:'row-reverse',gap:Spacing.two}, demoBtn:{flex:1,paddingVertical:Spacing.three,borderRadius:Spacing.two,alignItems:'center'}, simBtnText:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'700',color:'#fff'}, simResult:{fontFamily:Fonts.sans,fontSize:12,textAlign:'right',lineHeight:18,alignSelf:'flex-end'} });
