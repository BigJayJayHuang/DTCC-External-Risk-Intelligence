"""Independent arithmetic replay of saved synthetic margin/liquidity inputs.

Does not import the simulation engine or invoke its calculation functions.
This audits implementation under declared assumptions, not empirical validity.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import math
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
KEY=['scenario_id','replicate_id']


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def audit():
    receipt=json.loads((ROOT/'results/execution_receipt.json').read_text())
    plan=json.loads((ROOT/'config/resolved_plan.json').read_text())
    assert sha(ROOT/'src/margin_liquidity.py')==plan['engine_sha256']['margin_liquidity']
    names=['ml_runs','ml_market_inputs','ml_market_members','ml_concentration_inputs',
           'ml_concentration_positions','ml_liquidity_inputs','ml_liquidity_allocations',
           'ml_cross_inputs','ml_cross_members']
    frames={}
    for name in names:
        p=ROOT/'data'/f'{name}.csv'
        assert sha(p)==receipt['csv_sha256'][name],f'CSV changed: {name}'
        f=pd.read_csv(p,dtype={'scenario_seed':str},float_precision='round_trip')
        assert len(f)==receipt['tables'][name]
        assert f.source_type.eq('synthetic').all() and not f.empirical_validation.any()
        assert set(f.simulation_id)=={receipt['simulation_id']}
        frames[name]=f
    runs={(str(r.scenario_id),int(r.replicate_id)):r._asdict() for r in frames['ml_runs'].itertuples(index=False)}
    maxima=defaultdict(float);counts=defaultdict(int)
    def compare(got,want,name):
        got=float(got);want=float(want)
        assert math.isfinite(got) and math.isfinite(want),(name,got,want)
        difference=abs(got-want);maxima[name]=max(maxima[name],difference);counts[name]+=1
        assert difference<=1e-8+1e-12*abs(want),(name,got,want,difference)
    def group(name):return frames[name].groupby(KEY,sort=False)
    def indexed(name,idcol):
        return {(*k,str(r[idcol])):r for k,g in group(name) for r in g.to_dict('records')}
    def totals(key,records,columns,prefix):
        for column in columns:compare(runs[key][column],math.fsum(r[column] for r in records),prefix+':'+column)
        expected={column:math.fsum(r[column] for r in records) for column in columns}
        metric=runs[key]['primary_metric']
        if metric in expected:compare(runs[key]['primary_value'],expected[metric],prefix+':primary')
        return expected

    market_index=indexed('ml_market_members','member_id')
    for key,g in group('ml_market_inputs'):
        independent=[]
        for p in g.to_dict('records'):
            delta=p['signed_delta']*p['residual_fraction'];pnl=delta*p['move']
            paid=max(0.0,-pnl);received=max(0.0,pnl)
            opening=abs(p['signed_delta'])*p['unit_sigma']*p['risk_multiplier']
            ending=abs(delta)*p['unit_sigma']*p['risk_multiplier']*p['volatility_multiplier']
            call=max(0.0,ending-opening);release=max(0.0,opening-ending)
            resources=p['starting_cash_usd_million']+received;outgo=paid+call
            want={'effective_delta':delta,'pnl_usd_million':pnl,'vm_paid_usd_million':paid,
                  'vm_received_usd_million':received,'opening_required_margin_usd_million':opening,
                  'required_margin_usd_million':ending,'margin_call_usd_million':call,
                  'potential_margin_release_usd_million':release,'cash_needed_usd_million':outgo,
                  'funding_gap_usd_million':max(0.0,outgo-resources),
                  'ending_cash_usd_million':max(0.0,resources-outgo)}
            stored=market_index[(*key,str(p['member_id']))]
            for column,value in want.items():compare(stored[column],value,'market_member:'+column)
            independent.append(want)
        columns=[k for k in independent[0] if k!='effective_delta']
        summed=totals(key,independent,columns,'market_run')
        compare(summed['vm_paid_usd_million'],summed['vm_received_usd_million'],'market_vm_transfer_balance')
        compare(summed['required_margin_usd_million']-summed['opening_required_margin_usd_million'],
                summed['margin_call_usd_million']-summed['potential_margin_release_usd_million'],'market_margin_stock_identity')

    positions=indexed('ml_concentration_positions','security_id')
    for key,g in group('ml_concentration_inputs'):
        rows=g.to_dict('records');p=rows[0];normalizer=math.fsum(x['weight'] for x in rows)
        weights=[x['weight']/normalizer for x in rows];gross=p['gross_usd_million']
        for row,weight in zip(rows,weights):
            stored=positions[(*key,str(row['security_id']))]
            compare(stored['weight'],weight,'concentration_weight')
            compare(stored['position_usd_million'],gross*weight,'concentration_position')
        base=gross*p['base_margin_fraction'];addon=max(0.0,max(weights)-p['threshold'])*gross*p['addon_rate']
        want={'gross_position_usd_million':gross,'largest_security_share':max(weights),
              'security_hhi':math.fsum(x*x for x in weights),'base_margin_usd_million':base,
              'concentration_addon_usd_million':addon,'required_margin_usd_million':base+addon,
              'requirement_to_assumed_capital':(base+addon)/p['member_capital_usd_million']}
        for column,value in want.items():compare(runs[key][column],value,'concentration_run:'+column)
        compare(runs[key]['primary_value'],addon,'concentration_primary')

    allocations=indexed('ml_liquidity_allocations','member_id')
    for key,g in group('ml_liquidity_inputs'):
        rows=g.to_dict('records');p=rows[0];base=p['base_resources_usd_million'];mult=p['exposure_multiplier']
        families=defaultdict(list)
        for row in rows:families[str(row['family_id'])].append(row['exposure_usd_million']*mult)
        family_totals={f:math.fsum(v) for f,v in families.items()}
        largest=max(family_totals.values());call=max(0.0,largest-base)
        selected=sorted(family_totals,key=lambda f:(-family_totals[f],f))[:int(p['top_families'])]
        denominator=math.fsum(family_totals[f] for f in selected);collected=[];allocated=[]
        for row in rows:
            selected_member=str(row['family_id']) in selected
            member_call=call*row['exposure_usd_million']*mult/denominator if selected_member and denominator>0 else 0.0
            member_collection=min(member_call,row['available_cash_usd_million'])
            stored=allocations[(*key,str(row['member_id']))]
            assert bool(stored['selected_family'])==selected_member
            compare(stored['stressed_exposure_usd_million'],row['exposure_usd_million']*mult,'sld_member_exposure')
            compare(stored['sld_call_usd_million'],member_call,'sld_member_call')
            compare(stored['sld_collected_usd_million'],member_collection,'sld_member_collection')
            collected.append(member_collection);allocated.append(member_call)
        collected=math.fsum(collected);remaining=max(0.0,largest-base-collected)
        want={'largest_family_exposure_usd_million':largest,'base_resources_usd_million':base,
              'sld_called_usd_million':call,'sld_collected_usd_million':collected,
              'sld_unfunded_call_usd_million':call-collected,
              'remaining_liquidity_gap_usd_million':remaining,'unused_resources_usd_million':max(0.0,base+collected-largest)}
        for column,value in want.items():compare(runs[key][column],value,'sld_run:'+column)
        compare(math.fsum(allocated),call,'sld_allocation_conservation')
        compare(runs[key]['primary_value'],want[runs[key]['primary_metric']],'sld_primary')

    cross=indexed('ml_cross_members','member_id')
    for key,g in group('ml_cross_inputs'):
        independent=[]
        for row in g.to_dict('records'):
            a=row['treasury_exposure_usd_million'];b=row['futures_exposure_usd_million'];rho=row['correlation']
            # Orthogonal-factor decomposition rather than the engine covariance expansion.
            covariance_norm=math.hypot(a+rho*b,b*math.sqrt(max(0.0,1-rho*rho)))
            risk=row['risk_multiplier']*row['sigma_fraction']*row['volatility_multiplier']*covariance_norm
            gross=abs(a)+abs(b);floor=gross*row['gross_floor_fraction']
            standalone=row['risk_multiplier']*row['sigma_fraction']*row['volatility_multiplier']*gross
            want={'risk_component_usd_million':risk,'gross_floor_usd_million':floor,
                  'combined_requirement_usd_million':max(risk,floor),
                  'sum_standalone_risk_usd_million':standalone,'risk_offset_usd_million':standalone-risk}
            stored=cross[(*key,str(row['member_id']))]
            for column,value in want.items():compare(stored[column],value,'cross_member:'+column)
            independent.append(want)
        totals(key,independent,list(independent[0]),'cross_run')

    # Check that original virtual portfolios are shared across scenarios; scenario
    # decisions such as cash rescues and reallocation are allowed to differ.
    paired_specs={
        'ml_market_inputs':['member_id','signed_delta','starting_cash_usd_million'],
        'ml_concentration_inputs':['security_id','original_weight','gross_usd_million'],
        'ml_liquidity_inputs':['member_id','family_id','exposure_usd_million'],
        'ml_cross_inputs':['member_id','treasury_exposure_usd_million','baseline_futures_exposure_usd_million'],
    }
    pairs=0
    for name,columns in paired_specs.items():
        for _,g in frames[name].groupby(['model_id','replicate_id']):
            reference=None
            for _,scenario in g.groupby('scenario_id'):
                comparable=scenario[columns].sort_values(columns[0]).reset_index(drop=True)
                if reference is None:reference=comparable
                else:pd.testing.assert_frame_equal(reference,comparable,check_exact=True);pairs+=1
    result={'simulation_id':receipt['simulation_id'],'passed':True,
            'audit_method':'Independent arithmetic from saved CSV inputs; no engine import/function calls. Cross covariance replay uses orthogonal-factor decomposition.',
            'engine_and_csv_hashes_verified':True,'all_rows_synthetic':True,
            'scenario_runs_replayed':len(frames['ml_runs']),
            'member_security_outputs_replayed':sum(len(frames[x]) for x in ['ml_market_members','ml_concentration_positions','ml_liquidity_allocations','ml_cross_members']),
            'paired_workload_comparisons':pairs,
            'comparison_counts':dict(counts),'max_absolute_differences':dict(maxima),
            'claim_limit':'Implementation arithmetic under hypothetical assumptions; not empirical validation or real-world confidence/probability.'}
    (ROOT/'results/independent_margin_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['simulation_id','passed','scenario_runs_replayed','member_security_outputs_replayed','paired_workload_comparisons']}))
    return result


if __name__=='__main__':audit()
