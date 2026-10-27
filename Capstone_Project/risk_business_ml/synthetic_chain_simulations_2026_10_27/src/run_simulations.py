"""Run three explicitly hypothetical mechanism experiments in an isolated store.

No empirical database, historical chain status or weekly score is opened for write.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, csv, hashlib, importlib, importlib.metadata, json, math
import sqlite3, sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
MODELS=('dtc','epn','tba')
VERSION='synthetic-v1.0'

def stamp():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def digest(data):return hashlib.sha256(data).hexdigest()
def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,np.generic):return clean(value.item())
    if isinstance(value,float) and not math.isfinite(value):return None
    if value is pd.NA:return None
    return value
def dumps(value):return json.dumps(clean(value),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def write_json(path,value):Path(path).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def protected_checks():
    rows=json.loads((ROOT/'inputs/protected_real_artifacts.json').read_text())
    checks=[]
    for row in rows:
        p=Path(row['path'])
        # Original absolute locations can be absent in a portable offline copy.
        checks.append({'name':'empirical_unchanged:'+p.name,'passed':digest(p.read_bytes())==row['sha256'] if p.exists() else True,'detail':'Original artifact unchanged' if p.exists() else 'Original workspace path absent; frozen input hashes remain authoritative','original_present':p.exists()})
    assert all(x['passed'] for x in checks),'Protected empirical evidence changed; do not relabel it.'
    return checks

def reference_anchor():
    p=ROOT/'inputs/financial_guarantee_reconciliation.csv'
    with p.open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    matches=[r for r in rows if r['entity']=='MBSD' and r['quarter']=='2026Q2']
    assert len(matches)==1
    row=matches[0];pdf=ROOT/'inputs'/row['source_file']
    assert digest(pdf.read_bytes())==row['sha256']
    value=float(row['chosen_usd']);assert value==562_000_000_000
    return {'reference_id':'MBSD_2026Q2_broad_unsettled_notional','source_type':'public_reference','value':value,'units':'USD','reporting_period':'2026Q2','source_file':row['source_file'],'source_page':int(row['page']),'source_sha256':row['sha256'],'reconciliation_sha256':digest(p.read_bytes()),'source_url':'https://www.dtcc.com/legal/financial-statements','definition':'Broad MBSD unsettled guarantee notional; not a TBA-only portfolio or a cash payment obligation.','use':'Illustrative scale only; hypothetical TBA share is an assumption, not inferred from this aggregate.'}

def add_tags(frame,simulation_id):
    frame=frame.copy().reset_index(drop=True)
    required={'scenario_id','replicate_id','scenario_seed'}
    if not required<=set(frame):raise ValueError('Missing scenario identity columns: '+str(required-set(frame)))
    # A 64-bit unsigned RNG seed can exceed SQLite's signed integer range.
    # Keep the exact seed as text instead of losing bits in a JSON SQL view.
    frame['scenario_seed']=frame['scenario_seed'].map(str)
    frame['simulation_id']=simulation_id
    frame['source_type']='synthetic'
    frame['assumption_version']=VERSION
    frame['catalog_version']='expanded_v3'
    frame['empirical_validation']=False
    frame['observation_time_basis']='relative simulation clock; not historical observations'
    return frame

def store_database(path,simulation_id,plan,tables,checks,anchor):
    """Idempotent batch/key upsert with hard synthetic-only record constraints."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path)
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript('''
      CREATE TABLE IF NOT EXISTS simulation_batches(
        simulation_id TEXT PRIMARY KEY,assumption_version TEXT NOT NULL,
        plan_json TEXT NOT NULL,first_run_utc TEXT NOT NULL,last_run_utc TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS reference_anchors(
        reference_id TEXT PRIMARY KEY,payload TEXT NOT NULL,
        CHECK(json_extract(payload,'$.source_type') IS 'public_reference'));
      CREATE TABLE IF NOT EXISTS simulation_records(
        simulation_id TEXT REFERENCES simulation_batches(simulation_id),dataset TEXT,
        record_key TEXT,payload TEXT NOT NULL,content_hash TEXT NOT NULL,
        PRIMARY KEY(simulation_id,dataset,record_key),
        CHECK(json_extract(payload,'$.source_type') IS 'synthetic'),
        CHECK(json_extract(payload,'$.empirical_validation') IS 0));
      CREATE INDEX IF NOT EXISTS simulation_dataset ON simulation_records(dataset,simulation_id);
      CREATE TABLE IF NOT EXISTS simulation_checks(
        simulation_id TEXT REFERENCES simulation_batches(simulation_id),check_name TEXT,
        passed INTEGER NOT NULL,detail TEXT,PRIMARY KEY(simulation_id,check_name));
    ''')
    changes={'new':0,'changed':0,'unchanged':0}
    try:
        with c:
            old=c.execute('SELECT plan_json FROM simulation_batches WHERE simulation_id=?',(simulation_id,)).fetchone()
            if old and old[0]!=dumps(plan):raise ValueError('Simulation identity collision')
            c.execute('INSERT INTO simulation_batches VALUES(?,?,?,?,?) ON CONFLICT(simulation_id) DO UPDATE SET last_run_utc=excluded.last_run_utc',(simulation_id,VERSION,dumps(plan),stamp(),stamp()))
            c.execute('INSERT INTO reference_anchors VALUES(?,?) ON CONFLICT(reference_id) DO UPDATE SET payload=excluded.payload',(anchor['reference_id'],dumps(anchor)))
            for dataset,frame in tables.items():
                if not dataset.replace('_','').isalnum():raise ValueError('Unsafe dataset name')
                for i,row in enumerate(frame.to_dict('records')):
                    key=str(i);payload=dumps(row);h=digest(payload.encode())
                    old=c.execute('SELECT content_hash FROM simulation_records WHERE simulation_id=? AND dataset=? AND record_key=?',(simulation_id,dataset,key)).fetchone()
                    state='new' if not old else ('unchanged' if old[0]==h else 'changed');changes[state]+=1
                    c.execute('INSERT INTO simulation_records VALUES(?,?,?,?,?) ON CONFLICT(simulation_id,dataset,record_key) DO UPDATE SET payload=excluded.payload,content_hash=excluded.content_hash',(simulation_id,dataset,key,payload,h))
                # Expose convenient JSON-backed read views while retaining batch identity.
                cols=[]
                for col in frame:
                    if not col.replace('_','').isalnum():raise ValueError('Unsafe column name')
                    cols.append("json_extract(payload,'$."+col+"') AS \""+col+'\"')
                c.execute('DROP VIEW IF EXISTS synthetic_'+dataset)
                c.execute('CREATE VIEW synthetic_'+dataset+' AS SELECT '+','.join(cols)+" FROM simulation_records WHERE dataset='"+dataset+"'")
            for row in checks:
                c.execute('INSERT INTO simulation_checks VALUES(?,?,?,?) ON CONFLICT(simulation_id,check_name) DO UPDATE SET passed=excluded.passed,detail=excluded.detail',(simulation_id,row['name'],int(bool(row['passed'])),dumps(row)))
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        count=c.execute('SELECT count(*) FROM simulation_records WHERE simulation_id=?',(simulation_id,)).fetchone()[0]
        assert count==sum(len(x) for x in tables.values())
        return {'changes':changes,'records_in_batch':count,'integrity':'ok','foreign_keys':'ok'}
    finally:c.close()

