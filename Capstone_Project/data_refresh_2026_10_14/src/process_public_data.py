#!/usr/bin/env python3
"""Normalize the dated snapshot without overwriting earlier research inputs."""
from pathlib import Path
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date
import importlib.util, json, hashlib, re, csv, sqlite3, collections
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parent
DATA=ROOT/'data';DATA.mkdir(exist_ok=True)
START=date(2026,10,7);END=date(2026,10,14);ET_ZONE=ZoneInfo('America/New_York')
BUSINESSES=['FICC','ECS','RDS','WIS','ITP','Asset Services','DAS','DDA','Data Services','Consulting']
REGISTRY=json.loads((ROOT/'source_registry.json').read_text())
SOURCES={s['id']:s for s in REGISTRY}
MANIFEST=json.loads((ROOT/'source_manifest.json').read_text())
FETCHED={s['source_id']:s for s in MANIFEST if s['status'] in ['downloaded','retrieved_via_web'] and s['source_id'] in SOURCES}
spec=importlib.util.spec_from_file_location('news_prototype',PROJECT/'public_news_prototype/collect.py')
news=importlib.util.module_from_spec(spec);spec.loader.exec_module(news)

def dump(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str)+'\n')
def jsonl(path,rows):
    path.write_text(''.join(json.dumps(r,ensure_ascii=False,default=str)+'\n' for r in rows))
def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value,str) else value).hexdigest()
def export(name,rows,columns=None):
    d=pd.DataFrame(rows,columns=columns) if columns else pd.DataFrame(rows)
    for c in d:
        if d[c].map(lambda x:isinstance(x,(list,dict))).any():
            d[c]=d[c].map(lambda x:json.dumps(x,ensure_ascii=False) if isinstance(x,(list,dict)) else x)
    d.to_csv(DATA/name,index=False,encoding='utf-8-sig')
def canonical(url):
    return news.normalize_url(url,url)
def local_name(t):return t.rsplit('}',1)[-1]
def field(node,*names):return next((''.join(c.itertext()).strip() for n in names for c in node if local_name(c.tag)==n),'')

# Routing rules are reviewable candidates. Legal-entity-wide data are not allocated to segments.
ROUTES=[
 ('funding_rates',['treasury','treasuries','repo','repurchase agreement','ficc','mortgage-backed','fomc'],['FICC'],'funding_rates'),
 ('equities',['equity','equities','etf','exchange-traded','equity clearing','continuous net settlement'],['ECS'],'equity_market'),
 ('reporting',['trade repository','transaction reporting','trade reporting','emir','sftr','swap','swaps','derivatives'],['RDS'],'reporting_credit'),
 ('wealth',['mutual fund','fund/serv','fundserv','private market','private credit','annuity','annuities','insurance','aip'],['WIS'],'funds_insurance'),
 ('trade_processing',['ctm','tradesuite','trade affirmation','trade matching','standing settlement','ssi','t+1','settlement cycle'],['ITP'],'processing_settlement'),
 ('custody',['corporate action','custody','underwriting','ipo','dividend','reorganization','redemption','tax relief','depositary','issuer services','cusip'],['Asset Services'],'custody_corporate_actions'),
 ('tokenization',['tokenization','tokenisation','tokenized','tokenised','stablecoin','digital asset','blockchain'],['DAS','DDA'],'digital_asset'),
 ('platform',['composerx','digital launchpad','collateral appchain','interoperability','smart contract'],['DDA'],'platform_technology'),
 ('data',['market data','data quality','reference data','data transparency','kinetics'],['Data Services'],'data_management'),
 ('readiness',['clearing mandate','treasury clearing','regulatory readiness','regulatory reporting','t+1','emir','sftr'],['Consulting'],'regulatory_readiness'),
 ('settlement',['settlement cycle','t+1','settlement fail','settlement disruption','nscc','dtc settlement'],['ECS'],'processing_settlement'),
 ('shared_cyber',['cyber','ransomware','operational resilience','third-party','third party'],BUSINESSES,'cyber_third_party'),
]
def route(title,summary,source_id):
    text=title+'\n'+summary;links=[]
    for rule,terms,lines,channel in ROUTES:
        matches=[t for t in terms if re.search(r'(?<!\w)'+re.escape(t)+r'(?!\w)',text,re.I)]
        if matches:
            for b in lines:links.append({'business_line':b,'rule':rule,'matched_terms':matches,'risk_channel':channel,'review_status':'candidate_unreviewed','business_impact_confirmed':False})
    if source_id=='dtcc_notice_feed':
        if re.match(r'GOV|MBS|CMU',title,re.I):links.append({'business_line':'FICC','rule':'official_notice_prefix','matched_terms':[title],'risk_channel':'service_notice','review_status':'candidate_unreviewed','business_impact_confirmed':False})
    if source_id=='ici_money_market_release':
        for b in ['WIS','Asset Services','Data Services']:
            links.append({'business_line':b,'rule':'shared_industry_fund_assets','matched_terms':['official industry fund-asset table'],'risk_channel':'funds_market_context','review_status':'candidate_unreviewed','business_impact_confirmed':False})
    return links

