"""Collect public source bodies once; preserve failures and retrieval timestamps."""
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import hashlib, json, subprocess, ssl

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'raw'
RAW.mkdir(parents=True, exist_ok=True)
UA = 'CapstonePublicRiskResearch/1.0 (academic public-data analysis)'
END = '2026-10-20'

def fetch(job):
    name, url = job
    path = RAW / name
    record = dict(name=name, url=url, retrieved_at_utc=datetime.now(timezone.utc).isoformat())
    if path.exists():
        record.update(status='cached', bytes=path.stat().st_size,
                      sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        return record
    try:
        with urlopen(Request(url, headers={'User-Agent':UA, 'Accept':'*/*'}), timeout=25) as response:
            body=response.read()
            record.update(http_status=response.status, content_type=response.headers.get('Content-Type'), final_url=response.url)
        path.write_bytes(body)
        record.update(status='downloaded', bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    except Exception as exc:
        if isinstance(getattr(exc,'reason',None), ssl.SSLCertVerificationError):
            result=subprocess.run(['/usr/bin/curl','--fail','--location','--silent','--show-error','--max-time','30',url,'--output',str(path)],capture_output=True,text=True)
            if result.returncode==0:
                body=path.read_bytes()
                record.update(status='downloaded',transport='system curl; TLS verification enabled',python_tls_error=repr(exc),bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
            else:
                if path.exists():path.unlink()
                record.update(status='failed',error=repr(exc),curl_error=result.stderr.strip())
        else:
            record.update(status='failed', error=repr(exc))
    return record

def main():
    jobs=[]
    for mnemonic in ['REPO-GCF_AR_OO-F','REPO-DVP_AR_OO-F','REPO-GCF_TV_TOT-F','REPO-TRIV1_TV_TOT-F']:
        jobs += [(mnemonic+'.json', 'https://data.financialresearch.gov/v1/series/timeseries?'+urlencode(dict(mnemonic=mnemonic,start_date='2018-01-01',end_date=END))),
                 (mnemonic+'_metadata.json','https://data.financialresearch.gov/v1/metadata/query?'+urlencode(dict(mnemonic=mnemonic)))]
    # This endpoint currently ignores date predicates and returns its full catalog.
    # Save one response, inspect actual competitiveAuctionCloseDate, and filter locally.
    jobs.append(('treasury_auctions_all.json','https://www.treasurydirect.gov/TA_WS/securities/search?format=json'))
    for sid in ['BOGZ1FU632051000Q','BOGZ1FU653164205Q']:
        jobs.append((sid+'.csv','https://fred.stlouisfed.org/graph/fredgraph.csv?'+urlencode(dict(id=sid,cosd='2000-01-01',coed=END))))
    jobs += [
      ('acats_lehman_2008.pdf','https://www.dtcc.com/-/media/Files/pdf/2008/9/24/a6712.pdf'),
      ('acats_project_2012.pdf','https://www.dtcc.com/-/media/Files/pdf/2012/12/21/a7556.pdf'),
      ('dtc_chill_2016.pdf','https://www.dtcc.com/-/media/Files/Downloads/legal/rule-filings/2016/dtc/SR-DTC-2016-003.pdf'),
      ('epn_rules.pdf','https://www.dtcc.com/~/media/files/downloads/legal/rules/ficc_mbsd_epnrules.pdf'),
      ('dtc_settlement_guide.pdf','https://www.dtcc.com/~/media/Files/Downloads/legal/service-guides/Settlement.pdf'),
      ('ficc_mbsd_rules.pdf','https://www.dtcc.com/~/media/Files/Downloads/legal/rules/ficc_mbsd_rules.pdf'),
      ('nscc_rules.pdf','https://www.dtcc.com/~/media/Files/Downloads/legal/rules/nscc_rules.pdf'),
      ('dtc_rules.pdf','https://www.dtcc.com/~/media/Files/Downloads/legal/rules/dtc_rules.pdf'),
      ('dtcc_2025_annual.pdf','https://www.dtcc.com/about/-/media/Files/Downloads/Annual%20Report/2025/DTCC-Annual-Report-2025-Print.pdf'),
      ('dtcc_2020_annual.pdf','https://www.dtcc.com/annuals/2020/pdf/DTCC_2020_AR_Print.pdf'),
      ('dtcc_2022_annual.pdf','https://www.dtcc.com/about/-/media/Files/Downloads/Annual-Report-2022/DTCC2022AR-PRINT.pdf'),
      ('dtcc_sandy_financials_2012.pdf','https://www.dtcc.com/annuals/2012/images/auditors-report/DTCC-Consolidated_Financial-Statements-Jai.pdf'),
      ('cds_financial_risk_model_2025.pdf','https://www.cds.ca/resource/en/56'),
      ('sft_access_2026.html','https://www.dtcc.com/press-releases/2026/dtcc-receives-regulatory-approval-to-launch-new-client-access-model-for-nsccs-sft-clearing-service'),
    ]
    old_path=ROOT/'fetch_manifest.json'
    old=json.loads(old_path.read_text()) if old_path.exists() else []
    records={r['name']:r for r in old}
    with ThreadPoolExecutor(max_workers=5) as pool:
        for record in pool.map(fetch,jobs):
            if record['status']=='cached' and record['name'] in records:
                continue
            if record['name'] in records:
                prior=records[record['name']]
                record['prior_attempts']=prior.get('prior_attempts',[])+[{k:v for k,v in prior.items() if k!='prior_attempts'}]
            records[record['name']]=record
            print(json.dumps({k:record[k] for k in ['name','status','bytes','error'] if k in record}),flush=True)
    old_path.write_text(json.dumps(list(records.values()),ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__': main()
