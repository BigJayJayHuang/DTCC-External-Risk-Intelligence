"""Import reviewed project inputs once; never edit the original data or models."""
from pathlib import Path
import argparse, csv, json, re
import db

SPECS=[
 ('market_observations','market_observations_updated.csv',['series_id','observation_date'],'one provider series and observation date'),
 ('news','news_documents_all_current_feeds.jsonl',['url'],'one canonical document URL'),
 ('ficc_daily','ficc_daily_operations_history.csv',['source_id','date','metric'],'source/date/metric; units as reported'),
 ('ficc_monthly','ficc_gsd_mbsd_monthly_volumes.csv',['division','reporting_month','metric_code'],'division/month/metric; unscaled source values'),
 ('underwriting','asset_services_underwriting_monthly.csv',['reporting_month','security_category'],'month/security category'),
 ('equity_operations','ecs_itp_monthly_operations_snapshot.csv',['business_line','metric_label','region','reporting_period'],'business/metric/region/reporting month'),
 ('etf_reference','ecs_itp_etf_reference_snapshot.csv',['reference_as_of_date','ticker','cusip','participant_code_raw'],'reference date/ticker/CUSIP/participant; coded fields retained'),
 ('business_scale','business_public_snapshot_metrics.csv',['metric_id'],'published metric and stated reporting period'),
 ('wis_industry','wis_industry_money_market_assets.csv',['observation_date','fund_category','investor_type'],'week/fund type/investor type; overlapping totals'),
 ('rds_reports','rds_public_report_rows.jsonl',['source_id','report_date','source_row'],'jurisdiction/table/report date/source row; headers retained'),
 ('cds_reference','rds_tiw_cds_reference_rows.jsonl',['source_id','sheet','source_row'],'source workbook/sheet/source row; rounded source buckets'),
 ('external_events','external_cyber_provider_disaster_updates.jsonl',['source_id','event_id'],'provider/catalog/declaration record; no verified DTCC exposure'),
]
HISTORICAL=[
 ('pqd_quarterly','risk_business_ml/feedback_revision_report_2026_10_06/data/response_quarterly.csv',['entity','quarter'],'legal entity/division and quarter; GSD, MBSD, NSCC separate'),
 ('pqd_cell_evidence','risk_business_ml/event_vulnerability_tests_2026_10_06/data/pqd_cell_evidence.csv',None,'official workbook/PDF extraction evidence, source cell and units'),
 ('response_cell_evidence','risk_business_ml/feedback_revision_report_2026_10_06/data/response_cell_evidence.csv',None,'official quarterly margin call evidence'),
 ('financials','risk_business_ml/risk_category_expansion/data/business_quarterly_financials.csv',['entity','quarter'],'legal entity/quarter; not business segment profits'),
 ('quarterly_operations','risk_business_ml/risk_category_expansion/data/business_quarterly_operations.csv',None,'reported legal entity/division quarterly operations'),
 ('financial_metric_evidence','risk_business_ml/risk_category_expansion/data/business_metric_provenance.csv',None,'official quarterly financial and operational metric provenance'),
]

def normalized(row):
    out={}
    numeric={'value','assets_billion_usd','reported_change_vs_previous_week_billion_usd',
             'new_issuance_count','new_issuance_amount_usd','numeric_value_in_base_units',
             'value_raw_source_units','stress_loss_to_im','payment_to_qlr','payment_to_core_qlr',
             'resource_to_payment','im_qoq','im_call_to_im','im_call_to_prior_im','vm_peak_to_avg',
             'top5_open_share','top5_open_peak_share','backtest_uncovered_fraction',
             'backtest_uncovered_peak_to_im','backtest_coverage_fraction','liquidity_breach_days',
             'credit_resource_breach_days','backtest_breaches','backtest_observations','source_row','page'}
    for k,v in row.items():
        if v=='': v=None
        if isinstance(v,str):
            if v in ('True','False'):v=v=='True'
            elif v.startswith(('[','{')):
                try:v=json.loads(v)
                except ValueError:pass
            elif k in numeric or k.endswith(('_usd','_pct')):
                try:v=float(v)
                except ValueError:pass
        out[k]=v
    return out

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        if path.suffix=='.jsonl': yield from (json.loads(x) for x in f if x.strip())
        else: yield from (normalized(x) for x in csv.DictReader(f))