DOCUMENTS=[];PARSE=[]
def add_document(source,title,url,summary,date_raw,published_utc=None,extra=None):
    summary=summary or ''
    flags=[]
    pub_date=None;date_basis=None
    if published_utc:
        pub_date=datetime.fromisoformat(published_utc.replace('Z','+00:00')).astimezone(ET_ZONE).date();date_basis='known publication timestamp converted to America/New_York'
    elif date_raw:
        try:
            parsed=parse_date(date_raw,dayfirst=source['source_id']=='esma_news')
            pub_date=parsed.date();date_basis='publisher calendar date; timezone unverified'
            flags.append('publication_timezone_unverified')
        except Exception:flags.append('unparseable_publication_date')
    if not pub_date:flags.append('missing_publication_date')
    if published_utc and published_utc>source['collected_at_utc']:flags.append('publication_after_collection')
    url=canonical(url);links=route(title,summary,source['source_id'])
    record={'document_id':digest(url),'source_id':source['source_id'],'source_name':source['source_name'],'url':url,
            'title':news.clean(title),'source_summary':news.clean(summary),'published_at_raw':date_raw or None,
            'published_at_utc':published_utc,'publication_date':pub_date.isoformat() if pub_date else None,
            'date_filter_basis':date_basis,'collected_at_utc':source['collected_at_utc'],
            'raw_file':source['file'],'raw_sha256':source.get('sha256'),
            'in_requested_window':bool(pub_date and START<=pub_date<=END),'event_time':None,'effective_time':None,
            'text_scope':'publisher_feed_or_index_summary','review_status':'unreviewed',
            'business_lines_candidate':sorted(set(x['business_line'] for x in links)),
            'routing_evidence':links,'quality_flags':flags,'severity':None,'impact_analysis':None,'ai_generated_analysis':False}
    if extra:record.update(extra)
    record['content_hash']=digest(json.dumps({k:record[k] for k in ['title','source_summary','published_at_raw']},sort_keys=True))
    DOCUMENTS.append(record)

for sid,r in FETCHED.items():
    kind=r['kind'];path=ROOT/r['file']
    if kind=='rss':
        root=ET.fromstring(path.read_bytes());entries=[e for e in root.iter() if local_name(e.tag) in ['item','entry']]
        for e in entries:
            title=field(e,'title');url=field(e,'link')
            if local_name(e.tag)=='entry':url=next((c.get('href','') for c in e if local_name(c.tag)=='link'),'')
            if not title or not url:continue
            raw=field(e,'pubDate','published','date');stamp,issue=news.normalize_date(raw)
            add_document(r,title,url,field(e,'description','summary'),raw,stamp)
        PARSE.append({'source_id':sid,'parsed_records':len(entries),'last_publication_date':max((d['publication_date'] or '' for d in DOCUMENTS if d['source_id']==sid),default=None),'coverage_limit':'publisher current feed window; not complete historical coverage'})
    elif kind=='regulatory_documents':
        obj=json.loads(path.read_text());items=obj.get('results',[])
        for x in items:add_document(r,x['title'],x['html_url'],x.get('abstract',''),x['publication_date'],extra={'document_number':x['document_number'],'publication_type':x.get('type'),'agency_names':[a['name'] for a in x.get('agencies',[])]})
        PARSE.append({'source_id':sid,'parsed_records':len(items),'reported_count':obj.get('count'),'next_page_url':obj.get('next_page_url'),'coverage_limit':'Only SEC, CFTC and Federal Reserve publications; count is not risk severity'})
    elif sid=='esma_news':
        soup=BeautifulSoup(path.read_text(),'html.parser')
        for a in soup.select('a[href]'):
            if '/press-news/esma-news/' not in a['href']:continue
            text=a.get_text(' ',strip=True);m=re.search(r'\b(\d{2}/\d{2}/2026)\b',text)
            if m:add_document(r,text[:m.start()].strip(),urljoin(r['url'],a['href']),text[m.end():].strip(),m[1])
        PARSE.append({'source_id':sid,'parsed_records':sum(d['source_id']==sid for d in DOCUMENTS),'coverage_limit':'first public news-index page; date-only timestamps'})
    elif kind=='dated_article':
        soup=BeautifulSoup(path.read_text(),'html.parser')
        title=soup.find('h1').get_text(' ',strip=True)
        add_document(r,title,r['url'],'',SOURCES[sid]['publication_date_from_visible_listing'],extra={'text_scope':'original_article'})
    elif kind=='industry_table_capture':
        obj=json.loads(path.read_text())
        add_document(r,obj['title'],r['url'],'Industry money-market fund assets, with retail/institutional and fund-type breakdowns.',obj['publication_date'],extra={'text_scope':'public_official_table_transcription','business_lines_candidate':['WIS','Asset Services','Data Services']})

