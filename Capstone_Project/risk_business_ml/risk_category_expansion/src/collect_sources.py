"""Download bounded public risk sources; preserve successful and failed requests."""
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urlparse
import hashlib, json, time

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'raw'
RAW.mkdir(exist_ok=True)
ALLOWED = {'www.cisa.gov','status.cloud.google.com','www.google.com','fred.stlouisfed.org','www.fema.gov','www.federalregister.gov'}
jobs = [
    ('cisa_kev.json','https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'),
    ('google_cloud_incidents.json','https://status.cloud.google.com/incidents.json'),
    ('google_workspace_incidents.json','https://www.google.com/appsstatus/dashboard/incidents.json'),
    ('google_cloud_summary.html','https://status.cloud.google.com/summary'),
]
for series in ['JTU5200QUR','USEPUINDXM','DGS3MO']:
    jobs.append((series+'.csv','https://fred.stlouisfed.org/graph/fredgraph.csv?' + urlencode({'id':series,'cosd':'2019-01-01','coed':'2026-06-30'})))
fema_params = {'$filter':"declarationDate ge '2019-01-01T00:00:00.000Z' and declarationDate le '2026-06-30T23:59:59.000Z'",
               '$select':'disasterNumber,declarationDate,incidentType,state,declarationType,incidentBeginDate', '$orderby':'declarationDate', '$top':10000, '$skip':0}
fema_base='https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries'
jobs.append(('fema_declarations_00000.json',fema_base+'?'+urlencode(fema_params)))
fr_params = [('conditions[publication_date][gte]','2019-01-01'),('conditions[publication_date][lte]','2026-06-30'),
             ('conditions[type][]','RULE'),('conditions[agencies][]','securities-and-exchange-commission'),
             ('conditions[agencies][]','commodity-futures-trading-commission'),('conditions[agencies][]','federal-reserve-system'),
             ('per_page','1000'),('order','oldest')]
jobs.append(('federal_register_rules_001.json','https://www.federalregister.gov/api/v1/documents.json?'+urlencode(fr_params)))

def fetch(job):
    name,url=job
    assert urlparse(url).hostname in ALLOWED
    path=RAW/name
    record={'file':str(path.relative_to(ROOT)),'url':url,'fetched_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        req=Request(url,headers={'User-Agent':'Capstone public-data research','Accept':'application/json,text/csv,text/html'})
        with urlopen(req,timeout=45) as response:
            data=response.read(32*1024*1024+1)
            if len(data)>32*1024*1024: raise ValueError('Response exceeds bounded 32 MiB size')
            record.update(http_status=response.status,content_type=response.headers.get('content-type'))
        if name.endswith('.json'): json.loads(data)
        elif name.endswith('.csv') and b'<html' in data[:1000].lower():raise ValueError('HTML response instead of CSV')
        path.write_bytes(data)
        record.update(status='downloaded',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        print(name,'downloaded',len(data),'bytes',flush=True)
    except Exception as exc:
        record.update(status='unavailable',error=str(exc))
        print(name,'unavailable',str(exc),flush=True)
    return record

records=[]
with ThreadPoolExecutor(max_workers=4) as pool:
    for future in as_completed([pool.submit(fetch,j) for j in jobs]): records.append(future.result())

# Follow official pagination only after inspecting the first responses.
fp=RAW/'fema_declarations_00000.json'
if fp.exists():
    obj=json.loads(fp.read_text())
    n=len(obj.get('DisasterDeclarationsSummaries',[]))
    skip=n
    while n==10000 and skip<=90000:
        fema_params['$skip']=skip
        rec=fetch((f'fema_declarations_{skip:05}.json',fema_base+'?'+urlencode(fema_params)))
        records.append(rec)
        if rec['status']!='downloaded':break
        obj=json.loads((ROOT/rec['file']).read_text())
        n=len(obj.get('DisasterDeclarationsSummaries',[]))
        skip+=n
        time.sleep(.25)
frp=RAW/'federal_register_rules_001.json'
if frp.exists():
    obj=json.loads(frp.read_text())
    next_url=obj.get('next_page_url')
    page=2
    while next_url and page<=10:
        rec=fetch((f'federal_register_rules_{page:03}.json',next_url))
        records.append(rec)
        if rec['status']!='downloaded':break
        obj=json.loads((ROOT/rec['file']).read_text());next_url=obj.get('next_page_url');page+=1
        time.sleep(.25)
(ROOT/'source_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
print('Saved source manifest:',sum(r['status']=='downloaded' for r in records),'successful downloads',flush=True)
