from pathlib import Path
import json, shutil, hashlib
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parents[1]
OLD=PROJECT/'risk_business_ml/transmission_chain_tests_2026_10_16'
REG=PROJECT/'reports/transmission_chain_alignment_2026_10_21/output/chain_registry_v3.json'

def main():
    for sub in ['inputs','inputs/pqd','data','results','figures']:(ROOT/sub).mkdir(parents=True,exist_ok=True)
    sources={
      REG:'chain_registry_v3.json', OLD/'inputs/market_daily.csv':'market_daily.csv',
      OLD/'inputs/response_quarterly.csv':'response_quarterly.csv',
      OLD/'data/DCPF3M.csv':'DCPF3M.csv',OLD/'data/DTB3.csv':'DTB3.csv',
      PROJECT/'data_refresh_2026_10_14/data/ficc_gsd_mbsd_monthly_volumes.csv':'ficc_monthly.csv',
      OLD/'analysis_plan.json':'legacy_analysis_plan.json',
      OLD/'results/chain_status_EN.csv':'legacy_status_EN.csv',
      OLD/'results/chain_status_CN.csv':'legacy_status_CN.csv',
    }
    sources.update({p:'pqd/'+p.name for p in (OLD/'inputs/pqd').glob('*') if p.suffix in ['.xlsx','.pdf']})
    hashes=[]
    for p,name in sources.items():
        dest=ROOT/'inputs'/name
        if dest.exists():assert dest.read_bytes()==p.read_bytes()
        else:shutil.copy2(p,dest)
        hashes.append(dict(original_path=str(p),frozen_copy=str(dest.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    (ROOT/'input_manifest.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2)+'\n')
    old=json.loads((ROOT/'inputs/legacy_analysis_plan.json').read_text())
    plan=dict(prepared_at_utc=datetime.now(timezone.utc).isoformat(),
      question='Evaluate the 31 previously untested reference chains without transferring legacy pass labels.',
      definition_version='v3',chain_ids=json.loads(REG.read_text())['newly_added_chain_ids'],
      status='Exploratory extension after previous results were known; not preregistered and no untouched holdout.',
      framework='S times V, with chain matching as a relevance gate; no separate E multiplier; missing V remains missing.',
      market_snapshot_cutoff='2026-10-13',new_source_request_cutoff='2026-10-20',pqd_cutoff='2026Q2',
      events=old['events'],event_weekly=old['test1_weekly'],event_daily=old['test1_ecs_daily'],
      quarterly=old['test2_primary'],
      monthly=dict(minimum_observations=36,bootstrap_block_months=12,resamples=2000,seed=20261016,pass_component='positive rho >=0.3 and 95% paired moving-block lower bound >0; BH q supplementary'),
      no_overall_proxy_pass=True,
      definition_gate='A statistical result on an aggregate, adjacent market, or replacement outcome is a component/proxy result, not validation of a named-member or service-specific process.',
      case_gate='Record named event, actor/service role, process response, timing and limits. Rule text verifies a possible mechanism; it does not establish a historical impact. No inference from missing incidents to zero incidents.',
      tests=[
        dict(id='GCF_FUNDING',chain='FICC-GSD-05',signal='prior-only seasonally adjusted SOFR-EFFR high-shock dummy',outcome='OFR GCF minus DVP overnight/open final-vintage rate spread, bp',method='same-day OLS + month/quarter end, HAC5; positive coefficient and p<0.05',scope='funding-price proxy, not collateral-allocation deadlines or funds-settlement failures'),
        dict(id='MMF_GCF',chain='FICC-GSD-07',signal='negative quarterly MMF repo asset transactions, USD million (FU632051000)',outcome='negative quarterly log change in mean GCF transaction volume',method='same-quarter Spearman, next-quarter secondary, four-quarter blocks',scope='MMF market allocations and GCF activity; MMF series includes Fed counterparties; no CCIT-specific lender withdrawals'),
        dict(id='TRIPARTY_GCF',chain='FICC-GSD-07',signal='negative monthly log change in mean non-Fed triparty transaction volume',outcome='negative monthly log change in mean GCF transaction volume',method='separately declared supplementary monthly proxy, 12-month blocks',scope='neither named MMF investors nor CCIT; possible market substitution, no pre-assigned chain pass'),
        dict(id='CROSS_MARGIN',chain='FICC-GSD-09',signal='quarterly maximum absolute daily 10-year Treasury yield change, bp',outcome='GSD end-quarter IM qoq change',method='same-quarter Spearman, next-quarter secondary, four-quarter blocks',scope='cash-rate and aggregate margin proxies; missing futures return and linked-account Required Fund Deposit; extract 20.7.2 for description only, no preassigned direction for savings'),
        dict(id='AUCTION_GSD',chain='FICC-GSD-10',signal='monthly log change of offered Treasury amount grouped by issue/settlement month, bills+notes+bonds',outcome='monthly log change in GSD settled amount',method='same-month Spearman, next-month secondary; 12-month blocks; supplementary OLS with month effects, HAC3',scope='supply-to-aggregate-throughput proxy; no GSD auction-only purchases or disruption outcome; auction tails not computed without when-issued yields'),
        dict(id='TBA_PIPELINE',chain='FICC-MBSD-06',signal='MBSD average cleared notional, PQD23.1.2 OTC',outcome='MBSD novated but not-yet-settled notional, PQD23.2.1',method='same-quarter levels Spearman, next-quarter and calendar first-difference sensitivities',scope='business activity proxy for pipeline; no initiation-month/forward-settlement tenor breakdown and not an independent external shock'),
        dict(id='CONCENTRATION',chain='ECS-NSCC-04',signal='NSCC top-five open-position average share, PQD18.2.2',outcome='NSCC top-five IM average share, PQD18.3.2',method='internal-data diagnostic only; quarterly Spearman and differences',scope='top-five sets need not be same members; no named-member concentration add-on or external shock, so cannot validate reference mechanism'),
        dict(id='SLD_LIQUIDITY',chain='ECS-NSCC-05',signal='quarterly VIX maximum',outcome='NSCC maximum single-day VM paid, PQD6.7.1',method='same-quarter Spearman, next-quarter secondary, four-quarter blocks',scope='liquidity-demand proxy; VM is not a supplemental liquidity deposit and cannot inherit its pass label'),
      ],
      event_candidates=[
        dict(chain='FICC-GSD-05',signal='funding',mode='weekly',events=['repo_2019','covid_2020','treasury_2025']),
        dict(chain='FICC-GSD-07',signal='triparty_withdrawal',mode='weekly',events=['repo_2019','covid_2020','svb_2023','treasury_2025']),
        dict(chain='FICC-GSD-09',signal='ust10_abs_change',mode='weekly',events=['covid_2020','svb_2023','treasury_2025']),
        dict(chain='ECS-NSCC-05',signal='vix',mode='daily',events=['covid_2020','meme_2021','vol_2024','treasury_2025']),
        dict(chain='ECS-NSCC-09',signal='funding',mode='weekly',events=['svb_2023','treasury_2025'],restriction='SFT launched in 2022; exclude older events; funding signal not SFT-specific'),
        dict(chain='ECS-DTC-01',signal='cp_bill_spread',mode='weekly',events=['covid_2020','svb_2023']),
        dict(chain='ECS-DTC-06',signal='vix',mode='daily',events=['covid_2020','meme_2021','vol_2024','treasury_2025'],restriction='daily VIX is only a proxy for intraday moves; no NDC/CM blocked-delivery measurements'),
      ],
      quarterly_fund_flow_note='Quarterly fund-flow data cannot satisfy the legacy daily/weekly event test. Any quarterly event comparisons are descriptive and separately labelled.',
      statistics_note='No loss probabilities, calibrated risk scores, causal effects or new ML forecast claims. Existing model and results remain frozen.',
      references=['Legacy October16 analysis_plan.json','quant-tech statistical-inference notes: dependence and rare-event small-sample limitations','scipy.stats.spearmanr and statsmodels HAC routines'],
    )
    target=ROOT/'analysis_plan.json'
    if target.exists():
        previous=json.loads(target.read_text());plan['prepared_at_utc']=previous['prepared_at_utc']
        assert previous==plan,'Plan exists; do not silently revise after results.'
    else:target.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    print('Frozen',len(sources),'inputs and 31-chain analysis plan before calculation.')

if __name__=='__main__':main()
