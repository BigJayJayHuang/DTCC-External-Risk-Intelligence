"""Three missing-link experiments that never synthesize observed source fields.

Actual market supply, broad MBSD stock and NSCC concentration aggregates remain
fixed. Only unavailable obligations/resources, TBA decomposition, and compatible
member allocations are assumed. No production risk formula or real probability
is inferred. This module performs no filesystem writes.
"""
from __future__ import annotations

from pathlib import Path
import hashlib, math
import numpy as np
import pandas as pd

DEFAULT_CONFIG={
    'auction_source_month':'2026-09',
    'auction_participation_low':0.03,'auction_participation_high':0.08,
    'auction_netting_low':0.25,'auction_netting_high':0.60,
    'auction_baseline_opening_fraction':0.10,'auction_baseline_funding_fraction':0.90,
    'auction_stress_opening_fraction':0.05,'auction_stress_funding_fraction':0.65,
    'auction_stress_cash_delay_days':3,'auction_mitigation_added_cash_fraction':0.50,
    'auction_sensitivity_funding_fraction':0.50,'auction_sensitivity_cash_delay_days':5,
    'tba_share_low':0.35,'tba_share_high':0.65,'tba_horizon_days':30,
    'tba_maturity_dirichlet_shape':2.0,'tba_stress_deferral_fraction':0.60,
    'tba_stress_days':10,'tba_mitigation_stress_days':5,
    'tba_sensitivity_deferral_fraction':0.80,'tba_sensitivity_stress_days':15,
    'concentration_assumed_members':25,'concentration_normalized_total':100.0,
    'concentration_top5_dirichlet_shape':8.0,'concentration_stress_skew':0.80,
    'concentration_mitigation_skew':0.15,'concentration_addon_threshold_units':10.0,
    'concentration_addon_rate':0.20,'concentration_sensitivity_threshold_units':5.0,
}

SOURCE_FILES=('treasury_auction_observations.csv','financial_guarantee_reconciliation.csv',
              'new_pqd_fields.csv','new_pqd_cell_evidence.csv')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _float(v,name):
    v=float(v)
    if not math.isfinite(v) or v<0:raise ValueError(name+' must be finite and nonnegative')
    return v
def _records(frame):
    return [{k:(None if pd.isna(v) else v.item() if isinstance(v,np.generic) else v)
             for k,v in row.items()} for row in frame.to_dict('records')]

