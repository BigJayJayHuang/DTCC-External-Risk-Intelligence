from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from datetime import datetime,timezone
import json,hashlib,urllib.parse,time
ROOT=Path(__file__).resolve().parents[1];RAW=ROOT/'raw';MAN=ROOT/'fetch_manifest.json'
UA='CapstoneExternalRiskResearch/1.0 (public academic data collection)'

def fetch(name,url,timeout=20,method='GET',payload=None):
 dest=RAW/name
 rec={'name':name,'url':url,'method':method,'collected_at_utc':datetime.now(timezone.utc).isoformat()}
 if dest.exists():
  rec.update(status='cached',bytes=dest.stat().st_size,sha256=hashlib.sha256(dest.read_bytes()).hexdigest());return rec
 try:
  req=Request(url,data=json.dumps(payload).encode() if payload is not None else None,headers={'User-Agent':UA,'Accept':'*/*',**({'Content-Type':'application/json'} if payload else {})},method=method)
  with urlopen(req,timeout=timeout) as r:
   b=r.read();rec.update(status='downloaded',http_status=r.status,content_type=r.headers.get('Content-Type'),final_url=r.url)
  dest.write_bytes(b);rec.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 except Exception as e:rec.update(status='failed',error=repr(e))
 return rec

def main():
 jobs=[(s+'.csv','https://fred.stlouisfed.org/graph/fredgraph.csv?'+urllib.parse.urlencode({'id':s,'cosd':'2018-01-01','coed':'2026-10-15'})) for s in ['MORTGAGE30US','DCPF3M','DTB3']]
 jobs += [
 ('ofr_repo_mnemonics.json','https://data.financialresearch.gov/v1/metadata/mnemonics?dataset=repo'),
 ('cboe_2018.csv','https://cdn.cboe.com/resources/us/equities/market-statistics/historical-market-volume/market_history_2018.csv'),
 ('sec_ftd_index.html','https://www.sec.gov/data/foiadocsfailsdatahtm'),
 ('dtcc_2008_report.pdf','https://www.dtcc.com/-/media/Files/Downloads/About/Annual-Reports/2008_report.pdf'),
 ('treasury_icbc_2024.html','https://home.treasury.gov/news/press-releases/jy2114'),
 ('dtcc_t1_20240530.html','https://www.dtcc.com/press-releases/2024/dtcc-comments-on-industrys-t1-progress'),
 ('ofr_annual_2024.pdf','https://www.financialresearch.gov/annual-reports/files/OFR-AR-2024_web.pdf'),
 ('sec_treasury_2023.html','https://www.sec.gov/newsroom/press-releases/2023-247'),
 ('sec_treasury_extension_2025.pdf','https://www.sec.gov/files/rules/final/2025/34-102487.pdf')]
 old=json.loads(MAN.read_text()) if MAN.exists() else []
 with ThreadPoolExecutor(max_workers=4) as pool:r=list(pool.map(lambda x:fetch(*x),jobs))
 merged={x['name']:x for x in old}
 for x in r:merged[x['name']]=x;print(json.dumps({k:v for k,v in x.items() if k in ['name','status','bytes','error']},ensure_ascii=False),flush=True)
 MAN.write_text(json.dumps(list(merged.values()),ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
