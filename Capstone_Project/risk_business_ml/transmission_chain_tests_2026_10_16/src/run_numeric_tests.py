from pathlib import Path
import pandas as pd,numpy as np,json,hashlib
from scipy.stats import spearmanr,rankdata
import statsmodels.api as sm
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT.parents[1]
PLAN=json.loads((ROOT/'analysis_plan.json').read_text());EVENTS=PLAN['events'];RNG=20261016

def save(df,name,sub='results'):df.to_csv(ROOT/sub/name,index=False)
def qeflag(d):return d.weekday()<5 and (d+pd.offsets.BDay(3)).quarter!=d.quarter

def inputs():
 m=pd.read_csv(ROOT/'inputs/market_daily.csv',parse_dates=['observation_date'])
 m=m[m.observation_date<='2026-10-13'];assert not m.duplicated(['series_id','observation_date']).any()
 wide=m.pivot(index='observation_date',columns='series_id',values='value').sort_index()
 def ser(s):return wide[s].dropna()
 basis=(pd.concat([ser('SOFR'),ser('EFFR')],axis=1).dropna().eval('SOFR-EFFR'))*100
 flags=np.array([qeflag(d) for d in basis.index]);adj=[]
 for i,x in enumerate(basis):
  p=basis.iloc[max(0,i-252):i];f=flags[max(0,i-252):i]
  g=p.iloc[np.flatnonzero(f==flags[i])]
  adj.append(x-(g.median() if len(g)>=6 else p.median()) if len(p)>=126 else np.nan)
 sig={'ust10_abs_change':ser('DGS10').diff().abs()*100,'sofr_effr_adjusted':pd.Series(adj,index=basis.index),
      'baa_widen20':ser('BAA10Y').diff(20).clip(lower=0)*100,'vix':ser('VIXCLS'),
      'vix_jump':ser('VIXCLS')/ser('VIXCLS').shift(1).rolling(20,min_periods=20).mean()}
 # New official additions. CSV-form FRED preferred; table fallback parsed only from actual date-value rows.
 for sid in ['MORTGAGE30US','DCPF3M','DTB3']:
  p=ROOT/'data'/f'{sid}.csv'
  if not p.exists():p=ROOT/'raw'/f'{sid}.csv'
  if p.exists():
   f=pd.read_csv(p);dc=next(c for c in f.columns if c.lower() in ['date','observation_date']);f[dc]=pd.to_datetime(f[dc]);f[sid]=pd.to_numeric(f[sid],errors='coerce');wide[sid]=f.set_index(dc)[sid].reindex(wide.index)
   if sid=='MORTGAGE30US':mort=f.set_index(dc)[sid].dropna().loc['2018-01-01':'2026-10-15']
 if 'mort' in locals():
  rates=ser('DGS10').rename('DGS10').reset_index().rename(columns={'observation_date':'yield_date'})
  a=pd.merge_asof(mort.rename('mortgage').reset_index().rename(columns={mort.index.name or 'index':'date'}).sort_values('date'),rates.sort_values('yield_date'),left_on='date',right_on='yield_date',direction='backward',tolerance=pd.Timedelta(days=3)).set_index('date')
  spread=(a.mortgage-a.DGS10)*100
  # Calendar-week changes only, never bridge missing mortgage weeks.
  prev=spread.index.to_period('W-THU').asi8;sig['mortgage_spread_change']=spread.diff().abs().where(np.r_[False,np.diff(prev)==1])
  save(a.assign(mortgage_treasury_spread_bp=spread),'mortgage_yield_alignment.csv','data')
 if all(c in wide for c in ['DCPF3M','DTB3']):sig['cp_bill_spread']=(wide.DCPF3M-wide.DTB3).dropna()*100
 files=sorted((ROOT/'raw').glob('cboe_*.csv'))
 if files:
  f=pd.concat([pd.read_csv(p) for p in files]);f['date']=pd.to_datetime(f.Day);assert not f.duplicated(['Day','Market Participant']).any()
  # Source contains market-center rows, not an extra national total row.
  assert not f['Market Participant'].str.contains('total|all markets',case=False).any()
  t=f.groupby('date')[['Total Shares','Total Trade Count']].sum().rename(columns={'Total Shares':'equity_volume','Total Trade Count':'trade_count'})
  t=t.loc['2018-01-01':'2026-10-15'];sig['equity_volume']=t.equity_volume;save(t.reset_index(),'cboe_equity_daily.csv','data')
 p=pd.read_csv(ROOT/'inputs/response_quarterly.csv')
 assert not p.duplicated(['quarter','entity']).any();p['period']=pd.PeriodIndex(p.quarter,freq='Q');p=p.sort_values(['entity','period'])
 p['vm_peak_qoq']=p.groupby('entity').vm_peak_usd.pct_change(fill_method=None)
 save(p.drop(columns='period'),'business_responses_used.csv','data')
 return {k:v.dropna().sort_index() for k,v in sig.items()},p

