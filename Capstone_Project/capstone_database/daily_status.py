"""Report snapshot publication and source failures separately; never hide failures."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def build(collection,market=None,*,published=False):
    source_errors=collection.get('failed_sources',[])
    market_errors=(market or {}).get('failed_sources',[])
    incomplete=bool(source_errors or market_errors)
    return dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),
                snapshot_publication='published' if published else 'not_confirmed',
                collection_status='partial_failure' if incomplete else collection.get('status','unknown'),
                successful_sources=collection.get('successful_sources',[]),
                partially_successful_sources=collection.get('partially_successful_sources',[]),
                failed_sources=source_errors,scoring_input_failures=market_errors,
                scoring_input_refresh=(market or {}).get('status','not_run'),
                previous_valid_values_retained=True,
                historical_scores_recomputed=False,event_register_modified=False,
                interpretation=('A snapshot can publish while some sources remain unavailable. Inspect source failures and data coverage before using a card score.'
                                if incomplete else 'No source failures recorded in this collection; scoring still requires its own coverage and review checks.'))

def markdown(report):
    lines=['# Public-data pipeline status / 公开数据任务状态','',
           '- Snapshot / 快照：'+report['snapshot_publication'],
           '- Collection / 采集：'+report['collection_status'],
           '- Successful sources / 成功来源：'+str(len(report['successful_sources'])),
           '- Sources with partial new data / 部分取得新数据：'+str(len(report['partially_successful_sources'])),
           '- Sources with failed requests / 有请求失败的来源：'+str(len(report['failed_sources'])),
           '- Scoring input failures / 评分输入更新失败：'+str(len(report['scoring_input_failures'])),'',
           'Partial sources also appear in failed requests; do not add these counts. 部分成功的来源也会列入失败请求，两个数量不能相加。',
           '',report['interpretation'],'']
    if report['failed_sources'] or report['scoring_input_failures']:
        lines+=['| Source / 来源 | HTTP | Detail / 详情 |','|---|---|---|']
        for error in report['failed_sources']+report['scoring_input_failures']:
            if not isinstance(error,dict):error={'source_id':str(error)}
            clean=lambda x:str(x or '').replace('|','/').replace('\n',' ')[:500]
            lines.append('| '+clean(error.get('source_id') or error.get('source') or error.get('series_id'))+' | '+clean(error.get('http_status'))+' | '+clean(error.get('error') or error.get('reason') or error.get('status'))+' |')
    return '\n'.join(lines)+'\n'

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collection',type=Path,default=ROOT/'logs/latest_update.json')
    p.add_argument('--market',type=Path,default=ROOT/'logs/scoring_input_refresh.json')
    p.add_argument('--out',type=Path,default=ROOT/'logs/source_health_summary.json')
    p.add_argument('--snapshot-published',action='store_true')
    p.add_argument('--strict',action='store_true')
    a=p.parse_args(argv)
    collection=json.loads(a.collection.read_text())
    market=json.loads(a.market.read_text()) if a.market.exists() else None
    report=build(collection,market,published=a.snapshot_published)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    note=markdown(report);a.out.with_suffix('.md').write_text(note)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write(note)
    print(json.dumps(report,indent=2))
    if a.strict and (report['failed_sources'] or report['scoring_input_failures']):
        raise SystemExit('Snapshot publication and source completeness are separate: unavailable sources remain reported; prior values retained.')
    return report

if __name__=='__main__':main()
