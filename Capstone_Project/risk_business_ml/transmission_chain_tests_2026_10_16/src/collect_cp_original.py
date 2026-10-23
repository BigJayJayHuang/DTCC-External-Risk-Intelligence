from collect_additions import fetch,ROOT
from concurrent.futures import ThreadPoolExecutor
import json
jobs=[('fed_cp_xml.zip','https://www.federalreserve.gov/releases/cp/data/FRB_CP_xml.zip',45),('fed_h15_xml.zip','https://www.federalreserve.gov/releases/h15/data/FRB_h15_xml.zip',60)]
with ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(lambda x:fetch(*x),jobs))
(ROOT/'fed_original_fetch_manifest.json').write_text(json.dumps(r,indent=2)+'\n')
for x in r:print({k:v for k,v in x.items() if k in ['name','status','bytes','error']},flush=True)
