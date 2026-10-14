"""Strict public-source adapters. Unavailable values stay null, not zero."""
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo
import csv, io, json, re, xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date
import db

ROUTES=[
 ('funding_rates',['treasury','treasuries','repo','repurchase agreement','ficc','mortgage-backed','fomc'],['FICC']),
 ('equities',['equity','equities','etf','equity clearing','continuous net settlement'],['ECS']),
 ('reporting',['trade repository','transaction reporting','trade reporting','emir','sftr','swap','swaps','derivatives'],['RDS']),
 ('wealth',['mutual fund','fund/serv','fundserv','private market','private credit','annuity','insurance','aip'],['WIS']),
 ('trade_processing',['ctm','tradesuite','trade affirmation','trade matching','standing settlement','ssi','t+1','settlement cycle'],['ITP']),
 ('custody',['corporate action','custody','underwriting','ipo','dividend','reorganization','redemption','tax relief','depositary','cusip'],['Asset Services']),
 ('tokenization',['tokenization','tokenisation','tokenized','tokenised','stablecoin','digital asset','blockchain'],['DAS','DDA']),
 ('platform',['composerx','interoperability','smart contract','digital launchpad'],['DDA']),
 ('data',['market data','data quality','reference data','data transparency','kinetics'],['Data Services']),
 ('readiness',['clearing mandate','treasury clearing','regulatory readiness','regulatory reporting','t+1','emir','sftr'],['Consulting']),
 ('settlement',['settlement cycle','t+1','settlement fail','nscc','dtc settlement'],['ECS']),
 ('shared_cyber',['cyber','ransomware','operational resilience','third-party','third party'],None),
]

def clean(x):return BeautifulSoup(x or '', 'html.parser').get_text(' ',strip=True)

def canonical(url,base):
    p=urlsplit(urljoin(base,url.strip()))
    if p.scheme not in ['https','http'] or not p.hostname or p.username or p.password:raise ValueError('Invalid document URL')
    query=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in ['fbclid','gclid']]
    return urlunsplit((p.scheme,p.netloc.lower(),p.path or '/',urlencode(query),''))

def news_record(s,title,url,summary,raw_date,extra=None):
    title=clean(title);summary=clean(summary);url=canonical(url,s['url'])
    stamp=None;day=None;flags=[]
    if raw_date:
        try:
            d=parse_date(raw_date,dayfirst=s['id']=='esma_news')
            if d.tzinfo:
                stamp=d.astimezone(ZoneInfo('UTC')).isoformat();day=d.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            else:day=d.date().isoformat();flags.append('publication_timezone_unverified')
        except (ValueError,OverflowError):flags.append('unparseable_publication_date')
    else:flags.append('missing_publication_date')
    links=[]
    text=title+'\n'+summary
    for rule,terms,businesses in ROUTES:
        matches=[t for t in terms if re.search(r'(?<!\w)'+re.escape(t)+r'(?!\w)',text,re.I)]
        if matches:
            for b in businesses or s['business_lines']:
                links.append({'business_line':b,'rule':rule,'matched_terms':matches,'review_status':'candidate_unreviewed','business_impact_confirmed':False})
    if s['id']=='dtcc_notice_feed' and re.match(r'GOV|MBS|CMU',title,re.I):
        links.append({'business_line':'FICC','rule':'official_notice_prefix','matched_terms':[title],'review_status':'candidate_unreviewed','business_impact_confirmed':False})
    r={'document_id':db.sha(url),'source_id':s['id'],'source_name':s['name'],'url':url,'title':title,
       'source_summary':summary,'published_at_raw':raw_date or None,'published_at_utc':stamp,
       'publication_date':day,'event_time':None,'effective_time':None,'quality_flags':flags,
       'routing_evidence':links,'business_lines_candidate':sorted({x['business_line'] for x in links}),
       'text_scope':'publisher feed/index/API metadata; full original text not fetched by daily job',
       'review_status':'unreviewed','business_impact_confirmed':False}
    if extra:r.update(extra)
    return r

def xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('DTD/entities unsupported')
    return ET.fromstring(data)

def lname(tag):return tag.rsplit('}',1)[-1]
def field(node,*names):
    return next((''.join(c.itertext()).strip() for name in names for c in node if lname(c.tag)==name),'')

def number(token):
    if token is None or str(token).strip() in ['', '.', 'NA', 'N/A']:return None
    value=float(str(token).replace(',','').replace('$','').strip())
    import math
    if not math.isfinite(value):raise ValueError('Nonfinite numeric value')
    return value

