import json,sys
from datetime import datetime,timedelta,timezone
D="/home/ubuntu/biap-validation-20261016/data-u9/scan-cache/"
for m in "US/NASDAQ US/NYSE GB/LSE FR/EURONEXT_PARIS IT/EURONEXT_MILAN SE/NASDAQ_STOCKHOLM NO/EURONEXT_OSLO".split():
    p=D+m+".json"; w=json.load(open(p)); c=datetime.fromisoformat(w["cachedAt"])
    age=(datetime.now(timezone.utc)-c).total_seconds()/3600
    w["cachedAt"]=(c-timedelta(hours=max(0,24.5-age))).isoformat(); json.dump(w,open(p,"w")); print(m,"age was",round(age,1),"-> 24.5 h")  # copy only
