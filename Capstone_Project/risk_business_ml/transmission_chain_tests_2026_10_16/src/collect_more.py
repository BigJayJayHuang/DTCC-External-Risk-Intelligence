from collect_additions import fetch,ROOT,RAW,MAN
from concurrent.futures import ThreadPoolExecutor
import json,urllib.parse
jobs=[(s+'.csv','https://fred.stlouisfed.org/graph/fredgraph.csv?'+urllib.parse.urlencode({'id':s,'cosd':'2018-01-01'}),65) for s in ['MORTGAGE30US','DCPF3M','DTB3']]
jobs += [(f'cboe_{y}.csv',f'https://cdn.cboe.com/resources/us/equities/market-statistics/historical-market-volume/market_history_{y}.csv',25) for y in range(2019,2027)]
jobs += [('ofr_repo_metadata.json','https://data.financialresearch.gov/v1/metadata/dataset?dataset=repo',20),('sec_ftd_202001a.zip','https://www.sec.gov/files/data/fails-deliver-data/cnsfails202001a.zip',20),('dtcc_2008_report_cms.pdf','https://cms-prod.dtcc.com/globalassets/downloads/about/annual-reports/2008_report.pdf',25),('ficc_2016_q4.pdf','https://www.dtcc.com/-/media/Files/Downloads/legal/financials/2016/FICC-Q4-Statement-of-Income-with-2016-and-2015.pdf',25)]
with ThreadPoolExecutor(max_workers=5) as pool:
 r=list(pool.map(lambda x:fetch(*x),jobs))
merged={x['name']:x for x in json.loads(MAN.read_text())}
for x in r:
 merged[x['name']]=x;print(json.dumps({k:v for k,v in x.items() if k in ['name','status','bytes','error']},ensure_ascii=False),flush=True)
MAN.write_text(json.dumps(list(merged.values()),ensure_ascii=False,indent=2)+'\n')
