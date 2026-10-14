"""Build an inspectable catalog and ZIP without changing original document bytes."""
from pathlib import Path
from datetime import datetime, timezone
from hashlib import sha256
from zipfile import ZipFile, ZIP_DEFLATED
import json, shutil, collections, re, calendar

ROOT=Path(__file__).resolve().parents[1]
progress=ROOT/'collection_support/historical_collection_progress.json'
collection=json.loads(progress.read_text())
initial=json.loads((ROOT/'source_manifest.json').read_text())
backup=ROOT/'collection_support/initial_source_manifest.json'
if not backup.exists():backup.write_text(json.dumps(initial,ensure_ascii=False,indent=2))
records=collection['files']
groups=collections.defaultdict(list)
for record in records:
    if record.get('file'):groups[record['sha256']].append(record)
documents=[]
superseded=ROOT/'collection_support/superseded_download_paths'
for digest,group in groups.items():
    first=group[0]
    year=first['actual_year'];quarter=first['actual_quarter'];entity=first['actual_entity'];extension=first['actual_format']
    if first['document_kind']=='public_quantitative_disclosure':
        folder='quantitative_disclosures';stem=f'DTCC_PQD_{year}_Q{quarter}'
        document_period=f'{year} Q{quarter}';comparative_year=None
    else:
        source_title=first['listing_records'][0]['title']
        is_quarter=bool(re.search(r'\bQ[1-4]\b',source_title))
        if is_quarter:
            stem=f'{entity}_Q{quarter}_{year}';document_period=f'{year} Q{quarter}';comparative_year=year-1
        else:
            stem=f'{entity}_Annual_{year}_{year-1}';document_period=f'{year}/{year-1} Annual';comparative_year=year-1
        folder='flagged_source_records' if entity=='DTCC' else 'financial_statements'
    canonical=f'{folder}/{stem}.{extension}'
    target=ROOT/canonical;target.parent.mkdir(exist_ok=True)
    origins={r['file'] for r in group}
    if target.exists():assert sha256(target.read_bytes()).hexdigest()==digest,(canonical,'Name collision')
    else:shutil.copy2(ROOT/first['file'],target)
    assert sha256(target.read_bytes()).hexdigest()==digest
    for origin in origins:
        if origin!=canonical:
            path=ROOT/origin
            if path.exists():
                parked=superseded/origin;parked.parent.mkdir(parents=True,exist_ok=True)
                if not parked.exists():shutil.move(path,parked)
    listing_records=[]
    for record in group:
        record['file']=canonical
        for listing in record['listing_records']:
            entry=dict(listing)
            entry.pop('status',None);entry.pop('local_file',None)
            years=re.findall(r'\b20\d{2}\b',entry['title'])
            expected_entity=entry['title'].split()[0] if entry['category']=='financial_statements' else 'FICC and NSCC'
            issues=[]
            if expected_entity!=entity:issues.append('entity_mismatch')
            if years and int(years[0])!=year:issues.append('reporting_year_mismatch')
            q=re.search(r'\bQ([1-4])\b',entry['title'])
            if q and int(q[1])!=quarter:issues.append('quarter_mismatch')
            if entry['format']!=extension:issues.append('file_format_mismatch')
            entry['metadata_issues']=issues
            entry['listing_matches_document']=not issues
            listing_records.append(entry)
    usable=entity!='DTCC' and any(x['listing_matches_document'] for x in listing_records)
    documents.append(dict(file=canonical,sha256=digest,bytes=first['bytes'],actual_format=extension,
        actual_entity=entity,document_kind=first['document_kind'],reporting_year=year,reporting_quarter=quarter,
        reporting_period=document_period,comparative_year= comparative_year if first['document_kind']=='financial_statements' else None,
        report_period_end=f'{year}-{quarter*3:02d}-{calendar.monthrange(year,quarter*3)[1]}',
        collection_timestamps_utc=sorted({x['collected_at_utc'] for x in group}),
        source_urls=sorted({x['download_url'] for x in group}),source_listing_records=listing_records,
        usable_for_requested_business=usable,scope='NSCC/FICC GSD/MBSD; preserve metric-specific windows' if first['document_kind']=='public_quantitative_disclosure' else 'Legal entity; not a standalone ECS segment',
        verification='Original file format, readability/integrity, entity and reporting period checked',
        pages=first.get('pages'),sheet_names=first.get('sheet_names'),cover_excerpt=first['cover_excerpt']))

