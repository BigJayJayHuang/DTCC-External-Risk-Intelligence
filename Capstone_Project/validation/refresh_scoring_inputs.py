"""Audit scoring-input freshness offline or explicitly refresh current-year Cboe.

python -m validation.refresh_scoring_inputs --audit
python -m validation.refresh_scoring_inputs --refresh --report capstone_database/logs/scoring_input_refresh.json

Uses the standard library so the daily database workflow needs no analytical
runtime. Does not score cards, retrain models, refresh V, or change event reviews.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.request
from zoneinfo import ZoneInfo

PROJECT=Path(__file__).resolve().parents[1]
RAW=PROJECT/'data/raw'
DERIVED=PROJECT/'data/derived'
MARKET_DAILY=PROJECT/'capstone_database/exports/market_daily.csv'
CBOE_URL='https://cdn.cboe.com/resources/us/equities/market-statistics/historical-market-volume/market_history_{year}.csv'
LOG_FIELDS=['source','url','local_file','downloaded_utc','http_status','bytes','sha256','coverage_start','coverage_end','status','note']
CORE_SERIES=['SOFR','EFFR','DGS10','BAA10Y','VIXCLS','MORTGAGE30US']

def today_ny():
    return datetime.now(ZoneInfo('America/New_York')).date()

def atomic_write(path,body):
    """Validate before calling; replace only a fully written same-directory file."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(body);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def parse_cboe(body,*,year,as_of):
    """One per-venue row per day; malformed/partial responses never replace cache."""
    reader=csv.DictReader(io.StringIO(body.decode('utf-8-sig')))
    fields=reader.fieldnames or []
    required={'Day','Market Participant','Total Shares'}
    if not required<=set(fields) or len(fields)!=len(set(fields)):
        raise ValueError('Cboe schema changed: Day, Market Participant and Total Shares must be unique columns')
    rows=[];seen=set()
    for row in reader:
        if None in row or any(row.get(k) is None for k in required):
            raise ValueError('Cboe CSV has a broken row')
        day=date.fromisoformat(row['Day'].strip())
        if day.year!=year:raise ValueError('Cboe row outside requested year')
        if day>as_of:raise ValueError('Cboe response contains a future observation date')
        venue=row['Market Participant'].strip()
        if not venue:raise ValueError('Cboe participant is blank')
        key=(day.isoformat(),venue)
        if key in seen:raise ValueError('Duplicate Cboe Day/Market Participant row')
        seen.add(key)
        try:value=Decimal(row['Total Shares'].strip())
        except InvalidOperation as e:raise ValueError('Cboe Total Shares is not numeric') from e
        if not value.is_finite() or value<0:raise ValueError('Cboe Total Shares must be finite and nonnegative')
        rows.append({'day':day.isoformat(),'venue':venue,'shares':value})
    if not rows:raise ValueError('Cboe response is empty')
    return rows

def validate_replacement(new,old):
    if not old:return
    oldkeys={(r['day'],r['venue']) for r in old};newkeys={(r['day'],r['venue']) for r in new}
    if not oldkeys<=newkeys:raise ValueError('Cboe replacement loses previously retained observations')
    if max(r['day'] for r in new)<max(r['day'] for r in old):
        raise ValueError('Cboe replacement regresses date coverage')
    counts=Counter(r['day'] for r in new);days=sorted(counts)
    if len(days)>1:
        baseline=min(counts[d] for d in days[-21:-1])
        if counts[days[-1]]<max(1,baseline-1):
            raise ValueError('Latest Cboe day has materially incomplete venue coverage')

def row_changes(new,old):
    previous={(r['day'],r['venue']):r['shares'] for r in old}
    current={(r['day'],r['venue']):r['shares'] for r in new}
    return dict(new_venue_day_rows=len(current.keys()-previous.keys()),
                revised_venue_day_rows=sum(current[k]!=previous[k] for k in current.keys()&previous.keys()),
                removed_venue_day_rows=len(previous.keys()-current.keys()))

def cboe_rows(directory,*,as_of=None):
    """Exact annual filenames only; backups/overlapping files cannot double count."""
    as_of=as_of or today_ny();rows=[];seen=set()
    for path in sorted(Path(directory).glob('market_history_*.csv')):
        match=re.fullmatch(r'market_history_(\d{4})\.csv',path.name)
        if not match:continue
        parsed=parse_cboe(path.read_bytes(),year=int(match[1]),as_of=as_of)
        for row in parsed:
            key=(row['day'],row['venue'])
            if key in seen:raise ValueError('Cboe annual files overlap')
            seen.add(key);rows.append(row)
    if not rows:raise ValueError('No valid annual Cboe input files')
    return rows

def aggregate_cboe(rows):
    totals=defaultdict(Decimal);venues=defaultdict(set)
    for row in rows:
        totals[row['day']]+=row['shares'];venues[row['day']].add(row['venue'])
    return [{'Day':d,'total_shares':str(totals[d]),'venues':len(venues[d])} for d in sorted(totals)]

def write_derived(rows,path):
    buf=io.StringIO(newline='');w=csv.DictWriter(buf,fieldnames=['Day','total_shares','venues'],lineterminator='\n')
    w.writeheader();w.writerows(aggregate_cboe(rows));atomic_write(path,buf.getvalue().encode())

