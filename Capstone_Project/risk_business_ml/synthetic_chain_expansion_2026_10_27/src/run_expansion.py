"""Frozen, paired scenario expansion. Writes only the isolated synthetic store."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, importlib, importlib.metadata, json, math, sqlite3, sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULES = ('margin_liquidity', 'default_funding', 'service_operations')
VERSION = 'synthetic-v2.0'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [clean(v) for v in value]
    if isinstance(value,np.generic):return clean(value.item())
    if value is pd.NA:return None
    if isinstance(value,float) and not math.isfinite(value):return None
    return value

def dumps(value):return json.dumps(clean(value),sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def write_json(path,value):Path(path).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def protect():
    checks=[]
    for row in json.loads((ROOT/'inputs/protected_real_artifacts.json').read_text()):
        p=Path(row['path']);present=p.exists()
        checks.append({'name':'protected:'+p.name,'passed':sha(p)==row['sha256'] if present else True,
                       'original_present':present,'detail':'Unchanged original' if present else 'Original path absent in portable copy; not a live verification'})
    if not all(r['passed'] for r in checks):raise AssertionError('Original evidence changed')
    return checks

def tag(frame,simulation_id):
    frame=frame.copy().reset_index(drop=True)
    if not {'scenario_id','replicate_id','scenario_seed'}<=set(frame):raise ValueError('Scenario identity is required')
    frame['scenario_seed']=frame['scenario_seed'].map(str)
    frame['simulation_id']=simulation_id
    frame['source_type']='synthetic'
    frame['empirical_validation']=False
    frame['assumption_version']=VERSION
    frame['catalog_version']='expanded_v3'
    frame['observation_time_basis']='Hypothetical scenario clock, not observed dates'
    return frame

def _ident(name):
    if not name or not name.replace('_','').isalnum():raise ValueError('Unsafe SQL identifier')
    return '"'+name+'"'

def _sql_value(v):
    if v is None or v is pd.NA:return None
    if isinstance(v,np.generic):v=v.item()
    if isinstance(v,float) and not math.isfinite(v):return None
    if isinstance(v,(bool,np.bool_)):return int(v)
    return v

def store(path,simulation_id,plan,tables):
    """Immutable batch rows, exact seed text and DB-enforced synthetic labels."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path);c.execute('PRAGMA foreign_keys=ON')
    changes={'new':0,'changed':0,'unchanged':0}
    try:
        with c:
            c.execute('CREATE TABLE IF NOT EXISTS batches(simulation_id TEXT PRIMARY KEY,plan_json TEXT NOT NULL)')
            prior=c.execute('SELECT plan_json FROM batches WHERE simulation_id=?',(simulation_id,)).fetchone()
            if prior and prior[0]!=dumps(plan):raise ValueError('Simulation identity collision')
            c.execute('INSERT OR IGNORE INTO batches VALUES(?,?)',(simulation_id,dumps(plan)))
            for name,f in tables.items():
                table=_ident('synthetic_'+name)
                specs=[]
                for col in f:
                    dtype='TEXT' if col=='scenario_seed' else ('INTEGER' if pd.api.types.is_integer_dtype(f[col]) or pd.api.types.is_bool_dtype(f[col]) else 'REAL' if pd.api.types.is_float_dtype(f[col]) else 'TEXT')
                    specs.append(_ident(col)+' '+dtype)
                specs+=['record_key INTEGER NOT NULL','content_hash TEXT NOT NULL','PRIMARY KEY(simulation_id,record_key)',
                        'FOREIGN KEY(simulation_id) REFERENCES batches(simulation_id)',
                        "CHECK(source_type IS 'synthetic')",'CHECK(empirical_validation IS 0)']
                c.execute('CREATE TABLE IF NOT EXISTS '+table+'('+','.join(specs)+')')
                insert='INSERT INTO '+table+' VALUES('+','.join(['?']*(len(f.columns)+2))+')'
                saved={k:h for k,h in c.execute('SELECT record_key,content_hash FROM '+table+' WHERE simulation_id=?',(simulation_id,))}
                if saved and len(saved)!=len(f):raise ValueError('Immutable batch row count changed')
                additions=[]
                for key,values in enumerate(f.itertuples(index=False,name=None)):
                    values=tuple(_sql_value(v) for v in values)
                    h=hashlib.sha256(dumps(dict(zip(f.columns,values))).encode()).hexdigest()
                    if key in saved:
                        if saved[key]!=h:raise ValueError('Immutable simulation row changed')
                        changes['unchanged']+=1
                    else:additions.append((*values,key,h));changes['new']+=1
                if additions:c.executemany(insert,additions)
        integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
        assert integrity=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
        return {'changes':changes,'records_in_batch':sum(len(f) for f in tables.values()),'integrity':integrity}
    finally:c.close()

