import { authFetch, authHeaders } from '@/lib/auth-session';
import { KIASHA_API_BASE, fetchKiashaPerformanceSummary, fetchRecommendation, fetchWatchlist, parsePct } from '@/lib/api';
import { fetchMarketSymbols } from '@/lib/market-symbols';
import { getBusinessDataset, summarizeBusinessDataset, type BusinessDataset } from '@/lib/business-data';
import { analyzeSpecialized } from '@/lib/specialized-business-analysis';
import { fetchListedCompanyDetail } from '@/lib/listed-company-selection';
import type { DemoMetric } from '@/demo/demo-data';

export type RealModulePayload = { available: boolean; sourceLabel: string; summary: string; metrics: DemoMetric[]; bullets: string[]; note?: string };
export type RealModuleOptions = { code?: string; companyMode?: 'listed' | 'private' | 'hybrid' };
type ModuleInputs = Awaited<ReturnType<typeof loadInputs>>;
const TITLES:Record<string,string>={eda:'EDA',sql:'SQL / Data Query',anomaly:'Anomaly',forecast:'Forecast','kpi-extract':'KPI','business-kpi':'Business KPI',dashboard:'Dashboard',governance:'Governance',report:'Report',swot:'SWOT','market-entry':'Market Entry',journey:'Journey',crm:'CRM / Pipeline',campaign:'Campaign',pricing:'Pricing',plan:'Business Plan','executive-report':'Executive Report','financial-model':'Financial Model',scenario:'Scenario',unit:'Unit Economics',mbr:'MBR',voc:'VOC',behavior:'User Behavior'};
const fa=(n:number,d=0)=>n.toLocaleString('fa-IR',{maximumFractionDigits:d});
const fmt=(n:number)=>Math.abs(n)>=1_000_000?`${fa(n/1_000_000,2)}M`:fa(n,2);
const num=(v:unknown):number|null=>{const n=Number(v);return Number.isFinite(n)?n:null};

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

