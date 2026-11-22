import { useCallback, useState } from 'react';
import { Alert, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { fetchGlobalStatus, fetchGlobalBrokerReadiness, type GlobalBrokerIntegration } from '@/lib/global-api';
import { getGlobalMarketSelection, type GlobalMarketSelection } from '@/lib/global-market-selection';
import { getSelectedGlobalCompany, selectedGlobalCompanyMatchesMarket } from '@/lib/global-company-selection';
import { validatePaperTicket, paperTicketLabel, type PaperDraft, type PaperDraftFields } from '@/lib/global-paper-order';
import { listGlobalPaperDrafts, saveGlobalPaperDraft, clearGlobalPaperDrafts } from '@/lib/global-paper-draft-store';


const PLANNED_BROKERS = [
  { id: 'ibkr', name: 'Interactive Brokers', marketScope: 'Multiple markets (subject to permission)', onboardingDocs: 'https://ibkrcampus.eu/docs/web-api/trading/getting-started/trading-access-for-third-parties', usEquitiesOnly: false },
  { id: 'saxo', name: 'Saxo Bank', marketScope: 'Multiple markets (subject to permission)', onboardingDocs: 'https://www.developer.saxo/openapi/learn/other-clients-or-partners-request-for-openapi-application-credentials-for-the-l', usEquitiesOnly: false },
  { id: 'alpaca', name: 'Alpaca', marketScope: 'US equities (partner approval required)', onboardingDocs: 'https://docs.alpaca.markets/us/docs/using-oauth2-and-trading-api', usEquitiesOnly: true },
] as const;

export default function GlobalExecutionScreen(){
  const colors=useColorScheme()==='dark'?Colors.dark:Colors.light;
  const params=useLocalSearchParams<{ country?:string; ticker?:string }>();
  const[market,setMarket]=useState<GlobalMarketSelection|null>(null);const[status,setStatus]=useState<Record<string,unknown>|null>(null);
  const[brokerData,setBrokerData]=useState<GlobalBrokerIntegration[]|null>(null);
  const[brokerId,setBrokerId]=useState<'ibkr'|'saxo'|'alpaca'>('ibkr');
  const[side,setSide]=useState<'BUY'|'SELL'>('BUY');
  const[ticker,setTicker]=useState('');
  const[quantity,setQuantity]=useState('1');
  const[limitPrice,setLimitPrice]=useState('');
  const[preview,setPreview]=useState<string|null>(null);
  const[previewError,setPreviewError]=useState<string|null>(null);
  const[draftFields,setDraftFields]=useState<PaperDraftFields|null>(null);
  const[recentDrafts,setRecentDrafts]=useState<PaperDraft[]>([]);
  const[saveState,setSaveState]=useState<string|null>(null);
  const[sourceNotice,setSourceNotice]=useState<string|null>(null);

  useFocusEffect(useCallback(()=>{
    let active=true;
    Promise.all([getGlobalMarketSelection(),fetchGlobalStatus(),fetchGlobalBrokerReadiness(),getSelectedGlobalCompany(),listGlobalPaperDrafts()])
      .then(([m,s,b,selected,drafts])=>{
        if(!active)return;
        setMarket(m);setStatus(s);setBrokerData(b?.providers||null);setRecentDrafts(drafts);
        const fromRoute=params.ticker?.trim().toUpperCase();
        const routeCountry=params.country?.trim().toUpperCase();
        if(fromRoute && routeCountry && routeCountry !== m.country){
          setSourceNotice('This company belongs to a different market. Change the active market before creating a ticket.');
          setTicker('');
        }else if(fromRoute){
          setSourceNotice(null);setTicker(fromRoute);
        }else if(selected && selectedGlobalCompanyMatchesMarket(selected,m)){
          setSourceNotice(null);setTicker(selected.ticker.toUpperCase());
        }
      }).catch(()=>{if(active)setSourceNotice('Could not load all saved draft details.');});
    return()=>{active=false};
  },[params.country,params.ticker]));
  const liveBroker=Boolean(status?.liveBrokerConnected);const liveTrading=Boolean(status?.liveTrading);const switchRequested=Boolean(status?.liveTradingSwitchRequested);
  const brokers = PLANNED_BROKERS.map((known)=>({
    ...known, serverStatus: brokerData?.find((entry)=>entry.id===known.id)?.connectionStatus||'NOT_CONNECTED'
  }));
  const draftPreview = () => {
    setPreview(null);setPreviewError(null);setSaveState(null);setDraftFields(null);
    const result=validatePaperTicket({
      brokerId,side,ticker,quantity,limitPrice,
      country:market?.country||'',exchange:market?.exchange||'',currency:market?.currency||'',
      micCode:market?.mic||null,
    });
    if(!result.ok){setPreviewError(result.error);return;}
    setDraftFields(result.value);
    setPreview(paperTicketLabel(result.value)+' · Prospective broker '+PLANNED_BROKERS.find((b)=>b.id===brokerId)?.name+'. NOT SUBMITTED.');
  };

  const saveDraft = async () => {
    if(!draftFields)return;
    try{
      await saveGlobalPaperDraft(draftFields);
      setRecentDrafts(await listGlobalPaperDrafts());
      setSaveState('Saved on this device as an UNSENT research draft. No shares were bought or sold.');
      setDraftFields(null);
    }catch{
      setSaveState('Saving failed. No order was sent.');
    }
  };

  const clearDrafts = () => Alert.alert('Delete local paper drafts?','This only removes this device’s unsent drafts; it does not affect a brokerage account.',[
    {text:'Cancel',style:'cancel'},
    {text:'Delete',style:'destructive',onPress:()=>{
      void clearGlobalPaperDrafts().then(()=>{setRecentDrafts([]);setSaveState('Local drafts deleted.');})
        .catch(()=>setSaveState('Could not delete local drafts.'));
    }},
  ]);

  return <SafeAreaView style={[styles.safe,{backgroundColor:colors.background}]}><ScrollView contentContainerStyle={styles.content}><View style={styles.max}>
    <View style={styles.header}><Pressable onPress={()=>router.back()} style={[styles.back,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.backText,{color:colors.text}]}>← Back</Text></Pressable><View style={{flex:1}}><Text style={[styles.title,{color:colors.text}]}>Orders & Execution</Text><Text style={[styles.sub,{color:colors.textSecondary}]}>Global execution is isolated from the Iran order history and broker paths.</Text></View></View>

    <View style={[styles.hero,{backgroundColor:colors.backgroundElement}]}><Text style={styles.eyebrow}>ACTIVE MARKET</Text><Text style={[styles.market,{color:colors.text}]}>{market?`${market.countryName} • ${market.exchangeLabel}`:'Loading…'}</Text><Text style={[styles.meta,{color:colors.textSecondary}]}>{market?`${market.mic||market.exchange} • ${market.currency}`:''}</Text></View>

    <View style={styles.statusGrid}><View style={[styles.statusCard,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.statusValue,{color:Brand.positive}]}>PAPER</Text><Text style={[styles.statusLabel,{color:colors.textSecondary}]}>Current execution mode</Text></View><View style={[styles.statusCard,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.statusValue,{color:liveBroker?Brand.positive:colors.textSecondary}]}>{liveBroker?'CONNECTED':'NONE'}</Text><Text style={[styles.statusLabel,{color:colors.textSecondary}]}>Live broker</Text></View><View style={[styles.statusCard,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.statusValue,{color:liveTrading?Brand.positive:Brand.warning}]}>{liveTrading?'ON':'OFF'}</Text><Text style={[styles.statusLabel,{color:colors.textSecondary}]}>Live trading</Text></View></View>

    <View style={[styles.card,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.cardTitle,{color:colors.text}]}>Why there are no Global live orders here yet</Text><Text style={[styles.body,{color:colors.textSecondary}]}>BIAP Global can analyze markets and construct a paper portfolio, but sending an order requires a market-aware broker adapter, contract identifiers, trading permissions, lot sizes, fees, FX, audit logging and final risk checks. The Iran Paper/Order history is intentionally not reused for Global markets.</Text></View>

    <View style={[styles.flow,{backgroundColor:colors.backgroundElement}]}><Text style={[styles.cardTitle,{color:colors.text}]}>Execution pipeline</Text>{['Kiasha / Stock Analysis','Evidence + Risk Gate','Portfolio Agent','Paper Order Draft','Human Approval','Future Regulated Broker Adapter'].map((item,index)=><View key={item} style={styles.step}><View style={[styles.number,{backgroundColor:index<4?Brand.primary:colors.backgroundSelected}]}><Text style={styles.numberText}>{index+1}</Text></View><Text style={[styles.stepText,{color:colors.text}]}>{item}</Text></View>)}</View>

    {switchRequested&&!liveTrading?<View style={[styles.warning,{borderColor:Brand.warning}]}><Text style={[styles.warningTitle,{color:Brand.warning}]}>Live switch requested but not enabled</Text><Text style={[styles.body,{color:colors.textSecondary}]}>The backend still reports liveTrading=false. BIAP will not bypass this gate.</Text></View>:null}


    <View style={[styles.card,{backgroundColor:colors.backgroundElement}]}>
      <Text style={[styles.cardTitle,{color:colors.text}]}>Broker partners · research / onboarding</Text>
      <Text style={[styles.body,{color:colors.textSecondary}]}>Three API candidates; none is connected. Account opening, investment services, client consent and trading permissions require formal approvals. Paper preview is local, not broker paper trading.</Text>
      {brokers.map((broker)=><View key={broker.id} style={[styles.partner,{borderColor:colors.textSecondary}]}>
        <Text style={[styles.partnerName,{color:colors.text}]}>{broker.name}</Text>
        <Text style={[styles.partnerMeta,{color:Brand.warning}]}>{broker.serverStatus === 'NOT_CONNECTED' ? 'NOT CONNECTED · APPLICATION / APPROVAL REQUIRED' : 'SERVER STATUS: '+broker.serverStatus+' · VERIFY PERMISSIONS'}</Text>
        <Text style={[styles.body,{color:colors.textSecondary}]}>{broker.marketScope}</Text>
        <Pressable accessibilityRole="link" onPress={()=>void Linking.openURL(broker.onboardingDocs)}><Text style={[styles.partnerLink,{color:Brand.primary}]}>Official API partnership requirements ↗</Text></Pressable>
      </View>)}
    </View>

    <View style={[styles.card,{backgroundColor:colors.backgroundElement}]}>
      <Text style={[styles.cardTitle,{color:colors.text}]}>Buy / sell · paper order preview</Text>
      <Text style={[styles.body,{color:colors.textSecondary}]}>Research form only. No bank connection, money movement, portfolio holdings or order execution. Type your own indicative price; it is NOT a live quote. Fees, FX, spreads and taxes are excluded.</Text>
      {sourceNotice?<Text style={[styles.body,{color:Brand.warning}]}>{sourceNotice}</Text>:null}
      <Text style={[styles.fieldLabel,{color:colors.text}]}>Prospective broker</Text>
      <View style={styles.choiceRow}>{PLANNED_BROKERS.map((b)=><Pressable key={b.id} onPress={()=>{setBrokerId(b.id);setPreview(null);setDraftFields(null);setSaveState(null);}} style={[styles.choice,{borderColor:brokerId===b.id?Brand.primary:colors.textSecondary,backgroundColor:brokerId===b.id?colors.backgroundSelected:colors.background}]}><Text style={[styles.choiceLabel,{color:colors.text}]}>{b.name.split(' ')[0]}</Text></Pressable>)}</View>
      <Text style={[styles.fieldLabel,{color:colors.text}]}>Transaction</Text>
      <View style={styles.choiceRow}>{(['BUY','SELL'] as const).map((s)=><Pressable key={s} onPress={()=>{setSide(s);setPreview(null);setDraftFields(null);setSaveState(null);}} style={[styles.choice,{borderColor:side===s?Brand.primary:colors.textSecondary,backgroundColor:side===s?colors.backgroundSelected:colors.background}]}><Text style={[styles.choiceLabel,{color:colors.text}]}>{s}</Text></Pressable>)}</View>
      <Text style={[styles.fieldLabel,{color:colors.text}]}>Ticker</Text>
      <TextInput value={ticker} onChangeText={(value)=>{setTicker(value);setPreview(null);setDraftFields(null);setSaveState(null);}} autoCapitalize="characters" placeholder="e.g. AAPL" placeholderTextColor={colors.textSecondary} style={[styles.textField,{color:colors.text,borderColor:colors.textSecondary}]} maxLength={16}/>
      <Text style={[styles.fieldLabel,{color:colors.text}]}>Whole shares</Text>
      <TextInput value={quantity} onChangeText={(value)=>{setQuantity(value);setPreview(null);setDraftFields(null);setSaveState(null);}} keyboardType="number-pad" placeholder="1" placeholderTextColor={colors.textSecondary} style={[styles.textField,{color:colors.text,borderColor:colors.textSecondary}]} maxLength={6}/>
      <Text style={[styles.fieldLabel,{color:colors.text}]}>Indicative limit price ({market?.currency||'market currency'})</Text>
      <TextInput value={limitPrice} onChangeText={(value)=>{setLimitPrice(value);setPreview(null);setDraftFields(null);setSaveState(null);}} keyboardType="decimal-pad" placeholder="e.g. 100.00" placeholderTextColor={colors.textSecondary} style={[styles.textField,{color:colors.text,borderColor:colors.textSecondary}]} maxLength={13}/>
      <Pressable accessibilityRole="button" onPress={draftPreview} style={[styles.primary,{backgroundColor:Brand.primary}]}><Text style={styles.primaryText}>Preview only · NEVER SEND ORDER</Text></Pressable>
      {previewError?<Text style={[styles.body,{color:Brand.warning}]}>{previewError}</Text>:null}
      {preview?<View style={[styles.warning,{borderColor:Brand.warning}]}><Text style={[styles.warningTitle,{color:Brand.warning}]}>PREVIEW ONLY — NO BROKER ORDER</Text><Text style={[styles.body,{color:colors.text}]}>{preview}</Text></View>:null}
      {preview&&draftFields?<Pressable accessibilityRole="button" onPress={()=>void saveDraft()} style={[styles.secondary,{borderColor:Brand.primary}]}><Text style={styles.secondaryText}>Save UNSENT paper draft on this device</Text></Pressable>:null}
      {saveState?<Text style={[styles.body,{color:colors.textSecondary}]}>{saveState}</Text>:null}
    </View>

    <View style={[styles.card,{backgroundColor:colors.backgroundElement}]}>
      <Text style={[styles.cardTitle,{color:colors.text}]}>Recent paper drafts · this device only</Text>
      <Text style={[styles.body,{color:colors.textSecondary}]}>Unsent research tickets, not filled orders or positions. Not synchronized with any broker or BIAP account.</Text>
      {recentDrafts.length===0?<Text style={[styles.body,{color:colors.textSecondary}]}>No saved drafts yet.</Text>:recentDrafts.slice(0,5).map((draft)=><View key={draft.id} style={[styles.partner,{borderColor:colors.textSecondary}]}>
        <Text style={[styles.partnerName,{color:colors.text}]}>{draft.side} {draft.quantity} × {draft.ticker} · {draft.currency} {draft.indicativeNotional.toLocaleString('en-US',{maximumFractionDigits:2})}</Text>
        <Text style={[styles.partnerMeta,{color:Brand.warning}]}>UNSENT · DEVICE DRAFT</Text>
        <Text style={[styles.body,{color:colors.textSecondary}]}>{draft.country} / {draft.exchange} · {draft.brokerId.toUpperCase()} · {draft.createdAt.slice(0,10)}</Text>
      </View>)}
      {recentDrafts.length>0?<Pressable accessibilityRole="button" onPress={clearDrafts} style={[styles.secondary,{borderColor:colors.textSecondary}]}><Text style={[styles.secondaryText,{color:colors.textSecondary}]}>Clear device drafts</Text></Pressable>:null}
    </View>

    <Pressable onPress={()=>router.push('/portfolio')} style={[styles.primary,{backgroundColor:Brand.primary}]}><Text style={styles.primaryText}>Build a Global paper portfolio</Text></Pressable><Pressable onPress={()=>router.push('/market')} style={[styles.secondary,{borderColor:Brand.primary}]}><Text style={styles.secondaryText}>Open Market</Text></Pressable>

    <Text style={[styles.disclaimer,{color:colors.textSecondary}]}>No live order is transmitted from this screen. A future Global broker integration must be explicit and separate from the Iran production execution path.</Text>
  </View></ScrollView></SafeAreaView>;
}

const styles=StyleSheet.create({partner:{borderWidth:1,borderRadius:12,padding:12,marginTop:12},partnerName:{fontSize:14,fontFamily:Fonts.sans,fontWeight:'800'},partnerMeta:{fontSize:9,fontFamily:Fonts.mono,fontWeight:'900',marginTop:4},partnerLink:{fontSize:10,fontFamily:Fonts.sans,fontWeight:'700',marginTop:8},choiceRow:{flexDirection:'row',gap:8,marginTop:7},choice:{flex:1,borderWidth:1,borderRadius:9,minHeight:40,alignItems:'center',justifyContent:'center',paddingHorizontal:5},choiceLabel:{fontSize:10,fontFamily:Fonts.sans,fontWeight:'800'},fieldLabel:{fontSize:11,fontFamily:Fonts.sans,fontWeight:'800',marginTop:14},textField:{borderWidth:1,borderRadius:10,paddingHorizontal:12,minHeight:44,fontSize:14,fontFamily:Fonts.sans,marginTop:6},safe:{flex:1},content:{paddingHorizontal:Spacing.three,paddingBottom:BottomTabInset+Spacing.six},max:{maxWidth:MaxContentWidth,width:'100%',alignSelf:'center'},header:{flexDirection:'row',alignItems:'flex-start',gap:12,paddingTop:Spacing.four,paddingBottom:Spacing.three},back:{paddingHorizontal:11,paddingVertical:8,borderRadius:18},backText:{fontFamily:Fonts.sans,fontSize:10,fontWeight:'800'},title:{fontFamily:Fonts.sans,fontSize:22,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:10,lineHeight:15,marginTop:3},hero:{borderRadius:Radius.lg,padding:Spacing.four},eyebrow:{color:Brand.primary,fontFamily:Fonts.mono,fontSize:8.5,fontWeight:'900'},market:{fontFamily:Fonts.sans,fontSize:17,fontWeight:'900',marginTop:5},meta:{fontFamily:Fonts.mono,fontSize:9,marginTop:3},statusGrid:{flexDirection:'row',gap:8,marginTop:10},statusCard:{flex:1,borderRadius:Radius.md,paddingVertical:14,paddingHorizontal:6,alignItems:'center'},statusValue:{fontFamily:Fonts.mono,fontSize:12,fontWeight:'900',textAlign:'center'},statusLabel:{fontFamily:Fonts.sans,fontSize:8,textAlign:'center',marginTop:4},card:{borderRadius:Radius.lg,padding:Spacing.four,marginTop:14},cardTitle:{fontFamily:Fonts.sans,fontSize:13,fontWeight:'900'},body:{fontFamily:Fonts.sans,fontSize:10,lineHeight:16,marginTop:6},flow:{borderRadius:Radius.lg,padding:Spacing.four,marginTop:12},step:{flexDirection:'row',alignItems:'center',gap:10,marginTop:10},number:{width:26,height:26,borderRadius:13,alignItems:'center',justifyContent:'center'},numberText:{color:'#fff',fontFamily:Fonts.mono,fontSize:9,fontWeight:'900'},stepText:{fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'700'},warning:{borderWidth:1,borderRadius:Radius.md,padding:12,marginTop:12},warningTitle:{fontFamily:Fonts.sans,fontSize:11,fontWeight:'900'},primary:{minHeight:48,borderRadius:Radius.md,alignItems:'center',justifyContent:'center',marginTop:14},primaryText:{color:'#fff',fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'900'},secondary:{minHeight:46,borderRadius:Radius.md,borderWidth:1,alignItems:'center',justifyContent:'center',marginTop:8},secondaryText:{color:Brand.primary,fontFamily:Fonts.sans,fontSize:10.5,fontWeight:'900'},disclaimer:{fontFamily:Fonts.sans,fontSize:8.5,lineHeight:14,textAlign:'center',marginTop:18}});