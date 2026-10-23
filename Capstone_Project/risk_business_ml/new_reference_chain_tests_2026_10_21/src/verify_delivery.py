"""Independent numerical checks, source integrity, bilingual coverage and notebook checks."""
from pathlib import Path
import json,re,hashlib,math
import numpy as np
import pandas as pd
import nbformat
ROOT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    checks={}
    manifest=json.loads((ROOT/'input_manifest.json').read_text())
    assert all(digest(ROOT/r['frozen_copy'])==r['sha256'] for r in manifest)
    # Check original workspace inputs too when present; frozen inputs still suffice offline.
    present=[r for r in manifest if Path(r['original_path']).exists()]
    assert all(digest(r['original_path'])==r['sha256'] for r in present)
    checks['frozen_input_hashes_verified']=len(manifest);checks['existing_original_sources_unchanged']=len(present)
    old=ROOT.parents[1]/'reports/transmission_chain_alignment_2026_10_21/.qa/source_hashes_before.json'
    if old.exists():
        baseline=json.loads(old.read_text());assert all(digest(p)==h for p,h in baseline.items());checks['legacy_source_hashes_unchanged']=len(baseline)
    cn=pd.read_csv(ROOT/'results/new_chain_status_CN.csv');en=pd.read_csv(ROOT/'results/new_chain_status_EN.csv')
    reference=json.loads((ROOT/'inputs/chain_registry_v3.json').read_text());updated=json.loads((ROOT/'chain_registry_v3_with_test_status.json').read_text())
    expected=reference['newly_added_chain_ids'];assert cn.chain_id.tolist()==en.chain_id.tolist()==expected
    assert len(cn)==len(en)==31 and cn.shape[1]==en.shape[1]
    assert not cn.full_chain_validated.any() and not en.full_chain_validated.any()
    assert not re.search(r'[\u3400-\u9fff]',(ROOT/'results/new_chain_status_EN.csv').read_text())
    assert updated['chains'][:25]==reference['chains'][:25]
    for k in ['mappings','legacy_status_CN','legacy_status_EN']:assert updated[k]==reference[k]
    checks.update(bilingual_rows=31,bilingual_columns=len(en.columns),legacy_25_definitions_preserved=True,legacy_22_mappings_preserved=True)
    result=pd.read_csv(ROOT/'results/association_results.csv')
    independent=[]
    for row in result.itertuples():
        if row.test_id=='GCF_FUNDING':continue
        pairs=pd.read_csv(ROOT/'data'/f'{row.test_id}_lag{row.lag}_pairs.csv')
        # pandas average ranks + NumPy Pearson, independent of SciPy's Spearman helper.
        r=float(np.corrcoef(pairs.x.rank(method='average'),pairs.y.rank(method='average'))[0,1])
        assert abs(r-row.rho)<1e-12,(row.test_id,r,row.rho)
        assert len(pairs)==row.n and not pairs.period.duplicated().any()
        independent.append(row.test_id+':lag'+str(row.lag))
    checks['independently_recomputed_rank_associations']=len(independent)
    f=pd.read_csv(ROOT/'data/GCF_FUNDING_pairs.csv')
    x=np.column_stack([np.ones(len(f)),f[['shock','month_end','quarter_end']].to_numpy()]);y=f.outcome_bp.to_numpy()
    beta=np.linalg.lstsq(x,y,rcond=None)[0];u=y-x@beta;z=x*u[:,None];meat=z.T@z
    for lag in range(1,6):
        gamma=z[lag:].T@z[:-lag];meat+=(1-lag/6)*(gamma+gamma.T)
    inv=np.linalg.inv(x.T@x);cov=inv@meat@inv;se=float(np.sqrt(cov[1,1]))
    row=result[result.test_id.eq('GCF_FUNDING')].iloc[0]
    assert abs(beta[1]-row.coefficient_bp)<1e-10
    assert abs(beta[1]-1.959963984540054*se-row.ci_low)<1e-9
    assert abs(beta[1]+1.959963984540054*se-row.ci_high)<1e-9
    checks['independent_numpy_OLS_and_manual_Newey_West_HAC5']='passed'
    a=result[result.role.eq('primary')].copy();p=a.ordinary_p.fillna(a.hac_p).to_numpy();order=np.argsort(p);adjusted=np.minimum.accumulate((p[order]*len(p)/np.arange(1,len(p)+1))[::-1])[::-1].clip(0,1)
    assert np.allclose(a.bh_q_primary.to_numpy()[order],adjusted,rtol=1e-12,atol=1e-14)
    checks['BH_primary_family_size']=len(a)
    # Directly recompute two recorded historical thresholds without importing run_tests.
    funding=pd.read_csv(ROOT/'data/funding_signal.csv',parse_dates=['date']).set_index('date').value
    weekly=funding.resample('W-FRI').max();date=pd.Timestamp('2019-09-20');prior=weekly.loc[weekly.index<date].tail(52)
    alert=pd.read_csv(ROOT/'data/FICC-GSD-05_event_alerts.csv',parse_dates=['date']).set_index('date')
    assert abs(prior.quantile(.9)-alert.loc[date,'threshold'])<1e-10
    vix=pd.read_csv(ROOT/'data/vix_signal.csv',parse_dates=['date']).set_index('date').value;date=pd.Timestamp('2020-03-09')
    daily=pd.read_csv(ROOT/'data/ECS-NSCC-05_event_alerts.csv',parse_dates=['date']).set_index('date')
    assert abs(vix.loc[vix.index<date].tail(252).quantile(.9)-daily.loc[date,'threshold'])<1e-10
    checks['independent_past_only_threshold_spot_checks']=2
    recon=pd.read_csv(ROOT/'data/financial_guarantee_reconciliation.csv')
    discrepant=recon[recon.pqd_as_reported.notna()&~recon.within_rounding_tolerance]
    assert len(discrepant)==8 and np.allclose(discrepant.financial_to_pqd_ratio,1000)
    activity=pd.read_csv(ROOT/'data/mbsd_cleared_notional_reconciliation.csv');repairs=activity[activity.conversion_factor.ne(1)]
    assert repairs.quarter.tolist()==['2021Q3','2022Q3']
    assert ((repairs.chosen_usd-repairs.independent_daily_mean_usd).abs()<=501000).all()
    assert (repairs.conversion_factor==1e6).all()
    checks.update(financial_scale_discrepancies_reconciled=8,activity_scale_cells_reconciled=2,activity_repair_exclusion_sensitivity_present=bool(result.role.eq('data_quality_sensitivity').any()))
    notebook=nbformat.read(ROOT/'New_Reference_Chain_Validation.ipynb',as_version=4);nbformat.validate(notebook)
    cells=[c for c in notebook.cells if c.cell_type=='code'];errors=[o for c in cells for o in c.outputs if o.output_type=='error']
    assert all(c.execution_count is not None for c in cells) and not errors
    images=[o for c in cells for o in c.outputs if 'image/png' in o.get('data',{})];assert len(images)==2
    checks.update(executed_notebook_code_cells=len(cells),notebook_errors=len(errors),embedded_figure_outputs=len(images))
    summary=json.loads((ROOT/'results/review_summary.json').read_text());assert summary['distinct_numerically_screened_chains']==10
    for lang in ['CN','EN']:
        text=(ROOT/f'Concise_Test_Summary_{lang}.md').read_text();assert all(cid in text for cid in expected)
        assert '0.879' in text and '0.414' in text and '0.865' in text
        assert '0.817' not in text and '0.108' not in text
    checks.update(complete_new_chain_validations=0,bilingual_summary_result_consistency='passed',claim_limit='31 evidence reviews;10 partial numerical views,4 case/condition reviews,17 unrun data gaps; no causal/predictive/calibrated-score claim')
    (ROOT/'results/delivery_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(checks,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
