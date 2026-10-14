"""Independent value, scope, evidence and executed-output checks."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
import nbformat

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data';RESULTS=ROOT/'results'

def validate():
    obs=pd.read_csv(DATA/'expanded_risk_observations.csv')
    defs=pd.read_csv(DATA/'expanded_risk_dictionary.csv')
    assoc=pd.read_csv(RESULTS/'expanded_risk_business_associations.csv')
    matrix=pd.read_csv(RESULTS/'twelve_family_revenue_association_matrix.csv')
    legacy=pd.read_csv(DATA/'legacy_analysis_panel.csv')
    checks={}
    assert len(obs)==572 and len(defs)==26 and defs.feature.nunique()==20 and defs.family.nunique()==12
    assert not obs.duplicated(['quarter','feature','entity_scope']).any()
    assert obs.value.notna().all() and np.isfinite(obs.value).all()
    assert (pd.PeriodIndex(obs.quarter,freq='Q')<=pd.Period('2026Q2')).all()
    checks['risk_observations_unique_finite_and_before_cutoff']=True
    assert matrix.FICC_same_quarter_rho.notna().sum()==12
    assert matrix.NSCC_same_quarter_rho.notna().sum()==12
    assert matrix.DTC_same_quarter_rho.notna().sum()==10
    assert not assoc[(assoc.entity=='DTC') & assoc.risk_feature.isin(['clearing_core_failures_12m','margin_backtest_uncovered_pct'])].shape[0]
    checks['DTC_clearing_only_metrics_not_borrowed']=True
    # Recalculate financial targets directly from income values, rather than
    # accepting the original transformed panel as the comparison oracle.
    finance=pd.read_csv(DATA/'business_quarterly_financials.csv')
    financial_differences=[]
    calendar=pd.period_range('2019Q1','2026Q2',freq='Q')
    for entity,g in finance.groupby('entity'):
        g=g.set_index(pd.PeriodIndex(g.quarter,freq='Q')).reindex(calendar)
        targets={'revenue_growth_pct':(g.revenue_usd/g.revenue_usd.shift(1)-1)*100,
                 'operating_margin_change_pp':(g.operating_income_usd/g.revenue_usd*100).diff(),
                 'net_margin_change_pp':(g.net_income_usd/g.revenue_usd*100).diff()}
        for metric,value in targets.items():
            old=legacy[(legacy.entity==entity)&(legacy.metric==metric)]
            old=old.set_index(pd.PeriodIndex(old.quarter,freq='Q')).target.reindex(calendar)
            assert np.array_equal(value.isna(),old.isna())
            financial_differences.extend(abs(value-old).dropna())
    assert max(financial_differences)<1e-10
    checks['financial_targets_max_absolute_difference']=max(financial_differences)
    # Rank with pandas and compute Pearson of the ranks with NumPy. This is
    # independent of the SciPy Spearman function in the analysis program.
    differences=[]; verified_pairs=0
    for row in matrix.itertuples():
        for entity in ['FICC','NSCC','DTC']:
            relevant=assoc[(assoc.entity==entity)&(assoc.metric=='revenue_growth_pct') &
                (assoc.risk_feature==row.primary_feature)]
            for result in relevant.itertuples():
                risk=obs[(obs.feature==row.primary_feature)&(obs.entity_scope==result.risk_entity_scope)]
                x=risk.set_index(pd.PeriodIndex(risk.quarter,freq='Q')).value.reindex(calendar).shift(result.lag_quarters)
                b=legacy[(legacy.entity==entity)&(legacy.metric=='revenue_growth_pct')]
                y=b.set_index(pd.PeriodIndex(b.quarter,freq='Q')).target.reindex(calendar)
                pairs=pd.DataFrame({'x':x,'y':y}).dropna()
                assert len(pairs)==result.n_quarters
                rho=np.corrcoef(pairs.x.rank(method='average'),pairs.y.rank(method='average'))[0,1]
                differences.append(abs(rho-result.spearman_rho));verified_pairs+=1
    assert max(differences)<1e-12
    checks['headline_same_and_lag_pairs_independently_verified']=verified_pairs
    checks['headline_correlations_max_absolute_difference']=max(differences)
    for name in ['spearman_rho','pearson_r','season_trend_adjusted_spearman','spearman_block_ci_low','spearman_block_ci_high']:
        assert assoc[name].dropna().between(-1.00000000001,1.00000000001).all()
    assert assoc.n_quarters.min()>=8 and len(assoc)==482
    assert not assoc.passes_exploratory_fdr_5pct.any()
    assert assoc.fdr_q_exploratory.dropna().between(0,1).all()
    assert not assoc.causal_effect_estimated.any() and not assoc.point_in_time_forecast_claim.any()
    checks['result_ranges_minimum_n_and_no_causal_claims']=True
    # Audit calendar shifting and preserve every missing risk / target row.
    panel=pd.read_csv(DATA/'expanded_analysis_panel.csv')
    actual=pd.PeriodIndex(panel.risk_observation_quarter,freq='Q')
    expected=pd.PeriodIndex(panel.quarter,freq='Q')-panel.lag_quarters.to_numpy()
    assert (actual==expected).all()
    assert panel[(panel.risk_feature=='kev_new_entries') & (panel.quarter<'2022Q1')].risk_value.isna().all()
    assert panel[panel.risk_feature.str.startswith('cloud_') & (panel.quarter<'2022Q1')].risk_value.isna().all()
    checks['lag_uses_calendar_and_early_history_not_imputed']=True
    bt=pd.read_csv(DATA/'backtest_coverage_reconciliation.csv')
    assert bt.difference_pp.abs().max()<=.05+1e-10
    model=obs[obs.feature=='margin_backtest_uncovered_pct']
    assert model.value.between(0,100).all()
    checks['backtest_coverage_max_rounding_difference_pp']=bt.difference_pp.abs().max()
    kev=pd.read_csv(DATA/'cisa_catalog_entries.csv')
    assert not kev.cveID.duplicated().any()
    fr=pd.read_csv(DATA/'financial_regulator_final_rules.csv')
    source=json.loads((ROOT/'raw/federal_register_rules_001.json').read_text())
    assert len(fr)==source['count']==517 and not fr.document_number.duplicated().any()
    checks['CISA_and_regulator_document_keys_unique']=True
    hashes=0
    manifest=json.loads((ROOT/'source_manifest.json').read_text())
    successful=[r for r in manifest if r['status']=='downloaded']
    for r in successful:
        assert hashlib.sha256((ROOT/r['file']).read_bytes()).hexdigest()==r['sha256']
        hashes+=1
    assert len(successful)==23
    checks['new_source_snapshots_hash_verified']=hashes
    reused=json.loads((ROOT/'reused_input_manifest.json').read_text())
    for record in reused['pqd_workbooks']+reused['preserved_inputs']:
        assert hashlib.sha256((ROOT/record['file']).read_bytes()).hexdigest()==record['sha256']
    assert len(reused['pqd_workbooks'])==22
    checks['PQD_workbooks_hash_verified']=len(reused['pqd_workbooks'])
    checks['preserved_input_files_hash_verified']=len(reused['preserved_inputs'])
    nb=nbformat.read(ROOT/'Twelve_Risk_Families_FICC_ECS.ipynb',as_version=4)
    nbformat.validate(nb)
    code=[c for c in nb.cells if c.cell_type=='code']
    assert [c.execution_count for c in code]==list(range(1,len(code)+1))
    errors=[o for c in code for o in c.outputs if o.output_type=='error']
    figures=[o for c in code for o in c.outputs if 'image/png' in o.get('data',{})]
    assert not errors and len(figures)==3
    assert len(list((RESULTS/'figures').glob('*.png')))==3
    checks['notebook_executed_code_cells']=len(code)
    checks['notebook_runtime_errors']=len(errors)
    checks['notebook_embedded_figures']=len(figures)
    # The prior project's seed files must still match the delivered frozen copies.
    mapping={'legacy_risk_quarterly.csv':'risk_quarterly.csv','legacy_analysis_panel.csv':'analysis_panel.csv',
             'business_quarterly_financials.csv':'business_quarterly_financials.csv',
             'business_quarterly_operations.csv':'business_quarterly_operations.csv','business_metric_provenance.csv':'business_metric_provenance.csv'}
    if (ROOT.parent/'data/analysis_panel.csv').exists():
        for destination,original in mapping.items():
            assert (DATA/destination).read_bytes()==(ROOT.parent/'data'/original).read_bytes()
        checks['original_inputs_preserved']=True
    else:
        checks['original_inputs_preserved']='Parent project unavailable; included snapshot hashes checked above.'
    checks['validated_at_utc']=datetime.now(timezone.utc).isoformat()
    checks['visual_review']='See visual_review.json for image inspection; no full browser/HTML review is claimed.'
    (RESULTS/'validation_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
    print(json.dumps(checks,ensure_ascii=False,indent=2))

if __name__=='__main__': validate()
