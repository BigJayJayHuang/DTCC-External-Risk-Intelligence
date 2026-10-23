from collect_additions import fetch,ROOT
from concurrent.futures import ThreadPoolExecutor
import json
jobs=[('sec_ftd_canonical_index.html','https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data',20),('freddie_pmms_archive.html','https://www.freddiemac.com/pmms/pmms_archives',20),('freddie_pmms_history.xlsx','https://www.freddiemac.com/pmms/docs/historicalweeklydata.xlsx',20),('fred_mortgage_alt.csv','https://fred.stlouisfed.org/graph/fredgraph.csv?cosd=2018-01-01&coed=2026-10-15&id=MORTGAGE30US',25),('dtcc_sponsored_survey.html','https://www.dtcc.com/press-releases/2024/dtcc-survey-significant-improvements-in-industry-preparedness-around-expanded-us-treasury-clearing',20)]
with ThreadPoolExecutor(max_workers=5) as pool:r=list(pool.map(lambda x:fetch(*x),jobs))
r.append(fetch('finra_agency_mbs_probe.json','https://api.finra.org/data/group/fixedIncomeMarket/name/agencyMbsTradingActivity',timeout=20,method='POST',payload={'limit':3,'fields':['reportDate','agencyCode','categoryCode','productCode','subProductCode','valueAmount']}))
(ROOT/'source_page_fetch_manifest.json').write_text(json.dumps(r,indent=2)+'\n')
for x in r:print({k:v for k,v in x.items() if k in ['name','status','bytes','error']},flush=True)