def event_test(signal,mode,events,key):
 s=signal.dropna();last=s.index.max()
 if mode=='weekly':
  w=s.resample('W-FRI').max();w=w[w.index<=pd.Timestamp('2026-10-15')];thr=w.shift(1).rolling(52,min_periods=26).quantile(.9)
  frame=pd.DataFrame({'date':w.index,'value':w.values,'threshold':thr.values});frame['alarm']=(frame.value>frame.threshold).astype(float).where(frame.threshold.notna()&frame.value.notna());frame['week_start']=frame.date-pd.Timedelta(days=4)
 else:
  thr=s.shift(1).rolling(252,min_periods=126).quantile(.9);frame=pd.DataFrame({'date':s.index,'value':s.values,'threshold':thr.values});frame['alarm']=(frame.value>frame.threshold).astype(float).where(frame.threshold.notna())
 details=[];excluded=np.zeros(len(frame),bool)
 for eid in events:
  a,b=map(pd.Timestamp,EVENTS[eid]);lo=a-pd.offsets.BDay(20);hi=b+pd.offsets.BDay(20)
  if mode=='weekly':
   excluded|=((frame.date>=lo)&(frame.week_start<=hi)).values
   ins=s.loc[a:b];records=[]
   for week,g in ins.groupby(ins.index.to_period('W-FRI')):
    end=week.end_time.normalize()
    if end not in thr.index or pd.isna(thr.loc[end]):continue
    records.append((g.max(),thr.loc[end],g.max()>thr.loc[end]))
   v=pd.DataFrame(records,columns=['value','threshold','alarm']);available=len(v);hit=bool(v.alarm.any()) if available else None;fraction=v.alarm.mean() if available else np.nan
  else:
   excluded|=frame.date.between(lo,hi).values;v=frame[frame.date.between(a,b)&frame.alarm.notna()];available=len(v);hit=bool(v.alarm.eq(1).any()) if available>=2 else None;fraction=v.alarm.mean() if available else np.nan
  details.append({'test_key':key,'mode':mode,'event':eid,'n_periods':available,'hit':hit,'alarm_fraction':fraction})
 valid=[d for d in details if d['hit'] is not None];hitfrac=np.mean([d['hit'] for d in valid]) if valid else np.nan
 quiet=frame.loc[~excluded,'alarm'].mean();med=np.median([d['alarm_fraction'] for d in valid]) if valid else np.nan
 passed=len(valid)>=2 and hitfrac>=2/3 and quiet<=.15 and (mode=='weekly' or med>=.25)
 save(frame,f'{key}_{mode}_alerts.csv','data')
 return {'test_key':key,'mode':mode,'events_hit':sum(d['hit'] for d in valid),'events_available':len(valid),'hit_fraction':hitfrac,'median_event_alarm_fraction':med,'non_event_alarm_proxy':quiet,'status':'PASS' if passed else ('FAIL' if len(valid)>=2 else 'INSUFFICIENT')},details

def rho(x,y):
 if len(x)<3 or len(np.unique(x))<2 or len(np.unique(y))<2:return np.nan
 return float(spearmanr(x,y).statistic)

def block_ci(x,y,periods,seed=RNG):
 n=len(x);o=np.array([p.ordinal for p in periods]);starts=[i for i in range(n-3) if np.all(np.diff(o[i:i+4])==1)]
 if n<12 or not starts:return np.nan,np.nan
 ids=(np.random.default_rng(seed).choice(starts,(2000,int(np.ceil(n/4))))[:,:,None]+np.arange(4)).reshape(2000,-1)[:,:n]
 a=rankdata(x[ids],axis=1);b=rankdata(y[ids],axis=1);a-=a.mean(axis=1,keepdims=True);b-=b.mean(axis=1,keepdims=True);den=np.sqrt((a*a).sum(axis=1)*(b*b).sum(axis=1));vals=np.divide((a*b).sum(axis=1),den,out=np.full(2000,np.nan),where=den>0)
 return np.nanquantile(vals,[.025,.975])

def quarter(s,weekly=False):
 d=pd.DataFrame({'value':s.values,'period':s.index.to_period('Q')});g=d.groupby('period').value.agg(['max','count']);g.loc[g['count']<(9 if weekly else 45),'max']=np.nan;return g['max']

