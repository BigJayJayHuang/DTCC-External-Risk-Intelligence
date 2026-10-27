"""Independent saved-output arithmetic, provenance and isolation checks."""
from pathlib import Path
import hashlib,json,sqlite3
import numpy as np
import pandas as pd
from run_simulations import protected_checks,write_json

ROOT=Path(__file__).resolve().parents[1]
def load(name):return pd.read_csv(ROOT/'data'/f'{name}.csv',dtype={'scenario_seed':'string'},float_precision='round_trip')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    receipt=json.loads((ROOT/'results/execution_receipt.json').read_text());plan=json.loads((ROOT/'config/resolved_plan.json').read_text())
    for name,h in plan['engine_hashes'].items():assert sha(ROOT/'src'/f'{name}.py')==h
    assert sha(ROOT/'src/run_simulations.py')==plan['runner_sha256']
    for name,h in receipt['csv_sha256'].items():assert sha(ROOT/'data'/f'{name}.csv')==h
    for name,n in receipt['tables'].items():
        f=load(name);assert len(f)==n
        assert f.source_type.eq('synthetic').all() and f.empirical_validation.eq(False).all()
        assert f.simulation_id.eq(receipt['simulation_id']).all()
        assert f.scenario_seed.notna().all()
    events=load('dtc_events');runs=load('dtc_runs');inputs=load('dtc_inputs')
    ledger=events.initial_cash_usd_million+events.cumulative_cash_funding_usd_million+events.net_debit_usd_million-events.initial_debit_usd_million-events.settled_amount_usd_million-events.cash_balance_usd_million
    debit=events.initial_debit_usd_million+events.cumulative_new_debit_usd_million-events.cumulative_debit_repaid_usd_million-events.net_debit_usd_million
    queue=events.arrived_amount_usd_million-events.settled_amount_usd_million-events.pending_amount_usd_million
    maxima={name:float(x.abs().max()) for name,x in [('cash_ledger_usd_million',ledger),('debit_ledger_usd_million',debit),('queue_usd_million',queue)]}
    assert max(maxima.values())<1e-8
    assert np.allclose(events.eligible_collateral_usd_million,events.collateral_market_value_usd_million*(1-events.haircut),atol=1e-9,rtol=1e-12)
    admitted=events.loc[events.event_type.eq('settlement')]
    assert (admitted.net_debit_usd_million<=admitted.net_debit_cap_usd_million+1e-8).all()
    assert (admitted.net_debit_usd_million<=admitted.eligible_collateral_usd_million+1e-8).all()
    index=runs.set_index(['scenario_id','replicate_id']);area_errors=[]
    for key,group in events.groupby(['scenario_id','replicate_id'],sort=False):
        g=group.sort_values('event_index');t=g.time_minutes.to_numpy();q=g.pending_amount_usd_million.to_numpy()
        assert (np.diff(t)>=0).all()
        area=float((q[:-1]*np.diff(t)).sum())
        area_errors.append(abs(area-float(index.loc[key,'queue_area_usd_million_minutes'])))
    assert max(area_errors)<1e-6
    tx=inputs[inputs.input_type.eq('transaction')]
    for rep,g in tx.groupby('replicate_id'):
        baseline=g[g.scenario_id.eq('dtc_baseline')].sort_values('transaction_id')
        for _,case in g.groupby('scenario_id'):
            case=case.sort_values('transaction_id')
            assert np.array_equal(case[['time_minutes','amount_usd_million']].to_numpy(),baseline[['time_minutes','amount_usd_million']].to_numpy())
    for name in ['dtc','epn','tba']:
        frame=load(name+'_runs');sizes=frame.groupby('scenario_id').size()
        assert sizes.eq(plan['replications_per_scenario']).all()
        assert not frame.duplicated(['scenario_id','replicate_id']).any()
    metrics={'dtc':'eod_pending_amount_usd_million','epn':'overdue_order_fraction','tba':'peak_overdue_to_initial'}
    summary=pd.read_csv(ROOT/'results/scenario_summary.csv',float_precision='round_trip')
    for name,metric in metrics.items():
        frame=load(name+'_runs')
        for scenario,g in frame.groupby('scenario_id'):
            row=summary.loc[summary.scenario_id.eq(scenario)].iloc[0]
            assert row.metric==metric
            assert np.isclose(row['mean'],g[metric].mean(),rtol=1e-12,atol=1e-10)
    c=sqlite3.connect((ROOT/'data/synthetic_scenarios.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)
    try:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        n=c.execute('SELECT count(*) FROM simulation_records WHERE simulation_id=?',(receipt['simulation_id'],)).fetchone()[0]
        assert n==sum(receipt['tables'].values())==334757
        assert c.execute("SELECT count(*) FROM simulation_records WHERE json_extract(payload,'$.source_type')<>'synthetic' OR json_extract(payload,'$.empirical_validation')<>0").fetchone()[0]==0
        assert c.execute("SELECT count(*) FROM reference_anchors WHERE json_extract(payload,'$.source_type')='public_reference'").fetchone()[0]==1
        seed=c.execute('SELECT scenario_seed FROM synthetic_dtc_runs LIMIT 1').fetchone()[0]
        assert isinstance(seed,str) and seed==str(runs.iloc[0].scenario_seed)
        # Execute the maintained example queries through a read-only connection.
        buffer='';query_rows=[]
        for line in (ROOT/'src/query_synthetic.sql').read_text().splitlines(True):
            buffer+=line
            if sqlite3.complete_statement(buffer):query_rows.append(len(c.execute(buffer).fetchall()));buffer=''
        assert query_rows==[8,8,13],query_rows
    finally:c.close()
    protected=protected_checks();assert len(protected)==7 and all(x['passed'] for x in protected)
    independent=json.loads((ROOT/'results/independent_epn_tba_audit.json').read_text())
    # Independent replay script fails before writing this file on an assertion.
    statuses=pd.read_csv(ROOT/'results/chain_simulation_status.csv')
    assert len(statuses)==6 and not statuses.full_chain_validated.any()
    result={'simulation_id':receipt['simulation_id'],'source_and_engine_hashes':'passed','saved_csv_rows':sum(receipt['tables'].values()),'all_rows_labelled_synthetic':True,'dtc_independent_max_residuals':maxima,'dtc_admissions_checked':len(admitted),'dtc_queue_area_paths':len(area_errors),'dtc_queue_area_max_difference':max(area_errors),'paired_transaction_workloads':'identical within each replicate','scenario_summary_rows':len(summary),'read_only_query_results':query_rows,'sqlite_integrity':'ok','unsigned_seed_text_preserved':True,'idempotent_repeat_records':receipt['repeat_store']['changes'],'protected_empirical_artifacts':len(protected),'protected_empirical_artifacts_present':sum(x['original_present'] for x in protected),'original_empirical_status_changed':False,'independent_replay_receipt_sha256':sha(ROOT/'results/independent_epn_tba_audit.json'),'claim_limit':'Implementation/conservation/scenario checks only; no empirical chain validation or calibrated real-world probabilities.'}
    write_json(ROOT/'results/verification.json',result);print(json.dumps(result,indent=2))
    return result

if __name__=='__main__':main()
