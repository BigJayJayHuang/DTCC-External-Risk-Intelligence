"""Import reviewed public research inputs; do not overwrite legacy PQD values.

This is an explicit batch import, not a new daily collector. Sources remain disabled
in the daily scheduler until a supported refresh adapter has been implemented.
"""
from pathlib import Path
from collections import Counter
import argparse, csv, gzip, json, math, re, shutil, sqlite3, tempfile
import db

DEFAULT_BUNDLE = db.ROOT.parent/'risk_business_ml/new_reference_chain_tests_2026_10_21'
DATASETS = {
    'ofr_repo_observations': ('OFR final-vintage repo rates and volumes', 'mnemonic/observation date', 'Native OFR units and magnitude retained; null includes disclosure suppression. Not a settlement-failure measure.'),
    'treasury_auctions': ('Reviewed completed Treasury auctions', 'CUSIP/auction date/issue date/security type', 'Announced offering amount is not awarded amount or auction tail. Local completed/date filters are applied to the full response.'),
    'fund_flow_quarterly': ('Financial Accounts fund transactions', 'series/quarter', 'USD million; quarterly not seasonally adjusted transactions. Not CCIT-specific flows or gross Fund/SERV activity.'),
    'chain_pqd_observations': ('Additional reviewed PQD fields and explicit reconciliations', 'entity/quarter', 'Supplemental overlay; original canonical PQD values are retained. Chosen reconciled values have separate fields and evidence.'),
    'chain_pqd_cell_evidence': ('Additional original PQD cell evidence', 'entity/quarter/reference/dimension/sheet/cell', 'Raw reported cells, definitions and normalization; no imputation for missing spreadsheets.'),
    'financial_guarantee_reconciliation': ('FICC financial guarantee/PQD scale reconciliation', 'entity/quarter', 'Financial note rounded in billions; use note only when PQD is missing or outside rounding tolerance.'),
    'mbsd_activity_reconciliation': ('MBSD clearing notional scale reconciliation', 'quarter', 'Two candidate million-scale corrections cross-checked against independent monthly activity; calendar proxy and exclusion sensitivity remain required.'),
    'public_source_documents': ('Downloaded public-source response metadata', 'requested source URL/content hash', 'Body is deduplicated in evidence_blobs locally; public snapshot retains hashes. Retrieval date is not publication date.'),
}

NUMERIC = {'top5_position_share','top5_im_share','crossmargin_reduction_reported_pct',
           'cleared_notional_usd_as_reported','unsettled_notional_usd_as_reported',
           'value','financial_billions_usd','financial_usd','pqd_as_reported',
           'financial_to_pqd_ratio','chosen_usd','raw_pqd23_1_2','conversion_factor',
           'monthly_total_usd','observed_treasury_days','independent_daily_mean_usd',
           'page','offered_amount_usd','bidToCoverRatio','highYield'}

def number(value):
    if value is None or value == '': return None
    result=float(value)
    if not math.isfinite(result): raise ValueError('Non-finite numeric value')
    return result

def read_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        result=list(csv.DictReader(f))
    for row in result:
        for k in NUMERIC & row.keys(): row[k]=number(row[k])
        if 'within_rounding_tolerance' in row:
            row['within_rounding_tolerance']={'True':True,'False':False,'':None}[row['within_rounding_tolerance']]
    return result

def source_id(entry):
    # One source per URL, never one duplicated copy per business line.
    return 'research_'+db.sha(entry['url'])[:20]

def businesses(name):
    if name.startswith('REPO-') or name.startswith('gsd_') or name.startswith('ficc_') or name.startswith('epn_') or name.startswith('acs_') or name.startswith('treasury_'): return ['FICC']
    if name.startswith('fed_z1_'): return ['FICC','WIS']
    if name.startswith(('custody_','deposits_')): return ['Asset Services']
    if name.startswith(('dtc_','sec_dtc_','cds_')): return ['ECS','Asset Services']
    if name.startswith(('nscc_','sft_','acats_')): return ['ECS','WIS']
    return ['FICC','ECS','WIS','Asset Services']

def store_rows(c,rid,items):
    """Reject conflicting batch identities; caller owns one atomic transaction."""
    counts=Counter();seen={}
    for dataset,key,payload,sid,h,stamp,label in items:
        identity=(dataset,key); semantic=db.content_hash(payload)
        if identity in seen:
            if seen[identity]!=semantic: raise ValueError('Conflicting batch identity '+str(identity))
            continue
        seen[identity]=semantic
        counts[db.upsert(c,dataset,key,payload,rid,sid,h,stamp,label)]+=1
    return dict(counts)

