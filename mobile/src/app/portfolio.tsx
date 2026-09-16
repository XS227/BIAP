import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { buildGlobalPortfolio, fetchGlobalCountries, GlobalAnalysis, GlobalCountry, GlobalInstrument, GlobalPortfolioResponse, scanGlobalMarket } from '@/lib/global-api';
import { getGlobalMarketSelection, GlobalMarketSelection } from '@/lib/global-market-selection';

type Risk='low'|'medium'|'high';
type ScopeMarket={country:string;countryName:string;exchange:string;exchangeLabel:string;currency:string;mic?:string|null};
type MarketComparison={
  key:string; country:string; exchange:string; label:string; qualified:number; deep:number; coverage:number;
  pass:number; warn:number; block:number; avgScore:number|null; avgConfidence:number|null; topTicker:string; topScore:number|null;
};

const PRIORITY=['US','NO','SE','GB','JP','AU','DE','FR','NL','FI','DK','KR','IR'];
const MAX_PORTFOLIO_INPUTS=50;
const AGENTS=['fundamental','risk','forecast','comparison','quality','liquidity'] as const;

function num(value:number|undefined|null,digits=2){return value==null||!Number.isFinite(Number(value))?'—':Number(value).toLocaleString('en-US',{maximumFractionDigits:digits})}
function pct01(value:number|undefined|null){return value==null||!Number.isFinite(Number(value))?'—':`${Math.round(Number(value)*100)}%`}
function keyOf(m:ScopeMarket){return `${m.country}:${m.exchange}`}
function fromSelection(s:GlobalMarketSelection):ScopeMarket{return{country:s.country,countryName:s.countryName,exchange:s.exchange,exchangeLabel:s.exchangeLabel,currency:s.currency,mic:s.mic}}
function analysisKey(a:GlobalAnalysis){return `${a.country||''}:${a.exchange||''}:${a.ticker||''}`}

function marketStats(scope:ScopeMarket, body:Awaited<ReturnType<typeof scanGlobalMarket>>):MarketComparison{
  const deep=Array.isArray(body.deepResults)?body.deepResults:[];
  const scored=deep.filter((x)=>x.score!=null&&Number.isFinite(Number(x.score)));
  const confident=deep.filter((x)=>x.confidence!=null&&Number.isFinite(Number(x.confidence)));
  const avgScore=scored.length?scored.reduce((s,x)=>s+Number(x.score),0)/scored.length:null;
  const avgConfidence=confident.length?confident.reduce((s,x)=>s+Number(x.confidence),0)/confident.length:null;
  const top=[...(body.recommendations||[])].sort((a,b)=>Number(b.score||0)-Number(a.score||0))[0];
  return{
    key:keyOf(scope),country:scope.country,exchange:scope.exchange,label:scope.exchangeLabel,
    qualified:Number(body.recommendationCount||body.recommendations?.length||0),deep:Number(body.deepAnalyzed||deep.length||0),coverage:Number(body.screeningCoveragePct||0),
    pass:deep.filter((x)=>x.evidence?.status==='PASS').length,warn:deep.filter((x)=>x.evidence?.status==='WARN').length,block:deep.filter((x)=>x.evidence?.status==='BLOCK').length,
    avgScore,avgConfidence,topTicker:top?.ticker||'—',topScore:top?.score??null,
  };
}

function signalFor(analysis:GlobalAnalysis|undefined,agent:string){return analysis?.signals?.find((s)=>s.agent===agent)}
function factorSummary(analysis:GlobalAnalysis|undefined){
  const signals=analysis?.signals||[];
  const positive=[...signals].filter((s)=>s.vote>0.08&&s.confidence>0).sort((a,b)=>(b.vote*b.confidence)-(a.vote*a.confidence)).slice(0,3);
  const negative=[...signals].filter((s)=>s.vote<-0.08&&s.confidence>0).sort((a,b)=>(a.vote*a.confidence)-(b.vote*b.confidence)).slice(0,2);
  return{
    positive:positive.map((s)=>`${s.agent} ${s.vote>=0?'+':''}${s.vote.toFixed(2)}`).join(' • ')||'No strong positive agent factor',
    negative:negative.map((s)=>`${s.agent} ${s.vote.toFixed(2)}`).join(' • ')||'No material negative agent vote',
  };
}

