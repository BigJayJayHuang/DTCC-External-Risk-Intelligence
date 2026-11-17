"""Collect a bounded, deduplicated set of public sources. No login or paid calls.

An inaccessible page is recorded as unavailable, never bypassed. HTTP reachability
of a web page is not an observation of the health of the DTS service.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 8_000_000


def digest(value):
    return hashlib.sha256(value).hexdigest()


class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'): self.hidden += 1
        elif tag in ('p','div','br','h1','h2','h3','h4','li','tr'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'): self.hidden = max(0, self.hidden-1)
        elif tag in ('p','div','h1','h2','h3','h4','li','tr'): self.parts.append('\n')
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def text_of(raw, mime, raw_path):
    if raw.startswith(b'%PDF'):
        result = subprocess.run(['pdftotext', '-layout', str(raw_path), '-'],
                                capture_output=True, check=True, timeout=30)
        return result.stdout.decode('utf-8'), 'pdf_text_extraction'
    value = raw.decode('utf-8', errors='replace')
    if 'json' in mime:
        # Validate JSON. Retain publisher JSON without turning samples into facts.
        json.loads(value)
        return value, 'publisher_json'
    parser = Text(); parser.feed(value)
    return '\n'.join(' '.join(x.split()) for x in ''.join(parser.parts).splitlines() if x.strip()), 'html_visible_text'


def fetch(source, root=ROOT):
    record = dict(source, collected_at_utc=datetime.now(timezone.utc).isoformat(),
                  classification='PUBLIC_PUBLISHER_SOURCE', business_line='DAS')
    try:
        headers = {'User-Agent':'Capstone-DAS-Public-Research/1.0', 'Accept':'application/json' if 'api.github.com' in source['url'] else '*/*'}
        request = urllib.request.Request(source['url'], headers=headers)
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES: raise ValueError('Source exceeds bounded download limit')
            mime = response.headers.get('Content-Type','')
            record.update(http_status=response.status, final_url=response.url, content_type=mime,
                          pagination_truncated='rel="next"' in response.headers.get('Link',''))
        suffix = '.pdf' if raw.startswith(b'%PDF') else '.json' if 'json' in mime else '.html'
        raw_hash=digest(raw)
        raw_path = root/'evidence'/(source['source_id']+'-'+raw_hash[:16]+suffix)
        raw_path.write_bytes(raw)
        text, method = text_of(raw, mime, raw_path)
        text_path = root/'inputs'/(source['source_id']+'-'+raw_hash[:16]+'.txt')
        text_path.write_text(text)
        record.update(status='retrieved', raw_file=str(raw_path.relative_to(root)),
                      text_file=str(text_path.relative_to(root)), raw_sha256=digest(raw),
                      text_sha256=digest(text.encode()), byte_count=len(raw),
                      text_characters=len(text), retrieval_method=method, full_document=True)
    except Exception as error:
        record.update(status='unavailable', error=f'{type(error).__name__}: {error}')
        if isinstance(error, urllib.error.HTTPError): record['http_status'] = error.code
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', help='Refresh only named source(s), preserving others')
    args=parser.parse_args()
    config=json.loads((ROOT/'config/sources.json').read_text())
    if len({x['url'] for x in config}) != len(config): raise ValueError('Duplicate URLs; collect once and reuse')
    selected=[s for s in config if not args.source or s['source_id'] in args.source]
    if args.source and len(selected)!=len(set(args.source)): raise ValueError('Unknown source')
    for folder in ('inputs','evidence','results'): (ROOT/folder).mkdir(exist_ok=True)
    manifest_path=ROOT/'inputs/source_manifest.json'
    previous={s['source_id']:s for s in json.loads(manifest_path.read_text())} if manifest_path.exists() else {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        records=list(executor.map(fetch, selected))
    previous.update({s['source_id']:s for s in records})
    ordered=[previous[s['source_id']] for s in config if s['source_id'] in previous]
    manifest_path.write_text(json.dumps(ordered,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'sources':len(ordered),'refreshed':len(records),
                      'retrieved':sum(s['status']=='retrieved' for s in ordered),
                      'unavailable':[s['source_id'] for s in ordered if s['status']!='retrieved']}))


if __name__=='__main__': main()