# Preserve proper original text when obtainable; challenge pages remain unavailable evidence.
article_by_url={r['url']:r for r in FETCHED.values() if r['kind'] in ['article','dated_article']}
text_folder=DATA/'original_document_text';text_folder.mkdir(exist_ok=True)
content_inventory=[]
for d in DOCUMENTS:
    r=article_by_url.get(d['url'])
    if not r:
        d['original_content_status']='structured_public_table_capture' if d['source_id']=='ici_money_market_release' else 'not_downloaded_or_access_denied';continue
    path=ROOT/r['file'];blob=path.read_bytes();body='';status='available'
    if blob.startswith(b'%PDF-'):
        from pypdf import PdfReader
        try:body='\n\n'.join(p.extract_text() or '' for p in PdfReader(path).pages)
        except Exception as exc:status='pdf_extraction_failed';d['quality_flags'].append(status)
    else:
        soup=BeautifulSoup(blob,'html.parser');page_title=soup.title.get_text(' ',strip=True) if soup.title else ''
        if 'Request Access' in page_title or 'Access Denied' in page_title:
            status='publisher_automated_access_block';body=''
        else:
            area=soup.find('main') or soup.find('article') or soup.find(id='article') or soup.find(id='main-content') or soup.find(id='content')
            if area:
                for t in area.find_all(['script','style','nav','footer']):t.decompose()
                if 'dtcc.com' in d['url'] and area.select('.content-item--richtextblock .rtf'):
                    body='\n\n'.join(t.get_text('\n',strip=True) for t in area.select('.content-item--richtextblock .rtf'))
                else:body=area.get_text('\n',strip=True)
            else:status='no_article_body_identified'
    if body and len(body)<100:status='insufficient_original_text'
    d['original_content_status']=status;d['original_raw_file']=r['file']
    if status=='available' and body:
        textpath=text_folder/(d['document_id']+'.txt');textpath.write_text(body)
        d.update(original_text_file=str(textpath.relative_to(ROOT)),original_text_sha256=digest(body),original_text_characters=len(body))
        # Route on source article text, retaining unverified candidate status.
        d['routing_evidence']=route(d['title'],d['source_summary']+'\n'+body,d['source_id'])
        d['business_lines_candidate']=sorted(set(x['business_line'] for x in d['routing_evidence']))
    content_inventory.append({'document_id':d['document_id'],'url':d['url'],'original_content_status':status,'text_characters':len(body),'original_file':r['file'],'publisher_metadata_file':d['raw_file']})
export('original_document_content_coverage.csv',content_inventory)
for row in PARSE:
    if not row.get('last_publication_date'):
        row['last_publication_date']=max((d['publication_date'] or '' for d in DOCUMENTS if d['source_id']==row['source_id']),default=None)

# Document duplicates are merged by canonical URL; unrelated articles about one event remain distinct.
unique={}
for d in DOCUMENTS:
    if d['document_id'] not in unique:unique[d['document_id']]=dict(d,observed_source_ids=[d['source_id']])
    else:
        old=unique[d['document_id']];old['observed_source_ids']=sorted(set(old['observed_source_ids']+[d['source_id']]))
documents=sorted(unique.values(),key=lambda d:(d['publication_date'] or '',d['document_id']),reverse=True)
increment=[d for d in documents if d['in_requested_window']]
jsonl(DATA/'news_documents_all_current_feeds.jsonl',documents)
jsonl(DATA/'news_increment_2026_10_07_to_14.jsonl',increment)
export('news_increment_2026_10_07_to_14.csv',increment)
export('news_source_coverage.csv',PARSE)
links=[dict(document_id=d['document_id'],**x) for d in increment for x in d['routing_evidence']]
export('news_business_links.csv',links,['document_id','business_line','rule','matched_terms','risk_channel','review_status','business_impact_confirmed'])

# Update market series with a warm-up buffer; retain prior snapshots and log current-vintage revisions.
old_paths={}
for folder in [PROJECT/'risk_business_ml/raw/risk_series',PROJECT/'risk_business_ml/risk_category_expansion/raw',PROJECT/'risk_business_ml/event_vulnerability_tests_2026_10_06/raw/daily']:
    for p in folder.glob('*.csv'):
        sid=p.stem
        if sid in ['SOFR','EFFR','DGS10','DGS2','DGS3MO','BAA10Y','VIXCLS','NFCICREDIT','USEPUINDXM','JTU5200QUR']:
            if sid not in old_paths or pd.read_csv(p).iloc[-1,0]>pd.read_csv(old_paths[sid]).iloc[-1,0]:old_paths[sid]=p
