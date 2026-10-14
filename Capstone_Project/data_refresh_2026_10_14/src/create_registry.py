from pathlib import Path
from urllib.parse import urlencode
import json

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parent
BUSINESSES=['FICC','ECS','RDS','WIS','ITP','Asset Services','DAS','DDA','Data Services','Consulting']
sources=[]
def add(id,name,url,kind,lines=None,extension='html',**kw):
    sources.append(dict(id=id,name=name,url=url,kind=kind,business_lines=lines or BUSINESSES,extension=extension,**kw))

for source in json.loads((PROJECT/'public_news_prototype/sources.json').read_text()):
    add(source['id'],source['name'],source['feed_url'],'rss',extension='xml',reference_url=source['reference_url'])

series=[
 ('SOFR','Secured Overnight Financing Rate','percent','daily',['FICC','ECS','RDS','WIS','Asset Services','Data Services','Consulting']),
 ('EFFR','Effective Federal Funds Rate','percent','daily',['FICC','ECS','RDS','WIS','Asset Services','Data Services','Consulting']),
 ('DGS10','10-year Treasury yield','percent','daily',['FICC','RDS','WIS','Asset Services','Data Services']),
 ('DGS2','2-year Treasury yield','percent','daily',['FICC','RDS','WIS','Data Services']),
 ('DGS3MO','3-month Treasury yield','percent','daily',BUSINESSES),
 ('BAA10Y','Baa corporate yield minus 10-year Treasury yield','percentage points','daily',['FICC','RDS','WIS','Asset Services','Data Services']),
 ('VIXCLS','CBOE equity volatility index','index points','daily',['ECS','WIS','ITP','Data Services']),
 ('NFCICREDIT','Chicago Fed credit subindex','index points','weekly',['FICC','ECS','RDS','WIS','Data Services']),
 ('BAMLC0A0CM','ICE BofA US Corporate Index option-adjusted spread','percent','daily',['RDS','WIS','Asset Services','Data Services']),
 ('SP500','S&P 500 index','index points','daily',['ECS','WIS','ITP','Data Services']),
 ('DTWEXBGS','Nominal broad US dollar index','index points','daily',['RDS','ITP','Asset Services','Data Services']),
 ('WRMFSL','Retail money market funds','billions of USD','weekly',['WIS','Asset Services','Data Services']),
 ('WIMFSL','Institutional money market funds','billions of USD','weekly',['WIS','Asset Services','Data Services']),
 ('CBBTCUSD','Coinbase Bitcoin price','USD per bitcoin','daily',['DAS','DDA','Data Services']),
 ('CBETHUSD','Coinbase Ethereum price','USD per ether','daily',['DAS','DDA','Data Services']),
 ('USEPUINDXM','US economic policy uncertainty','index points','monthly',BUSINESSES),
 ('JTU5200QUR','Finance and insurance quits rate, not seasonally adjusted','percent','monthly',BUSINESSES),
]
for sid,name,units,freq,lines in series:
    add('fred_'+sid,name,'https://fred.stlouisfed.org/graph/fredgraph.csv?'+urlencode({'id':sid,'cosd':'2026-07-01','coed':'2026-10-14'}),'market_series',lines,'csv',series_id=sid,units=units,frequency=freq,definition_url='https://fred.stlouisfed.org/series/'+sid,
        measurement_scope='External market proxy; not a DTCC business performance measure',vintage='current retrieval vintage; historical revisions possible')

for id,slug,lines in [
 ('dtcc_asset_services','asset-services',['Asset Services','ECS','DAS']),
 ('dtcc_wealth','wealth-investment-solutions',['WIS']),
 ('dtcc_rds','repository-derivatives-services',['RDS']),
 ('dtcc_itp','trade-processing-solutions',['ITP']),
 ('dtcc_digital','digital-assets',['DAS','DDA']),
 ('dtcc_data_services','data-services',['Data Services','RDS','Asset Services']),
 ('dtcc_consulting','consulting',['Consulting']),
 ('dtcc_clearing','clearing-settlement-services',['FICC','ECS']),
]:
    add(id,id.replace('dtcc_','').replace('_',' ').title(),'https://www.dtcc.com/products-and-services/'+slug,'business_reference',lines)
for id,path,kind,lines in [
 ('dtcc_press','press-releases','news_index',BUSINESSES),
 ('dtcc_insights','insights','news_index',BUSINESSES),
 ('dtcc_notices','legal/important-notices','notice_index',BUSINESSES),
 ('dtcc_rules','legal/regulatory-rule-filings','rule_index',BUSINESSES),
 ('dtcc_policy','legal/policy-and-compliance','disclosure_index',['FICC','ECS']),
 ('dtcc_financials','legal/financial-statements','financial_index',BUSINESSES),
 ('dtcc_market_data','market-index-data','public_market_index',['ECS','RDS','ITP','Asset Services','Data Services']),
 ('dtcc_money_market','products-and-services/data-services/money-market-kinetics-insights','public_market_index',['WIS','Asset Services','Data Services']),
]:
    add(id,id.replace('_',' ').title(),'https://www.dtcc.com/'+path,kind,lines)

add('ici_fund_flows','ICI weekly long-term mutual fund flows','https://www.ici.org/research/statistics/mutual-funds/weekly-estimated-longterm-mutual-fund-flows','industry_data_index',['WIS','ECS','Data Services'])
add('fca_publications','Financial Conduct Authority news and publications','https://www.fca.org.uk/what-we-publish','regulator_index',['RDS','WIS','ITP','DAS','DDA','Consulting'])
add('esma_news','European Securities and Markets Authority news','https://www.esma.europa.eu/press-news/esma-news','news_index',['RDS','ITP','WIS','DAS','DDA','Data Services','Consulting'])
add('cisa_kev','CISA Known Exploited Vulnerabilities','https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json','cyber_catalog',extension='json')
add('google_cloud','Google Cloud public service incidents','https://status.cloud.google.com/incidents.json','provider_incidents',extension='json')
add('google_workspace','Google Workspace public service incidents','https://www.google.com/appsstatus/dashboard/incidents.json','provider_incidents',extension='json')
params=[('conditions[publication_date][gte]','2026-10-07'),('conditions[publication_date][lte]','2026-10-14'),('conditions[agencies][]','securities-and-exchange-commission'),('conditions[agencies][]','commodity-futures-trading-commission'),('conditions[agencies][]','federal-reserve-system'),('per_page','1000'),('order','oldest')]
add('federal_register','Federal Register: SEC, CFTC and Federal Reserve publications','https://www.federalregister.gov/api/v1/documents.json?'+urlencode(params),'regulatory_documents',extension='json')
fema={'$filter':"declarationDate ge '2026-10-07T00:00:00.000Z' and declarationDate le '2026-10-14T23:59:59.000Z'",'$select':'disasterNumber,declarationDate,incidentType,state,declarationType,incidentBeginDate','$orderby':'declarationDate','$top':10000}
add('fema','FEMA disaster declarations','https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries?'+urlencode(fema),'disaster_declarations',extension='json')
ROOT.mkdir(parents=True,exist_ok=True)
(ROOT/'source_registry.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
print('Sources:',len(sources),'unique URLs:',len(set(s['url'] for s in sources)))