def load_observed(source_root=None):
    """Select already-collected source rows; return exact observed provenance."""
    root=Path(source_root) if source_root else Path(__file__).resolve().parents[2]/'new_reference_chain_tests_2026_10_21/data'
    root=root.resolve()
    sources=[{'file':name,'path':str(root/name),'sha256':sha(root/name),
              'origin':'observed','use':'Preserved existing source; not generated'} for name in SOURCE_FILES]
    auctions=pd.read_csv(root/SOURCE_FILES[0],dtype={'cusip':'string'},keep_default_na=False)
    dates=pd.to_datetime(auctions.issue_date,errors='coerce')
    selected=auctions.loc[dates.dt.to_period('M').astype(str).eq(DEFAULT_CONFIG['auction_source_month'])].copy()
    if selected.empty:raise ValueError('No observed auction rows in the frozen source month')
    selected['offered_amount_usd']=pd.to_numeric(selected.offered_amount_usd,errors='raise')
    if selected.offered_amount_usd.lt(0).any():raise ValueError('Negative offered amount')
    selected=selected.sort_values(['issue_date','auction_date','cusip'],kind='stable').reset_index(drop=True)
    financials=pd.read_csv(root/SOURCE_FILES[1]);mbsd=financials[financials.entity.eq('MBSD')].sort_values('quarter').iloc[-1]
    broad=_float(mbsd.chosen_usd,'MBSD chosen amount')
    if broad<=0:raise ValueError('Positive actual MBSD reference required')
    fields=pd.read_csv(root/SOURCE_FILES[2]);nscc=fields[fields.entity.eq('NSCC')].sort_values('quarter').iloc[-1]
    evidence=pd.read_csv(root/SOURCE_FILES[3]);base=evidence[evidence.entity.eq('NSCC')&evidence.quarter.eq(nscc.quarter)&evidence.reference.eq('18.2.2')]
    avg=base[base.dimension.eq('AverageInQuarter')]
    peak=base[base.dimension.eq('PeakInQuarter')]
    if len(avg)!=1 or len(peak)!=1:raise ValueError('Exactly one observed NSCC average and peak source cell required')
    avg=avg.iloc[0];peak=peak.iloc[0]
    share=float(nscc.top5_position_share)
    if not math.isclose(share,float(avg.value),rel_tol=0,abs_tol=1e-12):raise ValueError('Source field/evidence average mismatch')
    if avg.unit!='fraction' or peak.unit!='fraction':raise ValueError('Explicit fraction source units required')
    if not 0<=share<=float(peak.value)<=1:raise ValueError('Invalid observed average/peak shares')
    source_rows={
        'auction_observations':_records(selected),
        'mbsd_broad_unsettled':_records(pd.DataFrame([mbsd]))[0],
        'nscc_fields':_records(pd.DataFrame([nscc]))[0],
        'nscc_average_evidence':_records(pd.DataFrame([avg]))[0],
        'nscc_peak_evidence':_records(pd.DataFrame([peak]))[0],
    }
    return {'auctions':selected,'mbsd':mbsd.to_dict(),'nscc':nscc.to_dict(),'avg_evidence':avg.to_dict(),
            'peak_evidence':peak.to_dict(),'sources':sources,'source_rows':source_rows}

def cash_ledger(obligations,funding,opening_cash=0.0):
    """Conserve hypothetical cash and overdue obligation stock, no netting inference."""
    obligations=[_float(x,'obligation') for x in obligations];funding=[_float(x,'funding') for x in funding]
    if not obligations or len(obligations)!=len(funding):raise ValueError('Equal nonempty schedules required')
    cash=_float(opening_cash,'opening cash');unpaid=paid_total=funded_total=due_total=0.0;rows=[]
    for day,(due,received) in enumerate(zip(obligations,funding),1):
        opening=cash;prior_unpaid=unpaid;cash+=received;due_total+=due;funded_total+=received
        payment=min(cash,prior_unpaid+due);cash-=payment;paid_total+=payment;unpaid=prior_unpaid+due-payment
        rows.append({'day_index':day,'opening_cash_usd':opening,'funding_received_usd':received,
                     'new_conditional_obligation_usd':due,'prior_unpaid_usd':prior_unpaid,
                     'paid_usd':payment,'closing_cash_usd':cash,'unpaid_usd':unpaid,
                     'cumulative_paid_usd':paid_total,'cumulative_due_usd':due_total,
                     'cash_conservation_residual_usd':opening+received-payment-cash,
                     'obligation_conservation_residual_usd':prior_unpaid+due-payment-unpaid})
    return rows,{'peak_unpaid_usd':max(r['unpaid_usd'] for r in rows),'terminal_unpaid_usd':unpaid,
                 'terminal_cash_usd':cash,'total_paid_usd':paid_total,'total_funding_received_usd':funded_total,
                 'opening_cash_usd':float(opening_cash),'total_conditional_obligations_usd':due_total}

