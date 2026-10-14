from pathlib import Path
import json
import warnings
import numpy as np
import pandas as pd
from scipy.stats import rankdata,spearmanr

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data';RESULTS=ROOT/'results'
PRIMARY={
 'business_continuity':'fema_major_declarations', 'cybersecurity':'kev_new_entries',
 'information_technology':'cloud_infrastructure_incidents', 'data_management':'cloud_data_service_incidents',
 'processing_operations':'clearing_core_failures_12m', 'clearing_financial':'funding_basis_max_bps',
 'corporate_financial':'treasury_bill_yield_volatility', 'model_risk':'margin_backtest_uncovered_pct',
 'legal_regulatory':'financial_regulator_final_rules', 'third_party':'workspace_provider_incidents',
 'human_capital':'finance_sector_quit_rate', 'strategic':'economic_policy_uncertainty',
}
SEED=20261005

def correlation(x,y):
    ok=np.isfinite(x)&np.isfinite(y)
    if ok.sum()<8 or np.std(x[ok])<1e-12 or np.std(y[ok])<1e-12:return np.nan
    return float(np.corrcoef(x[ok],y[ok])[0,1])

def block_bootstrap_spearman(x,y,rng,n_boot=2000):
    n=len(x)
    starts=rng.integers(0,n,size=(n_boot,int(np.ceil(n/4))))
    idx=((starts[:,:,None]+np.arange(4))%n).reshape(n_boot,-1)[:,:n]
    bx,by=x[idx],y[idx]
    ok=np.isfinite(bx)&np.isfinite(by);count=ok.sum(axis=1)
    rx=rankdata(np.where(ok,bx,np.nan),axis=1,nan_policy='omit')
    ry=rankdata(np.where(ok,by,np.nan),axis=1,nan_policy='omit')
    mx=np.nansum(rx,axis=1)/np.maximum(count,1);my=np.nansum(ry,axis=1)/np.maximum(count,1)
    dx=np.where(ok,rx-mx[:,None],0);dy=np.where(ok,ry-my[:,None],0)
    denominator=np.sqrt((dx*dx).sum(axis=1)*(dy*dy).sum(axis=1))
    out=np.divide((dx*dy).sum(axis=1),denominator,out=np.full(n_boot,np.nan),where=denominator>1e-12)
    out[count<8]=np.nan
    if np.isfinite(out).mean()<.8:return np.nan,np.nan,float(np.isfinite(out).mean())
    lo,hi=np.nanquantile(out,[.025,.975])
    return float(lo),float(hi),float(np.isfinite(out).mean())

def shift_p(x,y,rho):
    references=[]
    for shift in range(1,len(x)):
        sx=np.roll(x,shift);ok=np.isfinite(sx)&np.isfinite(y)
        if ok.sum()>=8 and np.std(sx[ok])>0 and np.std(y[ok])>0:
            references.append(abs(float(spearmanr(sx[ok],y[ok]).statistic)))
    if not references:return np.nan
    return (1+sum(v>=abs(rho)-1e-12 for v in references))/(len(references)+1)

def partial_spearman(frame):
    d=frame.dropna(subset=['risk_value','target'])
    if len(d)<12:return np.nan
    periods=d.index
    controls=np.column_stack([np.ones(len(d)),periods.asi8,
                             (periods.quarter==2).astype(float),(periods.quarter==3).astype(float),(periods.quarter==4).astype(float)])
    values=rankdata(d[['risk_value','target']].to_numpy(),axis=0)
    residual=values-controls@np.linalg.lstsq(controls,values,rcond=None)[0]
    return correlation(residual[:,0],residual[:,1])

def bh_adjust(pvalues):
    p=np.asarray(pvalues,dtype=float);q=np.full(len(p),np.nan);valid=np.isfinite(p)
    values=p[valid];order=np.argsort(values)
    adjusted=np.minimum.accumulate((values[order]*len(values)/np.arange(1,len(values)+1))[::-1])[::-1].clip(0,1)
    reordered=np.empty(len(values));reordered[order]=adjusted;q[valid]=reordered
    return q

