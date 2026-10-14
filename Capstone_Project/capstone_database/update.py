#!/usr/bin/env python3
"""Incremental daily refresh. Source failures retain the last valid records."""
from datetime import date, datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo
import argparse, collections, json, subprocess, tempfile
import db, parsers

def urls(c,s,as_of):
    kind=s['kind'];sid=s['id']
    if kind=='market_series':
        # A one-year overlap catches revisions; original older vintages remain in SQLite.
        return [s['url']+'&'+urlencode({'cosd':(as_of-timedelta(days=400)).isoformat(),'coed':as_of.isoformat()})]
    if kind in ['regulatory_documents','disaster_declarations']:
        row=c.execute('SELECT last_success FROM sources WHERE source_id=?',(sid,)).fetchone()
        start=date.fromisoformat(row[0][:10])-timedelta(days=7) if row and row[0] else as_of-timedelta(days=30)
        start=min(start,as_of-timedelta(days=7))
        if kind=='regulatory_documents':
            params=[('conditions[publication_date][gte]',start.isoformat()),('conditions[publication_date][lte]',as_of.isoformat()),
                    ('conditions[agencies][]','securities-and-exchange-commission'),('conditions[agencies][]','commodity-futures-trading-commission'),
                    ('conditions[agencies][]','federal-reserve-system'),('per_page','1000'),('order','oldest')]
        else:
            params={'$filter':f"declarationDate ge '{start}T00:00:00.000Z' and declarationDate le '{as_of}T23:59:59.000Z'",
                    '$select':'disasterNumber,declarationDate,incidentType,state,declarationType,incidentBeginDate',
                    '$orderby':'declarationDate','$top':10000,'$skip':0}
        return [s['url']+'?'+urlencode(params)]
    if kind=='repository_weekly':
        latest=as_of-timedelta(days=(as_of.weekday()-4)%7)
        row=c.execute("SELECT max(measurement_date) FROM records WHERE dataset_id='rds_reports' AND source_id=?",(sid,)).fetchone()
        start=date.fromisoformat(row[0]) if row and row[0] else latest
        days=[]
        while start<=latest and len(days)<8:
            days.append(start);start+=timedelta(days=7)
        return [s['url'].format(report_date=d.strftime('%Y%m%d')) for d in days]
    return [s['url']]

def fetch(url,headers=None):
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password:raise ValueError('Only public HTTPS URLs are supported')
    with tempfile.TemporaryDirectory(prefix='capstone-fetch-') as tmp:
        body=Path(tmp)/'body';head=Path(tmp)/'headers'
        command=['curl','--http1.1','--proto','=https','--proto-redir','=https','--fail','--location','--silent','--show-error',
                 '--connect-timeout','10','--max-time','45','--max-filesize','67108864','--dump-header',str(head),
                 '--output',str(body),'--write-out','%{http_code}']
        for k,v in (headers or {}).items():
            if '\n' in v or '\r' in v:raise ValueError('Invalid conditional header')
            command+=['--header',k+': '+v]
        command.append(url)
        try:result=subprocess.run(command,capture_output=True,text=True,timeout=50)
        except subprocess.TimeoutExpired:return {'url':url,'status':'failed','error':'Transport timed out','http_status':None,'checked_at':db.now()}
        code=int(result.stdout or 0);meta={}
        if head.exists():
            for line in head.read_text(errors='replace').splitlines():
                if line.startswith('HTTP/'):meta={}
                elif ':' in line:
                    k,v=line.split(':',1);meta[k.lower()]=v.strip()
        if result.returncode or code not in [200,304]:
            return {'url':url,'status':'failed','http_status':code,'error':result.stderr.strip()[:1000] or 'Unexpected HTTP response','checked_at':db.now()}
        return {'url':url,'status':'not_modified' if code==304 else 'downloaded','http_status':code,
                'data':body.read_bytes() if body.exists() else b'','headers':meta,'checked_at':db.now()}

