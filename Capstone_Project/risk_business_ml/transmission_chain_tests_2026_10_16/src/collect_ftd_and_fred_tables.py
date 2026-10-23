from collect_additions import fetch,ROOT,RAW
from concurrent.futures import ThreadPoolExecutor
import json,time

def ft():
 rows=[]
 # Full-year common coverage; no repeated fetch per chain or event.
 for year in range(2018,2027):
  for month in range(1,13):
   if year==2026 and month>9:continue
   for half in ['a','b']:
    name=f'sec_ftd_{year}{month:02}{half}.zip'
    u=f'https://www.sec.gov/files/data/fails-deliver-data/cnsfails{year}{month:02}{half}.zip'
    x=fetch(name,u,timeout=12);rows.append(x)
    if x['status']=='failed':
     print(name,x.get('error'),flush=True)
     if len(rows)>=4 and all(y['status']=='failed' for y in rows[-4:]):
      print('Stop after four consecutive source failures; no bypass.',flush=True)
      (ROOT/'ftd_fetch_manifest.json').write_text(json.dumps(rows,indent=2)+'\n');return rows
    elif len(rows)%24==0:print('FTD',year,month,len(rows),'files attempted',flush=True)
    time.sleep(.14)
  (ROOT/'ftd_fetch_manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
 (ROOT/'ftd_fetch_manifest.json').write_text(json.dumps(rows,indent=2)+'\n');return rows

jobs=[(s+'_table.html','https://fred.stlouisfed.org/data/'+s,25) for s in ['MORTGAGE30US','DCPF3M','DTB3']]
with ThreadPoolExecutor(max_workers=4) as pool:
 f=pool.submit(ft)
 rows=list(pool.map(lambda x:fetch(*x),jobs))
 (ROOT/'fred_table_fetch_manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
 for x in rows:print({k:v for k,v in x.items() if k in ['name','status','bytes','error']},flush=True)
 f.result()
