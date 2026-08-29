"""Resilient symbol universe for BIAP.

TSETMC remains the preferred source because it provides real instrument codes,
market flow and industry metadata. Some VPS networks cannot currently reach
TSETMC, so symbol discovery falls back to CODAL's verified issuer directory.
A last-known-good verified snapshot is also persisted to disk and can be reused
when both upstreams are temporarily unreachable. The fallback never fabricates
market metadata: only values previously returned by a verified upstream are
stored and replayed.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import gzip,json,os,re,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
from typing import Optional
from codal_data import CodalDataUnavailable, list_companies
DEFAULT_TSETMC_BASE="https://cdn.tsetmc.com/api";DEFAULT_TSETMC_LEGACY_URL="http://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0";CACHE_TTL_SECONDS=300.0;SNAPSHOT_ENV="BIAP_SYMBOL_SNAPSHOT";DEFAULT_SNAPSHOT_PATH=Path.home()/".cache"/"biap"/"symbol_universe.json"
class SymbolUniverseUnavailable(RuntimeError):pass
@dataclass(frozen=True)
class MarketSymbol:
    code:str;symbol:str;name:str;market:Optional[str];flow:Optional[int];industry_code:Optional[str];paper_type:Optional[str];is_active:bool=True;source:str="tsetmc"
    def to_dict(self)->dict:return asdict(self)
def tsetmc_base()->str:return os.getenv("BIAP_TSETMC_API_BASE",DEFAULT_TSETMC_BASE).rstrip("/")
def tsetmc_legacy_url()->str:return os.getenv("BIAP_TSETMC_LEGACY_URL",DEFAULT_TSETMC_LEGACY_URL)
def _market_from_flow(flow:int)->Optional[str]:return {1:"TSE",2:"IFB",4:"IFB_BASE"}.get(flow)
def _first(raw:dict,*keys:str):
    for key in keys:
        if key in raw and raw[key] not in(None,""):return raw[key]
    return None
def _parse_symbol(raw:dict)->Optional[MarketSymbol]:
    code=_first(raw,"insCode","ins_code");symbol=_first(raw,"lVal18AFC","l18","symbol");name=_first(raw,"lVal30","l30","name")
    try:flow=int(_first(raw,"flow"))
    except(TypeError,ValueError):return None
    market=_market_from_flow(flow)
    if market is None or not code or not symbol:return None
    industry=_first(raw,"cs","cSecVal","sectorCode");paper_type=_first(raw,"yVal","yval","paperType")
    return MarketSymbol(code=str(code),symbol=str(symbol).strip(),name=str(name or symbol).strip(),market=market,flow=flow,industry_code=str(industry) if industry not in(None,"") else None,paper_type=str(paper_type) if paper_type not in(None,"") else None)
def _market_watch_url()->str:
    params=[("market","0"),("withBestLimits","false"),("showTraded","false"),("hEven","0"),("RefID","0")];params.extend((f"paperTypes[{i}]",str(i+1)) for i in range(9));return f"{tsetmc_base()}/ClosingPrice/GetMarketWatch?{urllib.parse.urlencode(params)}"
def _read_url(url:str,*,timeout:float,accept:str="*/*")->bytes:
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 BIAP/1.0","Accept":accept,"Accept-Encoding":"gzip"})
    with urllib.request.urlopen(req,timeout=timeout) as resp:body=resp.read();encoding=(resp.headers.get("Content-Encoding") or "").lower()
    if encoding=="gzip" or body[:2]==b"\x1f\x8b":body=gzip.decompress(body)
    return body
def _dedupe_sort(items:list[MarketSymbol])->list[MarketSymbol]:
    seen=set();result=[]
    for item in items:
        key=(item.source,item.code)
        if key in seen:continue
        seen.add(key);result.append(item)
    result.sort(key=lambda x:((x.market or "ZZZ"),x.symbol));return result
def _snapshot_path()->Path:
    configured=os.getenv(SNAPSHOT_ENV);return Path(configured).expanduser() if configured else DEFAULT_SNAPSHOT_PATH
def _load_snapshot()->list[MarketSymbol]:
    path=_snapshot_path()
    try:payload=json.loads(path.read_text(encoding="utf-8"))
    except(OSError,json.JSONDecodeError):return []
    rows=payload.get("items") if isinstance(payload,dict) else None
    if not isinstance(rows,list):return []
    items=[]
    for raw in rows:
        if not isinstance(raw,dict):continue
        try:item=MarketSymbol(code=str(raw["code"]),symbol=str(raw["symbol"]),name=str(raw.get("name") or raw["symbol"]),market=raw.get("market"),flow=int(raw["flow"]) if raw.get("flow") is not None else None,industry_code=str(raw["industry_code"]) if raw.get("industry_code") not in(None,"") else None,paper_type=str(raw["paper_type"]) if raw.get("paper_type") not in(None,"") else None,is_active=bool(raw.get("is_active",True)),source=str(raw.get("source") or "snapshot"))
        except(KeyError,TypeError,ValueError):continue
        if item.code and item.symbol:items.append(item)
    return _dedupe_sort(items)
def _save_snapshot(items:list[MarketSymbol])->None:
    if not items:return
    path=_snapshot_path();payload={"savedAt":time.time(),"items":[item.to_dict() for item in items]}
    try:path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8");tmp.replace(path)
    except OSError:return
def _fetch_json_universe(*,timeout:float)->list[MarketSymbol]:
    try:payload=json.loads(_read_url(_market_watch_url(),timeout=timeout,accept="application/json"))
    except json.JSONDecodeError:return []
    rows=payload.get("marketwatch") if isinstance(payload,dict) else None
    if not isinstance(rows,list):return []
    return _dedupe_sort([item for raw in rows if isinstance(raw,dict) if(item:=_parse_symbol(raw))])
def _fetch_legacy_universe(*,timeout:float)->list[MarketSymbol]:
    text=_read_url(tsetmc_legacy_url(),timeout=timeout).decode("utf-8",errors="replace");parts=text.split("@")
    if len(parts)<3:return []
    items=[]
    for row in parts[2].split(";"):
        cols=row.split(",")
        if len(cols)<23:continue
        try:flow=int(cols[17])
        except ValueError:continue
        market=_market_from_flow(flow);code,symbol=cols[0].strip(),cols[2].strip()
        if market is None or not code or not symbol:continue
        items.append(MarketSymbol(code=code,symbol=symbol,name=cols[3].strip() or symbol,market=market,flow=flow,industry_code=cols[18].strip() or None,paper_type=cols[22].strip() or None))
    return _dedupe_sort(items)
def _looks_like_ticker(symbol:str)->bool:
    value=" ".join(symbol.split())
    if not value or len(value)>16 or value.count(" ")>3:return False
    if any(ch in value for ch in "/\\,:;()[]{}"):return False
    return bool(re.search(r"[\u0600-\u06FFA-Za-z0-9]",value))
def _relaxed_codal_symbol(symbol:str)->bool:
    value=" ".join(symbol.split())
    if not value or len(value)>28 or value.count(" ")>5:return False
    if any(ch in value for ch in "/\\,:;()[]{}"):return False
    return bool(re.search(r"[\u0600-\u06FFA-Za-z0-9]",value))
def _codal_item(row:dict)->Optional[MarketSymbol]:
    symbol=str(row.get("sy") or "").strip()
    if not symbol:return None
    name=str(row.get("n") or symbol).strip();return MarketSymbol(code=symbol,symbol=symbol,name=name,market=None,flow=None,industry_code=None,paper_type=None,source="codal")
def _fetch_codal_universe()->list[MarketSymbol]:
    rows=list_companies();strict=[];relaxed=[]
    for row in rows:
        item=_codal_item(row)
        if item is None:continue
        if _looks_like_ticker(item.symbol):strict.append(item)
        elif _relaxed_codal_symbol(item.symbol):relaxed.append(item)
    return _dedupe_sort(strict if len(strict)>=100 else strict+relaxed)
_cache_items:list[MarketSymbol]=[];_cache_expires_at=0.0
def _live_or_snapshot_universe(*,timeout:float=6.0)->list[MarketSymbol]:
    errors=[]
    try:
        items=_fetch_json_universe(timeout=timeout)
        if items:_save_snapshot(items);return items
    except(urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:errors.append(str(exc))
    try:
        items=_fetch_legacy_universe(timeout=timeout)
        if items:_save_snapshot(items);return items
    except(urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:errors.append(str(exc))
    try:
        items=_fetch_codal_universe()
        if items:return items
    except(CodalDataUnavailable,OSError,ValueError) as exc:errors.append(str(exc))
    snapshot=_load_snapshot()
    if snapshot:return snapshot
    raise SymbolUniverseUnavailable("symbol universe unavailable"+(f": {'; '.join(errors[-2:])}" if errors else ""))
def get_symbol_universe(*,force:bool=False,timeout:float=6.0)->list[MarketSymbol]:
    global _cache_items,_cache_expires_at
    now=time.monotonic()
    if not force and _cache_items and now<_cache_expires_at:return list(_cache_items)
    items=_live_or_snapshot_universe(timeout=timeout);_cache_items=items;_cache_expires_at=now+CACHE_TTL_SECONDS;return list(items)
def fetch_symbol_universe(*,timeout:float=6.0,use_cache:bool=True)->list[MarketSymbol]:
    """Backward-compatible API used by market_data and older callers."""
    return get_symbol_universe(force=not use_cache,timeout=timeout)
def query_symbols(*,market:Optional[str]=None,q:Optional[str]=None,limit:int=5000)->list[MarketSymbol]:
    # Route through the public wrapper, then filter locally. This keeps search
    # behavior consistent for callers/tests that replace fetch_symbol_universe,
    # while the wrapper itself still owns cache policy and upstream fallback.
    items=fetch_symbol_universe();market_key=market.upper() if market else None;needle=(q or "").strip().replace("ي","ی").replace("ك","ک").lower();result=[]
    for item in items:
        if market_key and item.market!=market_key:continue
        if needle:
            hay=f"{item.symbol} {item.name} {item.code}".replace("ي","ی").replace("ك","ک").lower()
            if needle not in hay:continue
        result.append(item)
        if len(result)>=limit:break
    return result