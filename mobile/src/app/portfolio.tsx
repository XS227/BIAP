import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { buildGlobalPortfolio, fetchGlobalCountries, GlobalAnalysis, GlobalCountry, GlobalInstrument, GlobalPortfolioResponse, scanGlobalMarket } from '@/lib/global-api';
import { getGlobalMarketSelection, GlobalMarketSelection } from '@/lib/global-market-selection';

type Risk = 'low' | 'medium' | 'high';
type Scope = { country:string; countryName:string; exchange:string; exchangeLabel:string; currency:string; mic?:string|null };
type MarketStat = { key:string; country:string; label:string; qualified:number; deep:number; coverage:number; pass:number; warn:number; block:number; avgScore:number|null; avgConfidence:number|null; top:string };
const PRIORITY = ['US','NO','SE','GB','JP','AU','DE','FR','NL','FI','DK','KR','IR'];
const AGENTS = ['fundamental','risk','forecast','comparison','quality','liquidity'] as const;
const MAX_INPUTS = 50;

const n=(v:number|null|undefined,d=2)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toLocaleString('en-US',{maximumFractionDigits:d});
const pc=(v:number|null|undefined)=>v==null||!Number.isFinite(Number(v))?'—':`${Math.round(Number(v)*100)}%`;
const scopeKey=(m:Scope)=>`${m.country}:${m.exchange}`;
const analysisKey=(a:GlobalAnalysis)=>`${a.country||''}:${a.exchange||''}:${a.ticker||''}`;
const fromSelection=(s:GlobalMarketSelection):Scope=>({country:s.country,countryName:s.countryName,exchange:s.exchange,exchangeLabel:s.exchangeLabel,currency:s.currency,mic:s.mic});
const signal=(a:GlobalAnalysis|undefined,name:string)=>a?.signals?.find(x=>x.agent===name);

function factorText(a:GlobalAnalysis|undefined){
  const list=a?.signals||[];
  const positives=[...list].filter(x=>x.vote>.08&&x.confidence>0).sort((x,y)=>y.vote*y.confidence-x.vote*x.confidence).slice(0,3);
  const negatives=[...list].filter(x=>x.vote<-.08&&x.confidence>0).sort((x,y)=>x.vote*x.confidence-y.vote*y.confidence).slice(0,2);
  return {
    why: positives.length?positives.map(x=>`${x.agent} ${x.vote>=0?'+':''}${x.vote.toFixed(2)}`).join(' • '):'No strong positive factor',
    caution: negatives.length?negatives.map(x=>`${x.agent} ${x.vote.toFixed(2)}`).join(' • '):'No material negative agent vote',
  };
}

function stat(scope:Scope,r:Awaited<ReturnType<typeof scanGlobalMarket>>):MarketStat{
  const deep=r.deepResults||[];
  const scored=deep.filter(x=>x.score!=null&&Number.isFinite(Number(x.score)));
  const confident=deep.filter(x=>x.confidence!=null&&Number.isFinite(Number(x.confidence)));
  const top=[...(r.recommendations||[])].sort((a,b)=>Number(b.score||0)-Number(a.score||0))[0];
  return {key:scopeKey(scope),country:scope.country,label:scope.exchangeLabel,qualified:Number(r.recommendationCount||r.recommendations?.length||0),deep:Number(r.deepAnalyzed||deep.length||0),coverage:Number(r.screeningCoveragePct||0),pass:deep.filter(x=>x.evidence?.status==='PASS').length,warn:deep.filter(x=>x.evidence?.status==='WARN').length,block:deep.filter(x=>x.evidence?.status==='BLOCK').length,avgScore:scored.length?scored.reduce((s,x)=>s+Number(x.score),0)/scored.length:null,avgConfidence:confident.length?confident.reduce((s,x)=>s+Number(x.confidence),0)/confident.length:null,top:top?.ticker||'—'};
}

