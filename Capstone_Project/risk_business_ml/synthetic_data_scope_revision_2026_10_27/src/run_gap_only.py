"""Run only missing-link models with immutable observed inputs and provenance."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,gzip,hashlib,json,math,shutil,sqlite3,unittest
import numpy as np
import pandas as pd
from source_policy import ROOT,sha,verify_frozen_sources,protect_originals,assert_generation_allowed
import gap_models

def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [clean(x) for x in v]
    if isinstance(v,np.generic):return clean(v.item())
    if isinstance(v,float) and not math.isfinite(v):return None
    if v is pd.NA:return None
    return v
def dumps(v):return json.dumps(clean(v),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def write(path,value):Path(path).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def store(path,plan,source_rows,provenance,tables):
    sid=plan['simulation_id'];c=sqlite3.connect(path);changes={'new':0,'unchanged':0}
    try:
        c.execute('PRAGMA foreign_keys=ON')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS gap_batches(simulation_id TEXT PRIMARY KEY,plan_json TEXT NOT NULL,provenance_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS observed_references(simulation_id TEXT REFERENCES gap_batches,reference_id TEXT,payload TEXT NOT NULL,
          source_type TEXT NOT NULL CHECK(source_type IS 'observed_snapshot'),PRIMARY KEY(simulation_id,reference_id));
        CREATE TABLE IF NOT EXISTS gap_records(simulation_id TEXT REFERENCES gap_batches,dataset TEXT,record_key INTEGER,payload TEXT NOT NULL,
          content_hash TEXT NOT NULL,PRIMARY KEY(simulation_id,dataset,record_key),
          CHECK(json_extract(payload,'$.source_type') IS 'hybrid_scenario'),CHECK(json_extract(payload,'$.empirical_validation') IS 0));
        ''')
        with c:
            prior=c.execute('SELECT plan_json FROM gap_batches WHERE simulation_id=?',(sid,)).fetchone()
            if prior and prior[0]!=dumps(plan):raise ValueError('Immutable batch plan changed')
            c.execute('INSERT OR IGNORE INTO gap_batches VALUES(?,?,?)',(sid,dumps(plan),dumps(provenance)))
            for key,val in source_rows.items():
                old=c.execute('SELECT payload FROM observed_references WHERE simulation_id=? AND reference_id=?',(sid,key)).fetchone()
                if old and old[0]!=dumps(val):raise ValueError('Observed reference cannot change within a batch')
                c.execute("INSERT OR IGNORE INTO observed_references VALUES(?,?,?,'observed_snapshot')",(sid,key,dumps(val)))
            for dataset,f in tables.items():
                if not dataset.replace('_','').isalnum():raise ValueError('Unsafe dataset')
                for i,row in enumerate(f.to_dict('records')):
                    payload=dumps(row);h=hashlib.sha256(payload.encode()).hexdigest()
                    old=c.execute('SELECT content_hash FROM gap_records WHERE simulation_id=? AND dataset=? AND record_key=?',(sid,dataset,i)).fetchone()
                    if old:
                        if old[0]!=h:raise ValueError('Immutable scenario row changed')
                        changes['unchanged']+=1
                    else:c.execute('INSERT INTO gap_records VALUES(?,?,?,?,?)',(sid,dataset,i,payload,h));changes['new']+=1
                cols=[]
                for col in f:
                    if not col.replace('_','').isalnum():raise ValueError('Unsafe column')
                    cols.append("json_extract(payload,'$."+col+"') AS \""+col+'"')
                c.execute('DROP VIEW IF EXISTS '+dataset)
                c.execute('CREATE VIEW '+dataset+' AS SELECT '+','.join(cols)+" FROM gap_records WHERE dataset='"+dataset+"'")
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
        return changes
    finally:c.close()

def main(seed=20261027,replications=100):
    frozen=verify_frozen_sources();before=protect_originals()
    plan={'version':'real-data-first-gap-only-v1','catalog':'expanded_v3','seed':seed,'replications':replications,
          'config':gap_models.DEFAULT_CONFIG,'engine_sha256':sha(ROOT/'src/gap_models.py'),'runner_sha256':sha(__file__),
          'policy_sha256':sha(ROOT/'src/source_policy.py'),'source_sha256':{r['file']:r['sha256'] for r in frozen},
          'scope':'Exactly3missing-link demonstrations; no broad market/margin/VM regeneration.',
          'source_priority':'observed > derived_from_observed > explicitly assumed_missing; unknown values never overwrite observed columns',
          'claim_limit':'Conditional mechanism arithmetic and sensitivity, not empirical chain validation.'}
    sid='GAP_'+hashlib.sha256(dumps(plan).encode()).hexdigest()[:16];plan['simulation_id']=sid
    write(ROOT/'config/resolved_plan.json',plan)
    out=gap_models.run_experiment(seed,replications,source_root=ROOT/'inputs/observed')
    observed_fields={'issue_date','auction_date','offered_amount_usd','observed_broad_mbsd_stock_usd','observed_top5_average_share','observed_top5_peak_share','observed_top5_im_average_share'}
    requested=set()
    for fields in out['field_provenance']['assumed_missing']:
        requested.update(fields.split('/'))
    assert_generation_allowed(requested,observed_fields)
    tables={}
    for name,f in out['tables'].items():
        f=f.copy();f['scenario_seed']=f.scenario_seed.map(str)
        f['simulation_id']=sid;f['source_type']='hybrid_scenario';f['empirical_validation']=False
        f['observed_fields_regenerated']=False;f['field_provenance_reference']='results/field_provenance.json'
        f.to_csv(ROOT/'data'/f'{name}.csv',index=False,float_format='%.17g');tables[name]=f
    assert all(c['passed'] for c in out['checks'])
    for filename,key in [('observed_selected_rows.json','source_rows'),('field_provenance.json','field_provenance'),('model_assumptions.json','assumptions'),('scenario_definitions.json','scenarios')]:write(ROOT/'results'/filename,out[key])
    path=ROOT/'data/gap_scenarios.sqlite3'
    first=store(path,plan,out['source_rows'],out['field_provenance'],tables)
    again=store(path,plan,out['source_rows'],out['field_provenance'],tables)
    assert again['new']==0 and again['unchanged']==sum(len(f) for f in tables.values())
    verify_frozen_sources();after=protect_originals();assert before==after
    result=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    tests={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful()}
    write(ROOT/'results/unit_tests.json',tests);assert tests['passed']
    receipt={'simulation_id':sid,'executed_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
             'scenarios':len(out['scenarios']),'scenario_runs':len(tables['gap_runs']),'replications':replications,
             'tables':{k:len(v) for k,v in tables.items()},'csv_sha256':{k:sha(ROOT/'data'/f'{k}.csv') for k in tables},
             'source_files':frozen,'source_generation_guard':'passed','original_evidence_checks':after,
             'observed_fields_regenerated':False,'empirical_database_modified':False,'checks':out['checks'],
             'store_first':first,'store_repeat':again,'unit_tests':tests}
    write(ROOT/'results/execution_receipt.json',receipt)
    packed=path.with_suffix('.sqlite3.gz')
    with path.open('rb') as src,packed.open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as dst:shutil.copyfileobj(src,dst)
    write(ROOT/'data/snapshot_manifest.json',{'source_type':'hybrid_missing_link_scenarios','database_sha256':sha(path),'compressed_sha256':sha(packed),'simulation_id':sid})
    from build_results import main as build_results
    build_results()
    print(json.dumps({'simulation_id':sid,'scenarios':receipt['scenarios'],'runs':receipt['scenario_runs'],'tests':tests},indent=2));return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=20261027);p.add_argument('--replications',type=int,default=100);a=p.parse_args();main(a.seed,a.replications)