documents.sort(key=lambda x:(x['document_kind'],x['actual_entity'],-x['reporting_year'],-x['reporting_quarter'],x['file']))
failures=[x for x in records if not x.get('file')]
metadata_issues=[dict(title=x['title'],listed_date=x['listed_date'],download_url=x['download_url'],
    actual_file=d['file'],actual_period=d['reporting_period'],actual_entity=d['actual_entity'],issues=x['metadata_issues'])
    for d in documents for x in d['source_listing_records'] if x['metadata_issues']]
legacy_urls=[
 ('NSCC Annual 2025/2024','https://www.dtcc.com/-/media/Files/Downloads/legal/financials/2025/NSCC-Financial-Statements-Annual-2025.pdf'),
 ('DTC Annual 2019/2018','https://www.dtcc.com/-/media/Files/Downloads/legal/financials/2020/DTC-Annual-Financial-Statements-2019-and-2018-SEC-Filing-022820.pdf'),
 ('PQD 2019 Q4','https://www.dtcc.com/-/media/Files/Downloads/legal/policy-and-compliance/CPMI-IOSCO-Quantitative-Disclosure-Results-2019-Q4-1.pdf'),
 ('DTCC Annual 2019/2018','https://www.dtcc.com/annuals/2019/pdf/dtcc-2019-annual-financial-statements.pdf')]
checks=[dict(title=t,url=u,http_status=404,checked_date_local='2026-10-05',status='unavailable') for t,u in legacy_urls]
summary={'collection_date_local':'2026-10-05','timezone':'America/New_York','unique_original_documents':len(documents),
         'successful_source_urls':sum(bool(x.get('file')) for x in records),'failed_source_urls':len(failures),
         'duplicate_content_downloads':sum(bool(x.get('file')) for x in records)-len(documents),
         'document_counts_by_entity':dict(collections.Counter(x['actual_entity'] for x in documents)),
         'document_counts_by_format':dict(collections.Counter(x['actual_format'] for x in documents)),
         'valid_business_documents':sum(x['usable_for_requested_business'] for x in documents),
         'quantitative_quarters':sorted({x['reporting_period'] for x in documents if x['document_kind']=='public_quantitative_disclosure'}),
         'earliest_financial_data_year_FICC_NSCC':2019,'earliest_financial_data_year_DTC':2020,
         'earliest_quantitative_disclosure_report':'2020 Q4','latest_quarterly_report':'2026 Q2',
         'metadata_issue_listing_records':len(metadata_issues)}
manifest={**collection,'source_restriction':'Public official DTCC files only; no private uploads or AWS changes',
    'release_time_note':'Portal listed_date, report period and collection timestamps are different fields. The first public release time was not independently verified.',
    'scope_warning':'ECS is represented by NSCC clearing and DTC settlement, but legal-entity financial reports are not standalone ECS business-line results. Do not sum their profits as ECS-only performance. PQD covers FICC and NSCC, not DTC.',
    'summary':summary,'files':records,'documents':documents,'unavailable_downloads':failures,
    'metadata_issue_records':metadata_issues,'legacy_link_checks':checks,
    'coverage_limits':['Current portal financial reports start with 2020 annuals. Tested older indexed public links return 404; this is not a claim that earlier reports never existed.',
                       'Six financial source URLs return HTTP 403. One was also checked with its official browser download button and displayed Access Denied; no access controls were bypassed.',
                       'NSCC Annual 2025/2024 not listed in the inspected current portal; indexed legacy link returns 404.',
                       '2024 Q4 PQD has PDF but no listed XLSX; 2020 Q4 PQD has XLSX but no listed PDF.',
                       'Monthly or weekly business performance cannot be inferred as observed data from quarterly/annual reports.']}