def tba_stock_ledger(initial_tba_usd,maturity_fractions,deferral_fractions):
    """Move a hypothetical decomposition of a real broad stock through due/settled."""
    initial=_float(initial_tba_usd,'initial assumed TBA stock')
    weights=np.asarray(maturity_fractions,dtype=float);defer=np.asarray(deferral_fractions,dtype=float)
    if len(weights)==0 or len(weights)!=len(defer) or not np.isfinite(weights).all() or (weights<0).any() or not np.isclose(weights.sum(),1,atol=1e-12):raise ValueError('Nonnegative maturity fractions summing to1 required')
    if not np.isfinite(defer).all() or ((defer<0)|(defer>1)).any():raise ValueError('Deferral fractions must lie in[0,1]')
    overdue=settled_total=0.0;outstanding=initial;rows=[]
    for i,(fraction,delay) in enumerate(zip(weights,defer)):
        opening=outstanding;new_due=initial*fraction;prior=overdue;due=prior+new_due
        settled=due*(1-delay);overdue=due-settled;settled_total+=settled;outstanding=initial-settled_total
        unmatured=initial*float(weights[i+1:].sum())
        rows.append({'day_index':i+1,'maturity_fraction':fraction,'assumed_deferral_fraction':delay,
                     'opening_assumed_tba_stock_usd':opening,'new_due_usd':new_due,'prior_overdue_usd':prior,
                     'settled_usd':settled,'overdue_usd':overdue,'closing_assumed_tba_stock_usd':outstanding,
                     'unmatured_usd':unmatured,'cumulative_settled_usd':settled_total,
                     'stock_conservation_residual_usd':initial-settled_total-outstanding,
                     'partition_residual_usd':outstanding-unmatured-overdue})
    peak=max(r['overdue_usd'] for r in rows)
    return rows,{'peak_overdue_usd':peak,'peak_overdue_to_assumed_tba_stock':peak/initial if initial else 0.0,
                 'terminal_overdue_usd':overdue,'terminal_assumed_tba_stock_usd':outstanding,
                 'total_settled_usd':settled_total}

def compatible_member_shares(actual_top5_average_share,weights,assumed_members=25,skew=0.0):
    """Stylized average-compatible distribution, never an actual daily member book.

    Tail members are equal by assumption. Every top-five member gets at least
    that tail share; only the residual top-five mass is distributed randomly.
    A convex skew changes missing within-group composition while preserving
    the exact observed top-five aggregate and rank inequalities.
    """
    s=_float(actual_top5_average_share,'actual top5 average share');n=int(assumed_members)
    if n!=assumed_members or n<25 or not 5/n-1e-12<=s<=1:raise ValueError('Feasible top5 aggregate and assumed member count>=25 required')
    w=np.asarray(weights,dtype=float)
    if len(w)!=5 or not np.isfinite(w).all() or (w<0).any() or not np.isclose(w.sum(),1):raise ValueError('Five nonnegative normalized weights required')
    skew=_float(skew,'skew')
    if skew>1:raise ValueError('Skew must be<=1')
    tail=(1-s)/(n-5);excess=max(0.0,s-5*tail);favored=np.zeros(5);favored[int(np.argmax(w))]=1
    mixed=(1-skew)*w+skew*favored;top=np.sort(tail+excess*mixed)[::-1]
    result=np.r_[top,np.full(n-5,tail)]
    if not np.isclose(result.sum(),1,atol=1e-12) or not np.isclose(result[:5].sum(),s,atol=1e-12) or np.min(result[:5])+1e-12<np.max(result[5:]):raise AssertionError('Aggregate/rank construction failed')
    return result

def normalized_addon(shares,normalized_total=100.0,threshold_units=10.0,rate=0.20):
    shares=np.asarray(shares,dtype=float);total=_float(normalized_total,'normalized total')
    threshold=_float(threshold_units,'threshold');rate=_float(rate,'rate')
    if not np.isfinite(shares).all() or (shares<0).any() or not np.isclose(shares.sum(),1):raise ValueError('Normalized nonnegative member shares required')
    exposures=shares*total;addons=np.maximum(exposures-threshold,0)*rate
    return exposures,addons