def key_for(row,keys):
    return db.dumps([row.get(k) or '' for k in keys]) if keys else db.content_hash(row)

def create_config(project,target):
    old=json.loads((project/'data_refresh_2026_10_14/source_registry.json').read_text())
    configs=[]
    automatic={'rss','market_series','cyber_catalog','provider_incidents','regulatory_documents',
               'disaster_declarations','ficc_daily_series','ficc_monthly_series','business_timeseries','business_reference'}
    special={'esma_news','dtcc_equity_trade_volume_insights_embedded','dtcc_etf_listing_csv'}
    # Historical articles, discovery scripts, discontinued series and dynamic legal indexes
    # remain provenance/reference records, not daily downloads.
    for source in old:
        s=dict(source);s['enabled']=s['kind'] in automatic or s['id'] in special
        s['refresh_hours']=168 if s['kind']=='business_reference' else 20
        if s.get('series_id') in ['WRMFSL','WIMFSL']:s.update(enabled=False,update_note='Discontinued in 2021; historical reference only')
        if s['id']=='dtcc_etf_listing_csv':s['kind']='etf_reference'
        if s['id']=='dtcc_equity_trade_volume_insights_embedded':s['kind']='equity_operations'
        if s['id']=='esma_news':s['kind']='esma_news'
        if s['kind']=='market_series':s['url']='https://fred.stlouisfed.org/graph/fredgraph.csv?id='+s['series_id']
        if s['kind']=='regulatory_documents':s['url']='https://www.federalregister.gov/api/v1/documents.json'
        if s['kind']=='disaster_declarations':s['url']='https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries'
        if s['id'] in ['dtcc_policy','dtcc_financials','ici_money_market_release','ici_fund_flows','dtcc_press','dtcc_insights']:
            s['update_note']='Manual/browser review required; no supported automated structured discovery confirmed. Never mark the existing snapshot as newly published.'
        configs.append(s)
    for oldsource in old:
        if oldsource['kind']!='repository_weekly' or '_20261009' not in oldsource['id']:continue
        if any(x in oldsource['id'] for x in ['sftr_table3','sftr_table4']):continue
        s=dict(oldsource);s['id']=s['id'].replace('_20261009','')
        s.update(url=s['url'].replace('20261009','{report_date}'),enabled=True,refresh_hours=20)
        configs.append(s)
    assert len({x['id'] for x in configs})==len(configs)
    active=[x for x in configs if x['enabled']]
    assert len({x['url'] for x in active})==len(active),'Shared source should be fetched only once'
    (target/'sources.json').write_text(json.dumps(configs,ensure_ascii=False,indent=2)+'\n')
    businesses=json.loads((project/'data_refresh_2026_10_14/business_requirements.json').read_text())
    businesses=[{k:b[k] for k in ['business_line','full_name','legal_scope']} for b in businesses]
    (target/'businesses.json').write_text(json.dumps(businesses,ensure_ascii=False,indent=2)+'\n')
    return configs,businesses

