from pathlib import Path
import zipfile,io,hashlib,json,re
import pandas as pd,numpy as np,statsmodels.api as sm
ROOT=Path(__file__).resolve().parents[1];issues=[];daily=[];seen_hash={};logs=[]
for p in sorted((ROOT/'raw').glob('sec_ftd_*.zip')):
 h=hashlib.sha256(p.read_bytes()).hexdigest()
 if h in seen_hash:issues.append({'file':p.name,'issue':'duplicate_archive','other':seen_hash[h]});continue
 seen_hash[h]=p.name
 with zipfile.ZipFile(p) as z:
  names=[x for x in z.namelist() if not x.startswith('__MACOSX/') and not x.endswith('/')]
  for name in names:
   b=z.read(name);f=pd.read_csv(io.BytesIO(b),sep='|',dtype=str,encoding='cp1252',on_bad_lines='error',usecols=lambda c:c.strip() in ['SETTLEMENT DATE','CUSIP','QUANTITY (FAILS)'])
   f.columns=f.columns.str.strip();datecol=next(c for c in f if 'SETTLEMENT DATE' in c.upper());qcol=next(c for c in f if 'QUANTITY' in c.upper())
   f['date']=pd.to_datetime(f[datecol].str.strip(),format='%Y%m%d',errors='coerce');f['shares']=pd.to_numeric(f[qcol].str.strip(),errors='coerce');f=f.dropna(subset=['date','shares']);assert (f.shares>=0).all()
   assert not f.duplicated(['date','CUSIP']).any(),p.name
   expected=re.search(r'(\d{6})([ab])',p.name);ym,half=expected.groups();start=pd.Timestamp(ym[:4]+'-'+ym[4:]+'-01');end=start+pd.offsets.MonthBegin(1);valid=f.date.ge(start)&f.date.lt(end)
   if not valid.all():issues.append({'file':p.name,'issue':'rows_outside_filename_period','n':int((~valid).sum()),'observed_first':str(f.date.min().date()),'observed_last':str(f.date.max().date())})
   # Do not let a wrong half-month archive silently substitute for missing observations.
   f=f[valid]
   g=f.groupby('date').agg(outstanding_ftd_shares=('shares','sum'),securities_with_ftd=('CUSIP','nunique')).reset_index();g['source_file']=p.name;daily.append(g)
   print('Aggregated',p.name,len(f),'rows',flush=True) if len(logs)%30==0 else None
   logs.append({'file':p.name,'members':name,'records':len(f),'dates':len(g),'first':str(f.date.min().date()),'last':str(f.date.max().date()),'sha256':h})
d=pd.concat(daily).sort_values('date');dups=d[d.date.duplicated(False)];
if len(dups):
 assert dups.groupby('date')[['outstanding_ftd_shares','securities_with_ftd']].nunique().le(1).all().all(), 'Conflicting half-month boundary observations'
 d=d.drop_duplicates('date')
assert not d.date.duplicated().any();d.to_csv(ROOT/'data/sec_ftd_daily.csv',index=False)
pd.DataFrame(logs).to_csv(ROOT/'data/sec_ftd_file_coverage.csv',index=False);(ROOT/'results/ftd_quality_issues.json').write_text(json.dumps(issues,indent=2)+'\n')
from fit_equity_ftd import fit_volume_ftd
r=fit_volume_ftd()
print(json.dumps({k:v for k,v in r.items() if k!='source_quality_flags'},indent=2))