def download(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Python-urllib/3.12','Accept-Encoding':'identity'})
    with urllib.request.urlopen(req,timeout=35) as response:
        return response.status,response.read()

def refresh_cboe(*,raw=RAW,derived=DERIVED,as_of=None,fetch=download):
    """One public current-year request; all validation occurs before cache mutation."""
    as_of=as_of or today_ny();year=as_of.year;url=CBOE_URL.format(year=year)
    target=Path(raw)/'cboe'/f'market_history_{year}.csv'
    previous=target.read_bytes() if target.exists() else None
    status,body=fetch(url)
    if status!=200:raise ValueError(f'Cboe HTTP{status}; previous input retained')
    new=parse_cboe(body,year=year,as_of=as_of)
    old=parse_cboe(previous,year=year,as_of=as_of) if previous else []
    validate_replacement(new,old)
    # Validate all historic files before replacement too; never hide bad history.
    historical=[]
    for p in sorted((Path(raw)/'cboe').glob('market_history_*.csv')):
        m=re.fullmatch(r'market_history_(\d{4})\.csv',p.name)
        if m and int(m[1])!=year:historical+=parse_cboe(p.read_bytes(),year=int(m[1]),as_of=as_of)
    atomic_write(target,body)
    write_derived(historical+new,Path(derived)/'cboe_consolidated_daily.csv')
    stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
    log=Path(raw)/'SOURCES_LOG.csv';log.parent.mkdir(parents=True,exist_ok=True)
    local='data/raw/cboe/'+target.name
    receipt=dict(source='cboe',url=url,local_file=local,downloaded_utc=stamp,http_status=status,
                 bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),coverage_start=min(r['day'] for r in new),
                 coverage_end=max(r['day'] for r in new),status='OK',note='Validated current-year refresh; per-venue rows incl FINRA TRFs; historical annual files retained')
    header=not log.exists() or log.stat().st_size==0
    with log.open('a',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=LOG_FIELDS,lineterminator='\n')
        if header:w.writeheader()
        w.writerow(receipt)
    return dict(receipt,changed=previous!=body,previous_sha256=None if previous is None else hashlib.sha256(previous).hexdigest(),rows=len(new),**row_changes(new,old))

def audit(*,raw=RAW,market=MARKET_DAILY,as_of=None):
    """No network; dates are observation bounds, not a claim of complete weeks."""
    as_of=as_of or today_ny();values={s:[] for s in CORE_SERIES};errors=[]
    if Path(market).exists():
        with Path(market).open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                sid=row.get('series_id')
                if sid in values and row.get('value') not in (None,'','.'):
                    try:
                        d=date.fromisoformat(row['observation_date']);x=Decimal(row['value'])
                    except (ValueError,InvalidOperation):continue
                    if d<=as_of and x.is_finite():values[sid].append(d.isoformat())
    frozen=Path(raw)/'fred/MORTGAGE30US.csv'
    if frozen.exists():
        with frozen.open(encoding='utf-8-sig',newline='') as f:
            rd=csv.DictReader(f)
            for row in rd:
                fields=list(row)
                try:d=date.fromisoformat(row[fields[0]]);x=Decimal(row[fields[1]])
                except (ValueError,InvalidOperation,IndexError,TypeError):continue
                if d<=as_of and x.is_finite():values['MORTGAGE30US'].append(d.isoformat())
    latest={s:max(v) if v else None for s,v in values.items()}
    try:
        crows=cboe_rows(Path(raw)/'cboe',as_of=as_of)
        latest['CBOE_CONSOLIDATED']=max(r['day'] for r in crows)
    except (ValueError,OSError) as e:
        latest['CBOE_CONSOLIDATED']=None;errors.append({'source_id':'cboe_scoring_current_year','error':str(e)})
    return dict(as_of=as_of.isoformat(),last_observation_dates=latest,
                observation_age_calendar_days={k:None if v is None else (as_of-date.fromisoformat(v)).days for k,v in latest.items()},
                note='Observation dates only. Scoring must retain its per-series complete-week/release-date coverage guard.',
                audit_errors=errors)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group()
    mode.add_argument('--audit',action='store_true',help='No network calls (default)')
    mode.add_argument('--refresh',action='store_true',help='Download only current-year Cboe before auditing')
    p.add_argument('--as-of',type=date.fromisoformat);p.add_argument('--report',type=Path)
    p.add_argument('--strict',action='store_true',help='Exit nonzero on refresh/validation failure')
    args=p.parse_args(argv);as_of=args.as_of or today_ny();failures=[]
    result=dict(mode='refresh' if args.refresh else 'audit_only',model_calls=0,scoring_outputs_changed=False)
    if args.refresh:
        cache=RAW/'cboe'/f'market_history_{as_of.year}.csv'
        previous_hash=hashlib.sha256(cache.read_bytes()).hexdigest() if cache.exists() else None
        try:result['cboe_refresh']=refresh_cboe(as_of=as_of)
        except Exception as e:
            retained=(hashlib.sha256(cache.read_bytes()).hexdigest() if cache.exists() else None)==previous_hash
            failures.append(dict(source_id='cboe_scoring_current_year',error=f'{type(e).__name__}: {e}',previous_valid_input_retained=retained))
    result.update(audit(as_of=as_of));failures.extend(result['audit_errors']);result['failed_sources']=failures
    result['status']='partial_source_failure' if failures else 'ok'
    if args.report:atomic_write(args.report,(json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps(result,indent=2))
    if args.strict and failures:raise SystemExit(1)
    return result

if __name__=='__main__':main()
