"""Build a public-evidence DAS monitor, with no invented V or S×V scores.

Only documented service/software relationships route findings. A maintainer
advisory is not a confirmed service incident. The public calendar is not proof of
submission or non-compliance. API documentation examples are never business data.
"""
from __future__ import annotations
import argparse
import csv
from datetime import date, datetime, time, timedelta
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from authorized_orders import analyze_authorized_orders

ROOT=Path(__file__).resolve().parents[1]


def norm(s): return ' '.join(s.split())


def quarter_end(day):
    month=((day.month-1)//3+1)*3
    return date(day.year+int(month==12), month%12+1, 1)-timedelta(days=1)


def third_friday_after(end):
    """Three Fridays strictly following quarter end, not the third Friday in month."""
    first=end+timedelta(days=1)
    first+=timedelta(days=(4-first.weekday())%7)
    return first+timedelta(days=14)


def read_source(root, source):
    if source.get('status')!='retrieved': return None
    path=(root/source['text_file']).resolve()
    path.relative_to(root.resolve())
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=source['text_sha256']:
        raise ValueError('Changed source text: '+source['source_id'])
    return raw.decode('utf-8')


def checked_fact(source_id, fact_id, quote, statement, docs, sources, **fields):
    """A source quote is a support check, not proof of a fitted causal effect."""
    if source_id not in docs or norm(quote) not in norm(docs[source_id]): return None
    return dict(fact_id=fact_id,source_id=source_id,source_url=sources[source_id]['url'],
                evidence_quote=quote,statement=statement, evidence_status='SOURCE_SUPPORTED',**fields)


def recent_advisories(items, start, as_of):
    output=[]
    for item in items:
        published=item.get('published_at')
        if not published: continue
        withdrawn=item.get('withdrawn_at')
        if withdrawn and date.fromisoformat(withdrawn[:10])<=as_of: continue
        day=date.fromisoformat(published[:10])
        if not start<=day<=as_of: continue
        vulnerabilities=[v for v in item.get('vulnerabilities',[])
                         if v.get('package',{}).get('name')=='org.hyperledger.besu:besu']
        if not vulnerabilities: continue
        output.append((item,vulnerabilities))
    return output


def write_csv(path, rows):
    if not rows: path.write_text(''); return
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n'); writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in rows)


def build(root=ROOT, as_of=date(2026,11,17), start=date(2026,11,9), orders_path=None):
    if start>as_of: raise ValueError('Window start exceeds as-of date')
    manifest=json.loads((root/'inputs/source_manifest.json').read_text())
    sources={x['source_id']:x for x in manifest}
    if len(sources)!=len(manifest): raise ValueError('Duplicate source IDs')
    docs={k:t for k,s in sources.items()
          if (not s.get('publication_date') or date.fromisoformat(s['publication_date'])<=as_of)
          and (t:=read_source(root,s)) is not None}
    facts=[]
    candidates=[
        ('launch','live_networks',"currently integrated with the Canton Network and DTCC’s private Besu network",
         'DTS launch evidence documents Canton and DTCC private Besu as integrated networks.'),
        ('solana','solana_future',"planned for the second half of 2027",
         'Solana integration is planned for H2 2027; this is not evidence of current production deployment.'),
        ('sec_letter','report_deadline',"the third Friday following each quarter’s end date",
         'The quarterly report is due to SEC staff no later than the third Friday following quarter end.'),
        ('sec_letter','relief_expiry',"three years from the date DTC launches operation",
         'Relief expiry depends on formal Preliminary Base Version launch; no exact expiry date is assumed.'),
        ('notice_das001','conversion_window',"Monday through Friday between 2:00 a.m. and 6:00 p.m.",
         'The published order submission window is weekdays 02:00–18:00 ET; actual order delays are not observed.'),
    ]
    for sid,fid,quote,statement in candidates:
        fact=checked_fact(sid,fid,quote,statement,docs,sources)
        if fact: facts.append(fact)
    fact_ids={f['fact_id'] for f in facts}
    reviewed_file=root/'results/aws_reviewed_facts.json'
    aws_fact_count=0
    stale_aws_facts=[]
    if reviewed_file.exists():
        reviewed=json.loads(reviewed_file.read_text())
        for f in reviewed['facts']:
            sid=f['source_id']
            if sid not in docs: continue
            if f['source_text_sha256']!=sources[sid]['text_sha256']:
                # A source change quarantines the old interpretation, without
                # blocking the structured monitor or retrying a paid request.
                stale_aws_facts.append(f['fact_id']); continue
            if norm(f['quote']) not in norm(docs[sid]) or len(norm(f['quote']).split())>20:
                raise ValueError('Unsupported AWS reviewed quote: '+f['fact_id'])
            facts.append(dict(f,source_url=sources[sid]['url'],evidence_quote=f['quote'],
                              evidence_status='API_INTERPRETATION_LOCALLY_SOURCE_CHECKED_NOT_BUSINESS_SIGNOFF'))
            aws_fact_count+=1
    networks=[]
    if 'live_networks' in fact_ids:
        for name in ('Canton','Besu'):
            networks.append(dict(network_id=name,source_id='launch',deployment_status='DOCUMENTED_LIVE',
                                 publication_date='2026-10-28',as_of_date=as_of.isoformat(),
                                 monitor_scope='public_dependency_context',internal_service_health=None,
                                 limitation='Deployment statement does not identify DTS versions, balances or service uptime.'))
    if 'solana_future' in fact_ids:
        networks.append(dict(network_id='Solana',source_id='solana',deployment_status='PLANNED_NOT_LIVE_IN_THIS_EVIDENCE',
                             publication_date='2026-11-12',planned_window='H2 2027',as_of_date=as_of.isoformat(),
                             include_in_current_outage_assessment=False,internal_service_health=None))
    findings=[]
    if 'besu_advisories' in docs and 'live_networks' in fact_ids:
        for item,vulnerabilities in recent_advisories(json.loads(docs['besu_advisories']),start,as_of):
            ghsa=item['ghsa_id']
            # Association is software-level only. No deployed-version or exploit claim.
            findings.append(dict(finding_id=ghsa,source_id='besu_advisories',source_ids=['launch','besu_advisories'],
                title=item['summary'],publication_date=item['published_at'][:10],source_url=item['html_url'],
                chain_ids=['DAS-01'],event_type='dependency_security_advisory',
                publisher_severity=item.get('severity'),severity_scale='GitHub maintainer severity, not DAS risk score',
                source_checked_conditions=[condition for fact in facts
                    if fact.get('source_id')=={'GHSA-hhgq-3gvc-4jhp':'besu_qbft','GHSA-6pcq-hcgg-5q76':'besu_ibft'}.get(ghsa)
                    for condition in fact.get('applicability_conditions',[])],
                affected_versions=[v.get('vulnerable_version_range') for v in vulnerabilities],
                patched_versions=[v.get('patched_versions') for v in vulnerabilities],
                review_status='APPLICABILITY_REVIEW_REQUIRED',applicability='UNKNOWN_DEPLOYED_VERSION_AND_CONFIGURATION',
                proposed_pathway='If the deployed Besu version and configuration are affected, availability degradation could delay DTS processing.',
                internal_V=None,shock_score=None,risk_score=None,confirmed_DAS_incident=None,
                next_action='Ask the DTS service owner to confirm deployed version, consensus configuration, peering exposure and patch status.'))
    if 'solana_future' in fact_ids and start<=date(2026,11,12)<=as_of:
        findings.append(dict(finding_id='DTS-SOLANA-20261112',source_id='solana',source_url=sources['solana']['url'],
            title='Solana integration planned for H2 2027',publication_date='2026-11-12',chain_ids=['DAS-04'],
            event_type='future_service_change',review_status='FUTURE_CHANGE_WATCHLIST',
            applicability='PLANNED_NETWORK_NOT_CURRENT_OUTAGE_EXPOSURE',
            next_action='Monitor official readiness, approved network scope and launch notices before changing current exposure.',
            internal_V=None,shock_score=None,risk_score=None,confirmed_DAS_incident=None))
    deadlines=[]
    if 'report_deadline' in fact_ids:
        current_end=quarter_end(as_of)
        quarter_start=date(current_end.year,current_end.month-2,1)
        previous_end=quarter_start-timedelta(days=1)
        end=min((e for e in (previous_end,current_end) if third_friday_after(e)>=as_of),key=third_friday_after)
        due=third_friday_after(end)
        deadlines.append(dict(deadline_id='SEC-REPORT-'+end.isoformat(),source_id='sec_letter',card_id='DAS-04',
            reporting_quarter=f'{end.year}Q{(end.month-1)//3+1}',quarter_end=end.isoformat(),deadline=due.isoformat(),
            calendar_days_remaining=(due-as_of).days,as_of_date=as_of.isoformat(),
            status='UPCOMING' if due>=as_of else 'PAST_DATE_SUBMISSION_UNKNOWN',
            submission_status='NOT_PUBLICLY_OBSERVED',
            limitation='A non-public SEC staff report is not assumed missing or late because it is absent from public websites.'))
    if 'relief_expiry' in fact_ids:
        deadlines.append(dict(deadline_id='SEC-RELIEF-EXPIRY',source_id='sec_letter',card_id='DAS-04',
            deadline=None,as_of_date=as_of.isoformat(),status='FORMAL_LAUNCH_DATE_CONFIRMATION_REQUIRED',
            limitation='Do not substitute the letter date, July trials or October press launch for formal written launch notice.'))
    decisions=[
      ('DAS-01','ACTIVE_PUBLIC_MONITOR','软件安全／基础设施事件','Software and infrastructure','维护方安全公告；当前部署范围','Actual version, consensus configuration, patch and failover evidence'),
      ('DAS-02','DEFER_INTERNAL_MEASUREMENT','记录与对账','Records and reconciliation','保留定义，暂不评分','Reconciliation breaks, backlog, resolution capacity and timestamps'),
      ('DAS-03','DEFER_INTERNAL_MEASUREMENT','钱包与安全控制','Wallet and security controls','保留定义，暂不做未知钱包制裁筛查','Registered-wallet inventory, key-control attestations and screening logs'),
      ('DAS-04','ACTIVE_PUBLIC_MONITOR','监管、资格与网络变更','Regulation, eligibility and scope','官方规则、网络变更及报告日历','Formal launch notice, contingency capacity and affected positions'),
      ('DAS-05','AUTHORIZED_DATA_ADAPTER_READY','转换及公司行动处理','Conversion and corporate actions','授权订单CSV／JSON接入已准备','Actual order and completion logs; capacity benchmarks and corporate-action outcomes'),
    ]
    scope=[dict(card_id=cid,implementation_status=status,name_cn=cn,name_en=en,
                available_output=output,minimum_missing_data=missing,internal_V=None,risk_score=None,
                model_status='NOT_EMPIRICALLY_VALIDATED') for cid,status,cn,en,output,missing in decisions]
    metrics=[]
    def metric(mid,value,unit,sid=None,**extra):
        metrics.append(dict(metric_id=mid,value=value,unit=unit,source_id=sid,as_of_date=as_of.isoformat(),
                            interpretation='Monitor output, not internal V or a DAS risk score',**extra))
    metric('sources_retrieved',len(docs),'sources')
    advisory_source=sources.get('besu_advisories',{})
    known='besu_advisories' in docs and 'live_networks' in fact_ids
    metric('besu_advisories_in_window',sum(f['event_type']=='dependency_security_advisory' for f in findings) if known else None,
           'advisories','besu_advisories' if advisory_source else None,
           coverage='At most 100 publisher advisories; configured date window; withdrawn advisories excluded',
           pagination_truncated=advisory_source.get('pagination_truncated',False))
    if 'canton_dso' in docs:
        dso=json.loads(docs['canton_dso']); svs=dso.get('dso_rules',{}).get('contract',{}).get('payload',{}).get('svs')
        metric('canton_published_sv_entries',len(svs) if isinstance(svs,(dict,list)) else None,'configured entries','canton_dso',
               limitation='Configuration context only, not live-node health or DTS exposure; no V mapping is accepted.')
    ny=ZoneInfo('America/New_York')
    order_start=datetime.combine(start,time.min,tzinfo=ny).isoformat()
    order_end=datetime.combine(as_of+timedelta(days=1),time.min,tzinfo=ny).isoformat()
    order_result=analyze_authorized_orders(orders_path,window_start=order_start,window_end=order_end)
    summary=dict(as_of_date=as_of.isoformat(),window_start=start.isoformat(),window_end_inclusive=as_of.isoformat(),
                 business_line='DAS',mode='PUBLIC_EVIDENCE_MONITOR',sources_retrieved=len(docs),sources_expected=len(manifest),
                 applicability_reviews=sum(f['review_status']=='APPLICABILITY_REVIEW_REQUIRED' for f in findings),
                 future_change_watchlist=sum(f['review_status']=='FUTURE_CHANGE_WATCHLIST' for f in findings),
                 aws_interpreted_source_checked_facts=aws_fact_count,
                 stale_aws_fact_ids=stale_aws_facts,
                 risk_score=None,internal_V=None,accepted_proxy_V=None,
                 empirical_validation=False,automation_enabled=False,
                 historical_point_in_time_verified=False,
                 bounds=('Public events and documentation; no authorized business telemetry was obtained.'
                         if order_result['availability']=='awaiting_authorized_data' else
                         'Public evidence plus supplied authorized order export; order outcomes are not internal buffer V.'))
    return dict(summary=summary,sources=manifest,findings=findings,facts=facts,scope=scope,
                networks=networks,metrics=metrics,deadlines=deadlines,authorized_orders=order_result)


def report(monitor,zh):
    s=monitor['summary']; findings=monitor['findings']; deadlines=monitor['deadlines']
    title='DAS 公开证据监测：实际运行结果' if zh else 'DAS public-evidence monitor: observed results'
    lines=['# '+title,'',f"As of / 核验日：{s['as_of_date']} · {s['window_start']}–{s['window_end_inclusive']}",'',
      ('本轮将五条研究链收窄为两个可运行的公开监测模块，并准备一个授权订单数据接口。输出待复核发现、未来变更观察、来源证据和报告日历；真实内部V与S×V分数继续为空。' if zh else
       'Five research chains are narrowed to two executable public monitors and an authorized-order data adapter. Outputs are applicability reviews, future changes, evidence and a reporting calendar. Internal V and S×V scores remain unavailable.'),'',
      ('## 实际发现' if zh else '## Findings'),'']
    for f in findings:
        if f['event_type']=='dependency_security_advisory':
            text=(f"{f['publication_date']}，Besu维护方发布安全公告，严重程度为 {f['publisher_severity']}，影响版本 {', '.join(f['affected_versions'])}，修复版本 {', '.join(f['patched_versions'])}。需要核对DTS实际版本与配置；尚未确认DAS事故。" if zh else
                  f"Published {f['publication_date']}; maintainer severity {f['publisher_severity']}; affected {', '.join(f['affected_versions'])}; patched {', '.join(f['patched_versions'])}. Confirm DTS version and configuration. No DAS incident has been established by this evidence.")
            lines+=['- ['+f['finding_id']+']('+f['source_url']+'): '+text]
        else:
            lines+=['- [Solana]('+f['source_url']+'): '+('2027年下半年计划接入，放入未来变更观察，不计作当前生产网络故障暴露。' if zh else
                      'Integration is planned for H2 2027. This belongs in a future-change watchlist, not current production outage exposure.')]
    if not findings: lines+=['No finding generated; check source coverage before interpreting this as an empty window.']
    lines+=['',('## 五条链的取舍' if zh else '## Scope decisions'),'',
            '| ID | '+('内容 | 当前处理 | 最少仍需什么' if zh else 'Subject | Treatment | Minimum missing input')+' |',
            '|---|---|---|---|']
    for c in monitor['scope']:
        treatment={'ACTIVE_PUBLIC_MONITOR':'启用公开监测','DEFER_INTERNAL_MEASUREMENT':'内部指标暂缓','AUTHORIZED_DATA_ADAPTER_READY':'授权数据接口已准备'}
        missing={'DAS-01':'实际Besu版本、共识配置、补丁与切换测试记录',
                 'DAS-02':'对账差异、积压数量、处理能力及时间戳',
                 'DAS-03':'已注册钱包清单、密钥控制证明与筛查日志',
                 'DAS-04':'正式启动通知、应急转换能力与受影响头寸',
                 'DAS-05':'实际订单、完成日志、处理能力与公司行动结果'}
        lines.append(f"| {c['card_id']} | {c['name_cn'] if zh else c['name_en']} | {treatment[c['implementation_status']] if zh else c['implementation_status']} | {missing[c['card_id']] if zh else c['minimum_missing_data']} |")
    lines+=['',('## 可计算的日历' if zh else '## Computable calendar'),'']
    for d in deadlines:
        if d.get('deadline'):
            lines+=['- '+(f"{d['reporting_quarter']} SEC staff报告期限：**{d['deadline']}**，距核验日 {d['calendar_days_remaining']} 天。提交情况未公开观察到，不能据此判定未提交。" if zh else
                         f"{d['reporting_quarter']} report to SEC staff: **{d['deadline']}**, {d['calendar_days_remaining']} calendar days from the as-of date. Submission is not publicly observed; this does not imply non-submission.")]
    lines+=['- [SEC source / 监管文件](https://www.sec.gov/files/tm/no-action/dtc-nal-121125.pdf) — '+('监管宽限的精确到期日保留为空：须确认正式Preliminary Base Version启动及书面通知，不能用新闻日期推算。' if zh else
                 'The exact relief expiry remains null until the formal Preliminary Base Version launch notice is established.'),'',
            ('## 砍掉的内容' if zh else '## Removed from this implementation'),'']
    removed=(['不制作2020Q4起的DAS上线前季度模拟，不用模拟值填补内部V。','不把币价、Canton Coin交易量、泛NVD漏洞数或公共网页HTTP成功率充当DAS内部脆弱度。','不扫描未知Registered Wallet，不把合作方名单当成钱包或托管控制证明。','不强行做缺少业务结果变量的机器学习回归；不输出未经支持的风险分数。'] if zh else
             ['No prelaunch quarterly DAS simulation and no fabricated internal V.','No crypto prices, Canton Coin volume, generic CVE counts or HTTP reachability substituted for DAS internal vulnerability.','No screening of unknown Registered Wallets or inference of controls from collaborator names.','No machine-learning regression without operating outcomes and no unsupported risk score.'])
    lines+=['- '+t for t in removed]
    lines+=['',('## 授权数据接入' if zh else '## Authorized data interface'),'',
      '[Public API documentation](https://dtcc-da.com/api/tokenization-service/api-reference-guide/content). '+('公开API说明书已取得，但业务接口需要参与机构账号。本轮未请求业务访问权限，也未调用业务接口。已提供只有表头的CSV模板，收到授权真实导出后可计算去重订单数、状态分布与明确确认的完成耗时。这些是运行结果指标，并非内部缓冲V。' if zh else
       'The public API guide was collected; actual service endpoints require participant authorization and were not called. A header-only template is supplied. Authorized exports can yield unique orders, order status outcomes and explicitly confirmed completion durations. These are operating outcomes, not internal buffer V.'),'',
      f"Current order input: `{monitor['authorized_orders']['availability']}`",'',
      ('## 运行与证据' if zh else '## Execution and evidence'),'',
      f"Sources retrieved: {s['sources_retrieved']}/{s['sources_expected']}. Raw files, dates and SHA-256 hashes are in inputs/source_manifest.json. Findings remain review-only. No production event register or existing final16 scoring was modified.",'',
      (f"公开文件已由现有AWS API解读；{s['aws_interpreted_source_checked_facts']}条解读事实经过本地原文复核。API原始结果中的引用错误、资格边界及不受支持的到期日期已单独记录修订，不代表业务方签字或实证验证。" if zh else
       f"The existing AWS API interpreted the public documents; {s['aws_interpreted_source_checked_facts']} interpreted facts have local source checks. Quote and interpretation corrections are retained separately. This is not business signoff or empirical validation."),'',
      ('Stale API fact IDs (excluded until source review): '+json.dumps(s['stale_aws_fact_ids'])),'',
      'Rebuild: `python3 src/build_monitor.py --as-of '+s['as_of_date']+' --window-start '+s['window_start']+'`',
      'Refresh public sources: `python3 src/collect_public.py` (network; no paid model call).',
      'Read new documents through the existing AWS API: `python3 src/read_public_with_aws.py --invoke` (explicit manual call; cached attempt prevents accidental repeat).',
      'Import: `python3 src/import_monitor_db.py` (portable SQLite; optional targeted existing-database import).','']
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--as-of',type=date.fromisoformat,default=datetime.now(ZoneInfo('America/New_York')).date())
    p.add_argument('--window-start',type=date.fromisoformat)
    p.add_argument('--orders',type=Path)
    args=p.parse_args()
    m=build(as_of=args.as_of,start=args.window_start or args.as_of-timedelta(days=8),orders_path=args.orders)
    for folder in ('results','data'): (ROOT/folder).mkdir(exist_ok=True)
    (ROOT/'results/monitor.json').write_text(json.dumps(m,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    for key in ('findings','facts','scope','networks','metrics','deadlines'): write_csv(ROOT/'data'/(key+'.csv'),m[key])
    for zh,lang in ((True,'CN'),(False,'EN')): (ROOT/('RESULTS_'+lang+'.md')).write_text(report(m,zh))
    print(json.dumps(m['summary'],ensure_ascii=False))


if __name__=='__main__': main()
