import { KIASHA_API_BASE } from '@/lib/api';
import { authFetch, getValidAccessToken } from '@/lib/auth-session';
import type { InvestmentHorizon } from '@/lib/kiasha-picks';

export type AutoInvestRun = { runId:string; tehranDay:string; startedAt:string; finishedAt?:string|null; status:string; result?:Record<string,unknown>|null };
export type AutoInvestStatus = {
  enabled:boolean; horizon:InvestmentHorizon; maxDailyTrades:number;
  dailyBudgetPct?:number; maxSymbolPct?:number; minCashReservePct?:number;
  runnerEnabled:boolean; paperExecutionEnabled:boolean; paperOnly:true; liveExecution:false;
  authRequired?:boolean; latestRun?:AutoInvestRun|null; createdAt?:string; updatedAt?:string;
};
type PublicAiStatus={runnerEnabled?:boolean;paperExecutionEnabled?:boolean;liveExecution?:boolean};

async function fetchPublicReadiness(timeoutMs=5000):Promise<PublicAiStatus|null>{const c=new AbortController();const t=setTimeout(()=>c.abort(),timeoutMs);try{const r=await fetch(`${KIASHA_API_BASE}/performance/ai/status`,{headers:{Accept:'application/json'},signal:c.signal});if(!r.ok)return null;return await r.json() as PublicAiStatus}catch{return null}finally{clearTimeout(t)}}
function authFallback(r:PublicAiStatus|null):AutoInvestStatus|null{if(!r)return null;return{enabled:false,horizon:'short',maxDailyTrades:3,dailyBudgetPct:15,maxSymbolPct:5,minCashReservePct:30,runnerEnabled:Boolean(r.runnerEnabled),paperExecutionEnabled:Boolean(r.paperExecutionEnabled),paperOnly:true,liveExecution:false,authRequired:true,latestRun:null}}

export async function fetchAutoInvestStatus(timeoutMs=8000):Promise<AutoInvestStatus|null>{
  if(!(await getValidAccessToken())) return authFallback(await fetchPublicReadiness());
  const c=new AbortController();const t=setTimeout(()=>c.abort(),timeoutMs);
  try{const r=await authFetch(`${KIASHA_API_BASE}/performance/ai/auto-invest`,{signal:c.signal});if(r.status===401||r.status===403)return authFallback(await fetchPublicReadiness());if(!r.ok)return null;return await r.json() as AutoInvestStatus}catch{return null}finally{clearTimeout(t)}
}

export async function updateAutoInvest(params:{enabled:boolean;horizon:InvestmentHorizon;maxDailyTrades?:number}):Promise<AutoInvestStatus|null>{
  try{const r=await authFetch(`${KIASHA_API_BASE}/performance/ai/auto-invest`,{method:'PUT',body:JSON.stringify({enabled:params.enabled,horizon:params.horizon,maxDailyTrades:params.maxDailyTrades??3})});if(!r.ok)return null;return await r.json() as AutoInvestStatus}catch{return null}
}

export async function runAutoInvestNow():Promise<Record<string,unknown>|null>{
  try{const r=await authFetch(`${KIASHA_API_BASE}/performance/ai/auto-invest/run-now`,{method:'POST'});if(!r.ok)return null;return await r.json() as Record<string,unknown>}catch{return null}
}
