"""Saved-output, source, catalog, SQL and original-evidence checks.

Mechanism arithmetic is separately reconstructed by the three independent audits.
"""
from pathlib import Path
import json,math,re,sqlite3
import numpy as np
import pandas as pd
from run_expansion import ROOT,sha,protect,write_json

def load(name):return pd.read_csv(ROOT/'data'/f'{name}.csv',dtype={'scenario_seed':'string'},float_precision='round_trip',low_memory=False)

def main():
    receipt=json.loads((ROOT/'results/execution_receipt.json').read_text());sid=receipt['simulation_id']
    plan=json.loads((ROOT/'config/resolved_plan.json').read_text())
    for name,h in plan['engine_sha256'].items():assert sha(ROOT/'src'/f'{name}.py')==h
    assert sha(ROOT/'src/run_expansion.py')==plan['runner_sha256']
    assert sha(ROOT/'inputs/chain_registry_v3.json')==plan['registry_sha256']
    assert sha(ROOT/'inputs/source_register.json')==plan['source_register_sha256']
    for r in json.loads((ROOT/'inputs/source_register.json').read_text()):
        if r.get('local') and r.get('sha256'):assert sha(ROOT/r['local'])==r['sha256']
    frames={}
    for dataset,count in receipt['tables'].items():
        assert sha(ROOT/'data'/f'{dataset}.csv')==receipt['csv_sha256'][dataset]
        f=load(dataset);frames[dataset]=f
        assert len(f)==count
        assert f.source_type.eq('synthetic').all() and f.empirical_validation.eq(False).all()
        assert f.simulation_id.eq(sid).all() and f.assumption_version.eq(plan['assumption_version']).all()
        assert f.catalog_version.eq('expanded_v3').all()
        assert f.scenario_seed.map(lambda v:isinstance(v,str) and v.isdigit()).all()
    runs=pd.concat([f for n,f in frames.items() if n.endswith('_runs')],ignore_index=True)
    assert not runs.duplicated(['scenario_id','replicate_id']).any()
    assert runs.groupby('scenario_id').size().eq(plan['replications_per_scenario']).all()
    assert len(runs)==receipt['scenario_count']*plan['replications_per_scenario']
    assert runs.groupby(['model_id','replicate_id']).scenario_seed.nunique().eq(1).all()
    assert np.isfinite(runs.primary_value).all() and (runs.primary_value>=-1e-10).all()
    fractions=runs.primary_units.str.contains('fraction')
    assert runs.loc[fractions,'primary_value'].between(0,1).all()
    summary=pd.read_csv(ROOT/'results/scenario_summary.csv',float_precision='round_trip')
    assert len(summary)==runs.scenario_id.nunique()==receipt['scenario_count']
    mean_errors=[]
    for _,r in summary.iterrows():
        g=runs[runs.scenario_id.eq(r.scenario_id)];values=g.primary_value.tolist()
        expected=math.fsum(values)/len(values)
        mean_errors.append(abs(expected-r['mean']))
        assert math.isclose(expected,r['mean'],abs_tol=1e-10,rel_tol=1e-12)
        assert r.metric==g.primary_metric.iloc[0] and r.units==g.primary_units.iloc[0]
    comparisons=pd.read_csv(ROOT/'results/chain_outcome_comparisons.csv',float_precision='round_trip')
    assert comparisons.chain_id.nunique()==len(comparisons)==len(receipt['new_chain_ids'])
    for _,r in comparisons.iterrows():
        for role in ['baseline','stress','mitigation']:
            g=runs[runs.scenario_id.eq(r[role+'_scenario'])]
            # Some default-engine primary names are descriptive aliases.
            values=g[r.metric] if r.metric in g and g[r.metric].notna().all() else g.primary_value
            assert math.isclose(math.fsum(values)/len(values),r[role+'_mean'],abs_tol=1e-10,rel_tol=1e-12)
    coverage=pd.read_csv(ROOT/'results/chain_coverage_bilingual.csv')
    catalog=json.loads((ROOT/'inputs/chain_registry_v3.json').read_text())
    assert len(coverage)==coverage.chain_id.nunique()==len(catalog['chains'])==56
    assert set(coverage.chain_id)=={r['chain_id'] for r in catalog['chains']}
    assert not coverage.full_chain_validated.any() and not coverage.real_world_probability_calibrated.any()
    counts=json.loads((ROOT/'results/coverage_counts.json').read_text())
    assert counts['all_partial_mechanism_chain_ids']+counts['generic_context_only_chain_ids']+counts['not_simulated_chain_ids']==56
    assert counts['new_chain_ids']==len(receipt['new_chain_ids'])==20
    audits={}
    for name in ['margin','default','operations']:
        p=ROOT/'results'/f'independent_{name}_audit.json';audit=json.loads(p.read_text())
        assert sid in json.dumps(audit) and audit['passed'] is True,'Audit failed or belongs to a different batch'
        audits[name]={'sha256':sha(p),'receipt':str(p.relative_to(ROOT))}
    tests=json.loads((ROOT/'results/unit_tests.json').read_text());assert tests['passed'] and tests['failures']==tests['errors']==0
    c=sqlite3.connect((ROOT/'data/synthetic_scenarios.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)
    total=0
    try:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        for name,f in frames.items():
            n=c.execute('SELECT count(*) FROM synthetic_'+name+' WHERE simulation_id=?',(sid,)).fetchone()[0]
            assert n==len(f);total+=n
            assert c.execute('SELECT count(*) FROM synthetic_'+name+" WHERE source_type IS NOT 'synthetic' OR empirical_validation IS NOT 0").fetchone()[0]==0
            seed=c.execute('SELECT scenario_seed FROM synthetic_'+name+' WHERE simulation_id=? ORDER BY record_key LIMIT 1',(sid,)).fetchone()[0]
            assert isinstance(seed,str) and seed==str(f.iloc[0].scenario_seed)
        buffer='';query_rows=[]
        for line in (ROOT/'src/query_synthetic.sql').read_text().splitlines(True):
            buffer+=line
            if sqlite3.complete_statement(buffer):query_rows.append(len(c.execute(buffer).fetchall()));buffer=''
        assert query_rows==[31,5,5,35,12]
        try:c.execute('DELETE FROM batches')
        except sqlite3.OperationalError:pass
        else:raise AssertionError('Read-only write guard failed')
    finally:c.close()
    assert total==sum(receipt['tables'].values())==receipt['database_store']['records_in_batch']
    assert receipt['repeat_store']['changes']=={'new':0,'changed':0,'unchanged':total}
    protected=protect();assert all(r['passed'] for r in protected)
    links=[]
    for doc in list(ROOT.glob('*.md')):
        for dest in re.findall(r'\]\(([^)]+)\)',doc.read_text()):
            if '://' in dest or dest.startswith('#'):continue
            target=(doc.parent/dest.split('#')[0]).resolve()
            # This verification receipt is created at the end of the current pass.
            assert target.exists() or target==ROOT/'results/verification.json',(doc,dest)
            links.append((doc.name,dest))
    result={'passed':True,'simulation_id':sid,'source_and_engine_hashes':'passed','synthetic_records':total,
            'scenario_runs':len(runs),'scenarios':len(summary),'model_count':receipt['model_count'],
            'new_catalog_chain_ids':len(comparisons),'catalog_coverage_rows':len(coverage),
            'max_summary_mean_difference':max(mean_errors),'all_rows_labelled_synthetic':True,
            'independent_replays':audits,'unit_tests':tests,'sqlite_integrity':'ok','exact_seed_text':'passed',
            'read_only_queries_row_counts':query_rows,'read_only_write_rejected':True,'repeat_store':receipt['repeat_store']['changes'],
            'original_artifacts_checked':len(protected),'original_artifacts_present':sum(r['original_present'] for r in protected),
            'original_empirical_status_changed':False,'markdown_links_checked':len(links),
            'claim_limit':'Implementation and conditional scenario checks only; no empirical validation or calibrated probabilities.'}
    write_json(ROOT/'results/verification.json',result);print(json.dumps(result,indent=2));return result

if __name__=='__main__':main()
