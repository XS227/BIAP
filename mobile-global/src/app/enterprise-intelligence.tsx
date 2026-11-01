import { ScrollView, Text, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Colors, BottomTabInset } from '@/constants/theme';

const workflows = [
  ['Financial & ERP Intelligence', 'Analyze authorized financial statements, cash flow, receivables and budgets. Highlight missing evidence and unusual movements.'],
  ['AI-Assisted Audit & Risk', 'Identify potential anomalies, control gaps and payment delays for qualified human review. No automated audit opinion.'],
  ['Decision Intelligence & Audit Trail', 'Compare scenarios, document assumptions, uncertainty, supporting evidence and human approval decisions.'],
];
export default function EnterpriseIntelligence() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  return <SafeAreaView style={{flex:1,backgroundColor:colors.background}}><ScrollView contentContainerStyle={{padding:22,paddingBottom:BottomTabInset+32}}>
    <Text style={{fontSize:12,fontWeight:'700',color:'#4385ff'}}>BIAP GLOBAL · ENTERPRISE AI</Text>
    <Text style={{fontSize:25,fontWeight:'800',color:colors.text,marginTop:12}}>Financial Analysis & Audit Decision Support</Text>
    <Text style={{color:colors.textSecondary,lineHeight:21,marginVertical:15}}>Proposed evidence-based enterprise workflows. These are not active ERP integrations or certified audit services.</Text>
    {workflows.map(([title,description],index)=><View key={title} style={{padding:20,marginBottom:12,borderRadius:18,backgroundColor:colors.backgroundElement}}>
      <Text style={{fontSize:11,fontWeight:'700',color:'#4385ff'}}>WORKFLOW 0{index+1}</Text>
      <Text style={{fontSize:19,fontWeight:'800',color:colors.text,marginTop:8}}>{title}</Text>
      <Text style={{fontSize:13,lineHeight:21,color:colors.textSecondary,marginTop:10}}>{description}</Text>
    </View>)}
    <Text style={{color:colors.textSecondary,lineHeight:21,marginTop:8}}>Private company data requires authorization. Investment recommendations and broker execution remain separate. Human review is mandatory for audit decisions.</Text>
  </ScrollView></SafeAreaView>;
}