def parse(s,data,as_of,requested_url):
    kind=s['kind'];sid=s['id'];rows=[];dataset=None
    if kind=='rss':
        root=xml(data)
        if lname(root.tag) not in ['rss','RDF','feed']:raise ValueError('Not an RSS/Atom response')
        for n in root.iter():
            if lname(n.tag) not in ['item','entry']:continue
            title=field(n,'title');url=field(n,'link')
            if lname(n.tag)=='entry':url=next((c.get('href','') for c in n if lname(c.tag)=='link' and c.get('rel','alternate')=='alternate'),'')
            if not title or not url:raise ValueError('Feed entry missing title or URL')
            rows.append(news_record(s,title,url,field(n,'description','summary'),field(n,'pubDate','published','date')))
        dataset='news'
    elif kind=='esma_news':
        soup=BeautifulSoup(data,'html.parser')
        for a in soup.select('a[href]'):
            if '/press-news/esma-news/' not in a['href']:continue
            text=a.get_text(' ',strip=True);m=re.search(r'\b(\d{2}/\d{2}/\d{4})\b',text)
            if m:rows.append(news_record(s,text[:m.start()],a['href'],text[m.end():],m[1]))
        if not rows:raise ValueError('ESMA date/title layout changed or no dated entries found')
        dataset='news'
    elif kind=='regulatory_documents':
        obj=json.loads(data)
        for x in obj['results']:
            rows.append(news_record(s,x['title'],x['html_url'],x.get('abstract') or '',x['publication_date'],
                        {'document_number':x['document_number'],'publication_type':x.get('type'),'agency_names':[a.get('name') for a in x.get('agencies',[])]}))
        dataset='news'
    elif kind=='market_series':
        reader=csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
        if reader.fieldnames!=['observation_date',s['series_id']]:raise ValueError('FRED CSV schema changed: '+str(reader.fieldnames))
        for x in reader:
            date=datetime.strptime(x['observation_date'],'%Y-%m-%d').date()
            if date>as_of:continue
            period=date.isoformat();end=period
            if s['frequency']=='quarterly':
                import calendar
                month=((date.month-1)//3+1)*3;period=f'{date.year}Q{(date.month-1)//3+1}';end=f'{date.year}-{month:02}-{calendar.monthrange(date.year,month)[1]}'
            elif s['frequency']=='monthly':
                import calendar
                period=date.strftime('%Y-%m');end=date.replace(day=calendar.monthrange(date.year,date.month)[1]).isoformat()
            rows.append({'series_id':s['series_id'],'observation_date':date.isoformat(),'value':number(x[s['series_id']]),'units':s['units'],'frequency':s['frequency'],'source_id':sid,'measurement_period':period,'measurement_period_end':end,'publication_date':None})
        dataset='market_observations'
    elif kind=='ficc_daily_series':
        table=list(csv.reader(io.StringIO(data.decode('utf-8-sig'))));header=[x.strip() for x in table[0]];count=0;trailer=None
        for row in table[1:]:
            if not row or not row[0].strip():continue
            if row[0].strip()=='TRAILER':trailer=int(row[1]);continue
            if len(row)!=len(header):raise ValueError('FICC column count changed')
            day=datetime.strptime(row[0].strip(),'%m/%d/%Y').date();count+=1
            if day>as_of:continue
            for metric,token in zip(header[1:],row[1:]):
                rows.append({'date':day.isoformat(),'metric':metric,'value':number(token),'unit':'USD' if '$' in token else 'as reported in original CSV','raw_value':token,'source_id':sid,'measurement_scope':'FICC public activity; not revenue or realized loss'})
        if trailer is None or trailer!=count:raise ValueError(f'FICC trailer mismatch: {count} != {trailer}')
        dataset='ficc_daily'
    elif kind=='ficc_monthly_series':
        for division in xml(data):
            for year in division.findall('year'):
                for month in year.findall('month'):
                    period=f"{int(year.attrib['id']):04}-{int(month.attrib['id']):02}"
                    if period>as_of.strftime('%Y-%m'):continue
                    for metric in month:
                        if not (metric.text or '').strip():continue
                        rows.append({'division':{'gsd':'GSD','mbs':'MBSD'}.get(division.tag,division.tag),'reporting_month':period,'metric_code':metric.tag,'value_raw_source_units':number(metric.text),'source_id':sid,'source_display_unit':'Chart displays USD trillions; XML contains unscaled numeric amounts','measurement_scope':'monthly activity; not revenue or internal loss'})
        dataset='ficc_monthly'
    elif kind=='business_timeseries':
        root=xml(data)
        if root.tag!='uw_data':raise ValueError('Underwriting XML schema changed')
        for entry in root.findall('entry'):
            day=entry.findtext('date');month=day[:7]
            if month>as_of.strftime('%Y-%m'):continue
            for p in entry.findall('product'):
                rows.append({'source_date':day,'reporting_month':month,'security_category':p.findtext('index'),'new_issuance_count':int(p.findtext('count')),'new_issuance_amount_usd':number(p.findtext('amount')),'source_id':sid,'scope':'DTC new issuance/eligibility; not Asset Services revenue'})
        dataset='underwriting'
    elif kind=='etf_reference':
        lines=data.decode('utf-8-sig').splitlines();match=re.search(r'TRANS(\d{8})',lines[0])
        if not match:raise ValueError('ETF transmission date missing')
        day=datetime.strptime(match[1],'%Y%m%d').date().isoformat()
        for row in csv.reader(lines[1:]):
            if len(row)!=6:raise ValueError('ETF reference schema changed')
            ticker,cusip,name,participant,stype,active=row
            rows.append({'ticker':ticker.strip(),'cusip':cusip.strip().removeprefix('="').removesuffix('"'),'security_name':name.strip(),'participant_code_raw':participant,'security_type_raw':stype,'active_flag_raw':active,'reference_as_of_date':day,'source_id':sid,'header_raw':lines[0],'quality_flag':'test_record_identifier' if 'TEST' in ticker.upper() or re.search(r'\bTEST\b',name,re.I) else None,'scope':'reference listing; not ETF flows or transaction volume'})
        dataset='etf_reference'
    elif kind=='repository_weekly':
        m=re.search(r'(20\d{6})',requested_url)
        if not m:raise ValueError('RDS report date missing')
        day=datetime.strptime(m[1],'%Y%m%d').date().isoformat()
        table=list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
        if not table or data.lstrip().startswith(b'<'):raise ValueError('Not a repository CSV')
        for i,row in enumerate(table,1):
            rows.append({'source_id':sid,'report_date':day,'jurisdiction':'EU EMIR' if 'esma' in sid else ('UK SFTR' if 'sftr' in sid else 'UK EMIR'),'source_row':i,'row_values':row,'scope':'Preserve table/jurisdiction/units; EU and UK cannot simply be summed; not RDS revenue'})
        dataset='rds_reports'
    elif kind in ['cyber_catalog','provider_incidents','disaster_declarations']:
        obj=json.loads(data)
        if kind=='cyber_catalog':
            for x in obj['vulnerabilities']:
                rows.append({'source_id':sid,'event_id':x['cveID'],'event_kind':'known_exploited_vulnerability_catalog_addition','observation_date':x['dateAdded'],'event_time':None,'source_record':x,'actual_dtcc_exposure_verified':False})
        elif kind=='provider_incidents':
            if not isinstance(obj,list):raise ValueError('Provider feed is not a list')
            for x in obj:
                begin=x.get('begin') or x.get('start');modified=x.get('modified') or x.get('most_recent_update',{}).get('modified') or begin
                rows.append({'source_id':sid,'event_id':sid+':'+str(x.get('id') or db.sha(db.dumps(x))),'event_kind':'provider_incident_or_update','observation_date':str(modified)[:10] if modified else None,'event_time':begin,'source_record':x,'actual_dtcc_exposure_verified':False})
        else:
            for x in obj['DisasterDeclarationsSummaries']:
                rows.append({'source_id':sid,'event_id':sid+':'+str(x['disasterNumber'])+':'+x['state']+':'+x['declarationType'],'event_kind':'official_disaster_declaration','observation_date':x['declarationDate'][:10],'event_time':x.get('incidentBeginDate'),'source_record':x,'actual_dtcc_exposure_verified':False})
        dataset='external_events'
    elif kind=='business_reference':
        soup=BeautifulSoup(data,'html.parser')
        for section in soup.select('.stat-cards-container'):
            foot=section.select_one('.stat-cards-container__footnote');period=foot.get_text(' ',strip=True) if foot else 'reporting period unspecified'
            for card in section.select('.stat-card'):
                q=card.select_one('.stat-card__quantity');label=card.select_one('.stat-card__description');unit=card.select_one('.stat-card__unit');note=card.select_one('.stat-card__footnote')
                if not q or not label:continue
                raw=q.get('aria-label');label=label.get_text(' ',strip=True)
                if not raw:raise ValueError('Animated stat lacks accessible source value')
                unit=unit.get_text(' ',strip=True) if unit else ('percent' if '%' in raw else 'count')
                value=float(re.sub(r'[$%,+]','',raw))*{'Million':1e6,'Billion':1e9,'Trillion':1e12,'Quadrillion':1e15}.get(unit,1)
                measurement='2025' if 'in 2025' in label else (note.get_text(' ',strip=True) if note else period)
                metric_id=db.sha(sid+'\n'+label+'\n'+period)
                if 'CDS market share' in label:metric_id=db.sha('tiw_cds_market_share\n'+measurement)
                rows.append({'metric_id':metric_id,'source_id':sid,'metric_label':label,'reported_value':raw,'reported_unit':unit,'numeric_value_in_base_units':value,'base_unit':'USD' if '$' in raw else ('percent' if '%' in raw else 'count'),'reporting_period':measurement,'source_context_as_of':period,'qualifier':'lower bound' if '+' in raw else 'reported','measurement_scope':'public scale/context; not current-day activity or profitability'})
        dataset='business_scale'
    elif kind=='equity_operations':
        soup=BeautifulSoup(data,'html.parser');flat=soup.get_text(' ',strip=True)
        m=re.search(r'As of ([A-Za-z]+ \d{4})',flat)
        if not m:raise ValueError('Monthly operations reporting period missing')
        month=datetime.strptime(m[1],'%B %Y').strftime('%Y-%m')
        for card in soup.select('.metric-card'):
            text=card.get_text(' ',strip=True);m=re.match(r'([\d.]+)M\s*[↑↓].*?\)\s*(.*)',text)
            if m:
                label=m[2].strip();b='ITP' if any(x in label for x in ['TradeSuite','CTM']) else 'ECS'
                rows.append({'business_line':b,'metric_label':label,'region':None,'reporting_period':month,'value':float(m[1])*1e6,'unit':'transactions/day','source_id':sid,'reported_comparison_raw':text})
        for label,end,b in [('Industry-Wide Affirmation Rate','Netting Rates','ITP'),('Netting Rates','Fail Rates','ECS'),('Fail Rates NSCC','DTC Pre-U.S.','ECS'),('DTC Pre-U.S.','Industry Affirmation Rate Details','ECS')]:
            segment=flat[flat.index(label):flat.index(end)];values=re.findall(r'([\d.]+)%',segment)
            if len(values)!=2:raise ValueError('Rate comparison layout changed')
            name={'DTC Pre-U.S.':'DTC fail rate','Fail Rates NSCC':'NSCC fail rate'}.get(label,label)
            for period,value in zip(['2024-05',month],values):
                rows.append({'business_line':b,'metric_label':name,'region':None,'reporting_period':period,'value':float(value),'unit':'percent','source_id':sid,'reported_comparison_raw':segment})
        for region in ['Americas','EMEA','APAC']:
            m=re.search(region+r' ([\d.]+)M [↑↓].*?Trade Vol\. ([\d.]+)% [↑↓].*?Rate',flat)
            if not m:raise ValueError('Regional monthly operations layout changed')
            for label,value,unit in [('CTM same-day matching trade volume',float(m[1])*1e6,'trades/month'),('CTM same-day match agreed rate',float(m[2]),'percent')]:
                rows.append({'business_line':'ITP','metric_label':label,'region':region,'reporting_period':month,'value':value,'unit':unit,'source_id':sid,'reported_comparison_raw':m[0]})
        dataset='equity_operations'
    else:raise ValueError('No active adapter: '+kind)
    return dataset,rows

KEYS={'market_observations':['series_id','observation_date'],'ficc_daily':['source_id','date','metric'],
      'ficc_monthly':['division','reporting_month','metric_code'],'underwriting':['reporting_month','security_category'],
      'equity_operations':['business_line','metric_label','region','reporting_period'],
      'etf_reference':['reference_as_of_date','ticker','cusip','participant_code_raw'],'business_scale':['metric_id'],
      'rds_reports':['source_id','report_date','source_row'],'external_events':['source_id','event_id']}
def record_key(dataset,row):
    return row['document_id'] if dataset=='news' else db.dumps([row.get(k) or '' for k in KEYS[dataset]])

def deduplicate(dataset,rows):
    groups={}
    for row in rows:groups.setdefault(record_key(dataset,row),[]).append(row)
    output=[]
    for key,group in groups.items():
        if len(group)==1:output.append(group[0]);continue
        if dataset=='news':
            # A publisher may list the same PDF under two notice labels. Keep one
            # document, retain both feed variants, and keep the full raw response.
            winner=dict(max(group,key=lambda x:(len(x['source_summary']),len(x['title']),x['title'])))
            variants={db.dumps({k:x[k] for k in ['title','source_summary','published_at_raw']}) for x in group}
            winner['publisher_feed_variants']=[json.loads(x) for x in sorted(variants)]
            output.append(winner)
        elif len({db.content_hash(x) for x in group})==1:
            output.append(group[0])
        else:raise ValueError('Conflicting duplicate identity in '+dataset+': '+key)
    return output,len(rows)-len(output)
