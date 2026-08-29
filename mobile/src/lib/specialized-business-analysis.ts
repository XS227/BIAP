import type { BusinessDataset } from '@/lib/business-data';
import type { DemoMetric } from '@/demo/demo-data';

export type SpecializedResult = { summary: string; metrics: DemoMetric[]; bullets: string[]; note?: string };

type NumericSeries = { column: string; values: number[]; avg: number; min: number; max: number; total: number };
const norm=(s:string)=>s.toLowerCase().replace(/[\s_-]/g,'');
const n=(v:unknown)=>{const x=Number(String(v??'').replace(/,/g,''));return Number.isFinite(x)?x:null};
function series(d:BusinessDataset):NumericSeries[]{return d.columns.map(column=>{const values=d.rows.map(r=>n(r[column])).filter((x):x is number=>x!==null);if(values.length<Math.max(2,Math.ceil(d.rows.length*.5)))return null;const total=values.reduce((a,b)=>a+b,0);return{column,values,avg:total/values.length,min:Math.min(...values),max:Math.max(...values),total}}).filter((x):x is NumericSeries=>Boolean(x));}
function find(ss:NumericSeries[],words:string[]){return ss.find(s=>words.some(w=>norm(s.column).includes(norm(w))))}
const fa=(x:number,d=1)=>x.toLocaleString('fa-IR',{maximumFractionDigits:d});
const money=(x:number)=>Math.abs(x)>=1e9?`${fa(x/1e9,2)}B`:Math.abs(x)>=1e6?`${fa(x/1e6,2)}M`:fa(x,2);

export function analyzeSpecialized(key:string,d:BusinessDataset):SpecializedResult|null{
 const ss=series(d); const revenue=find(ss,['revenue','sales','درآمد','فروش']); const cost=find(ss,['cost','expense','هزینه']); const customers=find(ss,['customer','customers','مشتری']); const price=find(ss,['price','قیمت']); const units=find(ss,['unit','quantity','qty','تعداد']); const leads=find(ss,['lead','سرنخ']); const wins=find(ss,['won','closedwon','conversion','فروشموفق']);
 if(key==='financial-model'){
   const profit=revenue&&cost?revenue.total-cost.total:null; const margin=profit!==null&&revenue!.total?profit/revenue!.total:null;
   return{summary:'مدل مالی اختصاصی از ستون‌های درآمد/فروش و هزینه موجود در داده شرکت ساخته می‌شود.',metrics:[{label:'درآمد کل',value:revenue?money(revenue.total):'—'},{label:'هزینه کل',value:cost?money(cost.total):'—'},{label:'حاشیه مشاهده‌شده',value:margin===null?'—':`${fa(margin*100,1)}٪`,tone:margin===null?'neutral':margin>=0?'positive':'negative'}],bullets:[revenue?`ستون درآمد: ${revenue.column}`:'ستون revenue/sales شناسایی نشد.',cost?`ستون هزینه: ${cost.column}`:'ستون cost/expense شناسایی نشد.','هیچ رقم آینده بدون سری زمانی معتبر ساخته نمی‌شود.']};
 }
 if(key==='unit'){
   const volume=units??customers; const unitRevenue=revenue&&volume&&volume.total?revenue.total/volume.total:null; const unitCost=cost&&volume&&volume.total?cost.total/volume.total:null; const contribution=unitRevenue!==null&&unitCost!==null?unitRevenue-unitCost:null;
   return{summary:'Unit Economics با تقسیم مقادیر واقعی درآمد و هزینه بر واحد/مشتری مشاهده‌شده محاسبه می‌شود.',metrics:[{label:'درآمد/واحد',value:unitRevenue===null?'—':money(unitRevenue)},{label:'هزینه/واحد',value:unitCost===null?'—':money(unitCost)},{label:'Contribution',value:contribution===null?'—':money(contribution),tone:contribution===null?'neutral':contribution>=0?'positive':'negative'}],bullets:[volume?`مبنای واحد: ${volume.column}`:'ستون واحد/تعداد/مشتری لازم است.',revenue?`منبع درآمد: ${revenue.column}`:'درآمد شناسایی نشد.',cost?`منبع هزینه: ${cost.column}`:'هزینه شناسایی نشد.']};
 }
 if(key==='pricing'){
   const p=price??(revenue&&units?{...revenue,avg:revenue.total/Math.max(units.total,1)}:null); const spread=p?p.max-p.min:null;
   return{summary:'Pricing از قیمت واقعی یا قیمت ضمنی فروش/تعداد استفاده می‌کند.',metrics:[{label:'قیمت میانگین',value:p?money(p.avg):'—'},{label:'کمینه',value:p?money(p.min):'—'},{label:'دامنه قیمت',value:spread===null?'—':money(spread)}],bullets:[p?`مبنای قیمت: ${p.column}`:'ستون price یا ترکیب sales/quantity لازم است.','دامنه قیمت از داده مشاهده‌شده است؛ قیمت پیشنهادی ساختگی تولید نمی‌شود.']};
 }
 if(key==='crm'||key==='journey'||key==='campaign'){
   const base=leads??customers; const conv=wins&&base&&base.total?wins.total/base.total:null;
   return{summary:'تحلیل CRM/Pipeline بر فیلدهای واقعی مشتری، لید و تبدیل اجرا می‌شود.',metrics:[{label:'حجم مشتری/لید',value:base?fa(base.total,0):'—'},{label:'تبدیل',value:conv===null?'—':`${fa(conv*100,1)}٪`,tone:conv===null?'neutral':conv>=.2?'positive':'neutral'},{label:'فیلدهای داده',value:fa(d.columns.length,0)}],bullets:[base?`مبنای قیف: ${base.column}`:'ستون customer/lead برای قیف لازم است.',wins?`خروجی تبدیل: ${wins.column}`:'ستون conversion/won شناسایی نشد.','نتیجه فقط از فیلدهای موجود ساخته می‌شود.']};
 }
 if(key==='swot'){
   const trends=ss.map(s=>{const m=Math.max(1,Math.floor(s.values.length/2));const a=s.values.slice(0,m).reduce((x,y)=>x+y,0)/m;const b=s.values.slice(m).reduce((x,y)=>x+y,0)/Math.max(1,s.values.slice(m).length);return{column:s.column,change:a?((b-a)/Math.abs(a)):0}}).sort((a,b)=>b.change-a.change);
   return{summary:'SWOT داده‌محور: نقاط قوت/ضعف از روندهای مثبت و منفی قابل‌اندازه‌گیری استخراج می‌شوند؛ Opportunity/Threat بدون داده بیرونی ادعا نمی‌شود.',metrics:[{label:'شاخص عددی',value:fa(ss.length,0)},{label:'قوی‌ترین روند',value:trends[0]?`${fa(trends[0].change*100,1)}٪`:'—',tone:trends[0]?.change>=0?'positive':'negative'},{label:'ضعیف‌ترین روند',value:trends.at(-1)?`${fa((trends.at(-1)?.change??0)*100,1)}٪`:'—',tone:(trends.at(-1)?.change??0)>=0?'positive':'negative'}],bullets:[trends[0]?`Strength candidate: ${trends[0].column}`:'داده عددی کافی نیست.',trends.at(-1)?`Weakness candidate: ${trends.at(-1)?.column}`:'داده عددی کافی نیست.','Opportunity/Threat نیازمند فیلد بازار/رقیب یا منبع بیرونی است.']};
 }
 return null;
}