def _scenario_definitions():
    labels={
        'auction_missing_cash':('真实发行日供给→缺失现金约束','Observed issue-date supply → missing cash constraint'),
        'tba_missing_ladder':('真实MBSD总存量→缺失TBA期限分解','Observed broad MBSD stock → missing TBA maturity decomposition'),
        'concentration_missing_members':('真实前五会员平均份额→缺失组内配置','Observed top-five average share → missing within-group composition')}
    roles=[('baseline','基准假设','Baseline assumptions'),('stress','缺失环节压力假设','Missing-link stress assumptions'),
           ('mitigation','缺失环节缓解假设','Missing-link mitigation assumptions'),('unrelated','无关事件对照','Unrelated-event control'),
           ('sensitivity','缺失参数敏感性','Missing-parameter sensitivity')]
    return [{'scenario_id':'gap_'+model+'_'+role,'model_id':model,'role':role,
             'label_cn':cn+'：'+rcn,'label_en':en+': '+ren} for model,(cn,en) in labels.items() for role,rcn,ren in roles]

def run_experiment(seed:int,replications:int,source_root=None):
    if int(replications)!=replications or replications<1:raise ValueError('Positive integer replications required')
    observed=load_observed(source_root);cfg=dict(DEFAULT_CONFIG);scenarios=_scenario_definitions()
    runs=[];auction_rows=[];auction_lots=[];tba_rows=[];members=[];checks=[]
    month=cfg['auction_source_month'];dates=pd.date_range(month+'-01',pd.Period(month).end_time.normalize(),freq='D')
    date_index={d.date().isoformat():i for i,d in enumerate(dates)}
    auctions=observed['auctions'];daily_offered=auctions.groupby('issue_date').offered_amount_usd.sum().to_dict()
    actual_broad=float(observed['mbsd']['chosen_usd']);actual_avg=float(observed['nscc']['top5_position_share'])
    actual_peak=float(observed['peak_evidence']['value']);actual_im=float(observed['nscc']['top5_im_share'])
    for model_index,model in enumerate(['auction_missing_cash','tba_missing_ladder','concentration_missing_members']):
        for rep in range(int(replications)):
            uint=int(np.random.SeedSequence([seed,model_index,rep]).generate_state(1,dtype=np.uint64)[0]);rng=np.random.default_rng(uint)
            if model=='auction_missing_cash':
                participation=rng.uniform(cfg['auction_participation_low'],cfg['auction_participation_high'],len(auctions))
                netting=rng.uniform(cfg['auction_netting_low'],cfg['auction_netting_high'],len(auctions))
                conditional=auctions.offered_amount_usd.to_numpy(dtype=float)*participation*netting
                due=np.zeros(len(dates))
                for date,value in zip(auctions.issue_date,conditional):due[date_index[date]]+=value
                total=float(due.sum())
            elif model=='tba_missing_ladder':
                assumed_share=float(rng.uniform(cfg['tba_share_low'],cfg['tba_share_high']))
                maturity=rng.dirichlet(np.full(cfg['tba_horizon_days'],cfg['tba_maturity_dirichlet_shape']))
            else:weights=rng.dirichlet(np.full(5,cfg['concentration_top5_dirichlet_shape']))
            for spec in [s for s in scenarios if s['model_id']==model]:
                role=spec['role'];tags={'scenario_id':spec['scenario_id'],'model_id':model,'replicate_id':rep,'scenario_seed':str(uint)}
                if model=='auction_missing_cash':
                    for j,lot in enumerate(auctions.itertuples()):
                        auction_lots.append({**tags,'source_row_index':j,'observed_cusip':str(lot.cusip),
                            'observed_auction_date':str(lot.auction_date),'observed_issue_date':str(lot.issue_date),
                            'observed_offered_amount_usd':float(lot.offered_amount_usd),
                            'assumed_effective_eligible_participation_of_offered':float(participation[j]),
                            'assumed_net_obligation_fraction':float(netting[j]),
                            'conditional_obligation_usd':float(conditional[j])})
                    stress=role in ['stress','mitigation','sensitivity']
                    fraction=cfg['auction_sensitivity_funding_fraction'] if role=='sensitivity' else cfg['auction_stress_funding_fraction'] if stress else cfg['auction_baseline_funding_fraction']
                    delay=cfg['auction_sensitivity_cash_delay_days'] if role=='sensitivity' else cfg['auction_stress_cash_delay_days'] if stress else 0
                    opening_fraction=cfg['auction_stress_opening_fraction'] if stress else cfg['auction_baseline_opening_fraction']
                    extra=cfg['auction_mitigation_added_cash_fraction']*total if role=='mitigation' else 0.0
                    funding=np.zeros(len(dates));beyond=0.0
                    for i,value in enumerate(due*fraction):
                        if i+delay<len(dates):funding[i+delay]+=value
                        else:beyond+=value
                    trace,result=cash_ledger(due,funding,total*opening_fraction+extra)
                    for i,row in enumerate(trace):
                        date=dates[i].date().isoformat()
                        auction_rows.append({**tags,**row,'date':date,'observed_daily_offered_usd':float(daily_offered.get(date,0)),
                                             'source_month':month,'assumed_funding_fraction':fraction,'assumed_cash_delay_days':delay,
                                             'added_hypothetical_cash_usd':extra if i==0 else 0.0})
                    runs.append({**tags,'primary_metric':'conditional_peak_unpaid_usd_million','primary_value':result['peak_unpaid_usd']/1e6,
                                 'primary_units':'USD million','observed_source_period':month,
                                 'observed_month_offered_usd':float(auctions.offered_amount_usd.sum()),
                                 'assumed_obligation_to_offered_ratio':total/float(auctions.offered_amount_usd.sum()),
                                 'assumed_participation_min':float(participation.min()),'assumed_participation_max':float(participation.max()),
                                 'assumed_netting_min':float(netting.min()),'assumed_netting_max':float(netting.max()),
                                 'funding_after_horizon_usd':beyond,'added_hypothetical_cash_usd':extra,**result})
                elif model=='tba_missing_ladder':
                    duration=cfg['tba_sensitivity_stress_days'] if role=='sensitivity' else cfg['tba_mitigation_stress_days'] if role=='mitigation' else cfg['tba_stress_days'] if role=='stress' else 0
                    fraction=cfg['tba_sensitivity_deferral_fraction'] if role=='sensitivity' else cfg['tba_stress_deferral_fraction']
                    deferral=np.zeros(len(maturity));deferral[:duration]=fraction
                    initial=actual_broad*assumed_share;trace,result=tba_stock_ledger(initial,maturity,deferral)
                    for row in trace:tba_rows.append({**tags,**row,'observed_broad_mbsd_stock_usd':actual_broad,
                        'observed_source_period':observed['mbsd']['quarter'],'assumed_tba_share':assumed_share})
                    runs.append({**tags,'primary_metric':'peak_overdue_to_assumed_tba_stock','primary_value':result['peak_overdue_to_assumed_tba_stock'],
                        'primary_units':'fraction_of_assumed_tba_stock','observed_source_period':observed['mbsd']['quarter'],
                        'observed_broad_mbsd_stock_usd':actual_broad,'assumed_tba_share':assumed_share,
                        'initial_assumed_tba_stock_usd':initial,**result})
                else:
                    skew=cfg['concentration_stress_skew'] if role in ['stress','sensitivity'] else cfg['concentration_mitigation_skew'] if role=='mitigation' else 0.0
                    threshold=cfg['concentration_sensitivity_threshold_units'] if role=='sensitivity' else cfg['concentration_addon_threshold_units']
                    share=compatible_member_shares(actual_avg,weights,cfg['concentration_assumed_members'],skew)
                    exposures,addons=normalized_addon(share,cfg['concentration_normalized_total'],threshold,cfg['concentration_addon_rate'])
                    for rank,(weight,exposure,addon) in enumerate(zip(share,exposures,addons),1):
                        members.append({**tags,'synthetic_rank':rank,'assumed_member_share':weight,'normalized_exposure_units':exposure,
                                        'hypothetical_addon_units':addon,'observed_top5_average_share':actual_avg,
                                        'observed_top5_peak_share':actual_peak,'observed_top5_im_average_share':actual_im,
                                        'observed_source_period':observed['nscc']['quarter'],'assumed_member_count':cfg['concentration_assumed_members'],
                                        'assumed_skew':skew,'assumed_addon_threshold_units':threshold,'assumed_addon_rate':cfg['concentration_addon_rate']})
                    runs.append({**tags,'primary_metric':'hypothetical_addon_normalized_exposure_units','primary_value':float(addons.sum()),
                                 'primary_units':'normalized exposure units; total=100, not USD',
                                 'observed_source_period':observed['nscc']['quarter'],'observed_top5_average_share':actual_avg,
                                 'observed_top5_peak_share':actual_peak,'observed_top5_im_average_share':actual_im,
                                 'assumed_member_count':cfg['concentration_assumed_members'],'normalized_total_units':float(exposures.sum()),
                                 'generated_top5_share':float(share[:5].sum()),'generated_largest_member_share':float(share.max()),
                                 'top5_rank_gap':float(share[4]-share[5]),'assumed_skew':skew,
                                 'assumed_addon_threshold_units':threshold,'assumed_addon_rate':cfg['concentration_addon_rate']})
    tables={'gap_runs':pd.DataFrame(runs),'auction_lots':pd.DataFrame(auction_lots),'auction_trace':pd.DataFrame(auction_rows),'tba_trace':pd.DataFrame(tba_rows),'concentration_members':pd.DataFrame(members)}
    for f in tables.values():
        f['evidence_type']='conditional_missing_link_simulation'
        f['empirical_validation']=False
    def check(name,passed,detail):checks.append({'name':name,'passed':bool(passed),'detail':detail})
    a=tables['auction_trace'];t=tables['tba_trace'];c=tables['concentration_members'];r=tables['gap_runs']
    check('source_files_unchanged',all(sha(s['path'])==s['sha256'] for s in observed['sources']),'Source hashes unchanged after execution')
    check('cash_conservation',float(a.cash_conservation_residual_usd.abs().max())<.01,'USD residual below one cent')
    check('auction_obligation_conservation',float(a.obligation_conservation_residual_usd.abs().max())<.01,'Unpaid obligations carry forward')
    check('actual_offered_schedule_preserved',all(np.isclose(row.observed_daily_offered_usd,daily_offered.get(row.date,0),atol=0,rtol=0) for row in a.itertuples()),'Only observed issue-date offered supply; no invented auction dates or awards')
    check('tba_stock_conservation',float(t.stock_conservation_residual_usd.abs().max())<.01 and float(t.partition_residual_usd.abs().max())<.01,'Matured and unmatured partitions conserve assumed TBA stock')
    check('actual_broad_stock_preserved',t.observed_broad_mbsd_stock_usd.eq(actual_broad).all(),'Broad observed MBSD stock never replaced with synthetic observations')
    share_groups=c.groupby(['scenario_id','replicate_id'])
    check('actual_top5_average_preserved',all(np.isclose(g.loc[g.synthetic_rank<=5,'assumed_member_share'].sum(),actual_avg,atol=1e-12,rtol=0) for _,g in share_groups),'Only missing within-group allocation varies')
    check('top5_rank_and_normalization',all(np.isclose(g.assumed_member_share.sum(),1,atol=1e-12) and g.loc[g.synthetic_rank<=5,'assumed_member_share'].min()+1e-12>=g.loc[g.synthetic_rank>5,'assumed_member_share'].max() for _,g in share_groups),'Assumed25+member stylized average-compatible distributions; not observed daily books')
    check('actual_peak_separate',c.observed_top5_peak_share.eq(actual_peak).all() and c.observed_top5_average_share.eq(actual_avg).all(),'Actual average and peak remain separate fields')
    null=True
    for model in r.model_id.unique():
        g=r[r.model_id.eq(model)];base=g[g.scenario_id.eq('gap_'+model+'_baseline')].sort_values('replicate_id')
        other=g[g.scenario_id.eq('gap_'+model+'_unrelated')].sort_values('replicate_id')
        null &= np.array_equal(base.primary_value.to_numpy(),other.primary_value.to_numpy())
    check('unrelated_control_exact',null,'Unrelated events do not alter missing-link conditions')
    assert all(x['passed'] for x in checks),'Gap model control failed'
    field_provenance={
      'observed':{'auction_observations.issue_date':'Exact source issue_date; not generated',
          'auction_observations.offered_amount_usd':'Exact offered market supply in USD; not awards or actual GSD obligations',
          'observed_broad_mbsd_stock_usd':'Latest reconciled MBSD chosen_usd; broad guarantee notional, not TBA-only or cash',
          'observed_top5_average_share':'NSCC18.2.2 AverageInQuarter; stylized distribution compatibility only',
          'observed_top5_peak_share':'Separate NSCC18.2.2 PeakInQuarter; not used as average or vice versa',
          'observed_top5_im_average_share':'Separate margin aggregate; not same member group as top5positions'},
      'derived_from_observed':{'observed_daily_offered_usd':'Sum actual offered amounts by unchanged issue_date',
          'observed_month_offered_usd':'Sum actual selected source rows',
          'date':'Fixed calendar days in selected observed month; not synthetic auction events'},
      'assumed_missing':{'conditional_obligation_usd':'Offered supply times assumed participation/award-eligibility share and netting ratio; not observed GSD obligations',
          'opening_cash_usd/funding_received_usd':'Unknown cash buffers, available funding amounts and funding delays',
          'assumed_tba_share/maturity_fraction/assumed_deferral_fraction':'Unobserved TBA component and maturity/delivery decomposition',
          'assumed_member_share/assumed_member_count':'Virtual average-compatible member distribution; not observed identities or daily/quarter-end weights',
          'normalized_exposure_units/hypothetical_addon_units':'Normalized total100, arbitrary add-on threshold/rate; not dollars or official margin'},
      'derived_from_observed_and_assumed_missing':{'primary_value':'Conditional cash/stock/allocation consequences, not actual outcomes',
          'paid_usd/unpaid_usd/overdue_usd':'Model ledger consequences after only missing link assumptions are applied'}}
    assumptions={'config':cfg,'all_unknown_parameters':'Hypothetical, not official formulas or calibrated frequencies',
        'auction':'Observed offered supply and actual issue dates remain fixed. Hypothetical obligations/offered ratio combines unavailable awards, eligible participation and netting; offered is neither awarded nor GSD settlement. Funding/cash buffers are unknown and explicitly assumed.',
        'tba':'Observed broad MBSD guarantee stock stays fixed. Unknown TBA share/maturity ladder is decomposed without replacing the observed stock. No new trades/cancellations; 30 relative days are illustrative, not actual maturity dates.',
        'concentration':'The actual quarterly average top5position share is preserved. A virtual25member book is a stylized average-compatible distribution, not an actual daily, named or quarter-end book. Tail allocations are equal by assumption; only residual top5mass is generated. Actual peak and top5margin aggregate are stored separately and are not member matched. Exposures total100normalizedunits, not dollars.',
        'inference':'The missing link can be tested for arithmetic, monotonicity, sensitivity and feasible ranges only. No generated result repairs a failed empirical test, establishes an event-to-service causal relationship or validates a production risk score.'}
    return {'tables':tables,'checks':checks,'sources':observed['sources'],'source_rows':observed['source_rows'],
            'field_provenance':field_provenance,'assumptions':assumptions,'scenarios':scenarios}
