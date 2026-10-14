from pathlib import Path
from urllib.parse import urlencode
import json,hashlib
R=Path(__file__).resolve().parents[1]
sources=json.loads((R/'source_registry.json').read_text())
documents=[json.loads(l) for l in (R/'data/news_increment_2026_10_07_to_14.jsonl').read_text().splitlines()]
for d in documents:
    if d['url'] in {s['url'] for s in sources}:continue
    id='article_'+hashlib.sha256(d['url'].encode()).hexdigest()[:16]
    sources.append({'id':id,'name':d['source_name']+' original document','url':d['url'],'kind':'article','business_lines':d['business_lines_candidate'],'extension':'pdf' if 'files.dtcc.com/download/' in d['url'] else 'html','parent_document_id':d['document_id']})
sources.append({'id':'dtcc_insight_20261014','name':'DTCC Insights','url':'https://www.dtcc.com/insights/2026/why-data-quality-will-shape-the-next-era-of-regulatory-reporting','kind':'dated_article','business_lines':['RDS','Data Services','Consulting'],'extension':'html','publication_date_from_visible_listing':'2026-10-14'})
for sid,name,units in [('RMFSL','Retail money market funds, monthly seasonally adjusted','billions of USD'),('MMMFFAQ027S','Money market funds total financial assets','millions of USD')]:
    sources.append({'id':'fred_'+sid,'name':name,'url':'https://fred.stlouisfed.org/graph/fredgraph.csv?'+urlencode({'id':sid,'cosd':'2026-07-01' if sid=='RMFSL' else '2026-01-01','coed':'2026-10-14'}),'kind':'market_series','series_id':sid,'units':units,'frequency':'monthly' if sid=='RMFSL' else 'quarterly','business_lines':['WIS','Asset Services','Data Services'],'extension':'csv','definition_url':'https://fred.stlouisfed.org/series/'+sid})
sources=list({s['url']:s for s in sources}.values())
assert len({s['id'] for s in sources})==len(sources)
(R/'source_registry.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2))
print('Registered',len(documents),'original documents plus business article and replacement money-market series')
