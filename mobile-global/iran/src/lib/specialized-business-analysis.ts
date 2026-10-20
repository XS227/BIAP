import type { BusinessDataset } from '@/lib/business-data';
import type { DemoMetric } from '@/demo/demo-data';

export type SpecializedResult = { summary: string; metrics: DemoMetric[]; bullets: string[]; note?: string };

type NumericSeries = { column: string; values: number[]; avg: number; min: number; max: number; total: number };
const norm=(s:string)=>s.toLowerCase().replace(/[\s_\-()%]/g,'').replace(/ي/g,'ی').replace(/ك/g,'ک');
const n=(v:unknown)=>{const x=Number(String(v??'').replace(/,/g,''));return Number.isFinite(x)?x:null};
function series(d:BusinessDataset):NumericSeries[]{return d.columns.map(column=>{const values=d.rows.map(r=>n(r[column])).filter((x):x is number=>x!==null);if(values.length<Math.max(2,Math.ceil(d.rows.length*.5)))return null;const total=values.reduce((a,b)=>a+b,0);return{column,values,avg:total/values.length,min:Math.min(...values),max:Math.max(...values),total}}).filter((x):x is NumericSeries=>Boolean(x));}
function find(ss:NumericSeries[],words:string[]){return ss.find(s=>words.some(w=>norm(s.column).includes(norm(w))))}
function col(d:BusinessDataset,words:string[]){return d.columns.find(c=>words.some(w=>norm(c).includes(norm(w))))}
const fa=(x:number,d=1)=>x.toLocaleString('fa-IR',{maximumFractionDigits:d});
const money=(x:number)=>Math.abs(x)>=1e9?`${fa(x/1e9,2)}B`:Math.abs(x)>=1e6?`${fa(x/1e6,2)}M`:fa(x,2);
const text=(v:unknown)=>String(v??'').trim();
const clamp=(x:number,min=0,max=1)=>Math.max(min,Math.min(max,x));