export default function GlobalPortfolioScreen(){
  const colors=useColorScheme()==='dark'?Colors.dark:Colors.light;
  const[current,setCurrent]=useState<GlobalMarketSelection|null>(null);
  const[countries,setCountries]=useState<GlobalCountry[]>([]);
  const[scopes,setScopes]=useState<Scope[]>([]);
  const[capital,setCapital]=useState('50000'); const[baseCurrency,setBaseCurrency]=useState('EUR');
  const[risk,setRisk]=useState<Risk>('medium'); const[horizon,setHorizon]=useState('5y');
  const[maxPositions,setMaxPositions]=useState('10'); const[cashReserve,setCashReserve]=useState('15');
  const[loading,setLoading]=useState(false); const[refreshing,setRefreshing]=useState(false);
  const[error,setError]=useState(''); const[notes,setNotes]=useState<string[]>([]);
  const[stats,setStats]=useState<MarketStat[]>([]); const[result,setResult]=useState<GlobalPortfolioResponse|null>(null);
  const[candidateCount,setCandidateCount]=useState(0);

  useFocusEffect(useCallback(()=>{Promise.all([getGlobalMarketSelection(),fetchGlobalCountries()]).then(([s,c])=>{setCurrent(s);setCountries(c.countries);setScopes(p=>p.length?p:[fromSelection(s)]);});},[]));

  const options=useMemo(()=>{
    const rows:Scope[]=[]; for(const c of countries)for(const e of c.exchanges)rows.push({country:c.country,countryName:c.name,exchange:e.code,exchangeLabel:e.label,currency:e.currencies[0]||'',mic:e.mic});
    const rank=new Map(PRIORITY.map((x,i)=>[x,i])); const ck=current?`${current.country}:${current.exchange}`:'';
    return rows.sort((a,b)=>scopeKey(a)===ck?-1:scopeKey(b)===ck?1:(rank.get(a.country)??99)-(rank.get(b.country)??99)||a.exchangeLabel.localeCompare(b.exchangeLabel));
  },[countries,current]);

  const toggle=(m:Scope)=>setScopes(prev=>{const exists=prev.some(x=>scopeKey(x)===scopeKey(m));if(exists)return prev.length===1?prev:prev.filter(x=>scopeKey(x)!==scopeKey(m));return prev.length>=4?prev:[...prev,m];});

  const build=async()=>{
    const amount=Number(capital.replace(/,/g,'')); const positions=Math.max(1,Math.min(30,Number(maxPositions)||10)); const reserve=Math.max(0,Math.min(80,Number(cashReserve)||0));
    if(!Number.isFinite(amount)||amount<=0){setError('Enter a positive capital amount.');return}
    if(!/^[A-Za-z]{3}$/.test(baseCurrency.trim())){setError('Base currency must be a 3-letter code such as EUR, USD or NOK.');return}
    setLoading(true);setError('');setResult(null);setNotes([]);setStats([]);setCandidateCount(0);
    try{
      const perMarket=Math.min(50,Math.max(1,Math.floor(MAX_INPUTS/scopes.length)),Math.max(5,Math.ceil(positions*1.5)));
      const scans=await Promise.allSettled(scopes.map(s=>scanGlobalMarket(s.country,s.exchange,perMarket)));
      const instruments:GlobalInstrument[]=[]; const nextStats:MarketStat[]=[]; const nextNotes:string[]=[];
      scans.forEach((r,i)=>{const s=scopes[i];if(r.status==='rejected'){nextNotes.push(`${s.country}/${s.exchange}: scan failed`);return}nextStats.push(stat(s,r.value));nextNotes.push(`${s.country}/${s.exchange}: ${r.value.recommendationCount??0} qualified from ${r.value.deepAnalyzed??0} deep analyses`);for(const x of r.value.recommendations||[]){if(!x.ticker)continue;instruments.push({country:x.country||s.country,exchange:x.exchange||s.exchange,currency:x.currency||s.currency,ticker:x.ticker,name:x.name||x.ticker,isin:x.isin||null,lei:x.lei||null,sector:x.company?.sector||null,industry:x.company?.industry||null,lot_size:x.company?.lot_size||null});}});
      setStats(nextStats);setNotes(nextNotes);
      const unique=[...new Map(instruments.map(x=>[`${x.country}:${x.exchange}:${x.ticker}`,x])).values()].slice(0,MAX_INPUTS); setCandidateCount(unique.length);
      if(!unique.length){setError('No evidence-qualified BUY candidates were found across the selected markets.');return}
      const countryCap=scopes.length<=1?100:Math.max(30,Math.min(60,Math.ceil(140/scopes.length)));
      setResult(await buildGlobalPortfolio({capital:amount,baseCurrency:baseCurrency.trim().toUpperCase(),riskTolerance:risk,horizon:horizon.trim()||'5y',allowedCountries:[...new Set(scopes.map(x=>x.country))],allowedExchanges:[...new Set(scopes.map(x=>x.exchange))],maxPositionPct:Math.min(25,Math.max(3,150/positions)),maxCountryPct:countryCap,maxSectorPct:35,minCashReservePct:reserve,maxPositions:positions},unique));
    }catch(e){setError(e instanceof Error?e.message.slice(0,360):'Portfolio Agent is unavailable.')}finally{setLoading(false);setRefreshing(false)}
  };

  const proposal=result?.proposal; const allocations=proposal?.allocations||[];
  const map=useMemo(()=>new Map((result?.analyses||[]).map(a=>[analysisKey(a),a])),[result]);

  return <SafeAreaView style={[s.safe,{backgroundColor:colors.background}]}><ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={()=>{setRefreshing(true);void build();}} tintColor={Brand.primary}/>} contentContainerStyle={s.content}><View style={s.max}>
    <View style={s.header}><View style={{flex:1}}><Text style={[s.title,{color:colors.text}]}>Global Portfolio Agent</Text><Text style={[s.sub,{color:colors.textSecondary}]}>Compare up to four exchanges, then build one evidence-gated cross-market portfolio.</Text></View><Pressable onPress={()=>router.push('/global')} style={[s.outline,{borderColor:Brand.primary}]}><Text style={s.outlineText}>Market selector</Text></Pressable></View>

    <View style={[s.card,{backgroundColor:colors.backgroundElement}]}><Text style={s.eyebrow}>MULTI-MARKET SCOPE • MAX 4</Text><Text style={[s.cardTitle,{color:colors.text}]}>Choose exchanges</Text><Text style={[s.body,{color:colors.textSecondary}]}>Every selected exchange is screened with the same six scoring agents. Evidence/Verification must PASS before a stock can enter the allocation stage.</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chips}>{options.map(m=>{const active=scopes.some(x=>scopeKey(x)===scopeKey(m));return <Pressable key={scopeKey(m)} onPress={()=>toggle(m)} style={[s.chip,{backgroundColor:active?Brand.primary:colors.backgroundSelected}]}><Text style={[s.chipCode,{color:active?'#fff':colors.text}]}>{m.country}</Text><Text numberOfLines={2} style={[s.chipName,{color:active?'#fff':colors.textSecondary}]}>{m.exchangeLabel}</Text></Pressable>})}</ScrollView><Text style={[s.tiny,{color:colors.textSecondary}]}>Selected: {scopes.map(x=>`${x.country}/${x.exchangeLabel}`).join(' • ')}</Text></View>

    <Text style={[s.section,{color:colors.text}]}>Investor profile</Text><View style={[s.card,{backgroundColor:colors.backgroundElement}]}><View style={s.two}><Field label="Capital" value={capital} onChange={setCapital} colors={colors}/><Field label="Base currency" value={baseCurrency} onChange={setBaseCurrency} colors={colors}/></View><Text style={[s.label,{color:colors.textSecondary}]}>Risk tolerance</Text><View style={s.segment}>{(['low','medium','high'] as Risk[]).map(x=><Pressable key={x} onPress={()=>setRisk(x)} style={[s.segmentBtn,{backgroundColor:risk===x?Brand.primary:colors.backgroundSelected}]}><Text style={{color:risk===x?'#fff':colors.text,fontFamily:Fonts.sans,fontWeight:'800'}}>{x}</Text></Pressable>)}</View><View style={s.two}><Field label="Horizon" value={horizon} onChange={setHorizon} colors={colors}/><Field label="Max positions" value={maxPositions} onChange={setMaxPositions} colors={colors}/></View><Field label="Minimum cash reserve (%)" value={cashReserve} onChange={setCashReserve} colors={colors}/></View>

    <Pressable disabled={loading||!scopes.length} onPress={()=>{void build();}} style={[s.primary,{backgroundColor:Brand.primary,opacity:loading?0.65:1}]}>{loading?<ActivityIndicator color="#fff"/>:<Text style={s.primaryText}>Compare markets and build global portfolio</Text>}</Pressable>
    {notes.length?<View style={[s.card,{backgroundColor:colors.backgroundElement,marginTop:8}]}>{notes.map(x=><Text key={x} style={[s.tiny,{color:colors.textSecondary}]}>• {x}</Text>)}</View>:null}
    {error?<Text style={[s.error,{color:Brand.warning}]}>{error}</Text>:null}

    {stats.length?<><Text style={[s.section,{color:colors.text}]}>Market comparison</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chips}>{stats.map(x=><View key={x.key} style={[s.marketCard,{backgroundColor:colors.backgroundElement}]}><Text style={s.eyebrow}>{x.country}</Text><Text style={[s.marketName,{color:colors.text}]}>{x.label}</Text><Text style={[s.marketLine,{color:colors.textSecondary}]}>Qualified {x.qualified} • Deep {x.deep}</Text><Text style={[s.marketLine,{color:colors.textSecondary}]}>Avg score {n(x.avgScore,3)} • Conf. {pc(x.avgConfidence)}</Text><Text style={[s.marketLine,{color:colors.textSecondary}]}>Evidence P/W/B {x.pass}/{x.warn}/{x.block}</Text><Text style={[s.marketTop,{color:colors.text}]}>Top candidate: {x.top}</Text></View>)}</ScrollView></>:null}

    {proposal?<><View style={[s.card,{backgroundColor:colors.backgroundElement,marginTop:18}]}><View style={s.between}><View><Text style={[s.label,{color:colors.textSecondary}]}>PROPOSAL STATUS</Text><Text style={[s.status,{color:proposal.status==='NO_RECOMMENDATION'?Brand.warning:Brand.positive}]}>{proposal.status||'—'}</Text></View><View style={{alignItems:'flex-end'}}><Text style={[s.label,{color:colors.textSecondary}]}>QUALIFIED INPUTS</Text><Text style={[s.big,{color:colors.text}]}>{candidateCount}</Text></View></View><Text style={[s.body,{color:colors.textSecondary}]}>Invested {n(proposal.invested_pct,1)}% • Cash {n(proposal.cash_pct,1)}% • Positions {allocations.length}</Text></View>

      <Text style={[s.section,{color:colors.text}]}>Proposed allocations</Text>{allocations.map((x,i)=>{const a=map.get(`${x.country||''}:${x.exchange||''}:${x.ticker||''}`);const f=factorText(a);return <View key={`${x.identity}-${i}`} style={[s.card,{backgroundColor:colors.backgroundElement,marginBottom:8}]}><View style={s.between}><View><Text style={[s.allocTicker,{color:colors.text}]}>#{i+1} {x.ticker}</Text><Text style={[s.tiny,{color:colors.textSecondary}]}>{x.country} • {x.exchange} • {x.currency}</Text></View><Text style={[s.weight,{color:Brand.primary}]}>{n(x.weight_pct,1)}%</Text></View><Text style={[s.tiny,{color:colors.textSecondary}]}>Amount {n(x.amount_base_currency)} {baseCurrency.toUpperCase()} • Score {n(x.score,3)} • Confidence {pc(x.confidence)}</Text><Text style={[s.why,{color:Brand.positive}]}>Why selected: {f.why}</Text><Text style={[s.caution,{color:f.caution.startsWith('No material')?colors.textSecondary:Brand.warning}]}>Remaining cautions: {f.caution}</Text></View>})}

      {allocations.length?<><Text style={[s.section,{color:colors.text}]}>Final analytical summary</Text><ScrollView horizontal showsHorizontalScrollIndicator={false}><View><View style={[s.row,s.rowHead,{backgroundColor:colors.backgroundSelected}]}><Cell w={145}>Stock / Market</Cell><Cell>Weight</Cell><Cell>Score</Cell><Cell>Conf.</Cell><Cell w={74}>Evidence</Cell>{AGENTS.map(a=><Cell key={a} w={82}>{a}</Cell>)}</View>{allocations.map((x,i)=>{const a=map.get(`${x.country||''}:${x.exchange||''}:${x.ticker||''}`);return <View key={`r-${i}`} style={[s.row,{backgroundColor:i%2?colors.backgroundElement:colors.background}]}><View style={{width:145}}><Text style={[s.rowTicker,{color:colors.text}]}>{x.ticker}</Text><Text style={[s.rowMeta,{color:colors.textSecondary}]}>{x.country}/{x.exchange}</Text></View><Cell>{n(x.weight_pct,1)}%</Cell><Cell>{n(x.score,2)}</Cell><Cell>{pc(x.confidence)}</Cell><Cell w={74} color={a?.evidence?.status==='PASS'?Brand.positive:Brand.warning}>{a?.evidence?.status||'—'}</Cell>{AGENTS.map(name=>{const z=signal(a,name);return <Cell key={name} w={82} color={z&&z.vote>=.2?Brand.positive:z&&z.vote<=-.2?Brand.negative:colors.textSecondary}>{z?`${z.vote>=0?'+':''}${z.vote.toFixed(2)}`:'—'}</Cell>})}</View>})}</View></ScrollView></>:null}
      {result?.fxErrors&&Object.keys(result.fxErrors).length?<Text style={[s.error,{color:Brand.warning}]}>FX unavailable: {Object.entries(result.fxErrors).map(([k,v])=>`${k}: ${v}`).join(' • ')}</Text>:null}
    </>:null}

    <View style={[s.card,{backgroundColor:colors.backgroundElement,marginTop:18}]}><Text style={[s.cardTitle,{color:colors.text}]}>Decision support, paper first</Text><Text style={[s.body,{color:colors.textSecondary}]}>Missing, stale or conflicting evidence can remove a stock entirely. This build proposes research allocations only and does not submit live broker orders.</Text></View>
  </View></ScrollView></SafeAreaView>;
}

function Field({label,value,onChange,colors}:{label:string;value:string;onChange:(v:string)=>void;colors:typeof Colors.light|typeof Colors.dark}){return <View style={{flex:1}}><Text style={[s.label,{color:colors.textSecondary}]}>{label}</Text><TextInput value={value} onChangeText={onChange} autoCapitalize="characters" style={[s.input,{color:colors.text,borderColor:colors.backgroundSelected}]}/></View>}
function Cell({children,w=62,color}:{children:React.ReactNode;w?:number;color?:string}){return <Text style={[s.cell,{width:w,color:color||'#9aa4b2'}]}>{children}</Text>}

const s=StyleSheet.create({safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingBottom:BottomTabInset+Spacing.six},max:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},header:{flexDirection:'row',alignItems:'center',gap:10,paddingTop:Spacing.four,paddingBottom:Spacing.three},title:{fontFamily:Fonts.sans,fontSize:24,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:10,lineHeight:15,marginTop:3},outline:{borderWidth:1,borderRadius:20,paddingHorizontal:10,paddingVertical:8},outlineText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:9,fontWeight:'900'},card:{borderRadius:Radius.lg,padding:Spacing.three},eyebrow:{color:Brand.primary,fontFamily:Fonts.mono,fontSize:8,fontWeight:'900'},cardTitle:{fontFamily:Fonts.sans,fontSize:14,fontWeight:'900',marginTop:4},body:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15,marginTop:5},chips:{gap:7,paddingVertical:10,paddingRight:6},chip:{width:118,borderRadius:Radius.md,padding:9},chipCode:{fontFamily:Fonts.mono,fontSize:11,fontWeight:'900'},chipName:{fontFamily:Fonts.sans,fontSize:8,lineHeight:11,marginTop:3},tiny:{fontFamily:Fonts.mono,fontSize:8,lineHeight:13},section:{fontFamily:Fonts.sans,fontSize:15,fontWeight:'900',marginTop:19,marginBottom:8},two:{flexDirection:'row',gap:8},label:{fontFamily:Fonts.sans,fontSize:8.5,marginTop:7,marginBottom:4},input:{borderWidth:1,borderRadius:Radius.md,paddingHorizontal:10,paddingVertical:9,fontFamily:Fonts.mono,fontSize:11},segment:{flexDirection:'row',gap:6},segmentBtn:{flex:1,minHeight:36,borderRadius:18,alignItems:'center',justifyContent:'center'},primary:{minHeight:49,borderRadius:Radius.md,alignItems:'center',justifyContent:'center',marginTop:12},primaryText:{color:'#fff',fontFamily:Fonts.sans,fontSize:11,fontWeight:'900'},error:{fontFamily:Fonts.sans,fontSize:9.5,lineHeight:15,marginTop:9},marketCard:{width:190,borderRadius:Radius.lg,padding:Spacing.three},marketName:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'900',marginTop:3,minHeight:28},marketLine:{fontFamily:Fonts.mono,fontSize:7.8,marginTop:5},marketTop:{fontFamily:Fonts.mono,fontSize:8.5,fontWeight:'800',marginTop:7},between:{flexDirection:'row',justifyContent:'space-between',alignItems:'flex-start'},status:{fontFamily:Fonts.mono,fontSize:11,fontWeight:'900',marginTop:3},big:{fontFamily:Fonts.mono,fontSize:16,fontWeight:'900'},allocTicker:{fontFamily:Fonts.mono,fontSize:13,fontWeight:'900'},weight:{fontFamily:Fonts.mono,fontSize:15,fontWeight:'900'},why:{fontFamily:Fonts.sans,fontSize:8.8,lineHeight:14,marginTop:10,fontWeight:'700'},caution:{fontFamily:Fonts.sans,fontSize:8.5,lineHeight:14,marginTop:4},row:{minWidth:920,flexDirection:'row',alignItems:'center',minHeight:46,paddingHorizontal:7,marginBottom:2},rowHead:{minHeight:36},cell:{fontFamily:Fonts.mono,fontSize:7.6,textAlign:'center'},rowTicker:{fontFamily:Fonts.mono,fontSize:9.5,fontWeight:'900'},rowMeta:{fontFamily:Fonts.mono,fontSize:6.8,marginTop:2}});