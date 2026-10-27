"""Independent read-only replay of preserved observations and missing-link math.

Does not import or call the simulation engine or its arithmetic helpers.
"""
from pathlib import Path
import hashlib,json,math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name):return pd.read_csv(ROOT/'data'/f'{name}.csv',dtype={'scenario_seed':'string','observed_cusip':'string'},float_precision='round_trip',low_memory=False)
ERRORS={};COUNTS={}
def close(name,actual,expected,atol=.01):
    a=np.asarray(actual,dtype=float);b=np.asarray(expected,dtype=float)
    error=float(np.max(np.abs(a-b))) if a.size else 0.
    ERRORS[name]=max(ERRORS.get(name,0.),error);COUNTS[name]=COUNTS.get(name,0)+int(a.size)
    assert np.all(np.isfinite(a)) and np.all(np.isfinite(b)) and np.allclose(a,b,atol=atol,rtol=1e-12),(name,error)

def main():
    ERRORS.clear();COUNTS.clear()
    receipt=json.loads((ROOT/'results/execution_receipt.json').read_text());sid=receipt['simulation_id']
    plan=json.loads((ROOT/'config/resolved_plan.json').read_text());cfg=plan['config']
    assert sha(ROOT/'src/gap_models.py')==plan['engine_sha256']
    manifest=json.loads((ROOT/'inputs/observed_source_manifest.json').read_text())
    for r in manifest:
        assert sha(ROOT/r['frozen_path'])==r['sha256']==plan['source_sha256'][r['file']]
        original=Path(r['source_path'])
        if original.exists():assert sha(original)==r['sha256']
        assert r['generation_permitted'] is False
    f={name:load(name) for name in receipt['tables']}
    for name,frame in f.items():
        assert len(frame)==receipt['tables'][name] and sha(ROOT/'data'/f'{name}.csv')==receipt['csv_sha256'][name]
        assert frame.simulation_id.eq(sid).all() and frame.observed_fields_regenerated.eq(False).all()
        assert frame.empirical_validation.eq(False).all()
    runs=f['gap_runs'].set_index(['scenario_id','replicate_id'])
    specs={r['scenario_id']:r for r in json.loads((ROOT/'results/scenario_definitions.json').read_text())}
    # Read the frozen real source, not a generated source-selector output.
    obs=pd.read_csv(ROOT/'inputs/observed/treasury_auction_observations.csv',dtype={'cusip':'string'},keep_default_na=False)
    obs=obs[pd.to_datetime(obs.issue_date).dt.to_period('M').astype(str).eq(cfg['auction_source_month'])].sort_values(['issue_date','auction_date','cusip'],kind='stable').reset_index(drop=True)
    assert len(obs)==37
    lots=f['auction_lots'];reference=obs.iloc[lots.source_row_index.to_numpy()]
    for a,b in [('observed_cusip','cusip'),('observed_auction_date','auction_date'),('observed_issue_date','issue_date')]:
        assert np.array_equal(lots[a].astype(str).to_numpy(),reference[b].astype(str).to_numpy()),a
    close('auction:observed_offered_exact',lots.observed_offered_amount_usd,reference.offered_amount_usd.to_numpy(),atol=0)
    close('auction:conditional_obligation',lots.conditional_obligation_usd,lots.observed_offered_amount_usd*lots.assumed_effective_eligible_participation_of_offered*lots.assumed_net_obligation_fraction)
    lots_by_key={key:g for key,g in lots.groupby(['scenario_id','replicate_id'],sort=False)}
    actual_daily=obs.assign(offered_amount_usd=pd.to_numeric(obs.offered_amount_usd)).groupby('issue_date').offered_amount_usd.sum()
    for key,g in f['auction_trace'].groupby(['scenario_id','replicate_id'],sort=False):
        g=g.sort_values('day_index');role=specs[key[0]]['role'];r=runs.loc[key];lot=lots_by_key[key]
        assert len(lot)==37 and list(lot.source_row_index)==list(range(37))
        due_by_date=lot.groupby('observed_issue_date').conditional_obligation_usd.sum()
        due=np.array([float(due_by_date.get(date,0)) for date in g.date]);total=math.fsum(lot.conditional_obligation_usd)
        stressed=role in ['stress','mitigation','sensitivity']
        fraction=cfg['auction_sensitivity_funding_fraction'] if role=='sensitivity' else cfg['auction_stress_funding_fraction'] if stressed else cfg['auction_baseline_funding_fraction']
        delay=cfg['auction_sensitivity_cash_delay_days'] if role=='sensitivity' else cfg['auction_stress_cash_delay_days'] if stressed else 0
        extra=cfg['auction_mitigation_added_cash_fraction']*total if role=='mitigation' else 0.
        cash=total*(cfg['auction_stress_opening_fraction'] if stressed else cfg['auction_baseline_opening_fraction'])+extra
        initial_cash=cash;prior=paid_total=due_total=peak=0.;paid=[];funds=[];closes=[];unpaid=[]
        for i,d in enumerate(due):
            received=due[i-delay]*fraction if i>=delay else 0.;payment=min(cash+received,prior+d)
            cash+=received-payment;prior+=d-payment;paid_total+=payment;due_total+=d;peak=max(peak,prior)
            paid.append(payment);funds.append(received);closes.append(cash);unpaid.append(prior)
        close('auction:observed_daily',g.observed_daily_offered_usd,[float(actual_daily.get(date,0)) for date in g.date],atol=0)
        for field,expected in [('new_conditional_obligation_usd',due),('funding_received_usd',funds),('paid_usd',paid),('closing_cash_usd',closes),('unpaid_usd',unpaid)]:close('auction:'+field,g[field],expected)
        for field,expected in [('primary_value',peak/1e6),('peak_unpaid_usd',peak),('terminal_unpaid_usd',prior),('terminal_cash_usd',cash),('total_paid_usd',paid_total),('total_conditional_obligations_usd',due_total),('opening_cash_usd',initial_cash)]:close('auction:run_'+field,r[field],expected)
    financial=pd.read_csv(ROOT/'inputs/observed/financial_guarantee_reconciliation.csv')
    broad=float(financial[financial.entity.eq('MBSD')].sort_values('quarter').iloc[-1].chosen_usd)
    assert broad==562_000_000_000
    for key,g in f['tba_trace'].groupby(['scenario_id','replicate_id'],sort=False):
        g=g.sort_values('day_index');r=runs.loc[key];role=specs[key[0]]['role'];w=g.maturity_fraction.to_numpy();share=float(r.assumed_tba_share)
        assert cfg['tba_share_low']<=share<=cfg['tba_share_high'] and len(g)==cfg['tba_horizon_days']
        assert g.observed_broad_mbsd_stock_usd.eq(broad).all() and r.observed_broad_mbsd_stock_usd==broad
        close('tba:maturity_mass',math.fsum(w),1.,atol=1e-12)
        initial=broad*share;duration=cfg['tba_sensitivity_stress_days'] if role=='sensitivity' else cfg['tba_mitigation_stress_days'] if role=='mitigation' else cfg['tba_stress_days'] if role=='stress' else 0
        fraction=cfg['tba_sensitivity_deferral_fraction'] if role=='sensitivity' else cfg['tba_stress_deferral_fraction']
        prior=settled_total=peak=0.;settled=[];overdue=[];closing=[];newdue=[];unmatured=[]
        for i,weight in enumerate(w):
            due=initial*weight;defer=fraction if i<duration else 0.;payment=(prior+due)*(1-defer)
            prior+=due-payment;settled_total+=payment;peak=max(peak,prior)
            settled.append(payment);overdue.append(prior);closing.append(initial-settled_total);newdue.append(due);unmatured.append(initial*math.fsum(w[i+1:]))
        for field,expected in [('settled_usd',settled),('overdue_usd',overdue),('closing_assumed_tba_stock_usd',closing),('new_due_usd',newdue),('unmatured_usd',unmatured)]:close('tba:'+field,g[field],expected)
        for field,expected in [('primary_value',peak/initial),('peak_overdue_usd',peak),('terminal_overdue_usd',prior),('total_settled_usd',settled_total),('terminal_assumed_tba_stock_usd',initial-settled_total)]:close('tba:run_'+field,r[field],expected)
        close('tba:partition',g.closing_assumed_tba_stock_usd,g.overdue_usd+g.unmatured_usd)
    fields=pd.read_csv(ROOT/'inputs/observed/new_pqd_fields.csv');actual=fields[fields.entity.eq('NSCC')].sort_values('quarter').iloc[-1]
    evidence=pd.read_csv(ROOT/'inputs/observed/new_pqd_cell_evidence.csv');ev=evidence[evidence.entity.eq('NSCC')&evidence.quarter.eq(actual.quarter)&evidence.reference.eq('18.2.2')]
    avg=float(ev[ev.dimension.eq('AverageInQuarter')].iloc[0].value);peak=float(ev[ev.dimension.eq('PeakInQuarter')].iloc[0].value);im=float(actual.top5_im_share)
    assert avg==float(actual.top5_position_share) and avg==.3649 and peak==.4025
    for key,g in f['concentration_members'].groupby(['scenario_id','replicate_id'],sort=False):
        g=g.sort_values('synthetic_rank');r=runs.loc[key];role=specs[key[0]]['role'];s=g.assumed_member_share.to_numpy()
        assert len(g)==cfg['concentration_assumed_members']==25
        assert g.observed_top5_average_share.eq(avg).all() and g.observed_top5_peak_share.eq(peak).all() and g.observed_top5_im_average_share.eq(im).all()
        close('concentration:total_mass',math.fsum(s),1.,atol=1e-12);close('concentration:actual_top5_mass',math.fsum(s[:5]),avg,atol=1e-12)
        assert s[4]+1e-12>=max(s[5:]) and (np.diff(s[:5])<=1e-12).all()
        exposure=s*cfg['concentration_normalized_total'];threshold=cfg['concentration_sensitivity_threshold_units'] if role=='sensitivity' else cfg['concentration_addon_threshold_units']
        addon=np.maximum(exposure-threshold,0)*cfg['concentration_addon_rate']
        close('concentration:normalized_exposure',g.normalized_exposure_units,exposure,atol=1e-10)
        close('concentration:addon',g.hypothetical_addon_units,addon,atol=1e-10)
        close('concentration:primary_value',r.primary_value,math.fsum(addon),atol=1e-10)
        close('concentration:reported_generated_top5',r.generated_top5_share,avg,atol=1e-12)
        assert r.primary_units=='normalized exposure units; total=100, not USD'
    result={'passed':True,'simulation_id':sid,'method':'Independent source-column comparison and saved-input arithmetic replay; no engine import or function calls.',
            'source_hashes_verified':len(manifest),'observed_fields_regenerated':False,
            'auction_observed_source_lots':len(obs),'auction_copied_lot_rows_verified':len(lots),
            'observed_broad_mbsd_usd':broad,'observed_nscc_top5_average':avg,'observed_nscc_top5_peak':peak,'observed_nscc_top5_im_average':im,
            'scenario_runs_replayed':len(runs),'all_3_model_primary_values_replayed':True,
            'numeric_comparisons':sum(COUNTS.values()),'max_absolute_residuals_by_field':ERRORS,
            'claim_limit':'Observed source preservation and conditional missing-link arithmetic only; no empirical chain validation or actual member allocation inferred.'}
    path=ROOT/'results/independent_source_audit.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='max_absolute_residuals_by_field'},indent=2));return result

if __name__=='__main__':main()
