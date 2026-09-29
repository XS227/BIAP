import { useMemo, useState } from 'react';
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { IndividualCreditScoringResponse, scoreIndividualCredit } from '@/lib/global-api';

function valueOf(text: string) {
  const n = Number(text.replace(',', '.'));
  return Number.isFinite(n) ? n : 0;
}
function payment(principal: number, aprPct: number, months: number) {
  if (principal <= 0 || months <= 0) return 0;
  const r = Math.max(0, aprPct) / 100 / 12;
  if (!r) return principal / months;
  const f = Math.pow(1 + r, months);
  return principal * r * f / (f - 1);
}
function fmt(v: number, digits=1) { return Number(v).toLocaleString('en-US',{maximumFractionDigits:digits}); }

export default function CreditLabScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [income,setIncome]=useState('5000');
  const [living,setLiving]=useState('2200');
  const [existing,setExisting]=useState('300');
  const [amount,setAmount]=useState('30000');
  const [months,setMonths]=useState('60');
  const [apr,setApr]=useState('6');
  const [asset,setAsset]=useState('40000');
  const [bureau,setBureau]=useState(false);
  const [arrears,setArrears]=useState(false);
  const [bankVerified,setBankVerified]=useState(false);
  const [paymentHistory,setPaymentHistory]=useState('97');
  const [utilization,setUtilization]=useState('30');
  const [historyYears,setHistoryYears]=useState('5');
  const [dti,setDti]=useState('36');
  const [activeAccounts,setActiveAccounts]=useState('4');
  const [bouncedChecks,setBouncedChecks]=useState('0');
  const [pastDefaults,setPastDefaults]=useState('0');
  const [agent10,setAgent10]=useState<IndividualCreditScoringResponse | null>(null);
  const [agent10Busy,setAgent10Busy]=useState(false);
  const [agent10Error,setAgent10Error]=useState('');

  const calc=useMemo(()=>{
    const inc=valueOf(income), liv=valueOf(living), old=valueOf(existing), principal=valueOf(amount), term=Math.max(1,Math.round(valueOf(months))), rate=valueOf(apr), assetValue=valueOf(asset);
    const p=payment(principal,rate,term);
    const stress=payment(principal,rate+3,term);
    const residual=inc-liv-old-p;
    const stressResidual=inc-liv-old-stress;
    const pti=inc>0?p/inc*100:0;
    const dsr=inc>0?(old+p)/inc*100:0;
    const ltv=assetValue>0?principal/assetValue*100:null;
    return {p,stress,residual,stressResidual,pti,dsr,ltv};
  },[income,living,existing,amount,months,apr,asset]);

  const runAgent10=async()=>{
    try{
      setAgent10Busy(true); setAgent10Error('');
      const response=await scoreIndividualCredit({
        paymentOnTimeRatio:valueOf(paymentHistory)/100,
        creditUtilization:valueOf(utilization)/100,
        creditHistoryYears:valueOf(historyYears),
        debtToIncome:valueOf(dti)/100,
        activeAccounts:valueOf(activeAccounts),
        bouncedChecks:valueOf(bouncedChecks),
        pastDefaults:valueOf(pastDefaults),
      });
      setAgent10(response);
    }catch(err){
      setAgent10(null);
      setAgent10Error(err instanceof Error?err.message.slice(0,220):'Agent 10 is unavailable.');
    }finally{setAgent10Busy(false);}
  };

  const fields=[
    ['Monthly net income',income,setIncome],['Essential / fixed living expenses',living,setLiving],
    ['Existing monthly debt payments',existing,setExisting],['Requested credit',amount,setAmount],
    ['Term (months)',months,setMonths],['APR %',apr,setApr],['Vehicle / asset value',asset,setAsset],
  ] as const;

  return <SafeAreaView style={[styles.safe,{backgroundColor:colors.background}]}><ScrollView contentContainerStyle={styles.content}><View style={styles.max}>
    <View style={styles.header}><Pressable onPress={()=>router.back()} style={[styles.back,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.backText,{color:colors.text}]}>← Back</Text></Pressable><View style={{flex:1}}><Text style={[styles.title,{color:colors.text}]}>Credit Underwriting Lab</Text><Text style={[styles.sub,{color:colors.textSecondary}]}>Tesla-style training for hypothetical consumer-finance cases.</Text></View></View>
    <View style={[styles.notice,{borderColor:Brand.warning}]}><Text style={[styles.noticeTitle,{color:Brand.warning}]}>Training only</Text><Text style={[styles.body,{color:colors.textSecondary}]}>Use hypothetical numbers. This screen does not evaluate a real person, does not use protected traits, and never returns approve/decline.</Text></View>

    <Text style={[styles.section,{color:colors.text}]}>Scenario inputs</Text>
    {fields.map(([label,v,setter])=><View key={label} style={styles.field}><Text style={[styles.label,{color:colors.textSecondary}]}>{label}</Text><TextInput value={v} onChangeText={setter} keyboardType="decimal-pad" style={[styles.input,{color:colors.text,backgroundColor:colors.backgroundElement,borderColor:colors.backgroundSelected}]}/></View>)}

    <Text style={[styles.section,{color:colors.text}]}>Evidence checklist</Text>
    {[
      ['Credit bureau / BKR checked',bureau,setBureau],
      ['Bureau shows arrears',arrears,setArrears],
      ['Bank statement / open-banking evidence verified',bankVerified,setBankVerified],
    ].map(([label,v,setter]: any)=><Pressable key={label} onPress={()=>setter(!v)} style={[styles.toggle,{backgroundColor:colors.backgroundElement,borderColor:v?Brand.positive:colors.backgroundSelected}]}><Text style={[styles.toggleText,{color:colors.text}]}>{label}</Text><Text style={[styles.toggleState,{color:v?Brand.positive:colors.textSecondary}]}>{v?'YES':'NO'}</Text></Pressable>)}

    <Text style={[styles.section,{color:colors.text}]}>Agent 10 · Personal Credit Scoring</Text>
    <View style={[styles.card,{backgroundColor:colors.backgroundElement}]}>
      <Text style={[styles.cardTitle,{color:colors.text}]}>Canonical DMA Agent 10 scorecard</Text>
      <Text style={[styles.body,{color:colors.textSecondary}]}>Separate from the company model. Enter a hypothetical natural-person profile; Agent 10 returns a transparent score, illustrative PD and reason codes. It never approves or declines credit.</Text>
      {[
        ['Payments on time %',paymentHistory,setPaymentHistory],
        ['Credit utilization %',utilization,setUtilization],
        ['Credit history years',historyYears,setHistoryYears],
        ['Debt-to-income %',dti,setDti],
        ['Active accounts',activeAccounts,setActiveAccounts],
        ['Bounced checks',bouncedChecks,setBouncedChecks],
        ['Past defaults',pastDefaults,setPastDefaults],
      ].map(([label,v,setter]:any)=><View key={label} style={styles.field}><Text style={[styles.label,{color:colors.textSecondary}]}>{label}</Text><TextInput value={v} onChangeText={setter} keyboardType="decimal-pad" style={[styles.input,{color:colors.text,backgroundColor:colors.background,borderColor:colors.backgroundSelected}]}/></View>)}
      <Pressable onPress={()=>void runAgent10()} disabled={agent10Busy} style={[styles.action,{backgroundColor:Brand.primary,opacity:agent10Busy?.65:1}]}><Text style={styles.actionText}>{agent10Busy?'Running Agent 10…':'Calculate Agent 10'}</Text></Pressable>
      {agent10Error?<Text style={[styles.flag,{color:Brand.negative}]}>{agent10Error}</Text>:null}
      {agent10?.creditScoring?<View style={{marginTop:12}}>
        <View style={styles.metric}><Text style={[styles.metricValue,{color:colors.text}]}>{agent10.creditScoring.score ?? '—'}</Text><Text style={[styles.metricLabel,{color:colors.textSecondary}]}>Credit score</Text></View>
        <View style={styles.metric}><Text style={[styles.metricValue,{color:colors.text}]}>{agent10.creditScoring.pd == null?'—':(agent10.creditScoring.pd*100).toFixed(2)+'%'}</Text><Text style={[styles.metricLabel,{color:colors.textSecondary}]}>Illustrative probability of default</Text></View>
        <View style={styles.metric}><Text style={[styles.metricValue,{color:colors.text}]}>{agent10.creditScoring.risk_band || '—'}</Text><Text style={[styles.metricLabel,{color:colors.textSecondary}]}>Risk band</Text></View>
        {agent10.creditScoring.reason_codes?.length?<Text style={[styles.flag,{color:Brand.warning}]}>Reason codes: {agent10.creditScoring.reason_codes.join(' • ')}</Text>:null}
        {agent10.creditScoring.caveat?<Text style={[styles.body,{color:Brand.warning}]}>{agent10.creditScoring.caveat}</Text>:null}
      </View>:null}
    </View>

    <Text style={[styles.section,{color:colors.text}]}>Calculated underwriting indicators</Text>
    <View style={[styles.card,{backgroundColor:colors.backgroundElement}]}>
      <View style={styles.metric}><Text style={[styles.metricValue,{color:colors.text}]}>{fmt(calc.p,2)}</Text><Text style={[styles.metricLabel,{color:colors.textSecondary}]}>Estimated monthly payment</Text></View>
      <View style={styles.metric}><Text style={[styles.metricValue,{color:colors.text}]}>{fmt(calc.pti)}%</Text><Text style={[styles.metricLabel,{color:colors.textSecondary}]}>Payment / income (PTI)</Text></View>
      <View style={styles.metric}><Text style={[styles.metricValue,{color:colors.text}]}>{fmt(calc.dsr)}%</Text><Text style={[styles.metricLabel,{color:colors.textSecondary}]}>Total debt service / income</Text></View>
      <View style={styles.metric}><Text style={[styles.metricValue,{color:calc.residual<0?Brand.negative:colors.text}]}>{fmt(calc.residual,2)}</Text><Text style={[styles.metricLabel,{color:colors.textSecondary}]}>Residual income</Text></View>
      <View style={styles.metric}><Text style={[styles.metricValue,{color:calc.stressResidual<0?Brand.negative:colors.text}]}>{fmt(calc.stressResidual,2)}</Text><Text style={[styles.metricLabel,{color:colors.textSecondary}]}>Residual at APR +3pp stress</Text></View>
      <View style={styles.metric}><Text style={[styles.metricValue,{color:colors.text}]}>{calc.ltv==null?'—':fmt(calc.ltv)+'%'}</Text><Text style={[styles.metricLabel,{color:colors.textSecondary}]}>Loan-to-value (LTV)</Text></View>
    </View>

    <View style={[styles.card,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.cardTitle,{color:colors.text}]}>How a real underwriter reads this</Text>
      <Text style={[styles.body,{color:colors.textSecondary}]}>• Bureau/BKR: existing credit commitments and payment history.</Text>
      <Text style={[styles.body,{color:colors.textSecondary}]}>• Bank evidence: verify recurring income, expenses and cash-flow consistency.</Text>
      <Text style={[styles.body,{color:colors.textSecondary}]}>• Affordability: income minus normative/verified living costs, existing obligations and new debt service.</Text>
      <Text style={[styles.body,{color:colors.textSecondary}]}>• Asset finance: compare financed amount with vehicle value and expected residual value.</Text>
      <Text style={[styles.body,{color:colors.textSecondary}]}>• Portfolio models: institutions may estimate PD/LGD/EAD from validated historical data; this lab does not fabricate those parameters.</Text>
    </View>

    <View style={[styles.card,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.cardTitle,{color:colors.text}]}>Scenario review flags</Text>
      {!bureau?<Text style={[styles.flag,{color:Brand.warning}]}>• Bureau/BKR evidence missing.</Text>:null}
      {arrears?<Text style={[styles.flag,{color:Brand.warning}]}>• Scenario contains adverse payment history.</Text>:null}
      {!bankVerified?<Text style={[styles.flag,{color:Brand.warning}]}>• Income/cash-flow evidence not independently verified.</Text>:null}
      {calc.residual<0?<Text style={[styles.flag,{color:Brand.negative}]}>• Negative residual income in the base scenario.</Text>:null}
      {calc.stressResidual<0?<Text style={[styles.flag,{color:Brand.negative}]}>• Negative residual income in the +3pp stress scenario.</Text>:null}
      {calc.ltv!=null&&calc.ltv>100?<Text style={[styles.flag,{color:Brand.warning}]}>• Credit exceeds the entered asset value.</Text>:null}
    </View>

    <Text style={[styles.disclaimer,{color:colors.textSecondary}]}>PTI/DTI are educational indicators, not Dutch legal lending limits. In the Netherlands lenders must apply current affordability policy and relevant AFM/VFN standards using the customer’s actual circumstances.</Text>
  </View></ScrollView></SafeAreaView>;
}

