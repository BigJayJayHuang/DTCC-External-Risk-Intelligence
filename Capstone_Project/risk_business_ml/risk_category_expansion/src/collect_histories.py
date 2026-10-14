from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import json,hashlib
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'raw'
records=[]
def get(name,url):
    rec={'file':'raw/'+name,'url':url,'fetched_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(url,headers={'User-Agent':'Capstone public-data research'}),timeout=35) as r:data=r.read(4*1024*1024+1)
        if len(data)>4*1024*1024:raise ValueError('Response exceeds 4 MiB')
        (RAW/name).write_bytes(data)
        rec.update(status='downloaded',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        print(name,'downloaded',len(data),flush=True)
    except Exception as e:
        rec.update(status='unavailable',error=str(e));print(name,str(e),flush=True)
    return rec

records.append(get('google_workspace_summary.html','https://www.google.com/appsstatus/dashboard/summary'))
groups={
 'it':['Google Compute Engine','Google Kubernetes Engine (GKE)','Google Cloud Networking','Virtual Private Cloud (VPC)'],
 'data':['Google Cloud Storage','Google Cloud SQL','Google BigQuery','Cloud Spanner'],
 'third_party':['Gmail','Google Drive','Google Calendar','Google Meet'],
}
discovered=[]
for group,names in groups.items():
    base='https://www.google.com/appsstatus/dashboard/' if group=='third_party' else 'https://status.cloud.google.com/'
    soup=BeautifulSoup((RAW/('google_workspace_summary.html' if group=='third_party' else 'google_cloud_summary.html')).read_text(),'html.parser')
    for name in names:
        found=[a for a in soup.select('a[href]') if a.get_text(' ',strip=True)=='See more for '+name]
        if not found:
            print('History link absent:',name,flush=True);continue
        url=urljoin(base,found[0]['href'])
        filename='history_'+group+'_'+name.lower().replace(' ','_').replace('(','').replace(')','')+'.html'
        discovered.append({'group':group,'product':name,'url':url,'file':'raw/'+filename})
with ThreadPoolExecutor(max_workers=3) as p:
    for result in as_completed([p.submit(get,x['file'].split('/')[-1],x['url']) for x in discovered]):records.append(result.result())
(ROOT/'history_products.json').write_text(json.dumps(discovered,ensure_ascii=False,indent=2))
manifest=json.loads((ROOT/'source_manifest.json').read_text())
manifest.extend(records)
for series in ['JTU5200QUR','USEPUINDXM','DGS3MO']:
    path=RAW/(series+'.csv')
    if path.exists():
        manifest.append({'file':'raw/'+path.name,'url':'https://fred.stlouisfed.org/graph/fredgraph.csv?id='+series+'&cosd=2019-01-01&coed=2026-06-30',
                         'status':'downloaded','method':'curl retry','bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                         'fetched_at_utc':datetime.now(timezone.utc).isoformat()})
(ROOT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