market=[];revisions=[];market_coverage=[];reuse=[]
for source in REGISTRY:
    if source['kind']!='market_series':continue
    sid=source['series_id'];r=FETCHED.get(source['id']);old={}
    if sid in old_paths:
        p=old_paths[sid];reuse.append({'file':str(p.relative_to(PROJECT)),'sha256':digest(p.read_bytes()),'use':'prior market history'})
        frame=pd.read_csv(p,dtype=str)
        for _,row in frame.iterrows():
            when=row.iloc[0];raw=row.iloc[1]
            val=pd.to_numeric(raw,errors='coerce')
            if when<=END.isoformat():old[when]={'series_id':sid,'observation_date':when,'value':float(val) if pd.notna(val) else None,'units':source['units'],'frequency':source['frequency'],'source_id':source['id'],'source_file':str(p.relative_to(PROJECT)),'evidence_location':'prior_project_snapshot','collected_at_utc':None,'vintage_id':'prior_snapshot','publication_date':None}
    new={}
    if r:
        frame=pd.read_csv(ROOT/r['file'],dtype=str)
        assert list(frame.columns)==['observation_date',sid],(sid,list(frame.columns))
        for _,row in frame.iterrows():
            when=row.iloc[0]
            # Some providers return full histories despite the requested date bounds.
            buffer_start=dict(parse_qsl(urlsplit(source['url']).query)).get('cosd','2026-07-01')
            if not buffer_start<=when<=END.isoformat():continue
            raw=row.iloc[1];val=pd.to_numeric(raw,errors='coerce')
            record={'series_id':sid,'observation_date':when,'value':float(val) if pd.notna(val) else None,'units':source['units'],'frequency':source['frequency'],'source_id':source['id'],'source_file':r['file'],'evidence_location':'current_snapshot','collected_at_utc':r['collected_at_utc'],'vintage_id':'2026-10-14_current_retrieval','publication_date':None}
            if when in old and old[when]['value']!=record['value']:
                revisions.append({'series_id':sid,'observation_date':when,'prior_value':old[when]['value'],'current_value':record['value'],'current_raw_file':r['file'],'interpretation':'historical revision or later publication; not a new event'})
            new[when]=record
        old.update(new)
    values=list(old.values());market.extend(values)
    fresh=[x for x in new.values() if x['observation_date']>=START.isoformat()]
    valid=[x['observation_date'] for x in values if x['value'] is not None]
    current_valid=[x['observation_date'] for x in new.values() if x['value'] is not None]
    provider_latest=frame.iloc[-1,0] if r and len(frame) else None
    market_coverage.append({'source_id':source['id'],'series_id':sid,'frequency':source['frequency'],'units':source['units'],'download_status':r['status'] if r else 'unavailable','latest_nonmissing_observation':max(valid,default=None),'latest_current_observation':max(current_valid,default=None),'raw_provider_last_date':provider_latest,'availability_status':'discontinued_history_only' if sid in ['WRMFSL','WIMFSL'] else ('observations_in_requested_window' if fresh else 'no_new_period_observation'),'window_rows':len(fresh),'window_nonmissing_rows':sum(x['value'] is not None for x in fresh),'current_buffer_rows':len(new),'freshness_note':'Observation date differs from release/collection date; monthly and weekly series update on their own schedule. No forward fill.'})
for x in market:
    freq=x['frequency'];d=pd.Timestamp(x['observation_date'])
    period=d.to_period('Q') if freq=='quarterly' else (d.to_period('M') if freq=='monthly' else None)
    x['measurement_period']=str(period) if period else x['observation_date']
    x['measurement_period_end']=period.end_time.date().isoformat() if period else x['observation_date']
market.sort(key=lambda x:(x['series_id'],x['observation_date']))
export('market_observations_updated.csv',market)
export('market_increment_2026_10_07_to_14.csv',[x for x in market if x['observation_date']>=START.isoformat()])
export('market_historical_revision_log.csv',revisions,['series_id','observation_date','prior_value','current_value','current_raw_file','interpretation'])
export('market_series_coverage.csv',market_coverage)

# Seven original daily signals, recalculated with strictly preceding thresholds.
wide=pd.DataFrame(market).pivot(index='observation_date',columns='series_id',values='value');wide.index=pd.to_datetime(wide.index)
daily={s:wide[s].dropna() for s in ['SOFR','EFFR','DGS10','BAA10Y','VIXCLS']}
basis=(daily['SOFR']-daily['EFFR']).dropna()*100
last_weekday=pd.Series([pd.offsets.BDay().rollback(d.to_period('Q').end_time.normalize()) for d in basis.index],index=basis.index)
flags=np.array([d>=e-pd.offsets.BDay(2) for d,e in last_weekday.items()]);adjusted=[]
for i in range(len(basis)):
    past=basis.iloc[max(0,i-252):i];pastflags=flags[max(0,i-252):i]
    if len(past)<126:
        adjusted.append(np.nan);continue
    group=past[pastflags==flags[i]]
    baseline=group.median() if len(group)>=6 else past.median()
    adjusted.append(basis.iloc[i]-baseline)
changes=daily['DGS10'].diff()*100
features={'sofr_effr':basis,'sofr_effr_adjusted':pd.Series(adjusted,index=basis.index),'ust10_abs_change':changes.abs(),'ust10_rv20':changes.rolling(20,min_periods=20).std(),'baa_spread':daily['BAA10Y']*100,'baa_widen20':(daily['BAA10Y'].diff(20)*100).clip(lower=0),'vix':daily['VIXCLS']}
derived=[]
for name,values in features.items():
    values=values.dropna();threshold=values.shift(1).rolling(252,min_periods=126).quantile(.9)
    for d,v in values.items():
        if START<=d.date()<=END:derived.append({'date':d.date().isoformat(),'indicator':name,'value':v,'unit':'index points' if name=='vix' else ('bp/day' if name=='ust10_rv20' else 'bp'),'threshold_past90':threshold.loc[d] if pd.notna(threshold.loc[d]) else None,'alarm':bool(v>threshold.loc[d]) if pd.notna(threshold.loc[d]) else None,'lookback_observations':min(values.index.get_loc(d),252),'interpretation':'external market monitoring signal; not a business risk score'})