def build_panel():
    business=pd.read_csv(DATA/'legacy_analysis_panel.csv')
    obs=pd.read_csv(DATA/'expanded_risk_observations.csv')
    defs=pd.read_csv(DATA/'expanded_risk_dictionary.csv')
    rows=[]
    full=pd.period_range('2019Q1','2026Q2',freq='Q')
    for (entity,metric),business_group in business.groupby(['entity','metric']):
        y=business_group.set_index(pd.PeriodIndex(business_group.quarter,freq='Q')).target.reindex(full)
        for definition in defs.itertuples():
            scope=definition.entity_scope
            applies=scope=='ALL' or scope==entity or (scope=='CLEARING' and (entity=='NSCC' or entity.startswith('FICC')))
            if not applies:continue
            d=obs[(obs.feature==definition.feature)&(obs.entity_scope==scope)]
            values=d.set_index(pd.PeriodIndex(d.quarter,freq='Q')).value.reindex(full)
            for lag in [0,1]:
                frame=pd.DataFrame({'risk_value':values.shift(lag),'target':y},index=full)
                frame['quarter']=frame.index.astype(str)
                frame['risk_observation_quarter']=(frame.index-lag).astype(str)
                frame['entity']=entity;frame['metric']=metric;frame['risk_feature']=definition.feature
                frame['risk_entity_scope']=scope;frame['family']=definition.family;frame['lag_quarters']=lag
                frame['risk_label_zh']=definition.label_zh;frame['measurement_window']=definition.measurement_window
                frame['interpretation_limit']=definition.interpretation_limit
                rows.append(frame.reset_index(drop=True))
    panel=pd.concat(rows,ignore_index=True)
    panel.to_csv(DATA/'expanded_analysis_panel.csv',index=False)
    return panel