def bootstrap(project,path):
    project=Path(project).resolve();refresh=project/'data_refresh_2026_10_14'
    configs,businesses=create_config(project,db.ROOT)
    with db.writer_lock(path):
        c=db.connect(path);db.register(c,configs,businesses);rid=db.start_run(c,'bootstrap')
        manifest=json.loads((refresh/'source_manifest.json').read_text());rawmap={};count=0
        for f in manifest:
            p=refresh/f.get('file','')
            if not p.is_file() or f.get('kind') in ['discovery','feed_catalog']:continue
            data=p.read_bytes();h=db.put_blob(c,data)
            if f.get('sha256') and f['sha256']!=h:raise ValueError('Source hash mismatch: '+f['file'])
            rawmap[f['file']]=h
            sid=f['source_id']
            if not c.execute('SELECT 1 FROM sources WHERE source_id=?',(sid,)).fetchone():continue
            c.execute('INSERT INTO fetches(run_id,source_id,requested_url,checked_at,status,http_status,blob_hash,detail) VALUES(?,?,?,?,?,?,?,?)',
                      (rid,sid,f['url'],f.get('collected_at_utc') or db.now(),'imported',f.get('http_status'),h,'Imported public-source evidence; not a new retrieval'))
            c.execute('UPDATE sources SET last_success=?,last_status=?,last_blob_hash=? WHERE source_id=?',
                      (f.get('collected_at_utc'),'imported',h,sid))
        specs=[(d,refresh/'data'/p,k,g) for d,p,k,g in SPECS]+[(d,project/p,k,g) for d,p,k,g in HISTORICAL]
        summary={}
        for dataset,path_in,keys,grain in specs:
            if not path_in.exists():raise FileNotFoundError(path_in)
            c.execute('INSERT OR IGNORE INTO datasets VALUES(?,?,?,?)',(dataset,dataset.replace('_',' '),grain,'Public evidence or exploratory derived fields; not a calibrated risk score, causal impact, or segment profit.'))
            file_hash=db.put_blob(c,path_in.read_bytes());n=0
            for row in rows(path_in):
                if dataset=='rds_reports':row['source_id']=re.sub(r'_20\d{6}$','',row['source_id'])
                if dataset=='news':
                    row['document_id']=db.sha(row['url'])
                    p=refresh/str(row.get('original_text_file') or '')
                    if p.is_file():row['original_text']=p.read_text()
                if dataset=='business_scale' and 'CDS market share' in row['metric_label']:
                    row['metric_id']=db.sha('tiw_cds_market_share\n'+row['reporting_period'])
                key=db.sha(row['url']) if dataset=='news' else key_for(row,keys);sid=row.get('source_id')
                raw=rawmap.get(row.get('source_file') or row.get('raw_file'))
                change=db.upsert(c,dataset,key,row,rid,sid,raw or file_hash,row.get('collected_at_utc'),str(path_in.relative_to(project)))
                if dataset=='news':
                    for link in row.get('routing_evidence',[]):
                        c.execute('INSERT OR REPLACE INTO document_business VALUES(?,?,?,?,?)',(row['document_id'],link['business_line'],link['rule'],db.dumps(link),'candidate_unreviewed'))
                n+=1
            summary[dataset]=n;c.commit()
        # Preserve the earlier collector history, merging the same canonical URL.
        import sqlite3
        prior=project/'public_news_prototype/output/news.sqlite3'
        if prior.exists():
            with sqlite3.connect('file:'+str(prior)+'?mode=ro',uri=True) as old:
                for (payload,) in old.execute('SELECT payload FROM documents'):
                    row=json.loads(payload);url=row['url'];key=db.sha(url)
                    if c.execute("SELECT 1 FROM records WHERE dataset_id='news' AND record_key=?",(key,)).fetchone():continue
                    row['document_id']=db.sha(url);row['source_summary']=row.get('summary',row.get('source_summary',''))
                    db.upsert(c,'news',key,row,rid,row.get('source_id'),observed_at=row.get('collected_at_utc'),evidence='earlier public RSS prototype')
        # In addition to normalized rows, preserve extraction evidence's official source files.
        for dataset in ['pqd_cell_evidence','response_cell_evidence']:
            for (payload,) in c.execute('SELECT payload FROM records WHERE dataset_id=?',(dataset,)).fetchall():
                row=json.loads(payload);relative=row.get('source_file')
                if not relative:continue
                candidates=[project/relative,project/'risk_business_ml/event_vulnerability_tests_2026_10_06'/relative]
                candidate=next((p for p in candidates if p.is_file()),None)
                if candidate:
                    h=db.put_blob(c,candidate.read_bytes());key=db.content_hash(row)
                    c.execute('INSERT OR IGNORE INTO record_evidence VALUES(?,?,?,?,?)',(dataset,key,row.get('source_url') or '',h,'Official historical PQD workbook/PDF'))
        c.execute('UPDATE runs SET finished_at=?,status=?,summary=? WHERE run_id=?',(db.now(),'success',db.dumps(summary),rid));c.commit()
        db.export_csv(c,db.ROOT/'exports');result=db.snapshot(c,path);c.close()
        print(json.dumps({'imported_rows':summary,'snapshot':result},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project-root',type=Path,default=db.ROOT.parent);p.add_argument('--db',type=Path,default=db.DEFAULT_DB)
    args=p.parse_args();bootstrap(args.project_root,args.db)