export('daily_market_signals_increment.csv',derived)

# Official business-page statistics. aria-label avoids duplicated animated numbers.
stats=[]
for sid,r in FETCHED.items():
    if SOURCES[sid]['kind']!='business_reference' or sid=='dtcc_etf_listing_csv':continue
    soup=BeautifulSoup((ROOT/r['file']).read_text(),'html.parser')
    for section in soup.select('.stat-cards-container'):
        footer=section.select_one('.stat-cards-container__footnote')
        period=footer.get_text(' ',strip=True) if footer else next((t for t in section.stripped_strings if t.startswith('Data as of')),'reporting period unspecified')
        for card in section.select('.stat-card'):
            q=card.select_one('.stat-card__quantity');label=card.select_one('.stat-card__description');unit=card.select_one('.stat-card__unit');foot=card.select_one('.stat-card__footnote')
            if not q or not label:continue
            raw=q.get('aria-label');label=label.get_text(' ',strip=True);numeric=float(re.sub(r'[$%,+]','',raw))
            unit_text=unit.get_text(' ',strip=True) if unit else ('percent' if '%' in raw else 'count')
            multiplier={'Million':1e6,'Billion':1e9,'Trillion':1e12,'Quadrillion':1e15}.get(unit_text,1)
            key=digest(sid+'\n'+label+'\n'+period)
            measurement_period='2025' if 'in 2025' in label else (foot.get_text(' ',strip=True) if foot else period)
            stats.append({'metric_id':key,'source_id':sid,'metric_label':label,'reported_value':raw,'reported_unit':unit_text,'numeric_value_in_base_units':numeric*multiplier,'base_unit':'USD' if '$' in raw else ('percent' if '%' in raw else 'count'),'qualifier':'lower bound' if '+' in raw else ('estimated share' if 'est.' in label else 'reported'),'reporting_period':measurement_period,'source_context_as_of':period,'measurement_window_note':'Annual scale; exact annual interval unspecified' if 'annually' in label else 'Preserve the stated period and metric definition','business_lines':SOURCES[sid]['business_lines'],'measurement_scope':'official public business scale/context; not an October observation or profitability measure','source_url':r['url'],'raw_file':r['file'],'collected_at_utc':r['collected_at_utc']})
dedup_stats={}
for x in stats:
    key=('tiw_cds_market_share',x['reporting_period']) if 'CDS market share' in x['metric_label'] else (x['metric_id'],x['reporting_period'])
    if key not in dedup_stats:dedup_stats[key]=dict(x,evidence_sources=[{'source_id':x['source_id'],'raw_file':x['raw_file'],'url':x['source_url']}])
    else:
        a=dedup_stats[key];assert a['numeric_value_in_base_units']==x['numeric_value_in_base_units']
        a['business_lines']=sorted(set(a['business_lines']+x['business_lines']))
        a['evidence_sources'].append({'source_id':x['source_id'],'raw_file':x['raw_file'],'url':x['source_url']})
stats=list(dedup_stats.values())
export('business_public_snapshot_metrics.csv',stats)

# Public money-market industry table; source hierarchy prevents subtotal double counting.
industry=[]
if 'ici_money_market_release' in FETCHED:
    r=FETCHED['ici_money_market_release'];obj=json.loads((ROOT/r['file']).read_text())
    for category,investor,a,b,change,c in obj['rows']:
        for when,value in [('2026-10-07',a),('2026-09-30',b),('2026-09-23',c)]:
            industry.append({'fund_category':category,'investor_type':investor,'observation_date':when,'assets_billion_usd':value,'reported_change_vs_previous_week_billion_usd':change if when=='2026-10-07' else None,'publication_date':obj['publication_date'],'source_id':r['source_id'],'source_file':r['file'],'scope':'whole-industry fund assets; not WIS processing or revenue','hierarchy_note':'Total rows overlap subtype rows; do not add all rows together.'})
export('wis_industry_money_market_assets.csv',industry)

# ETF reference snapshot has a transmission header followed by six-field records, not a CSV header row.
etfs=[]
if 'dtcc_etf_listing_csv' in FETCHED:
    r=FETCHED['dtcc_etf_listing_csv'];lines=(ROOT/r['file']).read_text().splitlines()
    for row in csv.reader(lines[1:]):
        if len(row)!=6:continue
        ticker,cusip,security_name,participant,security_type,active=row
        refdate=re.search(r'TRANS(\d{8})',lines[0])
        etfs.append({'ticker':ticker.strip(),'cusip':cusip.strip().removeprefix('="').removesuffix('"'),'security_name':security_name.strip(),'participant_code_raw':participant,'security_type_raw':security_type,'active_flag_raw':active,'source_id':r['source_id'],'source_file':r['file'],'header_raw':lines[0],'reference_as_of_date':datetime.strptime(refdate[1],'%Y%m%d').date().isoformat() if refdate else None,'quality_flag':'test_record_identifier' if 'TEST' in ticker.upper() or re.search(r'\bTEST\b',security_name,re.I) else None,'scope':'official reference listing; active/prelaunch status and coded fields need source definitions; not ETF flows or ECS transaction volume'})
