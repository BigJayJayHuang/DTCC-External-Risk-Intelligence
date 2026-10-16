"""Download the public inputs the chain cards still need.

    python -m validation.fetch --source fred|ofr|cboe|sec_ftd|dtcc_report|wayback|all

Files land in data/raw/<source>/; every request is appended to data/raw/SOURCES_LOG.csv
(URL, download time, HTTP status, bytes, sha256, coverage). Existing files are not
re-downloaded unless --refresh is given. A source that cannot be reached is logged as
BLOCKED and the run continues.
"""
import argparse, csv, datetime as dt, hashlib, io, json, re, time, urllib.error, urllib.request, zipfile

from .paths import RAW, SOURCES_LOG

GENERIC_UA = 'Python-urllib/3.12'   # default client UA; FRED stalls custom UA strings
SEC_UA = 'Duke FinTech Capstone wc232@duke.edu'   # approved for sec.gov only
SEC_PAUSE = 0.5                                     # well under SEC's 10 requests/second
LOG_FIELDS = ['source', 'url', 'local_file', 'downloaded_utc', 'http_status', 'bytes', 'sha256',
              'coverage_start', 'coverage_end', 'status', 'note']


def _ua(url):
    return SEC_UA if 'sec.gov' in url.split('/')[2] else GENERIC_UA


def log(row):
    new = not SOURCES_LOG.exists()
    SOURCES_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SOURCES_LOG.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, '') for k in LOG_FIELDS})


def get(url, timeout=120, retries=3):
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': _ua(url), 'Accept-Encoding': 'identity'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            last = (e.code, e.read() if e.fp else b'')
            if e.code in (403, 404):
                break
        except Exception as e:  # network errors
            last = (None, str(e).encode())
        time.sleep(2 * (attempt + 1))
    return last


def download(source, url, name, coverage=None, refresh=False, note=''):
    """Download url to RAW/source/name, log it, return the path or None."""
    path = RAW / source / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not refresh:
        return path
    status, body = get(url)
    ok = status == 200 and body
    row = {'source': source, 'url': url, 'downloaded_utc': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
           'http_status': status, 'bytes': len(body or b''), 'note': note}
    if ok:
        path.write_bytes(body)
        row.update(local_file=str(path.relative_to(RAW.parent.parent)), sha256=hashlib.sha256(body).hexdigest(), status='OK')
        if coverage:
            row['coverage_start'], row['coverage_end'] = coverage(body)
    else:
        row.update(status='BLOCKED', note=(note + ' ' + (body or b'')[:120].decode('utf-8', 'replace')).strip())
    log(row)
    return path if ok else None


def _csv_cov(date_col=0):
    def cov(body):
        rows = list(csv.reader(io.StringIO(body.decode('utf-8-sig'))))[1:]
        dates = sorted(r[date_col] for r in rows if r and r[date_col][:2] in ('19', '20'))
        return (dates[0], dates[-1]) if dates else ('', '')
    return cov


def fred(refresh):
    for sid in ['MORTGAGE30US']:
        download('fred', f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}', f'{sid}.csv', _csv_cov(), refresh)


def ofr(refresh):
    def cov(body):
        d = [x[0] for x in json.loads(body) if x[1] is not None]
        return (min(d), max(d)) if d else ('', '')
    for mn in ['REPO-GCF_AR_OO-F', 'REPO-DVP_AR_OO-F', 'REPO-GCF_AR_T-F']:   # D1 (v1) + GSD-02 post-hoc v2; Final only
        download('ofr', f'https://data.financialresearch.gov/v1/series/timeseries?mnemonic={mn}', f'{mn}.json', cov, refresh,
                 'OFR Short-term Funding Monitor API, Final vintage')


def cboe(refresh):
    this_year = dt.date.today().year
    for y in range(2018, this_year + 1):
        download('cboe', f'https://cdn.cboe.com/resources/us/equities/market-statistics/historical-market-volume/market_history_{y}.csv',
                 f'market_history_{y}.csv', _csv_cov(), refresh or y == this_year, 'per-venue daily rows incl. FINRA TRFs')


def sec_ftd(refresh):
    page = 'https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data'
    status, body = get(page)
    time.sleep(SEC_PAUSE)
    links = sorted(set(re.findall(r'href="([^"]*cnsfails(\d{6})([ab])(?:_\d+)?\.zip)"', (body or b'').decode('utf-8', 'replace'))))
    log({'source': 'sec_ftd', 'url': page, 'downloaded_utc': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
         'http_status': status, 'bytes': len(body or b''), 'status': 'OK' if links else 'BLOCKED',
         'note': f'index page; {len(links)} cnsfails links found'})
    for href, yyyymm, half in links:
        if yyyymm < '201801':
            continue
        url = href if href.startswith('http') else 'https://www.sec.gov' + href
        def cov(b):
            z = zipfile.ZipFile(io.BytesIO(b)); text = z.read(z.namelist()[0]).decode('latin-1').splitlines()
            d = sorted(l.split('|')[0] for l in text[1:] if l[:2] == '20')
            return (d[0], d[-1]) if d else ('', '')
        existed = (RAW / 'sec_ftd' / f'cnsfails{yyyymm}{half}.zip').exists()
        download('sec_ftd', url, f'cnsfails{yyyymm}{half}.zip', cov, refresh, 'SEC CNS fails-to-deliver, half-month file')
        if refresh or not existed:
            time.sleep(SEC_PAUSE)


def dtcc_report(refresh):
    # URL recorded in data/raw/dtcc/REPORT_URL.txt once located (see REPORT.md).
    p = RAW / 'dtcc' / 'REPORT_URL.txt'
    if not p.exists():
        log({'source': 'dtcc_report', 'status': 'BLOCKED', 'note': 'T+1 After-Action Report URL not yet located'})
        return
    url = p.read_text().strip()
    download('dtcc', url, 'T1_After_Action_Report_2024-09.pdf', None, refresh, 'DTCC T+1 After-Action Report')


def wayback(refresh):
    targets = ['www.dtcc.com/charts/equities-by-the-numbers',
               'www.dtcc.com/market-index-data/charts/equity-trade-volume-insights',
               'cms-prod.dtcc.com/globalassets/ftp/products/equity_trade_insights.html']
    for t in targets:
        cdx = f'https://web.archive.org/cdx/search/cdx?url={t}&output=json&filter=statuscode:200&collapse=timestamp:6&fl=timestamp,original'
        status, body = get(cdx, timeout=90)
        try:
            rows = json.loads(body)[1:]
        except Exception:
            rows = None
        log({'source': 'wayback', 'url': cdx, 'downloaded_utc': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
             'http_status': status, 'status': 'OK' if rows is not None else 'BLOCKED',
             'note': f'CDX index; {len(rows) if rows is not None else "n/a"} monthly snapshots'})
        for ts, original in rows or []:
            slug = re.sub(r'[^A-Za-z0-9]+', '_', original.split('//')[-1])[:60]
            download('wayback', f'https://web.archive.org/web/{ts}id_/{original}', f'{ts}_{slug}.html', None, refresh,
                     f'Wayback snapshot {ts} of {original}')
            time.sleep(1)


SOURCES = {'fred': fred, 'ofr': ofr, 'cboe': cboe, 'sec_ftd': sec_ftd, 'dtcc_report': dtcc_report, 'wayback': wayback}

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default='all', choices=['all', *SOURCES])
    ap.add_argument('--refresh', action='store_true')
    a = ap.parse_args()
    for name, fn in SOURCES.items():
        if a.source in ('all', name):
            print('fetching', name, flush=True)
            fn(a.refresh)
