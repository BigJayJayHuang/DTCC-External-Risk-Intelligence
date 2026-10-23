from collect_additions import fetch,ROOT,RAW
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urljoin
import json,re,time
class Links(HTMLParser):
 def __init__(self):super().__init__();self.hrefs=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':
   d=dict(attrs)
   if 'href' in d:self.hrefs.append(d['href'])
def main():
 jobs=[('freddie_pmms_history.csv','https://www.freddiemac.com/pmms/docs/PMMS_history.csv',25)]
 results=[fetch(*j) for j in jobs]
 p=RAW/'sec_ftd_canonical_index.html'
 if p.exists():
  parser=Links();parser.feed(p.read_text())
  urls=[]
  for h in parser.hrefs:
   m=re.search(r'cnsfails?(\d{6})([ab])\.zip',h,re.I)
   if m and '201801'<=m.group(1)<='202609':urls.append((f'sec_ftd_{m.group(1)}{m.group(2)}.zip',urljoin('https://www.sec.gov',h)))
  urls=list(dict(urls).items())
  for i,(name,url) in enumerate(urls):
   x=fetch(name,url,18);results.append(x)
   if i%24==0:print('FTD canonical',i,len(urls),name,x['status'],flush=True)
   time.sleep(.13)
 else:
  print('No local canonical index, use verified canonical distribution prefix after February2020',flush=True)
  for year in range(2020,2027):
   for month in range(1,13):
    if year==2026 and month>9:continue
    for half in ['a','b']:
     name=f'sec_ftd_{year}{month:02}{half}.zip';url=f'https://www.sec.gov/files/node/add/data_distribution/cnsfails{year}{month:02}{half}.zip';x=fetch(name,url,12);results.append(x)
     if x['status']=='failed':print(name,x.get('error'),flush=True)
     if len(results)>8 and all(z['status']=='failed' for z in results[-4:]):break
     time.sleep(.13)
    if len(results)>8 and all(z['status']=='failed' for z in results[-4:]):break
   print('FTD year',year,len(results),flush=True)
 (ROOT/'canonical_fetch_manifest.json').write_text(json.dumps(results,indent=2)+'\n')
 print('canonical total',len(results),'success',sum(x['status']!='failed' for x in results),flush=True)
if __name__=='__main__':main()