export('ecs_itp_etf_reference_snapshot.csv',etfs)

# Public CDS reference-entity statistics remain separate from repository reporting messages.
cds=[]
for sid,r in FETCHED.items():
    if r['kind']=='public_business_report' and (ROOT/r['file']).read_bytes().startswith(b'PK'):
        import openpyxl
        w=openpyxl.load_workbook(ROOT/r['file'],data_only=True,read_only=True)
        for sheet in w:
            for i,row in enumerate(sheet.iter_rows(values_only=True),1):
                if any(v is not None for v in row):cds.append({'source_id':sid,'sheet':sheet.title,'source_row':i,'row_values':list(row),'source_file':r['file'],'scope':'CDS market reference-entity report; preserve source header, date period, units and rounding buckets'})
        w.close()
jsonl(DATA/'rds_tiw_cds_reference_rows.jsonl',cds)

# Asset Services underwriting history: exact source dates retained, monthly periods explicit.
underwriting=[]
if 'dtcc_underwriting_xml' in FETCHED:
    r=FETCHED['dtcc_underwriting_xml'];root=ET.fromstring((ROOT/r['file']).read_bytes())
    for e in root.findall('entry'):
        source_date=e.findtext('date')
        for p in e.findall('product'):
            underwriting.append({'source_date':source_date,'reporting_month':source_date[:7],'security_category':p.findtext('index'),'new_issuance_count':int(p.findtext('count')),'new_issuance_amount_usd':float(p.findtext('amount')),'source_id':'dtcc_underwriting_xml','source_file':r['file'],'source_url':r['url'],'collected_at_utc':r['collected_at_utc'],'scope':'DTC new issuance / eligibility activity; not Asset Services revenue'})
export('asset_services_underwriting_monthly.csv',underwriting)

# Shared ECS/ITP monthly operations, extracted from the published Equities by the Numbers snapshot.
operations=[]
if 'dtcc_equity_trade_volume_insights_embedded' in FETCHED:
    r=FETCHED['dtcc_equity_trade_volume_insights_embedded'];soup=BeautifulSoup((ROOT/r['file']).read_text(),'html.parser')
    flat=soup.get_text(' ',strip=True)
    assert 'As of August 2026' in flat,'Reconfirm the reporting period before parsing a different snapshot'
    for card in soup.select('.metric-card'):
        text=card.get_text(' ',strip=True);m=re.match(r'([\d.]+)M\s*([↑↓]).*?\)\s*(.*)',text)
        if m:
            label=m[3].strip();b='ITP' if any(x in label for x in ['TradeSuite','CTM']) else 'ECS'
            operations.append({'business_line':b,'metric_label':label,'reporting_period':'2026-08','measurement_window':'August transaction daily average','value':float(m[1])*1e6,'unit':'transactions/day','comparison_basis':'FY 2025 daily average','reported_comparison_raw':text,'source_id':r['source_id'],'source_file':r['file']})
    for label,next_label,b in [('Industry-Wide Affirmation Rate','Netting Rates','ITP'),('Netting Rates','Fail Rates','ECS'),('Fail Rates NSCC','DTC Pre-U.S.','ECS'),('DTC Pre-U.S.','Industry Affirmation Rate Details','ECS')]:
        segment=flat[flat.index(label):flat.index(next_label)]
        values=re.findall(r'([\d.]+)%',segment)
        assert len(values)==2,(label,values)
        clean_label={'DTC Pre-U.S.':'DTC fail rate','Fail Rates NSCC':'NSCC fail rate'}.get(label,label)
        for period,v in zip(['2024-05','2026-08'],values):operations.append({'business_line':b,'metric_label':clean_label,'reporting_period':period,'measurement_window':'published monthly snapshot; pre-U.S. T+1 baseline is May 2024','value':float(v),'unit':'percent','comparison_basis':'Pre-U.S. T+1 (May 2024)','reported_comparison_raw':segment,'source_id':r['source_id'],'source_file':r['file']})
    for region in ['Americas','EMEA','APAC']:
        pattern=region+r' ([\d.]+)M [↑↓].*?Trade Vol\. ([\d.]+)% [↑↓].*?Rate'
        m=re.search(pattern,flat)
        assert m,region
        for label,value,unit in [('CTM same-day matching trade volume',float(m[1])*1e6,'trades/month'),('CTM same-day match agreed rate',float(m[2]),'percent')]:
            operations.append({'business_line':'ITP','metric_label':label,'region':region,'reporting_period':'2026-08','measurement_window':'published regional monthly snapshot','value':value,'unit':unit,'comparison_basis':'last month; displayed change retained without reinterpreting its units','reported_comparison_raw':m[0],'source_id':r['source_id'],'source_file':r['file']})
export('ecs_itp_monthly_operations_snapshot.csv',operations)