def collect(s,jobs):
    results=[]
    for url,headers in jobs:
        r=fetch(url,headers);results.append(r)
        if r['status']=='failed':continue
        if s['kind']=='regulatory_documents' and r['status']=='downloaded':
            obj=json.loads(r['data']);visited={url};next_url=obj.get('next_page_url')
            while next_url:
                if len(visited)>=20 or next_url in visited or urlsplit(next_url).hostname!=urlsplit(url).hostname:
                    raise ValueError('Unsafe, repeated, or excessive Federal Register pagination')
                visited.add(next_url);page=fetch(next_url);results.append(page)
                if page['status']=='failed':break
                next_url=json.loads(page['data']).get('next_page_url')
        elif s['kind']=='disaster_declarations' and r['status']=='downloaded':
            obj=json.loads(r['data']);offset=10000
            while len(obj.get('DisasterDeclarationsSummaries',[]))==10000:
                if offset>100000:raise ValueError('FEMA pagination exceeds bound; narrow the collection window')
                page_url=url.replace('%24skip=0','%24skip='+str(offset));page=fetch(page_url);results.append(page)
                if page['status']=='failed':break
                obj=json.loads(page['data']);offset+=10000
    return results

def update(path,as_of,force=False,only=None):
    db.restore(path)
    configs=json.loads((db.ROOT/'sources.json').read_text());businesses=json.loads((db.ROOT/'businesses.json').read_text())
    with db.writer_lock(path):
        c=db.connect(path);db.register(c,configs,businesses);rid=db.start_run(c,'daily_update')
        due=[];clock=datetime.now(ZoneInfo('UTC'));skipped=[]
        for s in configs:
            if not s['enabled'] or (only and s['id'] not in only):continue
            old=c.execute('SELECT * FROM sources WHERE source_id=?',(s['id'],)).fetchone()
            if not force and old['last_checked'] and (clock-datetime.fromisoformat(old['last_checked'])).total_seconds()<s['refresh_hours']*3600:
                skipped.append(s['id']);continue
            jobs=[]
            for url in urls(c,s,as_of):
                conditional={}
                prior=c.execute('SELECT blob_hash FROM fetches WHERE source_id=? AND requested_url=? AND status IN (\'downloaded\',\'not_modified\') ORDER BY fetch_id DESC LIMIT 1',(s['id'],url)).fetchone()
                bundled=c.execute("SELECT 1 FROM evidence_blobs WHERE sha256=? AND compression='zlib'",(old['last_blob_hash'],)).fetchone()
                if prior and bundled and s['kind'] not in ['market_series','regulatory_documents','disaster_declarations','repository_weekly']:
                    if old['etag']:conditional['If-None-Match']=old['etag']
                    if old['last_modified']:conditional['If-Modified-Since']=old['last_modified']
                jobs.append((url,conditional))
            due.append((s,jobs))
        requests=[url for s,jobs in due for url,h in jobs]
        if len(requests)!=len(set(requests)):raise ValueError('Duplicate URLs in this run; shared sources must be fetched once')
        summary={'run_id':rid,'as_of_date':as_of.isoformat(),'new_records':0,'revised_records':0,'unchanged_records':0,
                 'successful_sources':[],'failed_sources':[],'skipped_not_due':skipped,'source_results':[],
                 'manual_review_sources':[s['id'] for s in configs if s.get('update_note','').startswith('Manual')],
                 'models_retrained':False,'business_risk_scores_generated':False}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures={pool.submit(collect,s,jobs):s for s,jobs in due}
            for future in as_completed(futures):
                s=futures[future];sid=s['id']
                try: responses=future.result()
                except Exception as exc:responses=[{'url':s['url'],'status':'failed','http_status':None,'error':str(exc),'checked_at':db.now()}]
                failures=[r for r in responses if r['status']=='failed'];counts=collections.Counter();outcomes=[]
                if not failures:
                    try:
                        with c:
                            for r in responses:
                                data=r['data'] if r['status']=='downloaded' else db.blob(c,c.execute('SELECT last_blob_hash FROM sources WHERE source_id=?',(sid,)).fetchone()[0])
                                h=db.put_blob(c,data);dataset,rows=parsers.parse(s,data,as_of,r['url'])
                                rows,duplicates=parsers.deduplicate(dataset,rows)
                                keys=[parsers.record_key(dataset,row) for row in rows]
                                if len(keys)!=len(set(keys)):raise ValueError('Duplicate records within source response')
                                for key,row in zip(keys,rows):
                                    if dataset=='news':
                                        prior=c.execute('SELECT payload FROM records WHERE dataset_id=? AND record_key=?',(dataset,key)).fetchone()
                                        if prior:row=dict(json.loads(prior[0]),**row)
                                    row['collected_at_utc']=r['checked_at']
                                    counts[db.upsert(c,dataset,key,row,rid,sid,h,r['checked_at'])]+=1
                                    if dataset=='news':
                                        c.execute('DELETE FROM document_business WHERE document_id=?',(row['document_id'],))
                                        for link in row['routing_evidence']:
                                            c.execute('INSERT OR REPLACE INTO document_business VALUES(?,?,?,?,?)',(row['document_id'],link['business_line'],link['rule'],db.dumps(link),'candidate_unreviewed'))
                                c.execute('INSERT INTO fetches(run_id,source_id,requested_url,checked_at,status,http_status,blob_hash,record_count,detail) VALUES(?,?,?,?,?,?,?,?,?)',
                                          (rid,sid,r['url'],r['checked_at'],r['status'],r['http_status'],h,len(rows),'Parsed successfully; duplicate source rows merged: '+str(duplicates)))
                                headers=r.get('headers',{})
                                c.execute('UPDATE sources SET last_checked=?,last_success=?,last_status=?,last_error=NULL,last_blob_hash=?,etag=?,last_modified=? WHERE source_id=?',
                                          (r['checked_at'],r['checked_at'],r['status'],h,headers.get('etag'),headers.get('last-modified'),sid))
                                outcomes.append({'url':r['url'],'rows':len(rows),'duplicates_merged':duplicates,'status':r['status']})
                        summary['successful_sources'].append(sid)
                    except Exception as exc:
                        counts=collections.Counter();failures=[{'url':s['url'],'status':'parse_failed','http_status':None,'error':str(exc),'checked_at':db.now()}]
                if failures:
                    with c:
                        for r in failures:
                            c.execute('INSERT INTO fetches(run_id,source_id,requested_url,checked_at,status,http_status,error) VALUES(?,?,?,?,?,?,?)',
                                      (rid,sid,r['url'],r['checked_at'],r['status'],r['http_status'],r['error']))
                        c.execute('UPDATE sources SET last_checked=?,last_status=?,last_error=? WHERE source_id=?',(db.now(),'failed',failures[0]['error'],sid))
                    summary['failed_sources'].append({'source_id':sid,'error':failures[0]['error'],'http_status':failures[0]['http_status']})
                    outcomes=[{k:v for k,v in r.items() if k not in ['data','headers']} for r in failures]
                for key,name in [('new','new_records'),('revised','revised_records'),('unchanged','unchanged_records')]:summary[name]+=counts[key]
                summary['source_results'].append({'source_id':sid,'counts':dict(counts),'requests':outcomes})
                print(sid,dict(counts),'FAILED' if failures else 'OK',flush=True)
        summary['status']='partial_failure' if summary['failed_sources'] else 'success'
        with c:c.execute('UPDATE runs SET finished_at=?,status=?,summary=? WHERE run_id=?',(db.now(),summary['status'],db.dumps(summary),rid))
        db.export_csv(c,db.ROOT/'exports');summary['snapshot']=db.snapshot(c,path)
        folder=db.ROOT/'logs';folder.mkdir(exist_ok=True)
        (folder/'latest_update.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        c.close();return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=db.DEFAULT_DB)
    p.add_argument('--as-of',type=date.fromisoformat,default=datetime.now(ZoneInfo('America/New_York')).date())
    p.add_argument('--force',action='store_true');p.add_argument('--only',nargs='+');p.add_argument('--strict',action='store_true')
    a=p.parse_args();result=update(a.db,a.as_of,a.force,a.only)
    print(json.dumps({k:v for k,v in result.items() if k!='source_results'},indent=2))
    if a.strict and result['failed_sources']:raise SystemExit(1)
