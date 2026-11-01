import { ScrollView, Text, View, useColorScheme, SafeAreaView } from 'react-native';
import { Colors, BottomTabInset } from '@/constants/theme';
const workflows = [
  ['هوش مالی و ERP', 'تحلیل صورت‌های مالی، مطالبات، جریان نقد و بودجه بر پایه داده‌های مجاز و قابل استناد.'],
  ['حسابرسی هوشمند و ارزیابی ریسک', 'شناسایی ناهنجاری‌ها، ضعف کنترل‌های داخلی و شواهد ناقص برای بررسی حسابرس انسانی.'],
  ['هوش تصمیم‌گیری و ردپای حسابرسی', 'مقایسه سناریوها و ثبت فرضیات، عدم‌قطعیت، مستندات و تأیید تصمیم‌ها.'],
];
export default function EnterpriseIntelligence() {
 const colors=useColorScheme()==='dark'?Colors.dark:Colors.light;
 return <SafeAreaView style={{flex:1,backgroundColor:colors.background}}><ScrollView contentContainerStyle={{padding:22,paddingBottom:BottomTabInset+32}}>
 <Text style={{fontSize:12,fontWeight:'700',color:'#4385ff',textAlign:'right'}}>BIAP IRAN · هوش سازمانی</Text>
 <Text style={{fontSize:25,fontWeight:'800',color:colors.text,marginTop:12,textAlign:'right'}}>تحلیل مالی و پشتیبانی از تصمیم‌های حسابرسی</Text>
 <Text style={{color:colors.textSecondary,lineHeight:24,marginVertical:15,textAlign:'right'}}>سه مسیر پیشنهادی برای تحلیل مبتنی بر شواهد. این بخش هنوز به ERP متصل نیست و جایگزین اظهار نظر رسمی حسابرس نمی‌شود.</Text>
 {workflows.map(([title,description],index)=><View key={title} style={{padding:20,marginBottom:12,borderRadius:18,backgroundColor:colors.backgroundElement}}>
 <Text style={{fontSize:11,fontWeight:'700',color:'#4385ff',textAlign:'right'}}>مسیر {index+1}</Text>
 <Text style={{fontSize:19,fontWeight:'800',color:colors.text,marginTop:8,textAlign:'right'}}>{title}</Text>
 <Text style={{fontSize:13,lineHeight:23,color:colors.textSecondary,marginTop:10,textAlign:'right'}}>{description}</Text>
 </View>)}
 <Text style={{color:colors.textSecondary,lineHeight:23,marginTop:8,textAlign:'right'}}>استفاده از داده‌های خصوصی شرکت نیازمند مجوز است. تحلیل حسابرسی به بررسی و تأیید متخصص انسانی نیاز دارد و از معاملات سهام جداست.</Text>
 </ScrollView></SafeAreaView>;
}
