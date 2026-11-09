"""Publish inspectable DAS research data; missing internal measurements stay missing."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

from validate_outputs import load_bound_sources, validate_understanding

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parents[1]

def dump(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def csvwrite(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader()
        for r in rows: w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})

def rows_for_database(result, sources, availability):
    values=[]
    for s in sources: values.append(('das_source_documents',s['source_id'],s,s['source_id']))
    for f in result['facts']: values.append(('das_public_facts',f['fact_id'],dict(f,business_line='DAS',evidence_status='SOURCE_QUOTE_CHECKED_INTERPRETATION_REVIEW_REQUIRED'),f['source_id']))
    for c in result['chains']: values.append(('das_chain_candidates',c['card_id'],dict(c,business_line='DAS',status='HYPOTHESIS_REVIEW_REQUIRED',empirical_validation='NOT_RUN_MISSING_INTERNAL_OUTCOMES'),c['mechanism_evidence_source_id']))
    for a in availability: values.append(('das_v_availability',a['card_id']+'|'+a['quarter'],a,None))
    for folder in ('aws_reading','aws_reading_recovery','aws_reading_reviewed'):
        p=ROOT/folder/'attempt.json'
        if p.exists(): values.append(('das_api_reading_runs',folder,json.loads(p.read_text()),None))
    return values

DESCRIPTIONS={
    'das_source_documents':('Official public DAS document retrieval inventory','source document','Publication time and collection time are distinct; unsuccessful retrieval is not evidence absence.'),
    'das_public_facts':('AWS-extracted public DAS facts with source quotations','fact','Public disclosures and controls are not observed internal vulnerability.'),
    'das_chain_candidates':('AWS-proposed DAS transmission chains','candidate card','Mechanism hypotheses require team review and internal outcome data.'),
    'das_v_availability':('DAS historical internal-V availability','card-quarter','Unavailable prelaunch measurements remain null; no synthetic values have been substituted.'),
    'das_api_reading_runs':('Manual bounded AWS document-understanding receipts','API run','Estimated cost from recorded token usage, not a billing statement; no unattended automation.'),
}

def import_database(path, values, sources, make_snapshot=True):
    spec=importlib.util.spec_from_file_location('capstone_das_db',PROJECT/'capstone_database/db.py')
    db=importlib.util.module_from_spec(spec);spec.loader.exec_module(db)
    c=db.connect(path)
    run=db.start_run(c,'das_public_documents_and_api_understanding')
    counts={}
    try:
        businesses=json.loads((PROJECT/'capstone_database/businesses.json').read_text())
        configs=[dict(id='das_research_'+s['source_id'],name='DAS public evidence '+s['source_id'],url=s['url'],
                      kind='manual_official_document',refresh_hours=None,enabled=False,business_lines=['DAS']) for s in sources]
        db.register(c,configs,businesses)
        with c:
            for dataset,definition in DESCRIPTIONS.items():
                c.execute('INSERT INTO datasets VALUES(?,?,?,?) ON CONFLICT(dataset_id) DO UPDATE SET description=excluded.description,grain=excluded.grain,interpretation=excluded.interpretation',(dataset,*definition))
            blobs={}
            for s in sources:
                if s['status']=='retrieved': blobs[s['source_id']]=db.put_blob(c,(ROOT/s['raw_file']).read_bytes())
            for dataset,key,payload,sid in values:
                source='das_research_'+sid if sid else None
                change=db.upsert(c,dataset,key,payload,run,source,blobs.get(sid),evidence='public original document; API extraction is a candidate, not empirical validation')
                counts[dataset]=counts.get(dataset,0)+1
            c.execute('UPDATE runs SET finished_at=?,status=?,summary=? WHERE run_id=?',(db.now(),'completed',db.dumps(counts),run))
        packed=db.snapshot(c,path,public=True) if make_snapshot else None
        integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
        foreign_keys=list(c.execute('PRAGMA foreign_key_check'))
        return dict(rows_imported=counts,integrity_check=integrity,foreign_key_errors=len(foreign_keys),snapshot=packed)
    finally:c.close()

CN_DETAILS={
    'DAS-01':('经测试的备用处理能力／峰值所需处理量','备用站吞吐量、峰值转换指令速率，以及 LedgerScan/Factory 灾难恢复测试结果。','可做基于假设的敏感性测试。公开网络运行状态不能当成 DTS 私有网络的真实运行记录。'),
    'DAS-02':('单位时间内可解决的对账差异／同一时间尺度的峰值待解决积压','对账处理能力、受控撤销或更正调用记录、积压数量与解决时间。','可检验流程和参数敏感性；没有真实对账积压数据，不能据此验证实际风险。'),
    'DAS-03':('已核实采用多方授权控制的代币化资产／DTS 代币化资产总额','钱包密钥管理证明、对应资产金额、已注册钱包清单及制裁名单复筛记录。','可做假设覆盖率敏感性测试；合作机构名单不能直接视为已批准托管商名单。'),
    'DAS-04':('一天内可应急去代币化的头寸／受影响代币化头寸','应急转换处理能力、受影响头寸规模、应急操作手册及资格监控规则。','可测试给定监管情景下的转换负担；不能用模拟结果估计监管撤销概率。'),
    'DAS-05':('每小时转换处理能力／每小时峰值转换需求','转换吞吐量、同一小时尺度的峰值需求、排队规则和公司行动处理错误记录。','可测试假设需求下的队列和处理能力；当前没有真实 DTS 指令量或处理上限。'),
}

def bullets(value):
    return '\n'.join('- '+str(x) for x in value) if isinstance(value,list) else str(value)

def write_readme(result, sources, receipts):
    recovered=sum(s['status']=='retrieved' and s.get('retrieval_method')!='web_reader_excerpt' for s in sources)
    for lang in ('EN','CN'):
        zh=lang=='CN'
        text=['# '+('DAS 业务线：公开证据与传导链' if zh else 'DAS business line: public evidence and transmission chains'),'']
        text += [
            ('数据采集日期：2026-11-09。文档内容由现有 AWS Bedrock API 阅读、理解和提取；本地负责采集、证据核对、格式整理和入库。' if zh else
             'Collection date: 2026-11-09. The existing AWS Bedrock API read and interpreted the public documents and proposed the chains. Local code retrieved sources, checked provenance, and prepared the database.'),'',
            ('业务范围：DTC Digital Asset Solutions，重点是 DTC 托管证券的代币化、去代币化及其与传统系统的衔接。DDA 技术产品属于项目的另一条业务线。' if zh else
             'Scope: DTC Digital Asset Solutions, focusing on tokenization/de-tokenization of DTC-held securities and the connection to traditional systems. DDA technology products remain a separate project business line.'),'',
            ('本次结果是待审核的研究输入。尚未取得连续的 DAS 内部缓冲或运行结果，未进行事件—业务指标相关性检验，也未给出风险分数。' if zh else
             'These are research inputs requiring review. Continuous DAS internal buffers and operating outcomes were not obtained; event-to-business outcome correlations and risk scores have not been calculated.'),'',
            ('## 官方事实' if zh else '## Public facts'),'']
        for f in result['facts']:
            source=next(s for s in sources if s['source_id']==f['source_id'])
            statement=f['statement_zh' if zh else 'statement_en']
            text += ['- '+statement+f" ([{f['source_id']}]({source['url']}))"]
        text += ['',('## 候选传导链' if zh else '## Candidate transmission chains'),'',
                 ('以下编号为新增 DAS 研究编号，尚未改动原有 final16 卡片或生产新闻分类器。' if zh else
                  'The following new DAS research IDs do not modify the original final16 cards or production news classifier.'),'']
        for c in result['chains']:
            metric,needed,limits=CN_DETAILS[c['card_id']] if zh else (c['proposed_internal_buffer_metric'],c['exact_data_needed'],c['simulation_limits'])
            text += ['### '+c['card_id']+' '+c['name_zh' if zh else 'name_en'],'',c['transmission_pathway_zh' if zh else 'transmission_pathway_en'],'',
                     ('- 内部缓冲指标：' if zh else '- Internal-buffer metric: ')+metric,
                     ('- 所需真实数据：' if zh else '- Required real data: ')+needed,
                     ('- 模拟边界：' if zh else '- Simulation limit: ')+limits,'']
        text += [('## 验证与模型接口' if zh else '## Validation and model interface'),'',
                 ('风险框架保留 S × V，不加 E。先用业务机制确定相关性，再对外部冲击信号做事件检验；取得真实内部指标后，分别做同季度传导检验和下一季度预测检验。' if zh else
                  'Retain S × V without E. Use business mechanisms to establish relevance, screen external signals against events, and run separate same-quarter transmission and next-quarter predictive tests once real internal outcomes are available.'),'',
                 ('当前缺少连续真实 V：季度可用性表保留空值。若后续制作 2020Q4–2026Q2 的模拟序列，必须全部标成服务上线前的反事实模拟，并与真实值分表；不得称为历史实测或实证验证。' if zh else
                  'Continuous real V is unavailable: the quarterly availability table preserves nulls. Any later 2020Q4–2026Q2 simulated series must be labeled counterfactual/prelaunch and stored separately from observations; it cannot be described as measured history or empirical validation.'),'',
                 ('原有16卡的6张PQD V与10张真实公开代理V是不同层级；公开代理不是模拟值。新增DAS尚无已接受的代理V序列。见[与团队流程的衔接](TEAM_PIPELINE_ALIGNMENT_CN_EN.md)。' if zh else
                  'The existing16 cards distinguish six PQD V cards from ten actual public-proxy V cards. Public proxies are not simulated values. No accepted proxy-V series is yet available for the new DAS cards. See [team pipeline alignment](TEAM_PIPELINE_ALIGNMENT_CN_EN.md).'),'',
                 ('有合适序列后，沿用现有 V 算法：p = 历史值中小于等于当前值的比例；V = max(1, ceil(5p))。先按风险方向转换，只使用当时可获得的历史，短历史单独标记。' if zh else
                  'When a suitable series exists, reuse the V rule: p = fraction of historical values <= current value; V = max(1, ceil(5p)). Orient values toward higher risk, use only available history, and flag short histories.'),'',
                 ('## 数据与运行记录' if zh else '## Data and execution records'),'',
                 (f'- 成功下载 {recovered} 份 DTCC 官方文件，并取得 SEC 文件的网页阅读器节选（前约 11 页）。SEC 原始 39 页 PDF 直接下载返回 403，全文缺口已保留。' if zh else
                  f'- Downloaded {recovered} DTCC official documents plus a web-reader excerpt of approximately the first11 pages of the SEC letter. Direct download of the39-page SEC PDF returned HTTP403; the full-document gap remains.'),
                 ('- AWS 文档分析共运行三次：第一次达到输出长度限制；第二次候选结果未通过证据复核；第三次根据官方证据修订。原始响应和费用均保留。' if zh else
                  '- Three AWS reading calls: first output-length limit, second candidate failed source review, third source-backed revision. All raw responses and costs were retained.'),
                 ('- 按保存的配置费率和返回 token 用量估算费用：$' if zh else '- Estimated cost using saved configured rates and returned token usage: $')+receipts['total_estimated_cost_usd']+'.',
                 ('- API 候选经源文逐条复核，修订记录单独保存；准确引用不代表整条风险链已经得到实证支持。' if zh else
                  '- API candidates were checked against source excerpts with a separate correction record; exact quotation does not empirically validate a whole transmission chain.'),
                 ('- 新增资料已导入本地项目 SQLite 的独立 das_* 数据集；本批次提供独立共享快照。现有总库压缩快照没有重写，完整原文证据只保留在本地。' if zh else
                  '- Added separate das_* datasets to the live local project SQLite and supplied a dedicated shareable snapshot. The existing compressed master snapshot was not rewritten; original full-source evidence remains local.'),
                 '- [Chain registry](data/chain_candidates.json) · [Data request list](data/data_request_list.csv) · [Quarterly availability](data/quarterly_v_availability.csv)',
                 '- [Source manifest](inputs/source_manifest.json) · [Reviewed AWS interpretation](results/reviewed_understanding.json) · [Verification](results/verification.json)',
                 '- [Portable database](data/das_research.sqlite3.gz) · [Queries](queries.sql)','',
                 ('## 下一步' if zh else '## Next steps'),'',bullets(result['recommended_next_steps_zh' if zh else 'recommended_next_steps_en']),'']
        (ROOT/f'README_{lang}.md').write_text('\n'.join(text))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-project-database',action='store_true')
    args=parser.parse_args()
    docs=load_bound_sources(ROOT)
    result=json.loads((ROOT/'results/reviewed_understanding.json').read_text())
    errors=validate_understanding(result,docs)
    if errors: raise ValueError('DAS extraction needs revision: '+str(errors))
    sources=json.loads((ROOT/'inputs/source_manifest.json').read_text())
    cards=[dict(c,business_line='DAS',status='HYPOTHESIS_REVIEW_REQUIRED',empirical_validation='NOT_RUN_MISSING_INTERNAL_OUTCOMES') for c in result['chains']]
    dump(ROOT/'data/chain_candidates.json',cards)
    csvwrite(ROOT/'data/chain_candidates.csv',cards)
    csvwrite(ROOT/'data/public_facts.csv',result['facts'])
    requests=[dict(card_id=c['card_id'],business_line='DAS',internal_buffer_metric=c['proposed_internal_buffer_metric'],units=c['metric_units'],
                   risk_direction=c['risk_direction'],exact_data_needed=c['exact_data_needed'],external_information=c['public_external_information_to_collect'],
                   public_driver_candidate=c['public_driver_candidate'],simulation_suitable=c['simulation_suitable'],simulation_limits=c['simulation_limits'],
                   real_v_status='UNAVAILABLE',correlation_test_status='NOT_RUN_MISSING_INTERNAL_OUTCOMES',validation_needed=c['validation_needed']) for c in cards]
    csvwrite(ROOT/'data/data_request_list.csv',requests)
    availability=[]
    for card in cards:
        for index in range(23):
            qindex=2020*4+3+index; year, q=divmod(qindex,4)
            availability.append(dict(card_id=card['card_id'],business_line='DAS',quarter=f'{year}Q{q+1}',
                                     internal_buffer_value=None,V_score=None,data_origin='UNAVAILABLE',is_simulated=False,
                                     service_period='PRELAUNCH',usable_in_empirical_validation=False,
                                     reason='No observed DAS internal time series; hypothetical prelaunch V must be separate.'))
    csvwrite(ROOT/'data/quarterly_v_availability.csv',availability)
    receipts={'total_estimated_cost_usd':str(sum(__import__('decimal').Decimal(json.loads((ROOT/folder/'attempt.json').read_text())['estimated_cost_usd']) for folder in ('aws_reading','aws_reading_recovery','aws_reading_reviewed'))),
              'calls':3,'automation_enabled':False,'credential_type':'existing_temporary_sso','pricing_note':'Configured-rate estimate, not an AWS bill.'}
    dump(ROOT/'results/api_run_summary.json',receipts)
    values=rows_for_database(result,sources,availability)
    portable=ROOT/'data/das_research.sqlite3'
    db_result=import_database(portable,values,sources)
    verification=dict(status='SOURCE_AND_STRUCTURE_CHECKS_PASSED_MECHANISMS_REQUIRE_REVIEW',quote_errors=errors,
                      available_evidence_sources=len(docs),complete_dtcc_documents_retrieved=sum(s['status']=='retrieved' and s.get('retrieval_method')!='web_reader_excerpt' for s in sources),
                      partial_sec_web_reader_excerpts=1,unavailable_original_documents=len(sources)-len(docs),
                      public_facts=len(result['facts']),candidate_cards=len(cards),quarterly_positions=len(availability),
                      observed_internal_v_values=0,simulated_v_values=0,empirical_tests_run=0,aws=receipts,portable_database=db_result)
    if args.import_project_database:
        # The API-derived datasets are separate from observed market/PQD tables.
        verification['project_database']=import_database(PROJECT/'capstone_database/data/capstone.sqlite3',values,sources,make_snapshot=False)
    dump(ROOT/'results/verification.json',verification)
    write_readme(result,sources,receipts)
    print(json.dumps(verification,indent=2))

if __name__=='__main__':main()
