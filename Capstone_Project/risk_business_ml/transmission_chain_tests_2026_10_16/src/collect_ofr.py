from collect_additions import fetch,ROOT,RAW
from concurrent.futures import ThreadPoolExecutor
import json,urllib.parse
jobs=[]
for s in ['REPO-GCF_AR_OO-F','REPO-DVP_AR_OO-F']:
 jobs.append((s+'.json','https://data.financialresearch.gov/v1/series/timeseries?'+urllib.parse.urlencode({'mnemonic':s,'start_date':'2018-01-01','end_date':'2026-10-15'}),30))
 jobs.append((s+'_metadata.json','https://data.financialresearch.gov/v1/metadata/query?mnemonic='+s,20))
with ThreadPoolExecutor(max_workers=4) as pool:r=list(pool.map(lambda x:fetch(*x),jobs))
(ROOT/'ofr_fetch_manifest.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
for x in r:print({k:v for k,v in x.items() if k in ['name','status','bytes','error']},flush=True)
