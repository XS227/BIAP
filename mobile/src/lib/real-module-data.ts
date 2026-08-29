import { authFetch, authHeaders } from '@/lib/auth-session';
import { KIASHA_API_BASE, fetchKiashaPerformanceSummary, fetchWatchlist, parsePct } from '@/lib/api';
import { fetchMarketSymbols } from '@/lib/market-symbols';
import { getBusinessDataset, summarizeBusinessDataset, type BusinessDataset } from '@/lib/business-data';
import { analyzeSpecialized } from '@/lib/specialized-business-analysis';
import type { DemoMetric } from '@/demo/demo-data';

export type RealModulePayload = { available: boolean; sourceLabel: string; summary: string; metrics: DemoMetric[]; bullets: string[]; note?: string };
type ModuleInputs = Awaited<ReturnType<typeof loadInputs>>;
const TITLES:Record<string,string>={eda:'EDA',sql:'SQL / Data Query',anomaly:'Anomaly',forecast:'Forecast','kpi-extract':'KPI',dashboard:'Dashboard',governance:'Governance',report:'Report',swot:'SWOT',journey:'Journey',crm:'CRM / Pipeline',campaign:'Campaign',pricing:'Pricing',plan:'Business Plan','financial-model':'Financial Model',scenario:'Scenario',unit:'Unit Economics',mbr:'MBR'};
const fa=(n:number,d=0)=>n.toLocaleString('fa-IR',{maximumFractionDigits:d});
const fmt=(n:number)=>Math.abs(n)>=1_000_000?`${fa(n/1_000_000,2)}M`:fa(n,2);

async function loadInputs(){const [w,u,p]=await Promise.allSettled([fetchWatchlist(),fetchMarketSymbols({limit:5000}),fetchKiashaPerformanceSummary()]);return{watchlist:w.status==='fulfilled'?w.value:[],universe:u.status==='fulfilled'?u.value:[],performance:p.status==='fulfilled'?p.value:null}}
let cache:{at:number;data:ModuleInputs}|null=null;
async function inputs(){if(cache&&Date.now()-cache.at<30_000)return cache.data;const data=await loadInputs();cache={at:Date.now(),data};return data}

function commonDatasetPayload(key:string,d:BusinessDataset):RealModulePayload{
 const s=summarizeBusinessDataset(d);const first=s.numeric[0];const metrics:DemoMetric[]=[{label:'ردیف واقعی',value:fa(s.rows)},{label:'ستون',value:fa(s.columns)},{label:'کامل بودن',value:`${fa(s.completeness*100,1)}٪`,tone:s.completeness>=.9?'positive':'negative'}];
 const bullets=s.numeric.slice(0,3).map(x=>`${x.column}: میانگین ${fmt(x.avg)} • بازه ${fmt(x.min)} تا ${fmt(x.max)}`);
 if(key==='anomaly'){const spreads=s.numeric.map(x=>({...x,spread:x.max-x.min})).sort((a,b)=>b.spread-a.spread);return{available:true,sourceLabel:'Company Dataset • LIVE',summary:'Anomaly Analysis دامنه‌های عددی و کیفیت داده واقعی شرکت را بررسی می‌کند.',metrics:[...metrics.slice(0,2),{label:'بیشترین دامنه',value:spreads[0]?fmt(spreads[0].spread):'—'}],bullets:spreads.slice(0,3).map(x=>`${x.column}: دامنه ${fmt(x.spread)}`),note:'برای anomaly زمانی دقیق، ستون تاریخ/زمان و تاریخچه کافی لازم است.'}}
 if(key==='forecast'){const vals=first?d.rows.map(r=>Number(String(r[first.column]??'').replace(/,/g,''))).filter(Number.isFinite):[];const mid=Math.floor(vals.length/2);let trend:null|number=null;if(mid>0){const a=vals.slice(0,mid).reduce((x,y)=>x+y,0)/mid;const b=vals.slice(mid).reduce((x,y)=>x+y,0)/Math.max(1,vals.slice(mid).length);trend=a?((b-a)/Math.abs(a)):null}return{available:true,sourceLabel:'Company Dataset • LIVE',summary:'Forecast فقط روند مشاهده‌شده را گزارش می‌کند و بدون سری زمانی معتبر عدد آینده نمی‌سازد.',metrics:[...metrics.slice(0,2),{label:'روند مشاهده‌شده',value:trend===null?'—':`${trend>=0?'+':''}${fa(trend*100,1)}٪`,tone:trend===null?'neutral':trend>=0?'positive':'negative'}],bullets:[...bullets.slice(0,2),'برای پیش‌بینی آینده ستون زمانی معتبر لازم است.']}}
 if(key==='sql')return{available:true,sourceLabel:'Company Dataset • LIVE',summary:'ساختار dataset واقعی برای Query/Filter آماده است.',metrics,bullets:[`ستون‌ها: ${d.columns.slice(0,8).join('، ')}${d.columns.length>8?'…':''}`,...bullets.slice(0,2)],note:'اتصال مستقیم SQL خارجی پس از دریافت credential سازمان فعال می‌شود.'};
 return{available:true,sourceLabel:'Company Dataset • LIVE',summary:`${TITLES[key]??'تحلیل'} روی داده واقعی حساب کاربر اجرا می‌شود.`,metrics,bullets:[`منبع: ${d.name}`,...bullets]};
}