def run(seed=20261027,replications=100):
    checks=protected_checks();anchor=reference_anchor()
    modules={name:importlib.import_module(name) for name in MODELS}
    configurations={name:dict(module.DEFAULT_CONFIG) for name,module in modules.items()}
    configurations['tba'].update(broad_mbsd_reference_usd=anchor['value'],hypothetical_tba_share=0.5,horizon_days=60)
    plan={'question':'Mechanistic implementation and conditional scenario exploration, not historical event/PQD validation.','seed':seed,'replications_per_scenario':replications,'assumption_version':VERSION,'catalog_version':'expanded_v3','models':configurations,'engine_hashes':{name:digest((ROOT/'src'/f'{name}.py').read_bytes()) for name in MODELS},'runner_sha256':digest(Path(__file__).read_bytes()),'anchor':anchor,'scope':'DTC constraint queue, EPN notification-to-pool delivery, TBA stock-flow ladder.','inference_limits':['No real incident frequency, causal effect, empirical correlation or calibrated probability.','No synthetic sample is counted as a historical event or quarter.','Model differences reflect assumptions; they do not rank real DTCC business-line risk.','Real business database and historical missing-data statuses remain unchanged.'],'comparison_design':'Paired common random inputs within each model; unexposed/null, stress, mitigation and sensitivity scenarios; scenario spread is not a confidence interval.'}
    simulation_id='SIM_'+digest(dumps(plan).encode())[:16]
    write_json(ROOT/'config/resolved_plan.json',plan)
    write_json(ROOT/'config'/f'{simulation_id}.json',plan)
    tables={};assumptions={}
    for index,(name,module) in enumerate(modules.items()):
        outcome=module.run_experiment(seed=seed+index*100000,replications=replications,config=configurations[name])
        assumptions[name]=outcome['assumptions']
        for key,frame in outcome['tables'].items():
            if key in tables:raise ValueError('Duplicate table '+key)
            tables[key]=add_tags(frame,simulation_id)
            tables[key].to_csv(ROOT/'data'/f'{key}.csv',index=False,float_format='%.17g')
        for check in outcome['checks']:
            row=dict(check);row['name']=name+':'+str(row.get('name',row.get('check_id')));checks.append(row)
        print(name,'tables:',{key:len(frame) for key,frame in outcome['tables'].items()},flush=True)
    if not all(x['passed'] for x in checks):
        write_json(ROOT/'results/failed_checks.json',checks);raise AssertionError('A model control or conservation check failed')
    checks+=protected_checks()
    # Deduplicate repeated before/after protection checks by stable name.
    checks=list({x['name']:x for x in checks}.values())
    path=ROOT/'data/synthetic_scenarios.sqlite3'
    first=store_database(path,simulation_id,plan,tables,checks,anchor)
    repeat=store_database(path,simulation_id,plan,tables,checks,anchor)
    assert repeat['changes']['new']==0 and repeat['changes']['changed']==0
    receipt={'executed_at_utc':stamp(),'simulation_id':simulation_id,'assumption_version':VERSION,'seed':seed,'replications_per_scenario':replications,'database':str(path.relative_to(ROOT)),'database_store':first,'repeat_store':repeat,'tables':{key:len(frame) for key,frame in tables.items()},'csv_sha256':{key:digest((ROOT/'data'/f'{key}.csv').read_bytes()) for key in tables},'all_checks_passed':True,'checks':checks,'python':sys.version.split()[0],'libraries':{name:importlib.metadata.version(name) for name in ['numpy','pandas','matplotlib']},'empirical_database_modified':False,'historical_chain_validation_changed':False}
    write_json(ROOT/'results/execution_receipt.json',receipt)
    write_json(ROOT/'results/model_assumptions.json',assumptions)
    write_json(ROOT/'inputs/reference_anchor.json',anchor)
    print(json.dumps({'simulation_id':simulation_id,'records':first['records_in_batch'],'repeat_changes':repeat['changes'],'checks':len(checks)},indent=2))
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=20261027);p.add_argument('--replications',type=int,default=100);args=p.parse_args()
    if args.replications<2:raise ValueError('Use at least two scenario replications')
    run(args.seed,args.replications)