export default function GlobalPortfolioScreen(){
  const colors=useColorScheme()==='dark'?Colors.dark:Colors.light;
  const[current,setCurrent]=useState<GlobalMarketSelection|null>(null);
  const[countries,setCountries]=useState<GlobalCountry[]>([]);
  const[scopes,setScopes]=useState<ScopeMarket[]>([]);
  const[capital,setCapital]=useState('50000');
  const[baseCurrency,setBaseCurrency]=useState('EUR');
  const[risk,setRisk]=useState<Risk>('medium');
  const[horizon,setHorizon]=useState('5y');
  const[maxPositions,setMaxPositions]=useState('10');
  const[cashReserve,setCashReserve]=useState('15');
  const[loading,setLoading]=useState(false);
  const[refreshing,setRefreshing]=useState(false);
  const[error,setError]=useState('');
  const[scanNotes,setScanNotes]=useState<string[]>([]);
  const[comparison,setComparison]=useState<MarketComparison[]>([]);
  const[result,setResult]=useState<GlobalPortfolioResponse|null>(null);
  const[candidateCount,setCandidateCount]=useState(0);

  useFocusEffect(useCallback(()=>{
    Promise.all([getGlobalMarketSelection(),fetchGlobalCountries()]).then(([selection,catalog])=>{
      setCurrent(selection);setCountries(catalog.countries);setScopes((prev)=>prev.length?prev:[fromSelection(selection)]);
    });
  },[]));

  const marketOptions=useMemo(()=>{
    const currentKey=current?`${current.country}:${current.exchange}`:'';
    const rows:ScopeMarket[]=[];
    for(const country of countries){for(const exchange of country.exchanges){rows.push({country:country.country,countryName:country.name,exchange:exchange.code,exchangeLabel:exchange.label,currency:exchange.currencies[0]||'',mic:exchange.mic});}}
    const rank=new Map(PRIORITY.map((x,i)=>[x,i]));
    return rows.sort((a,b)=>keyOf(a)===currentKey?-1:keyOf(b)===currentKey?1:(rank.get(a.country)??99)-(rank.get(b.country)??99)||a.exchangeLabel.localeCompare(b.exchangeLabel));
  },[countries,current]);

  const toggleScope=(market:ScopeMarket)=>setScopes((prev)=>{
    const exists=prev.some((x)=>keyOf(x)===keyOf(market));
    if(exists)return prev.length===1?prev:prev.filter((x)=>keyOf(x)!==keyOf(market));
    if(prev.length>=4)return prev;
    return[...prev,market];
  });

  const build=async()=>{
    const amount=Number(capital.replace(/,/g,''));
    const positions=Math.max(1,Math.min(30,Number(maxPositions)||10));
    const reserve=Math.max(0,Math.min(80,Number(cashReserve)||0));
    if(!Number.isFinite(amount)||amount<=0){setError('Enter a positive capital amount.');return}
    if(!/^[A-Za-z]{3}$/.test(baseCurrency.trim())){setError('Base currency must be a 3-letter code such as EUR, USD or NOK.');return}
    if(!scopes.length){setError('Select at least one market.');return}
    setLoading(true);setError('');setResult(null);setCandidateCount(0);setScanNotes([]);setComparison([]);
    try{
      const perMarketCapacity=Math.max(1,Math.floor(MAX_PORTFOLIO_INPUTS/scopes.length));
      const desiredPerMarket=Math.max(5,Math.ceil(positions*1.5));
      const perMarket=Math.min(50,perMarketCapacity,desiredPerMarket);
      const scans=await Promise.allSettled(scopes.map((scope)=>scanGlobalMarket(scope.country,scope.exchange,perMarket)));
      const notes:string[]=[];const candidates:GlobalInstrument[]=[];const compare:MarketComparison[]=[];
      scans.forEach((scan,index)=>{
        const scope=scopes[index];
        if(scan.status==='rejected'){notes.push(`${scope.country}/${scope.exchange}: scan failed`);compare.push({key:keyOf(scope),country:scope.country,exchange:scope.exchange,label:scope.exchangeLabel,qualified:0,deep:0,coverage:0,pass:0,warn:0,block:0,avgScore:null,avgConfidence:null,topTicker:'—',topScore:null});return}
        const body=scan.value;
        compare.push(marketStats(scope,body));
        notes.push(`${scope.country}/${scope.exchange}: ${body.recommendationCount??0} qualified from ${body.deepAnalyzed??0} deep analyses`);
        for(const item of body.recommendations||[]){if(!item.ticker)continue;candidates.push({country:item.country||scope.country,exchange:item.exchange||scope.exchange,currency:item.currency||scope.currency,ticker:item.ticker,name:item.name||item.ticker,isin:item.isin||null,lei:item.lei||null,sector:item.company?.sector||null,industry:item.company?.industry||null,lot_size:item.company?.lot_size||null});}
      });
      setComparison(compare);
      const unique=[...new Map(candidates.map((x)=>[`${x.country}:${x.exchange}:${x.ticker}`,x])).values()].slice(0,MAX_PORTFOLIO_INPUTS);
      setCandidateCount(unique.length);setScanNotes(notes);
      if(!unique.length){setError('No evidence-qualified BUY candidates are available across the selected markets. Portfolio Agent will not manufacture a portfolio.');return}
      const countryCap=scopes.length<=1?100:Math.max(30,Math.min(60,Math.ceil(140/scopes.length)));
      const portfolio=await buildGlobalPortfolio({capital:amount,baseCurrency:baseCurrency.trim().toUpperCase(),riskTolerance:risk,horizon:horizon.trim()||'5y',allowedCountries:[...new Set(scopes.map((x)=>x.country))],allowedExchanges:[...new Set(scopes.map((x)=>x.exchange))],maxPositionPct:Math.min(25,Math.max(3,100/Math.max(positions,1)*1.5)),maxCountryPct:countryCap,maxSectorPct:35,minCashReservePct:reserve,maxPositions:positions},unique);
      setResult(portfolio);
    }catch(err){setError(err instanceof Error?err.message.slice(0,360):'Portfolio Agent is unavailable.')}finally{setLoading(false);setRefreshing(false)}
  };

  const proposal=result?.proposal;
  const allocations=proposal?.allocations||[];
  const analysisMap=useMemo(()=>new Map((result?.analyses||[]).map((a)=>[analysisKey(a),a])),[result]);

  return <SafeAreaView style={[styles.safe,{backgroundColor:colors.background}]}><ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={()=>{setRefreshing(true);void build()}} tintColor={Brand.primary}/>} contentContainerStyle={styles.content}><View style={styles.max}>
    <View style={styles.header}><View style={{flex:1}}><Text style={[styles.title,{color:colors.text}]}>Global Portfolio Agent</Text><Text style={[styles.subtitle,{color:colors.textSecondary}]}>Compare exchanges, select verified candidates, then allocate with FX, risk and concentration controls</Text></View><Pressable onPress={()=>router.push('/global')} style={[styles.marketButton,{borderColor:Brand.primary}]}><Text style={styles.marketButtonText}>Market selector</Text></Pressable></View>

    <View style={[styles.scopeCard,{backgroundColor:colors.backgroundElement}]}><Text style={styles.eyebrow}>MULTI-MARKET SCOPE • MAX 4 IN PREVIEW</Text><Text style={[styles.scopeTitle,{color:colors.text}]}>Select exchanges to compare and combine</Text><Text style={[styles.scopeText,{color:colors.textSecondary}]}>Each exchange is screened independently with the same six scoring agents and Evidence gate. Only verified BUY candidates enter the global allocation step.</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.scopeScroll}>{marketOptions.map((market)=>{const active=scopes.some((x)=>keyOf(x)===keyOf(market));return <Pressable key={keyOf(market)} onPress={()=>toggleScope(market)} style={[styles.scopeChip,{backgroundColor:active?Brand.primary:colors.backgroundSelected}]}><Text style={[styles.scopeCode,{color:active?'#fff':colors.text}]}>{market.country}</Text><Text style={[styles.scopeName,{color:active?'#fff':colors.textSecondary}]}>{market.exchangeLabel}</Text></Pressable>})}</ScrollView><Text style={[styles.selectedLine,{color:colors.textSecondary}]}>Selected: {scopes.map((x)=>`${x.country}/${x.exchangeLabel}`).join(' • ')}</Text></View>

    <Text style={[styles.sectionTitle,{color:colors.text}]}>Investor profile</Text><View style={[styles.form,{backgroundColor:colors.backgroundElement}]}><View style={styles.twoCols}><View style={styles.field}><Text style={[styles.label,{color:colors.textSecondary}]}>Capital</Text><TextInput value={capital} onChangeText={setCapital} keyboardType="decimal-pad" style={[styles.input,{color:colors.text,borderColor:colors.backgroundSelected}]}/></View><View style={styles.field}><Text style={[styles.label,{color:colors.textSecondary}]}>Base currency</Text><TextInput value={baseCurrency} onChangeText={setBaseCurrency} autoCapitalize="characters" maxLength={3} style={[styles.input,{color:colors.text,borderColor:colors.backgroundSelected}]}/></View></View><Text style={[styles.label,{color:colors.textSecondary}]}>Risk tolerance</Text><View style={styles.segment}>{(['low','medium','high'] as Risk[]).map((item)=><Pressable key={item} onPress={()=>setRisk(item)} style={[styles.segmentButton,{backgroundColor:risk===item?Brand.primary:colors.backgroundSelected}]}><Text style={[styles.segmentText,{color:risk===item?'#fff':colors.text}]}>{item}</Text></Pressable>)}</View><View style={styles.twoCols}><View style={styles.field}><Text style={[styles.label,{color:colors.textSecondary}]}>Horizon</Text><TextInput value={horizon} onChangeText={setHorizon} placeholder="5y" placeholderTextColor={colors.textSecondary} style={[styles.input,{color:colors.text,borderColor:colors.backgroundSelected}]}/></View><View style={styles.field}><Text style={[styles.label,{color:colors.textSecondary}]}>Max positions</Text><TextInput value={maxPositions} onChangeText={setMaxPositions} keyboardType="number-pad" style={[styles.input,{color:colors.text,borderColor:colors.backgroundSelected}]}/></View></View><Text style={[styles.label,{color:colors.textSecondary}]}>Minimum cash reserve (%)</Text><TextInput value={cashReserve} onChangeText={setCashReserve} keyboardType="decimal-pad" style={[styles.input,{color:colors.text,borderColor:colors.backgroundSelected}]}/></View>

    <Pressable disabled={loading||!scopes.length} onPress={()=>{void build()}} style={[styles.buildButton,{backgroundColor:Brand.primary,opacity:loading?.65:1}]}>{loading?<ActivityIndicator color="#fff"/>:<Text style={styles.buildText}>Compare markets and build global portfolio</Text>}</Pressable>
    {scanNotes.length?<View style={[styles.notes,{backgroundColor:colors.backgroundElement}]}>{scanNotes.map((note)=><Text key={note} style={[styles.noteText,{color:colors.textSecondary}]}>• {note}</Text>)}</View>:null}
    {error?<View style={[styles.errorBox,{borderColor:Brand.warning}]}><Text style={[styles.errorText,{color:colors.textSecondary}]}>{error}</Text></View>:null}

    {comparison.length?<><Text style={[styles.sectionTitle,{color:colors.text}]}>Market comparison</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.compareScroll}>{comparison.map((m)=><View key={m.key} style={[styles.compareCard,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.compareCountry,{color:Brand.primary}]}>{m.country}</Text><Text numberOfLines={2} style={[styles.compareName,{color:colors.text}]}>{m.label}</Text><View style={styles.compareGrid}><View><Text style={[styles.compareValue,{color:colors.text}]}>{m.qualified}</Text><Text style={[styles.compareLabel,{color:colors.textSecondary}]}>qualified</Text></View><View><Text style={[styles.compareValue,{color:colors.text}]}>{m.deep}</Text><Text style={[styles.compareLabel,{color:colors.textSecondary}]}>deep</Text></View><View><Text style={[styles.compareValue,{color:colors.text}]}>{num(m.avgScore,3)}</Text><Text style={[styles.compareLabel,{color:colors.textSecondary}]}>avg score</Text></View><View><Text style={[styles.compareValue,{color:colors.text}]}>{pct01(m.avgConfidence)}</Text><Text style={[styles.compareLabel,{color:colors.textSecondary}]}>avg conf.</Text></View></View><Text style={[styles.compareEvidence,{color:colors.textSecondary}]}>Evidence P/W/B: {m.pass}/{m.warn}/{m.block}</Text><Text style={[styles.compareTop,{color:colors.text}]}>Top: {m.topTicker} {m.topScore==null?'':`(${num(m.topScore,3)})`}</Text></View>)}</ScrollView></>:null}

    {proposal?<><View style={[styles.summary,{backgroundColor:colors.backgroundElement}]}><View style={styles.summaryTop}><View><Text style={[styles.summaryLabel,{color:colors.textSecondary}]}>Proposal status</Text><Text style={[styles.summaryStatus,{color:proposal.status==='NO_RECOMMENDATION'?Brand.warning:Brand.positive}]}>{proposal.status||'—'}</Text></View><View style={{alignItems:'flex-end'}}><Text style={[styles.summaryLabel,{color:colors.textSecondary}]}>Qualified inputs</Text><Text style={[styles.summaryNumber,{color:colors.text}]}>{candidateCount}</Text></View></View><View style={styles.summaryMetrics}><View><Text style={[styles.summaryValue,{color:colors.text}]}>{num(proposal.invested_pct)}%</Text><Text style={[styles.summaryLabel,{color:colors.textSecondary}]}>invested</Text></View><View><Text style={[styles.summaryValue,{color:colors.text}]}>{num(proposal.cash_pct)}%</Text><Text style={[styles.summaryLabel,{color:colors.textSecondary}]}>cash</Text></View><View><Text style={[styles.summaryValue,{color:colors.text}]}>{allocations.length}</Text><Text style={[styles.summaryLabel,{color:colors.textSecondary}]}>positions</Text></View></View>{proposal.reasoning?<Text style={[styles.reasoning,{color:colors.textSecondary}]}>{proposal.reasoning}</Text>:null}</View>

      <Text style={[styles.sectionTitle,{color:colors.text}]}>Proposed allocations</Text>{allocations.length?allocations.map((item,index)=>{const a=analysisMap.get(`${item.country||''}:${item.exchange||''}:${item.ticker||''}`);const factors=factorSummary(a);return <View key={`${item.identity}-${index}`} style={[styles.allocation,{backgroundColor:colors.backgroundElement}]}><View style={styles.allocationTop}><View><Text style={[styles.allocationTicker,{color:colors.text}]}>#{index+1} {item.ticker}</Text><Text style={[styles.allocationMeta,{color:colors.textSecondary}]}>{item.country} • {item.exchange} • {item.currency}</Text></View><View style={{alignItems:'flex-end'}}><Text style={[styles.weight,{color:Brand.primary}]}>{num(item.weight_pct)}%</Text><Text style={[styles.allocationMeta,{color:colors.textSecondary}]}>{num(item.quantity,0)} shares</Text></View></View><View style={styles.allocationMetrics}><Text style={[styles.allocationMetric,{color:colors.textSecondary}]}>Amount <Text style={{color:colors.text}}>{num(item.amount_base_currency)} {baseCurrency.toUpperCase()}</Text></Text><Text style={[styles.allocationMetric,{color:colors.textSecondary}]}>Score <Text style={{color:colors.text}}>{num(item.score,3)}</Text></Text><Text style={[styles.allocationMetric,{color:colors.textSecondary}]}>Confidence <Text style={{color:colors.text}}>{pct01(item.confidence)}</Text></Text></View><Text style={[styles.factorPositive,{color:Brand.positive}]}>Why selected: {factors.positive}</Text><Text style={[styles.factorRisk,{color:factors.negative.startsWith('No material')?colors.textSecondary:Brand.warning}]}>Remaining cautions: {factors.negative}</Text></View>}):<View style={[styles.empty,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.emptyText,{color:colors.textSecondary}]}>No allocation cleared all Portfolio Agent gates.</Text></View>}

      {allocations.length?<><Text style={[styles.sectionTitle,{color:colors.text}]}>Final analytical summary</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tableScroll}><View><View style={[styles.tableRow,styles.tableHeader,{backgroundColor:colors.backgroundSelected}]}><Text style={[styles.colStock,{color:colors.text}]}>Stock / Market</Text><Text style={[styles.colSmall,{color:colors.text}]}>Weight</Text><Text style={[styles.colSmall,{color:colors.text}]}>Score</Text><Text style={[styles.colSmall,{color:colors.text}]}>Conf.</Text><Text style={[styles.colEvidence,{color:colors.text}]}>Evidence</Text>{AGENTS.map((agent)=><Text key={agent} style={[styles.colAgent,{color:colors.text}]}>{agent}</Text>)}</View>{allocations.map((item,index)=>{const a=analysisMap.get(`${item.country||''}:${item.exchange||''}:${item.ticker||''}`);return <View key={`table-${item.identity}-${index}`} style={[styles.tableRow,{backgroundColor:index%2?colors.backgroundElement:colors.background}]}><View style={styles.colStock}><Text style={[styles.tableTicker,{color:colors.text}]}>{item.ticker}</Text><Text style={[styles.tableMeta,{color:colors.textSecondary}]}>{item.country}/{item.exchange}</Text></View><Text style={[styles.colSmall,{color:colors.text}]}>{num(item.weight_pct,1)}%</Text><Text style={[styles.colSmall,{color:colors.text}]}>{num(item.score,2)}</Text><Text style={[styles.colSmall,{color:colors.text}]}>{pct01(item.confidence)}</Text><Text style={[styles.colEvidence,{color:a?.evidence?.status==='PASS'?Brand.positive:Brand.warning}]}>{a?.evidence?.status||'—'}</Text>{AGENTS.map((agent)=>{const s=signalFor(a,agent);return <Text key={agent} style={[styles.colAgent,{color:s&&s.vote>=.2?Brand.positive:s&&s.vote<=-.2?Brand.negative:colors.textSecondary}]}>{s?`${s.vote>=0?'+':''}${s.vote.toFixed(2)}`:'—'}</Text>})}</View>})}</View></ScrollView></>:null}

      {result?.fxErrors&&Object.keys(result.fxErrors).length?<View style={[styles.errorBox,{borderColor:Brand.warning}]}><Text style={[styles.errorText,{color:colors.textSecondary}]}>FX unavailable: {Object.entries(result.fxErrors).map(([k,v])=>`${k}: ${v}`).join(' • ')}</Text></View>:null}</>:null}

    <View style={[styles.notice,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.noticeTitle,{color:colors.text}]}>Decision support, paper first</Text><Text style={[styles.noticeText,{color:colors.textSecondary}]}>The portfolio is a research proposal based on verified inputs and explicit constraints. Missing/stale evidence can remove a stock entirely. No live order is submitted in this build.</Text></View>
  </View></ScrollView></SafeAreaView>;
}

const styles=StyleSheet.create({
  safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingBottom:BottomTabInset+Spacing.six},max:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},
  header:{flexDirection:'row',alignItems:'center',gap:12,paddingTop:Spacing.four,paddingBottom:Spacing.three},title:{fontFamily:Fonts.sans,fontSize:25,fontWeight:'900'},subtitle:{fontFamily:Fonts.sans,fontSize:10.5,lineHeight:16,marginTop:3},marketButton:{borderWidth:1,borderRadius:20,paddingHorizontal:12,paddingVertical:8},marketButtonText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:9.5,fontWeight:'900'},
  scopeCard:{borderRadius:Radius.lg,padding:Spacing.four},eyebrow:{color:Brand.primary,fontFamily:Fonts.mono,fontSize:8,fontWeight:'900'},scopeTitle:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900',marginTop:5},scopeText:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15,marginTop:4},scopeScroll:{gap:7,paddingVertical:12,paddingRight:8},scopeChip:{width:118,borderRadius:Radius.md,padding:10},scopeCode:{fontFamily:Fonts.mono,fontSize:12,fontWeight:'900'},scopeName:{fontFamily:Fonts.sans,fontSize:8.5,lineHeight:12,marginTop:3},selectedLine:{fontFamily:Fonts.mono,fontSize:7.5,lineHeight:12},
  sectionTitle:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'900',marginTop:20,marginBottom:8},form:{borderRadius:Radius.lg,padding:Spacing.three},twoCols:{flexDirection:'row',gap:8},field:{flex:1},label:{fontFamily:Fonts.sans,fontSize:9,marginTop:8,marginBottom:4},input:{borderWidth:1,borderRadius:Radius.md,paddingHorizontal:11,paddingVertical:10,fontFamily:Fonts.mono,fontSize:12},segment:{flexDirection:'row',gap:6},segmentButton:{flex:1,minHeight:38,borderRadius:18,alignItems:'center',justifyContent:'center'},segmentText:{fontFamily:Fonts.sans,fontSize:10,fontWeight:'900',textTransform:'capitalize'},
  buildButton:{minHeight:50,borderRadius:Radius.md,alignItems:'center',justifyContent:'center',marginTop:12},buildText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11.5,fontWeight:'900'},notes:{borderRadius:Radius.md,padding:10,marginTop:8},noteText:{fontFamily:Fonts.mono,fontSize:8.5,lineHeight:14},errorBox:{borderWidth:1,borderRadius:Radius.md,padding:11,marginTop:10},errorText:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15},
  compareScroll:{gap:8,paddingRight:8},compareCard:{width:190,borderRadius:Radius.lg,padding:Spacing.three},compareCountry:{fontFamily:Fonts.mono,fontSize:10,fontWeight:'900'},compareName:{fontFamily:Fonts.sans,fontSize:12,fontWeight:'900',marginTop:3,minHeight:32},compareGrid:{flexDirection:'row',flexWrap:'wrap',justifyContent:'space-between',marginTop:8,rowGap:8},compareValue:{fontFamily:Fonts.mono,fontSize:12,fontWeight:'900'},compareLabel:{fontFamily:Fonts.sans,fontSize:7.5,marginTop:2},compareEvidence:{fontFamily:Fonts.mono,fontSize:8,marginTop:9},compareTop:{fontFamily:Fonts.mono,fontSize:9,fontWeight:'800',marginTop:4},
  summary:{borderRadius:Radius.lg,padding:Spacing.four,marginTop:16},summaryTop:{flexDirection:'row',justifyContent:'space-between'},summaryLabel:{fontFamily:Fonts.sans,fontSize:8.5},summaryStatus:{fontFamily:Fonts.mono,fontSize:12,fontWeight:'900',marginTop:3},summaryNumber:{fontFamily:Fonts.mono,fontSize:17,fontWeight:'900',marginTop:2},summaryMetrics:{flexDirection:'row',justifyContent:'space-between',marginTop:16},summaryValue:{fontFamily:Fonts.mono,fontSize:17,fontWeight:'900'},reasoning:{fontFamily:Fonts.sans,fontSize:9,lineHeight:14,marginTop:8},
  allocation:{borderRadius:Radius.lg,padding:Spacing.three,marginBottom:8},allocationTop:{flexDirection:'row',justifyContent:'space-between'},allocationTicker:{fontFamily:Fonts.mono,fontSize:14,fontWeight:'900'},allocationMeta:{fontFamily:Fonts.mono,fontSize:8.5,marginTop:3},weight:{fontFamily:Fonts.mono,fontSize:15,fontWeight:'900'},allocationMetrics:{flexDirection:'row',flexWrap:'wrap',gap:12,marginTop:10},allocationMetric:{fontFamily:Fonts.mono,fontSize:8.5},factorPositive:{fontFamily:Fonts.sans,fontSize:9,lineHeight:14,marginTop:10,fontWeight:'700'},factorRisk:{fontFamily:Fonts.sans,fontSize:8.7,lineHeight:14,marginTop:4},empty:{borderRadius:Radius.lg,padding:Spacing.four},emptyText:{fontFamily:Fonts.sans,fontSize:10,textAlign:'center'},
  tableScroll:{paddingBottom:4},tableRow:{minWidth:920,flexDirection:'row',alignItems:'center',minHeight:48,paddingHorizontal:8,borderRadius:4,marginBottom:2},tableHeader:{minHeight:38},colStock:{width:145,fontFamily:Fonts.mono,fontSize:8.5,fontWeight:'800'},colSmall:{width:62,fontFamily:Fonts.mono,fontSize:8,textAlign:'center'},colEvidence:{width:72,fontFamily:Fonts.mono,fontSize:8,textAlign:'center',fontWeight:'800'},colAgent:{width:82,fontFamily:Fonts.mono,fontSize:7.8,textAlign:'center'},tableTicker:{fontFamily:Fonts.mono,fontSize:10,fontWeight:'900'},tableMeta:{fontFamily:Fonts.mono,fontSize:7,marginTop:2},
  notice:{borderRadius:Radius.lg,padding:Spacing.four,marginTop:18},noticeTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900'},noticeText:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15,marginTop:5},
});