def run():
    panel=build_panel();rng=np.random.default_rng(SEED);result=[];attempts=[]
    keys=['entity','metric','risk_feature','risk_entity_scope','lag_quarters']
    for key,d in panel.groupby(keys,sort=True):
        entity,metric,feature,scope,lag=key
        d=d.set_index(pd.PeriodIndex(d.quarter,freq='Q')).sort_index()
        eligible=d.risk_value.notna()&d.target.notna();n=int(eligible.sum())
        if n<8:
            attempts.append(dict(zip(keys,key),n_quarters=n,status='insufficient_paired_quarters'));continue
        d=d.loc[eligible[eligible].index.min():eligible[eligible].index.max()]
        x=d.risk_value.to_numpy(float);y=d.target.to_numpy(float);ok=np.isfinite(x)&np.isfinite(y)
        if np.unique(x[ok]).size<3 or np.unique(y[ok]).size<3:
            attempts.append(dict(zip(keys,key),n_quarters=n,status='insufficient_variation'));continue
        rho=float(spearmanr(x[ok],y[ok]).statistic)
        lo,hi,valid_boot=block_bootstrap_spearman(x,y,rng)
        years=d.index.year;loyo=[]
        for year in sorted(set(years)):
            keep=ok&(years!=year)
            if keep.sum()>=8 and np.unique(x[keep]).size>=3:
                loyo.append(float(spearmanr(x[keep],y[keep]).statistic))
        row=dict(zip(keys,key),family=d.family.iloc[0],risk_label_zh=d.risk_label_zh.iloc[0],n_quarters=n,
                 first_business_quarter=str(d.index[ok][0]),last_business_quarter=str(d.index[ok][-1]),
                 spearman_rho=rho,pearson_r=correlation(x,y),spearman_block_ci_low=lo,spearman_block_ci_high=hi,
                 valid_bootstrap_fraction=valid_boot,season_trend_adjusted_spearman=partial_spearman(d),
                 circular_shift_p_exploratory=shift_p(x,y,rho),
                 leave_one_year_out_min_rho=min(loyo) if loyo else np.nan,
                 leave_one_year_out_max_rho=max(loyo) if loyo else np.nan,
                 leave_one_year_out_same_sign_fraction=np.mean(np.sign(loyo)==np.sign(rho)) if loyo else np.nan,
                 measurement_window=d.measurement_window.iloc[0],interpretation_limit=d.interpretation_limit.iloc[0],
                 causal_effect_estimated=False,point_in_time_forecast_claim=False)
        keep=ok&(years!=2020)
        row['excluding_2020_spearman']=float(spearmanr(x[keep],y[keep]).statistic) if keep.sum()>=8 and np.unique(x[keep]).size>=3 else np.nan
        # A separate change-based sensitivity for overlapping trailing-year snapshots.
        changed=d.risk_value.diff(4) if '12 months' in str(row['measurement_window']) else d.risk_value.diff()
        cm=changed.notna()&d.target.notna()
        row['change_sensitivity_n']=int(cm.sum())
        row['change_sensitivity_spearman']=float(spearmanr(changed[cm],d.target[cm]).statistic) if cm.sum()>=8 and changed[cm].nunique()>=3 else np.nan
        result.append(row);attempts.append(dict(zip(keys,key),n_quarters=n,status='estimated'))
    result=pd.DataFrame(result)
    result['fdr_q_exploratory']=bh_adjust(result.circular_shift_p_exploratory)
    result['passes_exploratory_fdr_5pct']=result.fdr_q_exploratory<.05
    result.to_csv(RESULTS/'expanded_risk_business_associations.csv',index=False)
    pd.DataFrame(attempts).to_csv(RESULTS/'association_attempts.csv',index=False)
    taxonomy=pd.read_csv(DATA/'risk_taxonomy.csv')
    overview=[]
    for family,label in taxonomy.itertuples(index=False,name=None):
        feature=PRIMARY[family]
        row={'family':family,'family_zh':label,'primary_feature':feature}
        for e in ['FICC','NSCC','DTC']:
            for lag in [0,1]:
                matching=result[(result.family==family)&(result.risk_feature==feature)&(result.entity==e)&
                                (result.metric=='revenue_growth_pct')&(result.lag_quarters==lag)]
                suffix=e+('_same_quarter' if lag==0 else '_next_quarter')
                row[suffix+'_rho']=matching.spearman_rho.iloc[0] if len(matching) else np.nan
                row[suffix+'_n']=int(matching.n_quarters.iloc[0]) if len(matching) else 0
                row[suffix+'_adjusted_rho']=matching.season_trend_adjusted_spearman.iloc[0] if len(matching) else np.nan
                row[suffix+'_fdr_q']=matching.fdr_q_exploratory.iloc[0] if len(matching) else np.nan
        overview.append(row)
    matrix=pd.DataFrame(overview)
    matrix.to_csv(RESULTS/'twelve_family_revenue_association_matrix.csv',index=False)
    # Comparable-calendar sensitivity, fixed across all available primary families.
    common=pd.period_range('2020Q1','2026Q2',freq='Q')
    series_map={};valid_calendar=pd.Series(True,index=common)
    for e in ['FICC','NSCC','DTC']:
        for family,feature in PRIMARY.items():
            d=panel[(panel.entity==e)&(panel.metric=='revenue_growth_pct')&(panel.family==family)&
                    (panel.risk_feature==feature)&(panel.lag_quarters==0)]
            if not len(d):continue
            d=d.set_index(pd.PeriodIndex(d.quarter,freq='Q')).reindex(common)
            series_map[(e,family)]=d
            valid_calendar &= d[['risk_value','target']].notna().all(axis=1)
    common_quarters=common[valid_calendar]
    comparable=[]
    for family,label in taxonomy.itertuples(index=False,name=None):
        row={'family':family,'family_zh':label}
        for e in ['FICC','NSCC','DTC']:
            if (e,family) in series_map:
                d=series_map[(e,family)].loc[common_quarters]
                row[e+'_rho']=float(spearmanr(d.risk_value,d.target).statistic) if len(d)>=8 and d.risk_value.nunique()>=3 else np.nan
                row[e+'_n']=len(d)
            else:row[e+'_rho']=np.nan;row[e+'_n']=0
        comparable.append(row)
    pd.DataFrame(comparable).to_csv(RESULTS/'common_calendar_revenue_associations.csv',index=False)
    (RESULTS/'common_calendar_quarters.json').write_text(json.dumps(common_quarters.astype(str).tolist(),indent=2))
    summary={'risk_families_with_collected_data':len(taxonomy),'distinct_risk_features':panel.risk_feature.nunique(),
             'risk_observations':len(pd.read_csv(DATA/'expanded_risk_observations.csv')),
             'business_target_series':len(panel[['entity','metric']].drop_duplicates()),
             'same_and_lagged_associations_estimated':len(result),'attempts':len(attempts),
             'passing_exploratory_fdr_5pct':int(result.passes_exploratory_fdr_5pct.sum()),
             'FICC_families_with_primary_revenue_association':int(matrix.FICC_same_quarter_rho.notna().sum()),
             'NSCC_families_with_primary_revenue_association':int(matrix.NSCC_same_quarter_rho.notna().sum()),
             'DTC_families_with_primary_revenue_association':int(matrix.DTC_same_quarter_rho.notna().sum()),
             'baseline_risk_features':6,'baseline_risk_families':3,
             'method':'Calendar-aligned same-quarter and lag-one Spearman/Pearson; 2000 paired four-quarter block bootstrap; season/trend adjustment; leave-one-year-out; change sensitivity; circular-shift reference and BH FDR.',
             'minimum_paired_quarters':8,'limited_sample_threshold':12,'causal_claim':False,'calibrated_risk_score':False,
             'ECS_mapping':'Separate NSCC clearing-side and DTC settlement-side legal entity proxies; no synthetic ECS revenue or pooled correlation.',
             'primary_features_preselected_by_family':PRIMARY,'bootstrap_seed':SEED}
    summary['common_calendar_quarters']=common_quarters.astype(str).tolist()
    (RESULTS/'expanded_analysis_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print(matrix[['family_zh','FICC_same_quarter_rho','FICC_same_quarter_n','NSCC_same_quarter_rho','NSCC_same_quarter_n','DTC_same_quarter_rho','DTC_same_quarter_n']].round(3).to_string(index=False))
    return result,matrix,summary

if __name__=='__main__':run()
