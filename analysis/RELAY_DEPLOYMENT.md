# BIAP data relay deployment

Use this only while the new BIAP VPS cannot reach TSETMC/CODAL directly.
The old/current production VPS acts as a read-only upstream relay; the new VPS
continues to run Kiasha/FIN.

## 1. Current/old BIAP server (89.42.199.20)

Pull the repository, install the existing analysis requirements, and run the
allow-listed relay on port 8090:

```bash
cd /root/BIAP
git pull --ff-only
cd analysis
./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn relay_server:app --host 0.0.0.0 --port 8090
```

Before leaving port 8090 exposed, restrict it at the host/provider firewall so
only the new BIAP server (`5.249.252.88`) can connect. The relay is not a general
proxy, but network-level restriction is still required.

Quick checks on the relay host:

```bash
curl -s http://127.0.0.1:8090/health | python3 -m json.tool
curl -s --max-time 20 'http://127.0.0.1:8090/codal-search/api/search/v1/companies' | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))'
curl -s --max-time 20 'http://127.0.0.1:8090/tsetmc-cdn/api/ClosingPrice/GetMarketWatch?market=0&withBestLimits=false&showTraded=false&hEven=0&RefID=0' | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d.get("marketwatch", [])))'
```

## 2. New BIAP server (5.249.252.88)

Pull the same commit and point all blocked upstreams at the relay:

```bash
cd ~/BIAP
git pull --ff-only
cd analysis

export BIAP_CODAL_BASE='http://89.42.199.20:8090/codal-search'
export BIAP_CODAL_EXCEL_BASE='http://89.42.199.20:8090/codal-excel'
export BIAP_CODAL_WWW_BASE='http://89.42.199.20:8090/codal-www'
export BIAP_TSETMC_API_BASE='http://89.42.199.20:8090/tsetmc-cdn/api'
export BIAP_TSETMC_LEGACY_URL='http://89.42.199.20:8090/tsetmc-old/tsev2/data/MarketWatchInit.aspx?h=0&r=0'
```

Then restart the FIN/Kiasha process with those environment variables (or place
them in its systemd EnvironmentFile if running under systemd).

Validation:

```bash
curl -s http://127.0.0.1:8088/health | python3 -m json.tool
curl -sG --max-time 30 --data-urlencode 'q=فولاد' --data-urlencode 'limit=5' http://127.0.0.1:8088/stock/symbols | python3 -m json.tool
curl -s --max-time 60 http://127.0.0.1:8088/stock/recommendation/46348559193224090 | python3 -m json.tool
```

Success means the symbol request returns real verified symbols and the فولاد
recommendation no longer fails with TSETMC/CODAL connection timeouts.

## Rollback

Unset the relay variables (or remove them from the service EnvironmentFile) and
restart FIN. All clients then return to the original direct upstream URLs.