async function listedCompanyPayload(key:string,code:string):Promise<RealModulePayload>{
 const stored=await fetchListedCompanyDetail(code);
 const market=(stored?.marketData??{}) as Record<string,unknown>;
 const fundamentals=(stored?.codalFundamentals??{}) as Record<string,unknown>;
 const tindex=(stored?.tindex??{}) as Record<string,unknown>;
 let last=num(market.last_price??market.price??market.closing_price??tindex.price);
 let change=num(market.change_percent??tindex.change_percent);
 let revenueYoy=num(fundamentals.revenue_yoy_pct);
 let margin=num(fundamentals.net_margin_pct);
 let prevMargin=num(fundamentals.net_margin_prev_pct);
 const storedAvailable=Boolean(stored?.company||stored?.enrichedAt);
 let name=stored?.name||stored?.symbol||code;
 let liveAvailable=Boolean(Object.keys(market).length);
 let codalAvailable=Boolean(stored?.dataAvailability?.codal||Object.keys(fundamentals).length);
 let tindexAvailable=Boolean(stored?.dataAvailability?.tindex||Object.keys(tindex).length);

 // Persistent DB is authoritative for the three listed-company data modules.
 // A live recommendation is only a freshness fallback when the DB record is not enriched yet.
 if(!storedAvailable){
  const rec=await fetchRecommendation(code,20_000);
  if(!rec)return{available:false,sourceLabel:'Listed Company DB',summary:'',metrics:[],bullets:[],note:`برای نماد ${code} هنوز رکورد غنی‌شده در دیتابیس BIAP موجود نیست.`};
  name=rec.name||rec.code;last=num(rec.livePrice?.lastPrice??rec.livePrice?.closingPrice);change=num(rec.livePrice?.changePercent);revenueYoy=num(rec.codalFundamentals?.revenue_yoy_pct);margin=num(rec.codalFundamentals?.net_margin_pct);prevMargin=num(rec.codalFundamentals?.net_margin_prev_pct);liveAvailable=Boolean(rec.livePrice);codalAvailable=Boolean(rec.dataAvailability?.codal);tindexAvailable=false;
 }
 const coverage=[liveAvailable,codalAvailable,tindexAvailable].filter(Boolean).length;
 const baseMetrics:DemoMetric[]=[{label:'قیمت بازار',value:last===null?'—':fa(last,0)},{label:'تغییر روز',value:change===null?'—':`${change>=0?'+':''}${fa(change,2)}٪`,tone:change===null?'neutral':change>=0?'positive':'negative'},{label:'پوشش منبع',value:`${coverage}/3`}];
 const evidence:string[]=[`نماد: ${name}`,`دیتابیس BIAP: ${storedAvailable?'متصل':'fallback live'}`,`TSETMC: ${liveAvailable?'متصل':'ناموجود'}`,`CODAL: ${codalAvailable?'متصل':'ناموجود'}`,`Tindex: ${tindexAvailable?'متصل':'ناموجود'}`];
 const source=storedAvailable?'BIAP Listed DB • TSETMC + CODAL + Tindex':'TSETMC + CODAL • LIVE FALLBACK';
 if(key==='pricing')return{available:false,sourceLabel:source,summary:'داده بورسی شرکت دریافت شد، اما قیمت‌گذاری محصول/خدمت به قیمت واحد، هزینه تمام‌شده و حجم فروش داخلی نیاز دارد.',metrics:baseMetrics,bullets:evidence,note:'برای Pricing عدد پیشنهادی از قیمت سهم ساخته نمی‌شود.'};
 if(key==='crm'||key==='journey'||key==='voc'||key==='behavior'||key==='unit')return{available:false,sourceLabel:source,summary:'داده عمومی شرکت بورسی موجود است، اما این ماژول به داده مشتری/عملیاتی داخلی نیاز دارد.',metrics:baseMetrics,bullets:evidence,note:'برای این ماژول داده داخلی شرکت لازم است.'};
 if(key==='financial-model')return{available:codalAvailable||tindexAvailable||liveAvailable,sourceLabel:source,summary:'Financial Model از رکورد پایدار همین شرکت بورسی/فرابورسی در دیتابیس BIAP استفاده می‌کند؛ مقدار ناموجود ساخته نمی‌شود.',metrics:[{label:'رشد درآمد YoY',value:revenueYoy===null?'—':`${revenueYoy>=0?'+':''}${fa(revenueYoy,1)}٪`,tone:revenueYoy===null?'neutral':revenueYoy>=0?'positive':'negative'},{label:'حاشیه خالص',value:margin===null?'—':`${fa(margin,1)}٪`,tone:margin===null?'neutral':margin>=0?'positive':'negative'},{label:'حاشیه قبلی',value:prevMargin===null?'—':`${fa(prevMargin,1)}٪`}],bullets:evidence,note:'برای P&L کامل، رقم‌های مطلق چند دوره باید در CODAL/Tindex موجود باشد.'};
 if(key==='kpi-extract'||key==='business-kpi'||key==='dashboard')return{available:liveAvailable||codalAvailable||tindexAvailable,sourceLabel:source,summary:'KPIهای قابل محاسبه از رکورد پایدار همین نماد در دیتابیس BIAP خوانده می‌شوند.',metrics:[...baseMetrics.slice(0,2),{label:'رشد درآمد YoY',value:revenueYoy===null?'—':`${revenueYoy>=0?'+':''}${fa(revenueYoy,1)}٪`,tone:revenueYoy===null?'neutral':revenueYoy>=0?'positive':'negative'}],bullets:[...evidence,margin===null?'حاشیه خالص فعلاً ناموجود است.':`حاشیه خالص: ${fa(margin,1)}٪`]};
 if(key==='sql')return{available:storedAvailable||liveAvailable||codalAvailable||tindexAvailable,sourceLabel:'BIAP Listed Company DB • QUERY',summary:'SQL / Data Query روی context ساختاریافته و پایدار همین نماد اجرا می‌شود؛ TSE و IFB از یک دیتابیس مشترک خوانده می‌شوند.',metrics:baseMetrics,bullets:[...evidence,revenueYoy===null?'revenue_yoy_pct: null':`revenue_yoy_pct: ${revenueYoy}`,margin===null?'net_margin_pct: null':`net_margin_pct: ${margin}`],note:'این Query روی دیتابیس BIAP است؛ اتصال SQL داخلی شرکت یک کانکتور جداگانه است.'};
 if(key==='swot'||key==='executive-report'||key==='report'||key==='market-entry'||key==='forecast'||key==='anomaly')return{available:true,sourceLabel:source,summary:`${TITLES[key]??'تحلیل'} برای همین نماد فقط از شواهد عمومی موجود استفاده می‌کند.`,metrics:[...baseMetrics.slice(0,2),{label:'حاشیه خالص',value:margin===null?'—':`${fa(margin,1)}٪`}],bullets:[...evidence,revenueYoy===null?'رشد درآمد ناموجود است.':`رشد درآمد YoY: ${revenueYoy>=0?'+':''}${fa(revenueYoy,1)}٪`],note:'هر نتیجه‌ای که به داده داخلی مشتری/محصول/بودجه نیاز داشته باشد تا زمان اتصال آن داده ارائه نمی‌شود.'};
 return{available:true,sourceLabel:source,summary:'Context واقعی شرکت بورسی/فرابورسی برای این ماژول دریافت شد.',metrics:baseMetrics,bullets:evidence};
}

export async function fetchRealModuleData(key:string,options:RealModuleOptions={}):Promise<RealModulePayload>{
 if(options.companyMode==='listed'&&options.code)return listedCompanyPayload(key,options.code);
 if(key==='scenario')return scenarioPayload();
 const company=await getBusinessDataset();
 if(company&&company.rows.length){const specialized=analyzeSpecialized(key,company);if(specialized)return{available:true,sourceLabel:`${TITLES[key]??key} Engine • Company Dataset`,...specialized};return commonDatasetPayload(key,company)}
 const data=await inputs();
 if(['eda','dashboard','kpi-extract','report','anomaly'].includes(key))return marketMetrics(data);
 if(['governance','mbr'].includes(key))return performanceMetrics(data);
 if(key==='forecast'){const p=performanceMetrics(data);return{...p,summary:p.available?'داده عملکرد واقعی متصل است، اما بدون تاریخچه معتبر عدد آینده ساخته نمی‌شود.':'',note:'برای Forecast عدد آینده، تاریخچه معتبر لازم است.'}}
 return{available:false,sourceLabel:'ورودی واقعی لازم است',summary:'',metrics:[],bullets:[],note:'از «اتصال داده» CSV/JSON/Excel واقعی شرکت را وارد کنید. SQL/CRM/API خارجی پس از ارائه مشخصات منبع فعال می‌شوند.'};
}
