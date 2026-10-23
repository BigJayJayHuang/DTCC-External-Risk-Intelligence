from collect_additions import fetch,ROOT
import json
jobs=[('sec_ftd_201910a.zip','https://www.sec.gov/files/data/fails-deliver-data/cnsfails201910a_0.zip',20),('sec_ftd_202605a.zip','https://www.sec.gov/files/data/other/fails-deliver-data/cnsfails202605a.zip',20),('sec_ftd_202605b.zip','https://www.sec.gov/files/data/other/fails-deliver-data/cnsfails202605b.zip',20)]
r=[fetch(*x) for x in jobs];(ROOT/'repaired_ftd_manifest.json').write_text(json.dumps(r,indent=2)+'\n');print([{k:v for k,v in x.items() if k in ['name','status','bytes','error']} for x in r],flush=True)
