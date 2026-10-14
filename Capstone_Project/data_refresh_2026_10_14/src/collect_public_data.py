#!/usr/bin/env python3
"""Bounded, public-only collection. Cache each exact URL once per dated snapshot."""
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import argparse, hashlib, json, subprocess, threading, fcntl
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'raw'
MANIFEST = ROOT / 'source_manifest.json'
LOCK = threading.Lock()
RETRY_TRANSPORT = False

@contextmanager
def manifest_lock():
    with LOCK:
        with (ROOT/'.manifest.lock').open('a') as file:
            fcntl.flock(file,fcntl.LOCK_EX)
            yield
            fcntl.flock(file,fcntl.LOCK_UN)

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)

def collect(source):
    url = source['url']
    parsed = urlparse(url)
    assert parsed.scheme == 'https' and parsed.hostname and not parsed.username
    assert not parsed.hostname.endswith(('.local', '.internal'))
    name = source['id'] + '_' + hashlib.sha256(url.encode()).hexdigest()[:12]
    path = RAW / (name + '.' + source.get('extension', 'html'))
    with manifest_lock():
        old = {r['url']: r for r in json.loads(MANIFEST.read_text())} if MANIFEST.exists() else {}
    if url in old:
        r = old[url]
        transport_retry=RETRY_TRANSPORT and r['status']=='failed' and any(x in r.get('error','') for x in ['curl: (92)','Operation timed out','Recv failure'])
        if not transport_retry and (r['status'] != 'downloaded' or (ROOT / r['file']).is_file()):
            return dict(r, reused_same_run=True)
    record = {'source_id': source['id'], 'source_name': source.get('name', source['id']),
              'url': url, 'file': str(path.relative_to(ROOT)), 'collected_at_utc': now(),
              'public_only': True, 'business_lines': source.get('business_lines', []),
              'kind': source.get('kind'), 'status': 'failed'}
    headers = RAW / (name + '.headers.txt')
    part = RAW / (name + '.part')
    command = ['/usr/bin/curl', '--http1.1', '--fail', '--location', '--silent', '--show-error',
               '--connect-timeout', '10', '--max-time', '45', '--max-filesize', '33554432',
               '--dump-header', str(headers), '--output', str(part),
               '--write-out', '%{http_code}\n%{url_effective}\n%{content_type}', url]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=50)
        parts = result.stdout.strip().splitlines()
        record.update(http_status=int(parts[0]) if parts else None,
                      final_url=parts[1] if len(parts)>1 else None,
                      content_type=parts[2] if len(parts)>2 else None)
        if result.returncode:
            record['error'] = result.stderr.strip()[:1500]
        else:
            data = part.read_bytes()
            if source.get('extension') == 'json':
                json.loads(data)
            if source.get('extension') == 'csv' and b'<html' in data[:2000].lower():
                raise ValueError('HTML returned in place of CSV')
            part.replace(path)
            record.update(status='downloaded', bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    except Exception as exc:
        record['error'] = str(exc)
    finally:
        part.unlink(missing_ok=True)
    if url in old:
        record['previous_attempts']=old[url].get('previous_attempts',[])+[{k:old[url].get(k) for k in ['status','error','http_status','collected_at_utc']}]
    dump(RAW/(name+'.metadata.json'),record)
    with manifest_lock():
        entries = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
        entries = [r for r in entries if r['url'] != url]
        entries.append(record)
        dump(MANIFEST, sorted(entries, key=lambda r:r['source_id']))
    print(record['source_id'], record['status'], record.get('bytes',record.get('error','')), flush=True)
    return record

def main():
    global RETRY_TRANSPORT
    parser = argparse.ArgumentParser()
    parser.add_argument('--registry', type=Path, default=ROOT/'source_registry.json')
    parser.add_argument('--ids', nargs='*')
    parser.add_argument('--retry-transport', action='store_true',help='Retry HTTP/2 transport failures once; do not retry HTTP access denials')
    args = parser.parse_args()
    RETRY_TRANSPORT=args.retry_transport
    RAW.mkdir(parents=True,exist_ok=True)
    sources=json.loads(args.registry.read_text())
    sources=[s for s in sources if s.get('fetch',True) and (not args.ids or s['id'] in args.ids)]
    # An endpoint shared by several services is still requested once.
    dedup={}
    for source in sources:
        if source['url'] not in dedup:
            dedup[source['url']]=source
        else:
            dedup[source['url']]['business_lines']=sorted(set(dedup[source['url']].get('business_lines',[])+source.get('business_lines',[])))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=[f.result() for f in as_completed([pool.submit(collect,s) for s in dedup.values()])]
    print(json.dumps({'requested_unique_urls':len(dedup),'downloaded_or_reused':sum(r['status']=='downloaded' for r in results)},ensure_ascii=False),flush=True)

if __name__ == '__main__':
    main()
