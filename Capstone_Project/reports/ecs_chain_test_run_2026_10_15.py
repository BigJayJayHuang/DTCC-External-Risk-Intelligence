# ECS chain test run, Oct 15 2026: Test 1 / Test 2 + change-based trend check. Run: python3 reports/ecs_chain_test_run_2026_10_15.py
import sqlite3,json,numpy as np,pandas as pd
import os; R=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))+'/'
c=sqlite3.connect(R+'data_refresh_2026_10_14/shared_public_data.sqlite3')
mo=pd.read_sql('select series_id,observation_date d,payload from market_observations',c)
mo['v']=mo.payload.map(lambda p: json.loads(p).get('value') if p else None)
mo['v']=pd.to_numeric(mo.v,errors='coerce'); mo['d']=pd.to_datetime(mo.d)
s=mo.pivot_table(index='d',columns='series_id',values='v')
di=pd.read_csv(R+'risk_business_ml/event_vulnerability_tests_2026_10_06/data/daily_indicators_with_thresholds.csv',parse_dates=['date'])
ind={k:g.set_index('date').value for k,g in di.groupby('indicator')}
vix=s.VIXCLS.dropna()
ind['vix']=vix
ind['vix_5d_rise']=vix-vix.shift(5)              # alt: change, not level
ind['vix_vs_20d']=vix/vix.rolling(20).mean()     # alt: relative jump
EV=[('repo_2019','2019-09-16','2019-09-20',['funding']),('covid_2020','2020-03-09','2020-03-23',['funding','rates','credit','equity']),
    ('svb_2023','2023-03-08','2023-03-17',['funding','rates','credit','equity']),('treasury_2025','2025-04-02','2025-04-11',['funding','rates','credit','equity'])]
def test1(x,ch,train=True):
    x=x.dropna(); thr=x.shift(1).rolling(252,min_periods=126).quantile(.9); al=(x>thr)&thr.notna()
    out={}
    evmask=pd.Series(False,index=x.index)
    for i,a,b,chs in EV:
        a,b=pd.Timestamp(a),pd.Timestamp(b)
        g=pd.Timestamp(a)-pd.offsets.BDay(20); h=b+pd.offsets.BDay(20); evmask|=(x.index>=g)&(x.index<=h)
        if ch in chs: out[i]=round(al[(al.index>=a)&(al.index<=b)].mean(),2)
    tr=al[al.index<'2025-01-01']; ne=tr[~evmask.reindex(tr.index)].mean()
    return out, round(ne,3)
print('TEST 1 (alarm share inside each event window; non-event alarm rate pre-2025)')
for k,ch in [('vix','equity'),('vix_5d_rise','equity'),('vix_vs_20d','equity'),('sofr_effr_adjusted','funding'),('baa_widen20','credit'),('ust10_abs_change','rates')]:
    print(' ',k,*test1(ind[k],ch))
# test2
P=pd.read_csv(R+'capstone_database/exports/pqd_quarterly.csv')
P=P[P.entity=='NSCC'].copy(); pay=P.payload.map(json.loads)
for f in ['im_call_to_im','vm_peak_to_avg','backtest_breaches','backtest_uncovered_peak_to_im','stress_loss_to_im','payment_to_qlr','top5_open_share','im_qoq']:
    P[f]=pay.map(lambda d:d.get(f))
P['q']=pd.PeriodIndex(P.quarter,freq='Q'); P=P.set_index('q').sort_index()
print('\nNSCC quarters',P.index.min(),P.index.max(),len(P))
def qmax(x): x=x.dropna(); g=x.groupby(x.index.to_period('Q')); return g.max()[g.count()>=45]
def rk(a): return pd.Series(a).rank().values
def sp(a,b): return np.corrcoef(rk(a),rk(b))[0,1]
rng=np.random.default_rng(7)
def boot(a,b,B=2000,L=4):
    n=len(a); r=[]
    for _ in range(B):
        idx=np.concatenate([np.arange(st,st+L)%n for st in rng.integers(0,n,int(np.ceil(n/L)))])[:n]
        if len(set(a[idx]))>2 and len(set(b[idx]))>2: r.append(sp(a[idx],b[idx]))
    return np.percentile(r,[2.5,97.5])
def test2(sig,f,lag):
    q=qmax(ind[sig]); y=P[f].astype(float)
    x=q.shift(lag) if lag else q
    d=pd.concat([x.rename('x'),y.rename('y')],axis=1).dropna()
    a,b=d.x.values,d.y.values; r=sp(a,b); lo,hi=boot(a,b)
    ok='PASS' if r>=.3 and lo>0 else 'fail'
    return f'{sig:20s} -> {f:30s} lag{lag} n={len(d):2d} rho={r:+.2f} CI[{lo:+.2f},{hi:+.2f}] {ok}'
print('\nTEST 2 (quarterly max signal vs NSCC PQD reaction field)')
for sig,f,ch in [('vix','im_call_to_im','01A'),('vix','vm_peak_to_avg','01B'),('vix','backtest_breaches','01C'),('vix','backtest_uncovered_peak_to_im','01C alt'),
 ('vix_vs_20d','im_call_to_im','01A alt sig'),('vix_vs_20d','vm_peak_to_avg','01B alt sig'),('vix_vs_20d','backtest_breaches','01C alt sig'),
 ('sofr_effr_adjusted','im_call_to_im','03B'),('sofr_effr_adjusted','vm_peak_to_avg','03B alt'),('baa_widen20','im_call_to_im','03A proxy')]:
    for lag in (0,1): print(ch.ljust(12),test2(sig,f,lag))
print('\nOverlap between NSCC reaction fields (Spearman)')
print(P[['im_call_to_im','vm_peak_to_avg','backtest_breaches','backtest_uncovered_peak_to_im']].astype(float).corr('spearman').round(2))
print('\nsignal overlap (quarterly max, Spearman)')
print(pd.concat({k:qmax(ind[k]) for k in ['vix','vix_vs_20d','sofr_effr_adjusted','baa_widen20']},axis=1).loc['2020Q4':].corr('spearman').round(2))
print(P[['im_call_to_im','vm_peak_to_avg','backtest_breaches']].tail(8))
print('\nTREND CHECK: same tests on quarter-to-quarter changes (removes shared upward drift)')
def test2d(sig,f,lag):
    q=qmax(ind[sig]); y=P[f].astype(float); x=q.shift(lag) if lag else q
    d=pd.concat([x.rename('x'),y.rename('y')],axis=1).dropna().diff().dropna()
    a,b=d.x.values,d.y.values; r=sp(a,b); lo,hi=boot(a,b)
    return f'{sig:20s} -> {f:18s} lag{lag} n={len(d)} rho={r:+.2f} CI[{lo:+.2f},{hi:+.2f}]'
for sig,f in [('sofr_effr_adjusted','im_call_to_im'),('sofr_effr_adjusted','vm_peak_to_avg'),('vix_vs_20d','vm_peak_to_avg'),('vix','backtest_breaches')]:
    for lag in (0,1): print(test2d(sig,f,lag))
q=qmax(ind['sofr_effr_adjusted']); print(pd.concat([q.loc['2020Q4':].rename('sofr_adj_qmax'),P.im_call_to_im],axis=1).round(2).T.to_string())
