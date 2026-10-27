"""Checksum-verified restoration and read-only queries of the synthetic store."""
from pathlib import Path
import argparse,gzip,hashlib,json,shutil,sqlite3,uuid

ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def restore(folder):
    folder=Path(folder);target=folder/'synthetic_scenarios.sqlite3'
    manifest=folder/'snapshot_manifest.json'
    m=json.loads(manifest.read_text()) if manifest.exists() else None
    if m is not None and m['source_type']!='synthetic':raise ValueError('Only synthetic snapshots supported')
    if target.exists():
        if m is not None and sha(target)!=m['database_sha256']:raise ValueError('Existing synthetic database checksum mismatch')
        return target
    if m is None:raise FileNotFoundError('Missing synthetic snapshot manifest')
    packed=folder/'synthetic_scenarios.sqlite3.gz'
    if sha(packed)!=m['compressed_sha256']:raise ValueError('Compressed synthetic snapshot checksum mismatch')
    temp=folder/('.restore_'+uuid.uuid4().hex+'.tmp')
    try:
        with gzip.open(packed,'rb') as src,temp.open('wb') as dst:shutil.copyfileobj(src,dst)
        if sha(temp)!=m['database_sha256']:raise ValueError('Restored synthetic database checksum mismatch')
        temp.replace(target)
    finally:
        if temp.exists():temp.unlink()
    return target

def query(sql,folder=ROOT/'data'):
    path=restore(folder);c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        c.row_factory=sqlite3.Row
        return [dict(r) for r in c.execute(sql)]
    finally:c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sql',default='SELECT model_id,scenario_id,primary_metric,primary_units,avg(primary_value) AS hypothetical_mean FROM synthetic_ml_runs GROUP BY simulation_id,model_id,scenario_id,primary_metric,primary_units');a=p.parse_args()
    print(json.dumps(query(a.sql),ensure_ascii=False,indent=2))