(ROOT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
progress.write_text(json.dumps(collection,ensure_ascii=False,indent=2))
(ROOT/'collection_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
(ROOT/'unavailable_and_metadata_issues.json').write_text(json.dumps({'unavailable_downloads':failures,'metadata_issue_records':metadata_issues,'legacy_link_checks':checks},ensure_ascii=False,indent=2))
url_records={x['download_url']:x for x in records}
queue=json.loads((ROOT/'historical_download_queue.json').read_text())
for listing in queue:
    result=url_records[listing['download_url']]
    listing['status']=result['status']
    if result.get('file'):listing['local_file']=result['file']
    else:listing['error']=result.get('error');listing.pop('local_file',None)
(ROOT/'historical_download_queue.json').write_text(json.dumps(queue,ensure_ascii=False,indent=2))

gap_lines=[]
for x in failures:
    title=x['listing_records'][0]['title']
    gap_lines.append(f"- **{title}**：官网当前下载链接返回 HTTP 403（访问拒绝），尚未取得该原文件。")
counts=summary['document_counts_by_entity']
readme=f'''# DTCC 历史公开业绩资料

采集日期：**2026 年 10 月 5 日**（美国东部时间）。原文件按内容整理，未修改其 PDF 或 Excel 数据。

## 已下载什么

已成功取得 **111 个来源链接对应的文件**；按文件内容校验值去重后，为 **110 个独立原文件**。

| 资料 | 文件数量 | 内容覆盖 |
|---|---:|---|
| FICC 财务报告 | {counts['FICC']} | 2020—2025 年报及官网列出的历史季度报告，最新 2026 Q2；最早年报含 2019 年对比数据 |
| NSCC 财务报告 | {counts['NSCC']} | 2020—2024 年报及可下载的历史季度报告，最新 2026 Q2；最早年报含 2019 年对比数据 |
| DTC 财务报告 | {counts['DTC']} | 可下载的历史年报与季度报告，最新 2026 Q2；最早已下载年报为 2021 年报，含 2020 年对比数据 |
| FICC / NSCC 季度定量披露 | {counts['FICC and NSCC']} | 2020 Q4—2026 Q2，共 23 个季度；22 份 PDF、22 份 Excel |
| 官网标错标题的 DTCC 集团报告 | {counts['DTCC']} | 实际为 DTCC 2023 Q2，单独保存，不计入 FICC 或 ECS 业务数据 |

全部共 **88 份 PDF、22 份 Excel**。其中 109 份适用于本次业务资料范围，另 1 份为误标链接带来的集团报告。

## 在哪里找文件

- `financial_statements/`：FICC、NSCC、DTC 的历史财务 PDF，文件名标明机构与报告期。
- `quantitative_disclosures/`：23 个季度的原始定量披露 PDF / Excel。
- `flagged_source_records/`：实际为集团报告的误标文件。
- [全部文件与来源目录](下载目录.md)：每份原文件的本地入口和官方来源。
- `source_manifest.json`：文件来源、官网日期、实际报告期、采集时间、校验值、机构与格式核对结果。
- `collection_summary.json`：下载数量与覆盖范围。
- `unavailable_and_metadata_issues.json`：失效链接、错误标注和较早报告的下载检查记录。
- `historical_download_inventory.json`：采集时两个官网目录的完整 189 条记录。
- `historical_download_queue.json`：118 条相关目录记录的最终下载状态，包括重复和误标条目。

## 能从这些数据中提取什么

财务报告提供法人机构的收入、费用、利润、资产负债、股东权益和现金流等数据。定量披露提供清算业务规模、保证金、信用风险、流动性风险、保证金回测、业务风险和运营等相关指标，具体字段随披露模板变化。这一阶段保存原始证据与元数据；尚未生成统一的指标时间序列或机器学习训练数据。

## 下载缺口

官网列出的 117 个不同相关下载链接均已尝试，其中 111 个成功、6 个返回访问拒绝：

{chr(10).join(gap_lines)}

此外，当前目录未列出 NSCC 的 2025/2024 年报；搜索结果中的旧官方地址返回 404。2024 Q4 定量披露只有 PDF、未列出 Excel；2020 Q4 只有 Excel、未列出 PDF。23 个季度均至少取得一种格式。

搜索到的更早 DTC 2019/2018 年报、2019 Q4 定量披露及 DTCC 2019 年报的旧官方地址亦返回 404。因此这里描述的是本次实际可取得的范围，不表示更早报告从未存在。

## 已纠正的官网标注问题

1. 一条“NSCC 2025 Q2”链接实际是 **DTCC 集团 2023 Q2**。文件保留在单独目录，不纳入 NSCC 的 2025 年数据；正确的 NSCC 2025 Q2 文件也已下载。
2. 一条标为“2025 Q2 Excel”的链接实际是 **2024 Q2 PDF**，同时也在正确的 2024 Q2 目录条目下出现。按实际内容保存，保留两条来源记录；正确的 2025 Q2 Excel 也已下载。
3. 2026 Q1 Excel 的两条不同链接返回相同内容，已合并为一份原文件，并保留两个来源地址。

## 使用时的口径

- FICC 是项目业务线；ECS 涉及 NSCC 清算和 DTC 结算。NSCC / DTC 法人财务报告涵盖的服务并不完全等于 ECS，不应直接相加后称为 ECS 专属收入或利润。
- 定量披露保留 NSCC、FICC GSD / MBSD 的原始口径；这套文件不是 DTC 定量披露。
- 数据观察期、官网显示日期、实际采集时间分别记录。年报内的上一年对比值不是上一年的独立发布文件。
- 定量披露中的年度指标、季度末值、季度平均值和过去 12 个月指标要分别处理，不能一律视为当季数据。
- 季度或年度数据不能当作实际观测的每周、每月业务业绩。

## 官方下载入口

- [Financial Statements：财务报告](https://www.dtcc.com/legal/financial-statements)
- [Policy & Compliance：季度定量披露](https://www.dtcc.com/legal/policy-and-compliance)

原文件与最终清单已打包为 `DTCC_Historical_Public_Data_2026-10-05.zip`。先前的 `DTCC_Public_Data_Progress_2026-10-05.zip` 保留为第一批 15 份文件的进度快照。
'''
(ROOT/'历史资料说明.md').write_text(readme)
(ROOT/'已保存进度与继续下载说明.md').write_text('# 进度已更新\n\n历史下载与文件整理已完成。请查看 [历史资料说明](历史资料说明.md) 和 [下载目录](下载目录.md)。\n\n原始报告已去重为 110 份，6 个官网链接返回访问拒绝，具体缺口见最新说明与清单。\n')

index=['# 原始文件下载目录','','采集日期：2026-10-05。全部文件保持原始字节；原始官网标题可能与实际文件不同，详见说明。','']
for heading,entity,kind in [('FICC 财务报告','FICC','financial_statements'),('NSCC 财务报告','NSCC','financial_statements'),('DTC 财务报告','DTC','financial_statements'),('季度定量披露（FICC / NSCC）','FICC and NSCC','public_quantitative_disclosure'),('误标链接文件','DTCC','financial_statements')]:
    index+=['## '+heading,'','| 实际报告期 | 格式 | 本地原文件 | 官方下载来源 |','|---|---|---|---|']
    for d in documents:
        if d['actual_entity']==entity and d['document_kind']==kind:
            name=Path(d['file']).name
            links='；'.join(f'[来源 {i+1}]({u})' for i,u in enumerate(d['source_urls']))
            index.append(f"| {d['reporting_period']} | {d['actual_format'].upper()} | [{name}]({d['file']}) | {links} |")
    index.append('')
index+=['## 未取得的官网文件','',*gap_lines,'','机构、日期、格式误标详情见 `unavailable_and_metadata_issues.json`。']
(ROOT/'下载目录.md').write_text('\n'.join(index)+'\n')
checkpoint=json.loads((ROOT/'collection_checkpoint.json').read_text())
checkpoint.update(saved_at_utc=datetime.now(timezone.utc).isoformat(),status='all_identified_links_attempted_available_files_collected',
    downloaded_and_verified_files=110,downloaded_source_urls=111,failed_source_urls=6,pending_listing_records=0,
    next_steps=['If missing original reports are needed, ask the project contact for fresh public download links; do not bypass Access Denied.',
                'Extract and normalize selected metrics with page/sheet evidence, units and observation windows before analysis.'],
    earliest_financial_report_listed='2020 annuals downloaded for FICC/NSCC, with 2019 comparative data; DTC 2020 annual link is inaccessible.',
    earliest_quantitative_disclosure_listed='2020 Q4 XLSX downloaded and checked.')
(ROOT/'collection_checkpoint.json').write_text(json.dumps(checkpoint,ensure_ascii=False,indent=2))

archive=ROOT.parent/'DTCC_Historical_Public_Data_2026-10-05.zip'
include=[ROOT/d['file'] for d in documents]
include += [ROOT/name for name in ('历史资料说明.md','下载目录.md','source_manifest.json','collection_summary.json','unavailable_and_metadata_issues.json','historical_download_inventory.json','historical_download_queue.json','collection_checkpoint.json')]
with ZipFile(archive,'w',compression=ZIP_DEFLATED) as z:
    for path in include:z.write(path,Path(ROOT.name)/path.relative_to(ROOT))
with ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(include)
    for d in documents:
        payload=z.read(str(Path(ROOT.name)/d['file']))
        assert sha256(payload).hexdigest()==d['sha256']
    packed=json.loads(z.read(str(Path(ROOT.name)/'source_manifest.json')))
    assert packed['summary']['unique_original_documents']==len(documents)
print(json.dumps({'summary':summary,'archive':str(archive),'archive_bytes':archive.stat().st_size,'archive_entries':len(include),'zip_integrity_and_original_sha256_verified':True},ensure_ascii=False),flush=True)