# FICC public operations: dates, trailer reconciliation and original metric columns retained.
ficc_daily=[];ficc_file_checks=[];ficc_monthly=[]
for sid,r in FETCHED.items():
    if r['kind']=='ficc_daily_series':
        rows=list(csv.reader((ROOT/r['file']).open(newline='',encoding='utf-8-sig')));header=[x.strip() for x in rows[0]];seen=0;trailer=None
        for row in rows[1:]:
            if not row or not row[0].strip():continue
            if row[0].strip()=='TRAILER':trailer=int(row[1]);continue
            when=datetime.strptime(row[0].strip(),'%m/%d/%Y').date().isoformat();seen+=1
            for metric,raw in zip(header[1:],row[1:]):
                token=raw.strip();value=float(token.replace('$','').replace(',','')) if token else None
                ficc_daily.append({'date':when,'metric':metric,'value':value,'unit':'USD' if '$' in token else 'as reported in original CSV','raw_value':raw,'source_id':sid,'source_file':r['file'],'measurement_scope':'FICC public market/service activity; not business revenue or realized loss'})
        assert seen==trailer,(sid,seen,trailer)
        ficc_file_checks.append({'source_id':sid,'data_rows':seen,'trailer_expected_rows':trailer,'trailer_count_matches':True,'latest_date':max(x['date'] for x in ficc_daily if x['source_id']==sid)})
    elif r['kind']=='ficc_monthly_series':
        root=ET.fromstring((ROOT/r['file']).read_bytes())
        for division in root:
            for year in division.findall('year'):
                for month in year.findall('month'):
                    period=f"{int(year.attrib['id']):04}-{int(month.attrib['id']):02}"
                    for metric in month:
                        raw=(metric.text or '').strip()
                        if not raw:continue
                        ficc_monthly.append({'division':'GSD' if division.tag=='gsd' else ('MBSD' if division.tag=='mbs' else division.tag),'reporting_month':period,'metric_code':metric.tag,'value_raw_source_units':float(raw.replace(',','')),'source_id':sid,'source_file':r['file'],'source_display_unit':'Chart displays USD trillions; XML contains unscaled numeric amounts','measurement_scope':'monthly clearing/settlement activity; not revenue or internal risk loss'})
export('ficc_daily_operations_history.csv',ficc_daily)
export('ficc_daily_operations_increment.csv',[x for x in ficc_daily if START.isoformat()<=x['date']<=END.isoformat()])
export('ficc_daily_file_reconciliation.csv',ficc_file_checks)
export('ficc_gsd_mbsd_monthly_volumes.csv',ficc_monthly)

# RDS reports remain separate by jurisdiction/table, with no cross-region or currency pooling.
rds=[];rds_manifest=[]
for sid,r in FETCHED.items():
    if r['kind']!='repository_weekly':continue
    path=ROOT/r['file'];rows=list(csv.reader(path.open(encoding='utf-8-sig',newline='')))
    normalized=DATA/(sid+'.csv');normalized.write_bytes(path.read_bytes())
    for rownum,row in enumerate(rows,1):
        rds.append({'source_id':sid,'report_date':'2026-10-09' if '20261009' in sid else '2026-10-02','jurisdiction':'EU EMIR' if 'esma' in sid else ('UK SFTR' if 'sftr' in sid else 'UK EMIR'),'source_row':rownum,'row_values':row,'source_file':r['file'],'scope':'repository public aggregates; not RDS revenue, reporting-error rate, or unique market-wide totals'})
    rds_manifest.append({'source_id':sid,'rows_including_headers':len(rows),'file':str(normalized.relative_to(ROOT)),'source_file':r['file'],'url':r['url'],'date':'2026-10-09' if '20261009' in sid else '2026-10-02','measurement_note':'EU and UK data cannot be simply summed; retain table dimensions and source currency/units.'})
jsonl(DATA/'rds_public_report_rows.jsonl',rds);export('rds_report_inventory.csv',rds_manifest)

# Provider incidents, cyber catalog additions and disasters: external observations only.
events=[]
for sid,r in FETCHED.items():
    if r['kind']=='cyber_catalog':
        obj=json.loads((ROOT/r['file']).read_text())
        for x in obj['vulnerabilities']:
            if START.isoformat()<=x['dateAdded']<=END.isoformat():events.append({'event_id':x['cveID'],'source_id':sid,'event_kind':'known_exploited_vulnerability_catalog_addition','observation_date':x['dateAdded'],'event_time':None,'source_record':x,'raw_file':r['file'],'business_lines_candidate':BUSINESSES,'actual_dtcc_exposure_verified':False})
    elif r['kind']=='provider_incidents':
        for x in json.loads((ROOT/r['file']).read_text()):
            begin=x.get('begin') or x.get('start') or ''
            end=x.get('end') or begin
            modified=x.get('modified') or x.get('most_recent_update',{}).get('modified') or begin
            if any(START.isoformat()<=str(t)[:10]<=END.isoformat() for t in [begin,end,modified]):events.append({'event_id':sid+':'+str(x.get('id',digest(json.dumps(x,sort_keys=True)))),'source_id':sid,'event_kind':'provider_incident_or_update','observation_date':str(modified)[:10],'event_time':begin,'source_record':x,'raw_file':r['file'],'business_lines_candidate':BUSINESSES,'actual_dtcc_exposure_verified':False})
    elif r['kind']=='disaster_declarations':
        obj=json.loads((ROOT/r['file']).read_text())
        for x in obj.get('DisasterDeclarationsSummaries',[]):
            when=x['declarationDate'][:10]
            if START.isoformat()<=when<=END.isoformat():events.append({'event_id':sid+':'+str(x['disasterNumber'])+':'+x['state']+':'+x['declarationType'],'source_id':sid,'event_kind':'official_disaster_declaration','observation_date':when,'event_time':x.get('incidentBeginDate'),'source_record':x,'raw_file':r['file'],'business_lines_candidate':BUSINESSES,'actual_dtcc_exposure_verified':False})