def association(cid,signal,outcome,p,entity,lag=0,label='primary',weekly=False):
 x=quarter(signal,weekly);y=p[p.entity==entity].set_index('period')[outcome]
 # Shift by calendar quarters, not by surviving row position.
 x.index=x.index+lag;z=pd.concat([x.rename('x'),y.rename('y')],axis=1).loc[:'2026Q2'].dropna();a=z.x.to_numpy();b=z.y.to_numpy();r=rho(a,b);lo,hi=block_ci(a,b,z.index)
 diff=z.diff().where(z.index.to_series().diff().map(lambda d:getattr(d,'n',0)==1),axis=0).dropna()
 stat={'chain_id':cid,'label':label,'entity':entity,'outcome':outcome,'lag':lag,'n':len(z),'first_quarter':str(z.index.min()),'last_quarter':str(z.index.max()),'rho':r,'ci_low':lo,'ci_high':hi,'ordinary_p':float(spearmanr(a,b).pvalue) if np.isfinite(r) else np.nan,'diff_n':len(diff),'rho_changes':rho(diff.x.to_numpy(),diff.y.to_numpy()),'rho_earlier':rho(z.loc[:'2024Q4'].x.to_numpy(),z.loc[:'2024Q4'].y.to_numpy()),'rho_later':rho(z.loc['2025Q1':].x.to_numpy(),z.loc['2025Q1':].y.to_numpy()),'pass_card':bool(len(z)>=12 and r>=.3 and lo>0)}
 save(z.assign(quarter=z.index.astype(str)).reset_index(drop=True),cid+'_'+label+f'_lag{lag}_pairs.csv','data')
 return stat

def funding_hac(sig):
 frames=[]
 for sid in ['REPO-GCF_AR_OO-F','REPO-DVP_AR_OO-F']:
  p=ROOT/'raw'/f'{sid}.json'
  if not p.exists():return None
  d=pd.DataFrame(json.loads(p.read_text()),columns=['date',sid]);d.date=pd.to_datetime(d.date);frames.append(d.set_index('date'))
 f=pd.concat(frames,axis=1).join(sig.rename('signal'));f['outcome_bp']=(f['REPO-GCF_AR_OO-F']-f['REPO-DVP_AR_OO-F'])*100
 threshold=sig.shift(1).rolling(252,min_periods=126).quantile(.9);f=f.join(threshold.rename('threshold'));f['shock']=(f.signal>f.threshold).astype(int);f['month_end']=[int((d+pd.offsets.BDay()).month!=d.month) for d in f.index];f['quarter_end']=[int(qeflag(d)) for d in f.index]
 f=f.dropna(subset=['outcome_bp','signal','threshold']);model=sm.OLS(f.outcome_bp,sm.add_constant(f[['shock','month_end','quarter_end']])).fit(cov_type='HAC',cov_kwds={'maxlags':5})
 save(f.reset_index(),'funding_ofr_hac_pairs.csv','data');r={'chain_id':'FICC-GSD-02','outcome':'GCF-DVP overnight/open final-vintage rate spread bp','n':len(f),'shock_days':int(f.shock.sum()),'coefficient_bp':model.params['shock'],'hac_p':model.pvalues['shock'],'ci_low':model.conf_int().loc['shock',0],'ci_high':model.conf_int().loc['shock',1],'r_squared':model.rsquared,'pass_card':bool(model.params['shock']>0 and model.pvalues['shock']<.05),'first':str(f.index.min().date()),'last':str(f.index.max().date())};(ROOT/'results/ofr_funding_hac.json').write_text(json.dumps(r,indent=2)+'\n');return r