const styles=StyleSheet.create({
safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingBottom:BottomTabInset+Spacing.six},max:{width:'100%',maxWidth:MaxContentWidth,alignSelf:'center'},header:{flexDirection:'row',gap:12,paddingVertical:Spacing.three},back:{paddingHorizontal:11,paddingVertical:8,borderRadius:18},backText:{fontFamily:Fonts.sans,fontSize:10,fontWeight:'800'},title:{fontFamily:Fonts.sans,fontSize:20,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:16,marginTop:4},notice:{borderWidth:1,borderRadius:Radius.md,padding:Spacing.three},noticeTitle:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'900'},body:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:17,marginTop:5},section:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'900',marginTop:20,marginBottom:8},field:{marginBottom:8},label:{fontFamily:Fonts.sans,fontSize:9.5,marginBottom:5},input:{borderWidth:1,borderRadius:Radius.md,minHeight:46,paddingHorizontal:12,fontFamily:Fonts.mono,fontSize:13},toggle:{borderWidth:1,borderRadius:Radius.md,minHeight:46,paddingHorizontal:12,flexDirection:'row',alignItems:'center',justifyContent:'space-between',marginBottom:8},toggleText:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'700',flex:1},toggleState:{fontFamily:Fonts.mono,fontSize:10,fontWeight:'900'},card:{borderRadius:Radius.lg,padding:Spacing.three,marginBottom:10},cardTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900',marginBottom:5},metric:{paddingVertical:9,borderBottomWidth:StyleSheet.hairlineWidth,borderBottomColor:'#ffffff22'},metricValue:{fontFamily:Fonts.mono,fontSize:14,fontWeight:'900'},metricLabel:{fontFamily:Fonts.sans,fontSize:9,marginTop:3},flag:{fontFamily:Fonts.sans,fontSize:10,lineHeight:17,marginTop:4},action:{minHeight:46,borderRadius:Radius.md,alignItems:'center',justifyContent:'center',marginTop:10},actionText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11,fontWeight:'900'},disclaimer:{fontFamily:Fonts.sans,fontSize:9,lineHeight:15,textAlign:'center',marginTop:12}
});
