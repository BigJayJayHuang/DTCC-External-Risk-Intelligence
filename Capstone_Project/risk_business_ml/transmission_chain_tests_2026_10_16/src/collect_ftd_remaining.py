from collect_additions import fetch,ROOT,RAW
from concurrent.futures import ThreadPoolExecutor
import json,time
jobs=[]
for y in range(2018,2027):
 for m in range(1,13):
  if y==2026 and m>9:continue
  for h in ['a','b']:
   name=f'sec_ftd_{y}{m:02}{h}.zip'
   if (RAW/name).exists():continue
   prefix='node/add/data_distribution' if y==2020 and m in [2,3,4] else 'data/fails-deliver-data'
   jobs.append((name,f'https://www.sec.gov/files/{prefix}/cnsfails{y}{m:02}{h}.zip'))
results=[]
# Two bounded workers, with pauses; well below SEC's 10 requests/sec limit.
def task(j):
 r=fetch(*j,timeout=15);time.sleep(.25);return r
with ThreadPoolExecutor(max_workers=2) as pool:
 for i,x in enumerate(pool.map(task,jobs),1):
  results.append(x)
  if x['status']=='failed' or i%24==0:print(i,len(jobs),x['name'],x['status'],x.get('error',''),flush=True)
  (ROOT/'remaining_ftd_manifest.json').write_text(json.dumps(results,indent=2)+'\n')
print('FTD complete attempts',len(results),'new successes',sum(x['status']!='failed' for x in results),flush=True)