def run(seed=20261027,replications=100):
    if replications<2:raise ValueError('At least two paths per scenario required')
    checks=protect()
    modules={name:importlib.import_module(name) for name in MODULES}
    plan={'question':'Expand conditional mechanism experiments; no empirical fitting or validation.',
          'seed':seed,'replications_per_scenario':replications,'assumption_version':VERSION,'catalog_version':'expanded_v3',
          'models':{name:module.DEFAULT_CONFIG for name,module in modules.items()},
          'engine_sha256':{name:sha(ROOT/'src'/f'{name}.py') for name in MODULES},
          'runner_sha256':sha(__file__),
          'registry_sha256':sha(ROOT/'inputs/chain_registry_v3.json'),
          'source_register_sha256':sha(ROOT/'inputs/source_register.json'),
          'v1_simulation_id':json.loads((ROOT/'inputs/v1_execution_receipt.json').read_text())['simulation_id'],
          'design':'Same generated inputs within each model, baseline/stress/mitigation/unexposed/sensitivity controls; all scenario formulas predeclared in hashed engines.',
          'limits':['No official numeric risk formula is replicated.','No actual incident, member mapping, frequency, causal relationship or loss probability is inferred.','VM, Clearing Fund margin and SLD are distinct.','Different services are not netted or ranked together.','No synthetic records enter the empirical database or weekly scores.']}
    simulation_id='SIM2_'+hashlib.sha256(dumps(plan).encode()).hexdigest()[:16]
    write_json(ROOT/'config/resolved_plan.json',plan)
    write_json(ROOT/'config'/f'{simulation_id}.json',plan)
    tables={};assumptions={};chain_map=[];scenarios=[]
    for index,(name,module) in enumerate(modules.items()):
        out=module.run_experiment(seed=seed+(index+1)*1000000,replications=replications,config=dict(plan['models'][name]))
        assumptions[name]=out['assumptions']
        chain_map.extend([{**r,'engine':name} for r in out['chain_map']])
        scenarios.extend([{**r,'engine':name} for r in out['scenarios']])
        for key,f in out['tables'].items():
            if key in tables:raise ValueError('Duplicate dataset')
            tables[key]=tag(f,simulation_id)
            tables[key].to_csv(ROOT/'data'/f'{key}.csv',index=False,float_format='%.17g')
        for r in out['checks']:checks.append({**r,'name':name+':'+r['name']})
        print(name,{k:len(v) for k,v in out['tables'].items()},flush=True)
    assert len({r['scenario_id'] for r in scenarios})==len(scenarios)
    valid={r['chain_id'] for r in json.loads((ROOT/'inputs/chain_registry_v3.json').read_text())['chains']}
    assert {r['chain_id'] for r in chain_map}<=valid,'Unknown chain ID'
    for name,f in tables.items():
        assert set(f.scenario_id)<=set(r['scenario_id'] for r in scenarios)
        if name.endswith('_runs'):
            assert {'model_id','primary_metric','primary_value','primary_units'}<=set(f)
            assert f.groupby('scenario_id').size().eq(replications).all()
            assert not f.duplicated(['scenario_id','replicate_id']).any()
    checks=checks+protect()
    checks=list({r['name']:r for r in checks}.values())
    assert all(r['passed'] for r in checks),'Mechanism check failed'
    path=ROOT/'data/synthetic_scenarios.sqlite3'
    first=store(path,simulation_id,plan,tables);again=store(path,simulation_id,plan,tables)
    assert again['changes']['new']==again['changes']['changed']==0
    write_json(ROOT/'results/model_assumptions.json',assumptions)
    write_json(ROOT/'results/scenario_definitions.json',scenarios)
    write_json(ROOT/'results/chain_model_map.json',chain_map)
    write_json(ROOT/'results/data_dictionary.json',{k:{'rows':len(f),'columns':[{'name':col,'dtype':str(f[col].dtype)} for col in f]} for k,f in tables.items()})
    receipt={'simulation_id':simulation_id,'executed_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
             'seed':seed,'replications_per_scenario':replications,'scenario_count':len(scenarios),
             'model_count':len({r['model_id'] for r in scenarios}),'new_chain_ids':sorted({r['chain_id'] for r in chain_map}),
             'tables':{k:len(f) for k,f in tables.items()},'csv_sha256':{k:sha(ROOT/'data'/f'{k}.csv') for k in tables},
             'database_store':first,'repeat_store':again,'all_checks_passed':True,'checks':checks,
             'empirical_database_modified':False,'historical_chain_validation_changed':False,
             'python':sys.version.split()[0],'libraries':{k:importlib.metadata.version(k) for k in ['numpy','pandas','matplotlib']}}
    write_json(ROOT/'results/execution_receipt.json',receipt)
    print(dumps({k:receipt[k] for k in ['simulation_id','scenario_count','model_count','new_chain_ids','tables']}),flush=True)
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=20261027);p.add_argument('--replications',type=int,default=100);a=p.parse_args()
    run(a.seed,a.replications)