def import_bundle(bundle=DEFAULT_BUNDLE,path=db.DEFAULT_DB,make_snapshot=True):
    bundle=Path(bundle);path=Path(path)
    attempts=json.loads((bundle/'fetch_manifest.json').read_text())
    frozen=json.loads((bundle/'input_manifest.json').read_text())
    # Verify all public raw files before touching the database.
    public_inputs=[x for x in frozen if str(x['frozen_copy']).startswith(('inputs/pqd/','inputs/financials/')) or str(x['frozen_copy'])=='inputs/ficc_clearing_volumes_source.xml']
    for x in attempts:
        if x['status']=='downloaded':
            if db.sha((bundle/'raw'/x['name']).read_bytes())!=x['sha256']:raise ValueError('Raw source checksum mismatch '+x['name'])
    for x in public_inputs:
        if db.sha((bundle/x['frozen_copy']).read_bytes())!=x['sha256']:raise ValueError('Frozen source checksum mismatch')
    imported_at=db.now();receipt={'imported_at_utc':imported_at,'bundle':bundle.name,'scope':'Reviewed public sources only; provided reference-chain text is not imported.', 'refresh_mode':'Explicit batch import; these added source adapters are not enabled for daily refresh.'}
    with db.writer_lock(path):
        c=db.connect(path);rid=db.start_run(c,'reviewed_chain_research_import')
        before={'records':c.execute('SELECT count(*) FROM records').fetchone()[0], 'versions':c.execute('SELECT count(*) FROM record_versions').fetchone()[0]}
        sources={}
        for x in attempts:
            sid=source_id(x)
            sources[sid]={'id':sid,'name':'Reviewed public source: '+x['name'],'url':x['url'],'kind':'reviewed_research_batch','enabled':False,'refresh_hours':None,'business_lines':businesses(x['name']),'refresh_note':receipt['refresh_mode']}
        # Persist configs so the daily scheduler preserves links without trying unsupported parsers.
        config_path=db.ROOT/'sources.json'
        configs=json.loads(config_path.read_text());byid={x['id']:x for x in configs}
        byid.update(sources)
        # On a test/custom DB, registration is local and does not mutate production config.
        db.register(c,list(sources.values()),json.loads((db.ROOT/'businesses.json').read_text()))
        try:
            with c:
                for key,(description,grain,interpretation) in DATASETS.items():
                    c.execute('INSERT INTO datasets VALUES(?,?,?,?) ON CONFLICT(dataset_id) DO UPDATE SET description=excluded.description,grain=excluded.grain,interpretation=excluded.interpretation',(key,description,grain,interpretation))
                blobs={};downloaded={};items=[];fetch_new=0
                def put_file(p,expected=None):
                    body=Path(p).read_bytes();h=db.sha(body)
                    if expected and h!=expected:raise ValueError('Checksum changed during import')
                    old=c.execute('SELECT compression FROM evidence_blobs WHERE sha256=?',(h,)).fetchone()
                    if not old or old[0]!='zlib':db.put_blob(c,body)
                    return h
                for x in attempts:
                    sid=source_id(x);h=None;stamp=x['retrieved_at_utc']
                    if x['status']=='downloaded':
                        h=put_file(bundle/'raw'/x['name'],x['sha256']);blobs[x['name']]=h;downloaded[x['name']]=x
                        payload={'source_url':x['url'],'final_url':x.get('final_url',x['url']),'file_name':x['name'],'sha256':h,'byte_count':x['bytes'],'retrieved_at_utc':stamp,'publication_date':None,'evidence_scope':'Publisher response, not confirmation of a business impact'}
                        items.append(('public_source_documents',db.dumps([x['url'],h]),payload,sid,h,stamp,'Downloaded public source body'))
                    fetch_identity=db.sha(db.dumps([x['url'],stamp,x['status'],x.get('sha256')]))
                    if not c.execute("SELECT 1 FROM fetches WHERE CASE WHEN json_valid(detail) THEN json_extract(detail,'$.fetch_identity') END=?",(fetch_identity,)).fetchone():
                        c.execute('INSERT INTO fetches(run_id,source_id,requested_url,checked_at,status,http_status,blob_hash,error,record_count,detail) VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,sid,x['url'],stamp,x['status'],x.get('http_status'),h,x.get('error'),x.get('n_records'),db.dumps({'fetch_identity':fetch_identity,'manifest_entry':x})));fetch_new+=1
                    c.execute('UPDATE sources SET last_checked=?,last_status=?,last_error=? WHERE source_id=?',(stamp,x['status'],x.get('error'),sid))
                    if h:c.execute('UPDATE sources SET last_success=?,last_blob_hash=? WHERE source_id=?',(stamp,h,sid))
                input_hashes={}
                for x in public_inputs:input_hashes[Path(x['frozen_copy']).name]=put_file(bundle/x['frozen_copy'],x['sha256'])
                def add(dataset,key,row,name,label):
                    x=downloaded[name];items.append((dataset,db.dumps(key),row,source_id(x),blobs[name],x['retrieved_at_utc'],label))
                for name,x in downloaded.items():
                    if not re.fullmatch(r'REPO-.+(?<!_metadata)\.json',name):continue
                    mnemonic=name[:-5];meta=json.loads((bundle/'raw'/f'{mnemonic}_metadata.json').read_text());unit=meta['unit']
                    for date,value in json.loads((bundle/'raw'/name).read_text()):
                        row={'mnemonic':mnemonic,'observation_date':date,'value':number(value),'units':unit['name'],'unit_magnitude':unit['magnitude'],'unit_display_magnitude':unit.get('display_magnitude'),'frequency':'daily','vintage':'Final','publisher_last_update':meta['schedule']['last_update'],'source_url':x['url'],'missing_value_note':meta['description'].get('notes') if value is None else None}
                        add('ofr_repo_observations',[mnemonic,date],row,name,'OFR final-vintage response; native units')
                for row in read_csv(bundle/'data/treasury_auction_observations.csv'):
                    row.update(observation_date=row['auction_date'],source_url=downloaded['treasury_auctions_all.json']['url'],filter_audit=json.loads((bundle/'results/auction_filter_audit.json').read_text()),amount_definition='Announced offering amount, not actual award')
                    add('treasury_auctions',[row[k] for k in ['cusip','auction_date','issue_date','securityType']],row,'treasury_auctions_all.json','Locally filtered completed auction; original full response retained')
                for filename,column in [('mmf_repo_flow_million_usd.csv','mmf_repo_flow_million_usd'),('mutual_fund_net_issuance_million_usd.csv','mutual_fund_net_issuance_million_usd')]:
                    for row in read_csv(bundle/'data'/filename):
                        row.update(series_id=row['source_series'],value=number(row.pop(column)),units='USD million',frequency='quarterly',seasonal_adjustment='not seasonally adjusted',measurement_type='transactions',vintage_publication_date='2026-09-11',source_url=downloaded['fed_z1_20260911.zip']['url'])
                        add('fund_flow_quarterly',[row['series_id'],row['quarter']],row,'fed_z1_20260911.zip','Federal Reserve Financial Accounts release 2026-09-11')
                financial=read_csv(bundle/'data/financial_guarantee_reconciliation.csv'); activity=read_csv(bundle/'data/mbsd_cleared_notional_reconciliation.csv')
                fin={(r['entity'],r['quarter']):r for r in financial};act={r['quarter']:r for r in activity}
                cell_rows=read_csv(bundle/'data/new_pqd_cell_evidence.csv');pqd_hash={}
                for row in cell_rows:
                    h=input_hashes[row['source_file']];assert h==row['sha256'];pqd_hash[(row['entity'],row['quarter'])]=h
                    row.update(source_url='https://www.dtcc.com/legal/policy-and-compliance')
                    key=[row[k] for k in ['entity','quarter','reference','dimension','sheet','cell']]
                    items.append(('chain_pqd_cell_evidence',db.dumps(key),row,None,h,imported_at,'Original PQD workbook cell'))
                for row in financial:
                    row.update(source_url='https://www.dtcc.com/legal/financial-statements')
                    items.append(('financial_guarantee_reconciliation',db.dumps([row['entity'],row['quarter']]),row,None,input_hashes[row['source_file']],imported_at,'Financial statement guarantee note/page; raw PQD preserved'))
                monthly_hash=input_hashes['ficc_clearing_volumes_source.xml']
                for row in activity:
                    row.update(calendar_note='Treasury observation dates are a calendar proxy; exclusion sensitivity accompanies analysis',source_url='https://www.dtcc.com/charts/dtcc-gsd-mbsd-volumes')
                    items.append(('mbsd_activity_reconciliation',db.dumps([row['quarter']]),row,None,monthly_hash,imported_at,'Independent original monthly clearing XML'))
                overlay=read_csv(bundle/'data/new_pqd_fields.csv')
                covered={(r['entity'],r['quarter']) for r in overlay}
                for identity in fin.keys()-covered:
                    overlay.append({'entity':identity[0],'quarter':identity[1],**{k:None for k in ['top5_position_share','top5_im_share','crossmargin_reduction_reported_pct','cleared_notional_usd_as_reported','unsettled_notional_usd_as_reported']},'missing_spreadsheet_note':'No spreadsheet extraction for this quarter; only financial-note unsettled notional is available.'})
                for row in overlay:
                    identity=(row['entity'],row['quarter']);chosen=fin.get(identity)
                    row.update(unsettled_notional_usd_reconciled=chosen['chosen_usd'] if chosen else None,unsettled_reconciliation_source=chosen['chosen_source'] if chosen else None)
                    row['cleared_notional_usd_reconciled']=act[row['quarter']]['chosen_usd'] if row['entity']=='MBSD' and row['quarter'] in act else row['cleared_notional_usd_as_reported']
                    row['overlay_note']='Additional fields; original PQD reporting scales remain in *_as_reported; original pqd_quarterly dataset is unchanged.'
                    h=pqd_hash.get(identity) or (input_hashes[chosen['source_file']] if chosen else None)
                    items.append(('chain_pqd_observations',db.dumps(list(identity)),row,None,h,imported_at,'Supplemental PQD extraction with explicit reconciled fields'))
                counts=store_rows(c,rid,items)
                # Reconciled overlay values reference both sources, not only the raw spreadsheet.
                for identity,row in fin.items():
                    key=db.dumps(list(identity))
                    c.execute('INSERT OR IGNORE INTO record_evidence VALUES(?,?,?,?,?)',('chain_pqd_observations',key,'',input_hashes[row['source_file']],'Financial guarantee reconciliation evidence'))
                for row in activity:
                    c.execute('INSERT OR IGNORE INTO record_evidence VALUES(?,?,?,?,?)',('chain_pqd_observations',db.dumps(['MBSD',row['quarter']]),'',monthly_hash,'Independent MBSD activity scale check'))
                receipt.update(run_id=rid,before=before,changes=counts,new_fetch_logs=fetch_new,dataset_counts=dict(c.execute('SELECT dataset_id,count(*) FROM records GROUP BY dataset_id')))
                c.execute('UPDATE runs SET finished_at=?,status=?,summary=? WHERE run_id=?',(db.now(),'success',db.dumps(receipt),rid))
            if path.resolve()==db.DEFAULT_DB.resolve():
                temp_config=config_path.with_suffix('.json.tmp');temp_config.write_text(json.dumps(list(byid.values()),ensure_ascii=False,indent=2)+'\n');temp_config.replace(config_path)
            if make_snapshot:
                from validate import validate
                source_result=validate(path);snapshot=db.snapshot(c,path)
                with tempfile.TemporaryDirectory(prefix='chain-db-check-') as tmp:
                    shared=Path(tmp)/'shared.sqlite3'
                    with gzip.open(path.with_suffix('.sqlite3.gz'),'rb') as src,shared.open('wb') as dst:shutil.copyfileobj(src,dst)
                    shared_result=validate(shared)
                manifest={**snapshot,'generated_at_utc':db.now(),'database':shared_result,'source_validation':source_result,'repository':'BigJayJayHuang/DTCC-External-Risk-Intelligence','distribution':'Structured data and evidence hashes; raw source bodies are not bundled in the public release.','local_import':receipt,'publication_status':'Local snapshot prepared; GitHub release has not been updated by this import.'}
                manifest_path=path.parent/'snapshot_manifest.json';temp=manifest_path.with_suffix('.json.tmp');temp.write_text(json.dumps(manifest,indent=2)+'\n');temp.replace(manifest_path)
                receipt.update(snapshot=snapshot,source_validation=source_result,shared_snapshot_validation=shared_result)
                if path.resolve()==db.DEFAULT_DB.resolve():db.export_csv(c,db.ROOT/'exports')
            receipt['after']={'records':c.execute('SELECT count(*) FROM records').fetchone()[0],'versions':c.execute('SELECT count(*) FROM record_versions').fetchone()[0]}
        except Exception as e:
            with c:c.execute('UPDATE runs SET finished_at=?,status=?,summary=? WHERE run_id=?',(db.now(),'failed',db.dumps({'error':str(e)}),rid))
            raise
        finally:c.close()
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,default=DEFAULT_BUNDLE);p.add_argument('--db',type=Path,default=db.DEFAULT_DB);p.add_argument('--no-snapshot',action='store_true');args=p.parse_args()
    result=import_bundle(args.bundle,args.db,not args.no_snapshot)
    target=args.bundle/'results/database_import_receipt.json';target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
