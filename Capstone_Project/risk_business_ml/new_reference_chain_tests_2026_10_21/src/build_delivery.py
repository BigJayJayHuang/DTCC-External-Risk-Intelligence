from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import json,re,sys,hashlib
import pandas as pd
from chain_review_notes import NOTES

ROOT=Path(__file__).resolve().parents[1]
LABELS={
 'PARTIAL_NUMERIC':{'CN':'已做部分数值检验','EN':'Partial numerical tests'},
 'CASE_REVIEW_ONLY':{'CN':'仅案例/条件核对','EN':'Case/condition review only'},
 'NOT_RUN_DATA_GAP':{'CN':'未运行：缺专属数据','EN':'Not run: specific data missing'},
}
TEST_NAMES={
 'GCF_FUNDING':('GCF 融资价差','GCF funding spread'),
 'MMF_GCF':('货币基金回购流量→GCF 活动','MMF repo flows to GCF activity'),
 'TRIPARTY_GCF':('非美联储三方回购→GCF（补充）','Non-Fed triparty to GCF (supplementary)'),
 'CROSS_MARGIN':('利率冲击→GSD 总保证金（代理）','Rate shock to GSD aggregate margin (proxy)'),
 'AUCTION_GSD':('拍卖供给→GSD 总交收（代理）','Auction supply to GSD total settlement (proxy)'),
 'TBA_PIPELINE':('MBSD 清算量→未交收头寸（代理）','MBSD cleared notional to unsettled positions (proxy)'),
 'CONCENTRATION':('NSCC 集中度→保证金份额（内部诊断）','NSCC concentration to margin share (internal diagnostic)'),
 'SLD_LIQUIDITY':('VIX→NSCC VM 支付（非 SLD）','VIX to NSCC VM payments (not SLD)'),
}
SOURCES=[
 dict(id='OFR',url='https://data.financialresearch.gov/',local='raw/REPO-GCF_TV_TOT-F_metadata.json',note='New final-vintage repo data with separately downloaded metadata. Final series end2026-06-30; rate matched sample is much shorter than volume history.'),
 dict(id='TREASURY',url='https://www.treasurydirect.gov/legal-information/developers/web-api-security/',local='raw/treasury_auctions_all.json',note='Server ignored request date filter; 11158 records received; local completed-auction and date filters retained3594 records. Offering amount is not actual awarded amount or auction tail.'),
 dict(id='FED_Z1',url='https://www.federalreserve.gov/releases/z1/20260911/z1_csv_files.zip',local='raw/fed_z1_20260911.zip',note='September11 2026 release. FU632051000.Q MMF repo asset transactions and FU653164205.Q mutual-fund net share issuance, USD million, not seasonally adjusted.'),
 dict(id='PQD',url='https://www.dtcc.com/legal/policy-and-compliance',local='inputs/pqd/',note='Frozen2020Q4–2026Q2 sources;22 XLSX plus one2024Q4 PDF. Additional cell extraction covers22 quarters, not an invented23rd spreadsheet.'),
 dict(id='FINANCIALS',url='https://www.dtcc.com/legal/financial-statements',local='inputs/financials/',note='23 FICC financial statement guarantee-note tables, with page evidence;23.2.1 early scale discrepancies and missing2024Q4 spreadsheet outcome reconciled explicitly.'),
 dict(id='LEGACY_MARKET',url='https://fred.stlouisfed.org/',local='inputs/market_daily.csv',note='Frozen prior market observations; individual dates differ. Not a fresh daily market update. DCPF3M/DTB3 frozen separately.'),
 dict(id='RULES_INDEX',url='https://www.dtcc.com/legal/rules-and-procedures',local='raw/dtcc_rules_index.html',note='Official current links resolve to files.dtcc.com. Current rules support mechanisms, not historical incidents or historical rule versions.'),
 dict(id='NSCC_RULES',url='https://files.dtcc.com/download/assets/nscc_rules.pdf/85bda02a369211f0a3ae820bd5ac0897',local='raw/nscc_rules_current.pdf',note='Rule4A SLD, Rule9 ESS, ACATS, I&RS, AIP, SFT and international-link provisions; September21 2026 version.'),
 dict(id='GSD_RULES',url='https://files.dtcc.com/download/assets/FICC-GSD%2BRulebook%2B%E2%80%93%2B2026-0826%2BFinal.pdf/b6c07124ceb411f09c9062cd3fe05a01',local='raw/gsd_rules_current.pdf',note='GCF, CCIT, auction purchases, cross-margining and ACS definitions.'),
 dict(id='MBSD_RULES',url='https://files.dtcc.com/download/assets/ficc_mbsd_rules.pdf/d410be52369111f0b606526112f6cc5f',local='raw/ficc_mbsd_rules.pdf',note='Watch List, pool settlement/fails, options, market/system disruption rules.'),
 dict(id='EPN_RULES',url='https://files.dtcc.com/download/assets/ficc_mbsd_epnrules.pdf/4c561ca4369211f09a845e09fb65ecc7',local='raw/epn_rules.pdf',note='EPN message and cybersecurity obligations; no message-error or attack history inferred.'),
 dict(id='DTC_RULES',url='https://files.dtcc.com/download/assets/dtc_rules.pdf/6064c95e369511f09a845e09fb65ecc7',local='raw/dtc_rules_current.pdf',note='MMI, settling banks, Canadian-Link, chills/locks, segregation and disruption provisions; April28 2026 version.'),
 dict(id='DTC_SETTLEMENT',url='https://files.dtcc.com/download/assets/Settlement.pdf/c83a99be369a11f093d0c204a2f8334f',local='raw/dtc_settlement_guide.pdf',note='Funding acknowledgments, NDC and Collateral Monitor controls. No participant exception logs collected.'),
 dict(id='SEC_CHILL',url='https://public-inspection.federalregister.gov/2014-06459.pdf',local='raw/sec_dtc_chill_2014.pdf',note='Historical SEC procedural discussion of DTC restrictions and International Power; does not establish a matched suspension-to-lock event series.'),
 dict(id='SEC_IPWG',url='https://www.sec.gov/news/digest/2012/dig031512.htm',local=None,note='Web text reviewed, lines101–103; confirms DTC suspension/procedural remand for IPWG; direct local request403. No inference that every SEC halt causes a lock.'),
 dict(id='ACATS_LEHMAN',url='https://www.dtcc.com/-/media/Files/pdf/2008/9/22/a6705.pdf',local=None,note='Official search-index excerpt only; body404. Describes no new Lehman ACATS initiation requests after September22 2008. Not a complete volume/duration test.'),
 dict(id='ACATS_PROJECT',url='https://www.dtcc.com/-/media/Files/pdf/2012/12/21/a7556.pdf',local=None,note='Official search-index excerpt only; body404. Describes Lehman-related ACATS process initiatives, not quantitative volumes.'),
 dict(id='CARTER_CLOSURE',url='https://www.dtcc.com/-/media/Files/pdf/2024/12/30/0275.pdf',local=None,note='Official search-index excerpt only; body404. Announcement that DTCC subsidiaries remain open for available settlement on January9 2025; condition check, not a post-event outage log.'),
 dict(id='ACS_LAUNCH',url='https://www.dtcc.com/press-releases/2025/dtccs-ficc-now-live-with-new-treasury-clearing-capabilities',local='raw/acs_launch_2025.html',note='Enhanced ACS launch March2025. Do not assign pre-launch crisis outcomes to this configuration.'),
 dict(id='SFT_ACCESS',url='https://www.dtcc.com/press-releases/2026/dtcc-receives-regulatory-approval-to-launch-new-client-access-model-for-nsccs-sft-clearing-service',local='raw/sft_access_2026.html',note='May13 2026 access-model extension; not an adverse outcome or time series. SFT launched2022 per DTCC2022 annual-report indexed text.'),
 dict(id='CDS',url='https://www.cds.ca/resource/en/56',local='raw/cds_financial_risk_model_2025.pdf',note='CDS link risk model; infrastructure CDS is not a credit-default swap. No link-outage history collected.'),
 dict(id='CFTC_MFG',url='https://www.cftc.gov/PressRoom/PressReleases/6626-13',local='raw/cftc_mfglobal.html',note='MF Global customer-fund enforcement history. Does not establish involvement of DTC Rule36/37 accounts.'),
]