def run():
 sig,p=inputs();events=[];detail=[]
 configs=[('FICC-GSD-01','ust10_abs_change','weekly',['covid_2020','svb_2023','treasury_2025']),('FICC-GSD-02','sofr_effr_adjusted','weekly',['repo_2019','covid_2020','treasury_2025']),('FICC-GSD-04','baa_widen20','weekly',['covid_2020','svb_2023']),('FICC-MBSD-01','mortgage_spread_change','weekly',['covid_2020','rates_2022H2','treasury_2025']),('ECS-R1','vix','daily',['covid_2020','meme_2021','vol_2024','treasury_2025']),('ECS-NSCC-03A','baa_widen20','weekly',['covid_2020','svb_2023']),('ECS-NSCC-03B','sofr_effr_adjusted','weekly',['repo_2019','covid_2020','svb_2023','treasury_2025']),('ECS-DTC-04','cp_bill_spread','weekly',['covid_2020','svb_2023']),('ECS-R2','equity_volume','daily',['covid_2020','meme_2021','vol_2024','treasury_2025'])]
 for cid,ind,mode,evs in configs:
  if ind not in sig:continue
  r,d=event_test(sig[ind],mode,evs,cid);events.append(r);detail+=d
 for cid,ind,mode,evs in [('ECS-R1-legacy-events','vix','daily',['covid_2020','svb_2023','treasury_2025']),('ECS-R1-vix-jump-secondary','vix_jump','daily',['covid_2020','svb_2023','treasury_2025']),('ECS-03B-daily-secondary','sofr_effr_adjusted','daily',['repo_2019','covid_2020','svb_2023','treasury_2025'])]:
  r,d=event_test(sig[ind],mode,evs,cid);events.append(r);detail+=d
 save(pd.DataFrame(events),'event_test_summary.csv');save(pd.DataFrame(detail),'event_test_details.csv')
 tests=[('FICC-GSD-01','ust10_abs_change','im_qoq','GSD',False),('ECS-NSCC-01A','vix','im_call_to_prior_im','NSCC',False),('ECS-NSCC-01B','vix','vm_peak_to_avg','NSCC',False),('ECS-NSCC-01C','vix','backtest_breaches','NSCC',False),('ECS-NSCC-03B','sofr_effr_adjusted','im_call_to_im','NSCC',False)]
 if 'mortgage_spread_change' in sig:tests.append(('FICC-MBSD-01','mortgage_spread_change','vm_peak_qoq','MBSD',True))
 res=[association(cid,sig[ind],out,p,e,label='primary',weekly=w) for cid,ind,out,e,w in tests]
 # Keep primary-card denominator and zero lag; variants never replace these rows.
 for cid,ind,out,e,w in tests:res.append(association(cid,sig[ind],out,p,e,lag=1,label='secondary_next_quarter',weekly=w))
 for cid,ind,out in [('ECS-NSCC-01A','vix','im_call_to_im'),('ECS-NSCC-01B','vix_jump','vm_peak_to_avg'),('ECS-NSCC-03B','sofr_effr_adjusted','vm_peak_to_avg')]:
  for lag in [0,1]:res.append(association(cid,sig[ind],out,p,'NSCC',lag=lag,label='secondary_changed_definition'))
 df=pd.DataFrame(res);df['bh_q_primary']=np.nan;ix=df.index[df.label=='primary'];pv=df.loc[ix,'ordinary_p'];order=pv.sort_values().index;adj=(df.loc[order,'ordinary_p']*len(order)/np.arange(1,len(order)+1)).iloc[::-1].cummin().iloc[::-1].clip(upper=1);df.loc[order,'bh_q_primary']=adj
 save(df,'quarterly_test_results.csv');fund=funding_hac(sig['sofr_effr_adjusted'])
 # Descriptive Sponsored before/after using the already-collected source, without event attribution.
 f=pd.read_csv(ROOT/'inputs/ficc_daily_operations_history.csv',parse_dates=['date']);s=f[(f.source_id=='ficc_sponsoredvolume')&(f.metric=='TOTAL_AMOUNT')].dropna(subset=['value']).set_index('date').value.sort_index();v=[]
 for d in ['2023-12-13','2025-02-25']:
  a=s[s.index<pd.Timestamp(d)].tail(20);b=s[s.index>pd.Timestamp(d)].head(20);v.append({'node':d,'before_n':len(a),'after_n':len(b),'before_mean_usd':a.mean(),'after_mean_usd':b.mean(),'change_pct':(b.mean()/a.mean()-1)*100,'interpretation':'observed change only; no causal attribution to rule announcement'})
 save(pd.DataFrame(v),'sponsored_node_descriptives.csv')
 manifest={'run_date':'2026-10-16','framework':'S*V with chain applicability gate; no E multiplier','signal_ranges':{k:{'n':len(s),'first':str(s.index.min().date()),'last':str(s.index.max().date())} for k,s in sig.items()},'new_numeric_tests_primary':len(tests)+(fund is not None),'no_blind_holdout':True,'input_hashes':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [ROOT/'inputs/market_daily.csv',ROOT/'inputs/response_quarterly.csv',ROOT/'analysis_plan.json',ROOT/'plan_availability_amendment.json']}}
 (ROOT/'run_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(df[df.label=='primary'].round(4).to_string(index=False));print('EVENTS',pd.DataFrame(events).round(4).to_string(index=False));print('OFR',fund)
 return sig,p
if __name__=='__main__':run()