async function scenarioPayload():Promise<RealModulePayload>{
 try{const headers=await authHeaders();const res=await authFetch(`${KIASHA_API_BASE}/business/scenario`,{method:'POST',headers});if(!res.ok)throw new Error(String(res.status));const x=await res.json() as any;if(x.status!=='ok'||!x.scenarios)return{available:false,sourceLabel:'Business Scenario Engine',summary:'',metrics:[],bullets:[],note:(x.missingData??[]).join('، ')||'داده کافی برای سناریو وجود ندارد.'};const label=(k:string)=>x.scenarios[k]?.direction??'—';return{available:true,sourceLabel:'scenario_engine.py • LIVE',summary:'سناریوهای جهت‌دار از داده واقعی همگام‌شده حساب و موتور backend ساخته شده‌اند؛ قیمت/درآمد آینده اختراع نمی‌شود.',metrics:[{label:'بدبینانه',value:label('pessimistic'),tone:label('pessimistic')==='positive'?'positive':label('pessimistic')==='negative'?'negative':'neutral'},{label:'پایه',value:label('base'),tone:label('base')==='positive'?'positive':label('base')==='negative'?'negative':'neutral'},{label:'خوش‌بینانه',value:label('optimistic'),tone:label('optimistic')==='positive'?'positive':label('optimistic')==='negative'?'negative':'neutral'}],bullets:[...(x.evidence??[]),`اعتماد: ${fa(Number(x.confidence??0)*100,1)}٪`],note:x.policy};
 }catch{return{available:false,sourceLabel:'Business Scenario Engine',summary:'',metrics:[],bullets:[],note:'موتور سناریوی backend فعلاً پاسخ نداد.'}}
}

function marketMetrics(d:ModuleInputs):RealModulePayload{const priced=d.watchlist.filter(x=>Number.isFinite(x.closingPrice??x.lastPrice));const pcts=priced.map(x=>parsePct(x.changePercent));const avg=pcts.length?pcts.reduce((a,b)=>a+b,0)/pcts.length:0;return{available:d.universe.length>0||priced.length>0,sourceLabel:'BIAP Market + FIN',summary:'نمای واقعی از داده‌های متصل BIAP؛ مقدار ناموجود با عدد نمونه پر نمی‌شود.',metrics:[{label:'نمادهای بازار',value:fa(d.universe.length)},{label:'قیمت معتبر',value:fa(priced.length)},{label:'میانگین تغییر',value:`${avg>=0?'+':''}${fa(avg,2)}٪`,tone:avg>=0?'positive':'negative'}],bullets:[`${fa(pcts.filter(x=>x>0).length)} نماد مثبت هستند.`,`فهرست بازار ${fa(d.universe.length)} رکورد دارد.`]}}
function performanceMetrics(d:ModuleInputs):RealModulePayload{const p=d.performance;if(!p)return{available:false,sourceLabel:'Kiasha Performance',summary:'',metrics:[],bullets:[]};const ready=p.agents.filter(a=>a.trustReady).length;const max=p.agents.reduce((m,a)=>Math.max(m,a.evaluatedCalls),0);const wa=p.agents.filter(a=>a.directionalAccuracy!==null);const avg=wa.length?wa.reduce((s,a)=>s+(a.directionalAccuracy??0),0)/wa.length:null;return{available:true,sourceLabel:'Kiasha Observed Performance',summary:'خلاصه واقعی عملکرد ثبت‌شده عامل‌های Kiasha.',metrics:[{label:'عامل آماده',value:fa(ready)},{label:'بیشترین ارزیابی',value:fa(max)},{label:'میانگین دقت',value:avg===null?'—':`${fa(avg*100,1)}٪`}],bullets:p.agents.map(a=>`${a.agent}: ${fa(a.evaluatedCalls)} ارزیابی`)}}

export async function fetchRealModuleData(key:string):Promise<RealModulePayload>{
 if(key==='scenario')return scenarioPayload();
 const company=await getBusinessDataset();
 if(company&&company.rows.length){const specialized=analyzeSpecialized(key,company);if(specialized)return{available:true,sourceLabel:`${TITLES[key]??key} Engine • Company Dataset`,...specialized};return commonDatasetPayload(key,company)}
 const data=await inputs();
 if(['eda','dashboard','kpi-extract','report','anomaly'].includes(key))return marketMetrics(data);
 if(['governance','mbr'].includes(key))return performanceMetrics(data);
 if(key==='forecast'){const p=performanceMetrics(data);return{...p,summary:p.available?'داده عملکرد واقعی متصل است، اما بدون تاریخچه معتبر عدد آینده ساخته نمی‌شود.':'',note:'برای Forecast عدد آینده، تاریخچه معتبر لازم است.'}}
 return{available:false,sourceLabel:'ورودی واقعی لازم است',summary:'',metrics:[],bullets:[],note:'از «اتصال داده» CSV/JSON/Excel واقعی شرکت را وارد کنید. SQL/CRM/API خارجی پس از ارائه مشخصات منبع فعال می‌شوند.'};
}