def text_result(row,lang):
    if row.test_id=='GCF_FUNDING':
        return f"n={int(row.n)}; β={row.coefficient_bp:.3f} bp; HAC p={row.hac_p:.3f}; 95% CI [{row.ci_low:.3f}, {row.ci_high:.3f}]"
    return f"n={int(row.n)}; ρ={row.rho:.3f}; 95% CI [{row.ci_low:.3f}, {row.ci_high:.3f}]"

def main():
    registry=json.loads((ROOT/'inputs/chain_registry_v3.json').read_text());chains=[c for c in registry['chains'] if c['chain_id'] in registry['newly_added_chain_ids']]
    assert set(NOTES)=={c['chain_id'] for c in chains}
    result=pd.read_csv(ROOT/'results/association_results.csv');events=pd.read_csv(ROOT/'results/event_test_summary.csv')
    tba=result[(result.test_id=='TBA_PIPELINE')&(result.lag==0)].iloc[0]
    tba_ex=result[result.test_id.eq('TBA_PIPELINE_EXCLUDE_REPAIRED')].iloc[0]
    primary=result[result.role.isin(['primary','internal_diagnostic','supplementary_proxy'])&result.lag.eq(0)]
    counts=Counter(NOTES[c['chain_id']][0] for c in chains)
    assert counts==dict(PARTIAL_NUMERIC=10,CASE_REVIEW_ONLY=4,NOT_RUN_DATA_GAP=17)
    assert result.chain_id.nunique()==7
    reviewed_at=datetime.now(timezone.utc).isoformat()
    all_rows={}
    for lang in ['CN','EN']:
        rows=[]
        for c in chains:
            cid=c['chain_id'];cat,cn,en,gap_cn,gap_en=NOTES[cid]
            er=events[events.chain_id.eq(cid)];ar=primary[primary.chain_id.eq(cid)]
            if len(er):
                e=er.iloc[0]; event=f"{e.status}; {int(e.events_hit)}/{int(e.events_available)}; " + (f"非事件预警比例 {e.non_event_alert_proxy:.1%}" if lang=='CN' else f"non-event alert proxy {e.non_event_alert_proxy:.1%}")
            else:event='未运行：缺适用日/周信号、事件或专属结果' if lang=='CN' else 'Not run: applicable signal/events or process data unavailable'
            assoc=' | '.join(r.test_id+': '+text_result(r,lang) for _,r in ar.iterrows()) or ('未运行：缺专属结果' if lang=='CN' else 'Not run: service-specific outcome unavailable')
            rows.append(dict(chain_id=cid,dtcc_process=c['dtcc_process'][lang],work_status=LABELS[cat][lang],event_test=event,outcome_test=assoc,
               finding=cn if lang=='CN' else en,full_chain_status='尚未验证（不是全部失败）' if lang=='CN' else 'Not yet validated (not a blanket failure)',
               missing_data=gap_cn if lang=='CN' else gap_en,numerical_component_executed=cat=='PARTIAL_NUMERIC',full_chain_validated=False))
        frame=pd.DataFrame(rows);frame.to_csv(ROOT/'results'/f'new_chain_status_{lang}.csv',index=False,encoding='utf-8-sig' if lang=='CN' else 'utf-8');all_rows[lang]=rows
    # Updated view of definitions + new evidence. Freeze legacy definitions/mappings/results intact.
    updated=json.loads(json.dumps(registry));updated['validation_run_date']='2026-10-21';updated['new_chain_review_complete']=True
    updated['validation_results_base']='results/';updated['complete_new_chain_validation_count']=0
    for c in updated['chains']:
        if c['chain_id'] not in NOTES:continue
        cat=NOTES[c['chain_id']][0]
        c.update(validation_status='not_yet_fully_validated',review_status=cat,data_readiness='partial_public_data_only',reviewed_at_utc=reviewed_at,
                 numerical_component_executed=cat=='PARTIAL_NUMERIC',full_chain_validated=False,historical_results_inherited=False,
                 results_file='results/new_chain_status_EN.csv')
    for k in ['mappings','legacy_status_CN','legacy_status_EN']:assert updated[k]==registry[k]
    assert updated['chains'][:25]==registry['chains'][:25]
    (ROOT/'chain_registry_v3_with_test_status.json').write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'results/source_register.json').write_text(json.dumps(SOURCES,ensure_ascii=False,indent=2)+'\n')
    summary=json.loads((ROOT/'run_manifest.json').read_text());summary.update(status_counts=dict(counts),reviewed_chains=31,distinct_numerically_screened_chains=10,event_component_passes=int(events.status.eq('PASS_COMPONENT').sum()),unique_event_signals=5,full_chain_validations=0)
    (ROOT/'results/review_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    for lang in ['CN','EN']:
        if lang=='CN':
            lines=['# 31 条新增传导链：检验汇总','', '2026-10-21 · 定义 v3 · 探索性分析','',
             '**31 条均完成数据与证据核对，但并非 31 条都能做数值检验。** 10 条运行了部分事件筛查、关联或内部诊断；4 条仅做案例/条件核对；17 条仍缺专属数据。尚无新增链完成整条链验证。这不意味着 31 条链全部无效。','',
             '7 条链运行事件筛查，复用 5 个信号；其中 5 条链的信号达到旧筛查门槛，实际上只涉及 3 个不同信号（融资、国债收益率变化、VIX）。8 种关联/诊断规格覆盖 7 条链，包括一项补充规格和一项内部诊断。不能把重复使用的信号或替代结果算成新的独立验证。','',
             '## 主要发现','',
             '- **拍卖供给→GSD 总交收**：同月变化 ρ=0.578，95% 区间 [0.451,0.688]，n=104 月。控制月份效应的 OLS-HAC p=0.204，稳健性不足；测量的是总业务吞吐，不是拍卖交收故障。',
             f'- **MBSD 活动→未交收头寸**：水平 ρ={tba.rho:.3f}，区间 [{tba.ci_low:.3f},{tba.ci_high:.3f}]，n={int(tba.n)} 季；连续季度差分 ρ={tba.rho_changes:.3f}，后期水平 ρ={tba.rho_later:.3f}。剔除两期清算额单位修正值后，水平 ρ={tba_ex.rho:.3f}、差分 ρ={tba_ex.rho_changes:.3f}。关联值得继续研究，但仍缺独立外部冲击与真正的 TBA 远期管道。',
             '- **利率→GSD 总保证金**：ρ=0.408，区间 [-0.014,0.764]，n=22，未达旧关联门槛；缺期货端和跨保证金账户数据。',
             '- **融资压力→GCF 价格**：HAC 系数 0.021 bp、p=0.976，n=246 日；不支持该代理规格，也不能据此否定抵押品/资金交收机制。',
             '- **NSCC 流动性**：VIX→VM 峰值 ρ=0.326，但区间跨零。VM 不是 SLD；下一季度 ρ=0.408 是单独的次要结果，不能取代主规格。',
             '- 非美联储三方回购收缩没有命中预设四个压力窗口；商业票据利差信号只命中两个窗口之一。保留结果，不换窗口追求通过。','',
             '## 方法与边界','',
             '沿用旧方法：阈值仅用历史数据，日度为前252个有效观测的90分位、周度为前52周峰值的90分位；事件至少可观察两次、命中率至少2/3、非事件预警代理比例不超过15%，日度还要求事件内预警比例中位数至少25%。“非事件预警”不是真实误报率：事件清单不穷尽。', '',
             '关联以同季度为主、下一季度为次；季度配对四季区块 bootstrap 2,000次，月度十二个月区块，固定种子20261016。旧季度门槛为 n≥12、ρ≥0.3、95%下界>0；新增月度规格要求n≥36。6项主规格做BH校正，普通p值/BH本身不校正时间依赖；依赖不确定性主要由区块区间/HAC体现。内部诊断和补充规格单列，不参与主规格选择。', '',
             '方案在新相关性计算前固定，但旧结果和历史事件已知，因此不是预注册，也无盲测留出集。辅助数据使用当前修订/最终版本；下一期配对仅为描述性领先滞后关系，尤其联储季度流量有发布滞后，不能当成真实时间预测能力。当前规则只说明可行机制，不能追认历史年份已适用同一规则。','',
             '框架仍为 S×V，不加 E 乘数。相关性检验不是脆弱度打分；没有为新增服务臆造V、权重、损失概率或机器学习风险分数。','',
             '## 数据核对与覆盖','',
             '发现2020Q4–2021Q3的GSD/MBSD PQD23.2.1原始数值较财务保证附注小1,000倍。逐期核对23份财务报表，早期不一致值使用附注“十亿美元”换算，原值仍保留；2024Q4无新增XLSX字段，未交收结果由当期财务附注明确补入。清算量仍缺该季，主配对n=22。修正规则和逐项证据见 data_quality_amendment.json、data/financial_guarantee_reconciliation.csv。', '',
             '另有2021Q3、2022Q3的MBSD23.1.2清算额数值疑似以百万美元编码。按×1,000,000解读后，均与独立月度清算面值合计÷64个国债观测日所得日均额在50.1万美元的舍入容差内匹配。按该交叉核对解释单位，同时另做剔除这两期的敏感性检验；不凭相关性推断单位。见 data/mbsd_cleared_notional_reconciliation.csv。', '',
             '新下载OFR最终数据截至2026-06-30；新拍卖记录筛选至2026-10-20，完整月度分析截至2026-09；联储流量截至2026Q2、版本2026-09-11。原市场快照各序列截至10月9日或13日，未改称10月21日行情。PQD结果截至2026Q2。每个序列实际覆盖见 results/series_coverage.csv。', '',
             '增强型ACS于2025年3月上线，SFT服务于2022年推出；不把更早事件当成这些服务配置的历史结果。Lehman和Carter历史通知目前仅取得DTCC官方索引摘录、正文链接404，因此相关案例仅为有限线索/条件核对，不能标成完整案例验证。', '',
             '## 逐链状态','', '| 链编号 | 已做工作 | 解释与关键缺项 |','|---|---|---|']
        else:
            lines=['# Test Summary: 31 New Transmission Chains','', 'October21,2026 · Definition v3 · Exploratory analysis','',
             '**All31 received an evidence/data review; not all31 support numerical testing.** Ten received partial event/association/internal diagnostics, four only case/condition reviews, and17 still lack specific data. No new chain is fully validated. This is not a blanket finding that all31 mechanisms are invalid.','',
             'Event screening covers seven chains using five shared signals. Five chain views meet the old event threshold, representing only three distinct signals: funding, Treasury-yield changes and VIX. Eight association/diagnostic specifications cover seven chains, including one supplementary proxy and one internal diagnostic. Repeated signals and replacement outcomes are not independent validations.','',
             '## Findings','',
             '- **Auction supply to GSD total settlement:** same-month changes have rho0.578, 95% interval[0.451,0.688], n104 months. Month-effect OLS-HAC p0.204 weakens robustness. This is aggregate throughput, not auction-specific settlement disruption.',
             f'- **MBSD activity to unsettled positions:** levels rho{tba.rho:.3f}, interval[{tba.ci_low:.3f},{tba.ci_high:.3f}], n{int(tba.n)} quarters; consecutive-quarter changes rho{tba.rho_changes:.3f} and later-period levels rho{tba.rho_later:.3f}. Excluding the two activity-unit repairs gives levels rho{tba_ex.rho:.3f} and changes rho{tba_ex.rho_changes:.3f}. The association merits further work, but an independent external shock and actual forward-TBA pipeline detail remain missing.',
             '- **Rate shock to GSD aggregate margin:** rho0.408, interval[-0.014,0.764], n22; below the old association gate. Futures and linked-account margin data are missing.',
             '- **Funding to GCF price:** HAC coefficient0.021bp, p0.976, n246 days. The proxy specification is unsupported; this does not disprove collateral/funds-settlement mechanisms.',
             '- **NSCC liquidity:** VIX to peak VM rho0.326, with an interval crossing zero. VM is not SLD. Next-quarter rho0.408 is a separate secondary result, not a replacement for the primary specification.',
             '- Non-Fed triparty contraction hit none of four predefined stress windows; the CP spread hit only one of two. The original windows and failures were retained.','',
             '## Methods and limitations','',
             'Legacy rules are retained: past-only90th-percentile thresholds over252 valid daily observations or52 weekly peaks; at least two observable events, event-hit fraction>=2/3 and non-event alert proxy<=15%; daily tests additionally require median in-window alarm share>=25%. Non-event alert share is not a true false-positive rate because the event list is incomplete.','',
             'Same-quarter associations are primary; next-quarter associations are secondary. Confidence intervals use2,000 paired moving-block resamples: four consecutive quarters or12months, seed20261016. The old quarterly component gate is n>=12, rho>=0.3 and95% lower bound>0; new monthly specifications require n>=36. BH correction covers six primary specifications. Ordinary p/BH do not themselves remove serial dependence; block intervals/HAC address dependence uncertainty. Internal and supplementary diagnostics stay separate.','',
             'The plan was fixed before new correlations were calculated, after previous results and historical events were known. It is not preregistered and has no blind holdout. Auxiliary series are current revised/final vintages. Lead-lag pairs are descriptive, not real-time predictive performance, particularly given quarterly Financial Accounts publication delays. Current rules establish possible mechanisms, not the applicable rule version in every historical event.','',
             'The framework remains S times V with no separate E multiplier. Association tests are not vulnerability scores. No new service V, weights, loss probabilities or ML risk scores were invented.','',
             '## Data reconciliation and coverage','',
             'GSD/MBSD PQD23.2.1 values for2020Q4–2021Q3 were1,000times smaller than contemporaneous guarantee-note disclosures. All23 financial statements were checked; inconsistent early outcomes use the financial-note billion-USD conversion while retaining raw PQD values. The missing2024Q4 spreadsheet outcome is explicitly supplied by its financial note; cleared-notional data remain missing, so primary pairs n22. See data_quality_amendment.json and data/financial_guarantee_reconciliation.csv.','',
             'MBSD23.1.2 activity for2021Q3/2022Q3 appears million-USD encoded. Multiplying by1,000,000 matches independent monthly clearing-par totals divided by64 Treasury-observation business dates to within0.501million USD rounding tolerance in each quarter. This cross-source unit interpretation is accompanied by a sensitivity excluding both repaired periods; units were not inferred from correlations. See data/mbsd_cleared_notional_reconciliation.csv.','',
             'New OFR final data endJune30,2026; auctions are filtered throughOctober20, with complete-month analysis throughSeptember2026; Financial Accounts flows end2026Q2 in the September11 release. Frozen market series endOctober9 or13 and are not relabelled as October21 observations. PQD outcomes end2026Q2. Exact spans are in results/series_coverage.csv.','',
             'Enhanced ACS launched in March2025 and SFT in2022; earlier crises are not outcomes of those configurations. Historical Lehman/Carter notices were available only as official search-index excerpts, with404body URLs; these remain limited leads/condition checks, not complete historical-case validation.','',
             '## Chain-by-chain status','', '| Chain | Work completed | Interpretation and required evidence |','|---|---|---|']
        for row in all_rows[lang]:
            lines.append('| '+row['chain_id']+' | '+row['work_status']+' | '+row['finding']+' '+row['missing_data']+' |')
        lines += ['', '## '+('已执行数值结果' if lang=='CN' else 'Executed numerical results'),'','| '+('规格 | 样本与结果 | 解释' if lang=='CN' else 'Specification | Sample and result | Scope')+' |','|---|---|---|']
        for _,row in primary.iterrows():
            name=TEST_NAMES[row.test_id][0 if lang=='CN' else 1]
            threshold=('数值分量达门槛；整链未验证' if lang=='CN' else 'Component gate met; full chain unvalidated') if row.component_threshold_met else ('数值分量未达门槛；并非否定机制' if lang=='CN' else 'Component gate unmet; mechanism not disproved')
            if row.role=='internal_diagnostic':threshold='仅内部诊断，不是外部冲击验证' if lang=='CN' else 'Internal diagnostic, not external-shock validation'
            lines.append('| '+name+' | '+text_result(row,lang)+' | '+threshold+' |')
        lines+=['','![Quarterly confidence intervals](figures/quarterly_components.png)','','![MBSD levels and changes](figures/mbsd_levels_changes.png)','',
          '## '+('交付与复跑' if lang=='CN' else 'Files and reproduction'),'',
          '- '+('[逐链CSV](results/new_chain_status_CN.csv)' if lang=='CN' else '[Chain status CSV](results/new_chain_status_EN.csv)'),
          '- [Executed notebook](New_Reference_Chain_Validation.ipynb)',
          '- [All association results](results/association_results.csv) / [event results](results/event_test_summary.csv)',
          '- [Source register](results/source_register.json) / [fetch attempts](fetch_manifest.json)',
          '- [Updated catalog view](chain_registry_v3_with_test_status.json)',
          '', '## '+('主要公开来源' if lang=='CN' else 'Public-source references'),'']
        for s in SOURCES:lines.append(f"- [{s['id']}]({s['url']}): {s['note']}")
        (ROOT/f'Concise_Test_Summary_{lang}.md').write_text('\n'.join(lines)+'\n')
    readme='''# New Reference Chain Tests / 新增传导链检验

2026-10-21. Start with **Concise_Test_Summary_CN.md** or **Concise_Test_Summary_EN.md**.
All31 chains were reviewed;10 received partial numerical diagnostics,4 case/condition reviews,
and17 remain unrun for lack of specific data. No new chain is fully validated.
原有25条定义、22条旧映射及历史结果不变。新增检验没有校准风险评分或证明因果。

The root contains bilingual summaries, an executed notebook and an updated catalog view.
`results/` contains all31 statuses, statistics and provenance; `data/` exact pairs and cell/page
evidence; `inputs/` frozen source data; `raw/` public downloads; `src/` runnable scripts.
Files are grouped in this one folder. The earlier catalog is a definition snapshot; use the
new `chain_registry_v3_with_test_status.json` for the review status.

New public inputs have also been stored in the existing project database:12,714 additional
records,55,436 total. See **DATABASE_UPDATE_CN_EN.md** for dataset counts, provenance,
SQL examples and the distinction between this batch import and daily collectors.

## Offline reproduction

Use Python3.12+ with `requirements.txt` (actual analysis used Python3.13).

```bash
python3 src/run_tests.py
python3 src/build_delivery.py
python3 src/make_notebook.py
```

The executed notebook also reruns calculations offline. To rebuild the financial source
reconciliation separately, install pypdf and run `python3 src/extract_financial_guarantees.py`.
Optional live collection is in `src/collect_sources.py`; it is not needed for offline reruns.
`prepare_plan.py` was used only to freeze inputs from the original workspace.

Do not overwrite the original October16 tests or infer a pass from matching IDs.
Review `data_quality_amendment.json` before using PQD23.2.1. Historical rule versions,
publication lags, quarterly revision vintages and service-specific outcome gaps remain limits.
'''
    (ROOT/'README.md').write_text(readme)
    print('31 bilingual statuses, summaries, source register and tested catalog view saved.')

if __name__=='__main__':main()