jsonl(DATA/'external_cyber_provider_disaster_updates.jsonl',events)

# A central database stores facts once and holds business relationships separately.
con=sqlite3.connect(ROOT/'shared_public_data.sqlite3')
con.executescript('CREATE TABLE IF NOT EXISTS documents(document_id TEXT PRIMARY KEY,canonical_url TEXT UNIQUE,payload TEXT); CREATE TABLE IF NOT EXISTS document_versions(document_id TEXT,content_hash TEXT,payload TEXT,PRIMARY KEY(document_id,content_hash)); CREATE TABLE IF NOT EXISTS business_document_links(document_id TEXT,business_line TEXT,rule TEXT,payload TEXT,PRIMARY KEY(document_id,business_line,rule)); CREATE TABLE IF NOT EXISTS market_observations(series_id TEXT,observation_date TEXT,payload TEXT,PRIMARY KEY(series_id,observation_date)); CREATE TABLE IF NOT EXISTS source_business_links(source_id TEXT,business_line TEXT,PRIMARY KEY(source_id,business_line));')
prior=PROJECT/'public_news_prototype/output/news.sqlite3'
if prior.exists():
    priorcon=sqlite3.connect(f'file:{prior}?mode=ro',uri=True)
    for (payload,) in priorcon.execute('SELECT payload FROM documents'):
        d=json.loads(payload);url=canonical(d['url']);id=digest(url)
        con.execute('INSERT OR IGNORE INTO documents VALUES(?,?,?)',(id,url,payload))
    priorcon.close();reuse.append({'file':str(prior.relative_to(PROJECT)),'sha256':digest(prior.read_bytes()),'use':'read-only prior news seed'})
for d in documents:
    payload=json.dumps(d,ensure_ascii=False)
    con.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?)',(d['document_id'],d['url'],payload))
    con.execute('INSERT OR IGNORE INTO document_versions VALUES(?,?,?)',(d['document_id'],d['content_hash'],payload))
    con.execute('DELETE FROM business_document_links WHERE document_id=?',(d['document_id'],))
for x in links:con.execute('INSERT OR REPLACE INTO business_document_links VALUES(?,?,?,?)',(x['document_id'],x['business_line'],x['rule'],json.dumps(x,ensure_ascii=False)))
for x in market:con.execute('INSERT OR REPLACE INTO market_observations VALUES(?,?,?)',(x['series_id'],x['observation_date'],json.dumps(x,ensure_ascii=False)))
con.execute('DELETE FROM source_business_links')
for s in REGISTRY:
    if s['kind'] in ['discovery','article','background_article','feed_catalog']:continue
    for b in s['business_lines']:con.execute('INSERT OR IGNORE INTO source_business_links VALUES(?,?)',(s['id'],b))
con.commit();con.close()
dump(ROOT/'reused_input_manifest.json',reuse)
dump(ROOT/'processing_summary.json',{'requested_window':{'start':'2026-10-07','end':'2026-10-14','timezone':'America/New_York','current_day_partial':True},'raw_unique_documents':len(documents),'window_documents':len(increment),'duplicate_document_urls_merged':len(DOCUMENTS)-len(documents),'news_candidates_by_business':dict(collections.Counter(b for _,b in set((x['document_id'],x['business_line']) for x in links))),'news_candidate_rule_matches':len(links),'market_series':len(market_coverage),'market_series_with_window_observations':sum(x['window_nonmissing_rows']>0 for x in market_coverage),'market_window_rows':sum(x['observation_date']>=START.isoformat() for x in market),'market_window_nonmissing_rows':sum(x['observation_date']>=START.isoformat() and x['value'] is not None for x in market),'market_revision_rows':len(revisions),'business_snapshot_metrics':len(stats),'ecs_itp_operations_rows':len(operations),'etf_reference_rows':len(etfs),'wis_industry_asset_rows':len(industry),'ficc_daily_increment_rows':sum(START.isoformat()<=x['date']<=END.isoformat() for x in ficc_daily),'ficc_monthly_rows':len(ficc_monthly),'ficc_monthly_latest':max((x['reporting_month'] for x in ficc_monthly),default=None),'underwriting_rows':len(underwriting),'underwriting_months':len(set(x['reporting_month'] for x in underwriting)),'underwriting_latest_month':max((x['reporting_month'] for x in underwriting),default=None),'rds_reports':len(rds_manifest),'external_catalog_incident_declaration_updates':len(events),'original_content_status':dict(collections.Counter(x['original_content_status'] for x in increment)),'unrouted_window_documents':sum(not x['business_lines_candidate'] for x in increment),'models_retrained':False,'business_risk_scores_generated':False})
print((ROOT/'processing_summary.json').read_text())