export function analyzeSpecialized(key:string,d:BusinessDataset):SpecializedResult|null{
 const ss=series(d); const revenue=find(ss,['revenue','sales','درآمد','فروش']); const cost=find(ss,['cost','expense','هزینه']); const customers=find(ss,['customer','customers','مشتری']); const price=find(ss,['price','قیمت']); const units=find(ss,['unit','quantity','qty','تعداد']); const leads=find(ss,['lead','سرنخ']); const wins=find(ss,['won','closedwon','conversion','فروشموفق']);
 const probabilityCol=col(d,['probability','احتمال','احتمالبستن']); const valueCol=col(d,['dealvalue','contractvalue','pipelinevalue','ارزشقرارداد','ارزش']); const stageCol=col(d,['stage','مرحله']); const customerCol=col(d,['customer','company','client','مشتری','شرکت']); const lastContactCol=col(d,['lastcontact','آخرینتماس']); const npsCol=col(d,['nps']); const csatCol=col(d,['csat','رضایت']); const churnCol=col(d,['churn','ریزش']); const funnelCol=col(d,['funnel','مرحلهقیف','event','رویداد']);
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
 if(key==='crm'){
   const deals=d.rows.map((r,i)=>{const rawProb=probabilityCol?n(r[probabilityCol]):null;const probability=rawProb===null?null:clamp(rawProb>1?rawProb/100:rawProb);const value=valueCol?n(r[valueCol]):null;const stage=stageCol?text(r[stageCol]):'';const name=customerCol?text(r[customerCol]):`#${i+1}`;const weighted=value!==null&&probability!==null?value*probability:null;return{name,stage,probability,value,weighted,last:lastContactCol?text(r[lastContactCol]):''}});
   const valued=deals.filter(x=>x.value!==null);const weighted=deals.filter(x=>x.weighted!==null);const pipeline=valued.reduce((s,x)=>s+(x.value??0),0);const weightedPipeline=weighted.reduce((s,x)=>s+(x.weighted??0),0);const high=deals.filter(x=>(x.probability??0)>=.7).sort((a,b)=>(b.weighted??0)-(a.weighted??0));
   const stageCounts=new Map<string,number>();deals.forEach(x=>{if(x.stage)stageCounts.set(x.stage,(stageCounts.get(x.stage)??0)+1)});const topStages=[...stageCounts.entries()].sort((a,b)=>b[1]-a[1]).slice(0,3);
   const bullets=[...topStages.map(([s,c])=>`${s}: ${fa(c,0)} فرصت`),...high.slice(0,2).map(x=>`${x.name}: احتمال ${fa((x.probability??0)*100,0)}٪${x.value!==null?` • ارزش ${money(x.value)}`:''}${x.last?` • آخرین تماس ${x.last}`:''}`)];
   return{summary:'CRM/Pipeline از داده همگام‌شده مرکز داده، ارزش فرصت، احتمال بستن و مرحله فروش را ترکیب می‌کند تا اولویت پیگیری را مشخص کند.',metrics:[{label:'Pipeline',value:valued.length?money(pipeline):'—'},{label:'Weighted Pipeline',value:weighted.length?money(weightedPipeline):'—',tone:weightedPipeline>0?'positive':'neutral'},{label:'فرصت ≥۷۰٪',value:fa(high.length,0),tone:high.length?'positive':'neutral'}],bullets:bullets.length?bullets:['برای Lead Scoring کامل ستون‌های مشتری، مرحله، ارزش قرارداد و احتمال بستن را وارد کنید.'],note:'اولویت‌ها از داده واقعی ساخته می‌شوند؛ احتمال یا ارزش ناموجود حدس زده نمی‌شود.'};
 }
 if(key==='journey'||key==='campaign'){
   const base=leads??customers; const conv=wins&&base&&base.total?wins.total/base.total:null;
   return{summary:key==='journey'?'Journey Map بر داده واقعی مشتری/قیف اجرا می‌شود.':'Campaign Analysis بر داده واقعی لید، مشتری و تبدیل اجرا می‌شود.',metrics:[{label:'حجم مشتری/لید',value:base?fa(base.total,0):'—'},{label:'تبدیل',value:conv===null?'—':`${fa(conv*100,1)}٪`,tone:conv===null?'neutral':conv>=.2?'positive':'neutral'},{label:'فیلدهای داده',value:fa(d.columns.length,0)}],bullets:[base?`مبنای قیف: ${base.column}`:'ستون customer/lead برای قیف لازم است.',wins?`خروجی تبدیل: ${wins.column}`:'ستون conversion/won شناسایی نشد.','نتیجه فقط از فیلدهای موجود ساخته می‌شود.']};
 }
 if(key==='business-kpi'){
   const profit=revenue&&cost?revenue.total-cost.total:null;const margin=profit!==null&&revenue?.total?profit/revenue.total:null;const conv=wins&&leads&&leads.total?wins.total/leads.total:null;
   return{summary:'داشبورد KPI کسب‌وکار شاخص‌های قابل محاسبه را مستقیم از dataset مرکز داده استخراج می‌کند.',metrics:[{label:'فروش/درآمد',value:revenue?money(revenue.total):'—'},{label:'حاشیه',value:margin===null?'—':`${fa(margin*100,1)}٪`,tone:margin===null?'neutral':margin>=0?'positive':'negative'},{label:'تبدیل لید',value:conv===null?'—':`${fa(conv*100,1)}٪`}],bullets:[cost?`هزینه ثبت‌شده: ${money(cost.total)}`:'هزینه برای محاسبه حاشیه شناسایی نشد.',customers?`حجم مشتری: ${fa(customers.total,0)}`:'ستون مشتری شناسایی نشد.',`کامل بودن داده بر اساس ${d.rows.length} ردیف بررسی می‌شود.`]};
 }
 if(key==='market-entry'){
   const market=find(ss,['marketsize','tam','اندازهبازار']);const share=find(ss,['marketshare','سهمبازار']);const competitor=col(d,['competitor','رقیب']);
   return{summary:'ورود به بازار جدید فقط از شواهد موجود درباره اندازه بازار، سهم، مشتری و رقیب استفاده می‌کند و TAM/SAM/SOM ساختگی تولید نمی‌کند.',metrics:[{label:'اندازه بازار ثبت‌شده',value:market?money(market.total):'—'},{label:'سهم بازار',value:share?`${fa(share.avg,1)}٪`:'—'},{label:'ردیف بازار',value:fa(d.rows.length,0)}],bullets:[competitor?`فیلد رقیب: ${competitor}`:'برای مقایسه بازار ستون competitor/رقیب اضافه کنید.',customers?`سیگنال مشتری: ${customers.column}`:'برای segmentation ستون مشتری لازم است.',revenue?`فروش مشاهده‌شده: ${money(revenue.total)}`:'فروش/درآمد شناسایی نشد.'],note:'کانال ورود و بودجه فقط زمانی عددی می‌شوند که داده مربوطه در مرکز داده موجود باشد.'};
 }
 if(key==='executive-report'){
   const profit=revenue&&cost?revenue.total-cost.total:null;const trend=ss.map(s=>{const m=Math.max(1,Math.floor(s.values.length/2));const a=s.values.slice(0,m).reduce((x,y)=>x+y,0)/m;const b=s.values.slice(m).reduce((x,y)=>x+y,0)/Math.max(1,s.values.slice(m).length);return{column:s.column,change:a?((b-a)/Math.abs(a)):0}}).sort((a,b)=>Math.abs(b.change)-Math.abs(a.change));
   return{summary:'گزارش مدیریتی از KPIهای واقعی و بزرگ‌ترین انحراف‌های قابل مشاهده در داده شرکت ساخته می‌شود.',metrics:[{label:'درآمد',value:revenue?money(revenue.total):'—'},{label:'سود مشاهده‌شده',value:profit===null?'—':money(profit),tone:profit===null?'neutral':profit>=0?'positive':'negative'},{label:'شاخص عددی',value:fa(ss.length,0)}],bullets:trend.slice(0,3).map(x=>`${x.column}: ${x.change>=0?'+':''}${fa(x.change*100,1)}٪ تغییر نیمه دوم نسبت به نیمه اول`),note:'علت انحراف فقط وقتی بیان می‌شود که در داده شواهد مربوط به علت وجود داشته باشد.'};
 }
 if(key==='voc'){
   const score=npsCol??csatCol;const scoreSeries=score?find(ss,[score]):undefined;const issueCol=col(d,['issue','complaint','feedback','friction','مشکل','شکایت','نظر']);const issues=issueCol?d.rows.map(r=>text(r[issueCol])).filter(Boolean):[];const freq=new Map<string,number>();issues.forEach(x=>freq.set(x,(freq.get(x)??0)+1));const top=[...freq.entries()].sort((a,b)=>b[1]-a[1]).slice(0,3);
   return{summary:'VOC + Friction Points صدای مشتری و اصطکاک‌های ثبت‌شده را از dataset مرکز داده خلاصه می‌کند.',metrics:[{label:score??'NPS/CSAT',value:scoreSeries?fa(scoreSeries.avg,1):'—'},{label:'بازخورد',value:fa(issues.length,0)},{label:'موضوع تکرارشونده',value:fa(top.length,0)}],bullets:top.length?top.map(([x,c])=>`${x}: ${fa(c,0)} بار`):['برای VOC دقیق ستون NPS/CSAT و feedback/complaint وارد کنید.'],note:'متن بازخورد تفسیر می‌شود اما مشکل یا علت ناموجود ساخته نمی‌شود.'};
 }
 if(key==='behavior'){
   const churn=churnCol?find(ss,[churnCol]):undefined;const funnel=funnelCol?d.rows.map(r=>text(r[funnelCol])).filter(Boolean):[];const counts=new Map<string,number>();funnel.forEach(x=>counts.set(x,(counts.get(x)??0)+1));const stages=[...counts.entries()].sort((a,b)=>b[1]-a[1]);
   return{summary:'رفتار کاربر از رخدادها/مراحل Funnel واقعی و نرخ ریزش ثبت‌شده استخراج می‌شود.',metrics:[{label:'رویداد/مرحله',value:fa(funnel.length,0)},{label:'مرحله یکتا',value:fa(stages.length,0)},{label:'Churn',value:churn?`${fa(churn.avg,1)}${churn.avg<=1?'':'٪'}`:'—',tone:churn&&churn.avg>10?'negative':'neutral'}],bullets:stages.slice(0,3).map(([x,c])=>`${x}: ${fa(c,0)} رکورد`).concat(stages.length?[]:['برای Funnel ستون event/stage و برای ریزش ستون churn اضافه کنید.'])};
 }
 if(key==='swot'){
   const trends=ss.map(s=>{const m=Math.max(1,Math.floor(s.values.length/2));const a=s.values.slice(0,m).reduce((x,y)=>x+y,0)/m;const b=s.values.slice(m).reduce((x,y)=>x+y,0)/Math.max(1,s.values.slice(m).length);return{column:s.column,change:a?((b-a)/Math.abs(a)):0}}).sort((a,b)=>b.change-a.change);
   return{summary:'SWOT داده‌محور: نقاط قوت/ضعف از روندهای مثبت و منفی قابل‌اندازه‌گیری استخراج می‌شوند؛ Opportunity/Threat بدون داده بیرونی ادعا نمی‌شود.',metrics:[{label:'شاخص عددی',value:fa(ss.length,0)},{label:'قوی‌ترین روند',value:trends[0]?`${fa(trends[0].change*100,1)}٪`:'—',tone:trends[0]?.change>=0?'positive':'negative'},{label:'ضعیف‌ترین روند',value:trends.at(-1)?`${fa((trends.at(-1)?.change??0)*100,1)}٪`:'—',tone:(trends.at(-1)?.change??0)>=0?'positive':'negative'}],bullets:[trends[0]?`Strength candidate: ${trends[0].column}`:'داده عددی کافی نیست.',trends.at(-1)?`Weakness candidate: ${trends.at(-1)?.column}`:'داده عددی کافی نیست.','Opportunity/Threat نیازمند فیلد بازار/رقیب یا منبع بیرونی است.']};
 }
 return null;
}
