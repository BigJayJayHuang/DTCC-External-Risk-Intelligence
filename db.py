"""Portable SQLite storage; no network filesystem or shared writable DB required."""
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
import csv, gzip, hashlib, json, os, sqlite3, uuid, zlib

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / 'data/capstone.sqlite3'

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def dumps(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def sha(x):
    return hashlib.sha256(x.encode() if isinstance(x,str) else x).hexdigest()

def connect(path=DEFAULT_DB):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path,timeout=30); c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA journal_mode=WAL')
    c.executescript((ROOT/'schema.sql').read_text())
    return c

def restore(path=DEFAULT_DB):
    path=Path(path); packed=path.with_suffix(path.suffix+'.gz')
    if not path.exists() and packed.exists():
        temporary=path.with_suffix('.restore.'+uuid.uuid4().hex+'.tmp')
        with gzip.open(packed,'rb') as src,temporary.open('wb') as dst:
            import shutil
            shutil.copyfileobj(src,dst)
        temporary.replace(path)
    if not path.exists():
        raise FileNotFoundError('No database snapshot. Run bootstrap.py in the original project, or download data/capstone.sqlite3.gz.')

def put_blob(c,data):
    h=sha(data)
    c.execute("INSERT INTO evidence_blobs VALUES(?,?,?,?) ON CONFLICT(sha256) DO UPDATE SET compression=excluded.compression,byte_count=excluded.byte_count,content=excluded.content",(h,'zlib',len(data),zlib.compress(data,6)))
    return h

def blob(c,h):
    row=c.execute('SELECT content,compression FROM evidence_blobs WHERE sha256=?',(h,)).fetchone()
    if not row: raise ValueError('Missing evidence blob '+str(h))
    if row['compression']!='zlib':raise ValueError('Raw evidence is referenced by hash but not bundled in the shared snapshot')
    return zlib.decompress(row[0])

def start_run(c,kind):
    rid=now()+'_'+uuid.uuid4().hex[:8]
    c.execute('INSERT INTO runs VALUES(?,?,NULL,?,?,NULL)',(rid,now(),kind,'running')); c.commit()
    return rid

VOLATILE={'collected_at_utc','source_file','raw_file','raw_sha256','vintage_id','evidence_location',
          'in_requested_window','original_file','original_text_file','content_hash','last_seen','first_seen','source_id'}

def content_hash(payload):
    return sha(dumps({k:v for k,v in payload.items() if k not in VOLATILE}))

def upsert(c,dataset,key,payload,run_id,source_id=None,blob_hash=None,observed_at=None,evidence='publisher response'):
    # Unknown publication/retrieval dates remain unknown inside the payload. observed_at
    # records when this database actually observed a version, never an inferred release date.
    stamp=now(); observed_at=observed_at or stamp
    old=c.execute('SELECT content_hash,payload FROM records WHERE dataset_id=? AND record_key=?',(dataset,key)).fetchone()
    h=content_hash(payload)
    measurement=next((payload.get(k) for k in ['observation_date','publication_date','date','reporting_month','report_date','reporting_period','quarter','reference_as_of_date'] if payload.get(k)),None)
    c.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(dataset_id,record_key) DO UPDATE SET source_id=excluded.source_id,measurement_date=excluded.measurement_date,payload=excluded.payload,content_hash=excluded.content_hash,last_seen=excluded.last_seen',
              (dataset,key,source_id,measurement,dumps(payload),h,stamp,stamp))
    change='unchanged' if old and old['content_hash']==h else ('revised' if old else 'new')
    if change!='unchanged':
        c.execute('INSERT INTO record_versions(dataset_id,record_key,content_hash,observed_at,ingested_at,run_id,blob_hash,payload) VALUES(?,?,?,?,?,?,?,?)',
                  (dataset,key,h,observed_at,stamp,run_id,blob_hash,dumps(payload)))
    if blob_hash:
        c.execute('INSERT OR IGNORE INTO record_evidence VALUES(?,?,?,?,?)',(dataset,key,source_id or '',blob_hash,evidence))
    return change

def register(c,configs,businesses):
    for b in businesses:
        c.execute('INSERT OR REPLACE INTO business_lines VALUES(?,?,?)',(b['business_line'],b['full_name'],b['legal_scope']))
    for s in configs:
        c.execute('INSERT INTO sources(source_id,name,url,kind,refresh_hours,enabled,config) VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET name=excluded.name,url=excluded.url,kind=excluded.kind,refresh_hours=excluded.refresh_hours,enabled=excluded.enabled,config=excluded.config',
                  (s['id'],s.get('name',s['id']),s['url'],s['kind'],s.get('refresh_hours'),int(s.get('enabled',False)),dumps(s)))
        c.execute('DELETE FROM source_business WHERE source_id=?',(s['id'],))
        for b in s.get('business_lines',[]):
            c.execute('INSERT OR IGNORE INTO source_business VALUES(?,?)',(s['id'],b))
    c.commit()

def snapshot(c,path=DEFAULT_DB,public=True):
    path=Path(path); target=path.with_suffix('.snapshot.'+uuid.uuid4().hex+'.tmp')
    out=sqlite3.connect(target)
    try:
        c.backup(out)
        out.execute('PRAGMA journal_mode=DELETE')
        if public:
            out.execute("UPDATE evidence_blobs SET content=X'',compression='not_bundled'")
            for table in ['records','record_versions']:
                for rowid,payload in out.execute('SELECT rowid,payload FROM '+table+" WHERE json_type(payload,'$.original_text') IS NOT NULL").fetchall():
                    payload=json.loads(payload);payload.pop('original_text',None)
                    out.execute('UPDATE '+table+' SET payload=?,content_hash=? WHERE rowid=?',(dumps(payload),content_hash(payload),rowid))
            out.commit();out.execute('VACUUM')
    finally:out.close()
    packed=path.with_suffix(path.suffix+'.gz'); temp=packed.with_suffix('.gz.tmp')
    with target.open('rb') as src,temp.open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as dst:
            import shutil
            shutil.copyfileobj(src,dst)
    temp.replace(packed);target.unlink()
    return {'file':packed.name,'sha256':sha(packed.read_bytes()),'bytes':packed.stat().st_size}

def export_csv(c,outdir):
    outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
    for table in ['market_daily','news','pqd_quarterly','source_health']:
        cur=c.execute('SELECT * FROM '+table)
        with (outdir/(table+'.csv')).open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f,lineterminator='\n');w.writerow([x[0] for x in cur.description]);w.writerows(cur)
    datasets=[]
    for x in c.execute('SELECT dataset_id,count(*) n,max(measurement_date) latest FROM records GROUP BY dataset_id'):
        datasets.append(dict(x))
    (outdir/'dataset_inventory.json').write_text(json.dumps(datasets,indent=2)+'\n')

@contextmanager
def writer_lock(path):
    p=Path(str(path)+'.lock');p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a+b') as f:
        if os.name=='nt':
            import msvcrt
            if not f.tell():f.write(b'0');f.flush()
            f.seek(0)
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('Another updater is running; no overlapping writes allowed')
            try:yield
            finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise RuntimeError('Another updater is running; no overlapping writes allowed')
            try: yield
            finally: fcntl.flock(f,fcntl.LOCK_UN)
