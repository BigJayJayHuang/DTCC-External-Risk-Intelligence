from pathlib import Path
import pandas as pd,numpy as np,statsmodels.api as sm,json
ROOT=Path(__file__).resolve().parents[1]
def fit_volume_ftd():
 d=pd.read_csv(ROOT/'data/sec_ftd_daily.csv',parse_dates=['date'])
 logs=pd.read_csv(ROOT/'data/sec_ftd_file_coverage.csv').to_dict('records')
 issues=json.loads((ROOT/'results/ftd_quality_issues.json').read_text())
 v=pd.read_csv(ROOT/'data/cboe_equity_daily.csv',parse_dates=['date']).set_index('date').equity_volume
 threshold=v.shift(1).rolling(252,min_periods=126).quantile(.9);alarms=(v>threshold).astype(float).where(threshold.notna())
 a=pd.concat([v.rename('volume'),alarms.rename('shock')],axis=1);a['week']=a.index.to_period('W-FRI');x=a.groupby('week').agg(weekly_volume_max=('volume','max'),shock=('shock','max'),volume_days=('volume','count'));d['week']=d.date.dt.to_period('W-FRI');y=d.groupby('week').agg(outstanding_ftd_shares=('outstanding_ftd_shares','mean'),ftd_days=('date','count'))
 f=x.join(y);f=f[(f.volume_days>=3)&(f.ftd_days==f.volume_days)&(f.index.end_time.normalize()<=min(v.index.max(),d.date.max()))].dropna();f['month_end']=[int(p.start_time.month!=p.end_time.month or (p.end_time+pd.offsets.BDay()).month!=p.end_time.month) for p in f.index];f['quarter_end']=[int(p.start_time.quarter!=p.end_time.quarter or (p.end_time+pd.offsets.BDay()).quarter!=p.end_time.quarter) for p in f.index]
 # Regression uses the quarter-varying volume threshold. Outstanding stocks are averaged within a week, never summed as new fail flows.
 m=sm.OLS(f.outstanding_ftd_shares/1e6,sm.add_constant(f[['shock','month_end','quarter_end']])).fit(cov_type='HAC',cov_kwds={'maxlags':4})
 f.reset_index().to_csv(ROOT/'data/equity_volume_ftd_weekly_pairs.csv',index=False)
 r={'chain_id':'ECS-NSCC-02A','n_weeks':len(f),'shock_weeks':int(f.shock.sum()),'first_week':str(f.index.min()),'last_week':str(f.index.max()),'coefficient_million_outstanding_shares':float(m.params['shock']),'hac_p':float(m.pvalues['shock']),'ci_low':float(m.conf_int().loc['shock',0]),'ci_high':float(m.conf_int().loc['shock',1]),'pass_card':bool(m.params['shock']>0 and m.pvalues['shock']<.05),'interpretation':'association with outstanding fail balances, not a failure rate, causal effect or new fail flows','files':len(logs),'raw_security_day_rows':sum(x['records'] for x in logs),'daily_observations':len(d),'source_quality_flags':issues}
 (ROOT/'results/equity_volume_ftd_hac.json').write_text(json.dumps(r,indent=2)+'\n');return r
if __name__=='__main__':print(json.dumps(fit_volume_ftd(),indent=2))
