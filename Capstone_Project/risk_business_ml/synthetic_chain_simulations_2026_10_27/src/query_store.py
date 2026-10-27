"""Restore the isolated synthetic snapshot if needed, then query READ-ONLY."""
from pathlib import Path
import argparse,gzip,hashlib,json,shutil,sqlite3,uuid

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def restore(folder):
    folder=Path(folder);target=folder/'synthetic_scenarios.sqlite3'
    if target.exists():return target
    packed=folder/'synthetic_scenarios.sqlite3.gz';m=json.loads((folder/'snapshot_manifest.json').read_text())
    if sha(packed)!=m['compressed_sha256']:raise ValueError('Synthetic snapshot checksum mismatch')
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
    p=argparse.ArgumentParser();p.add_argument('--sql',default='SELECT scenario_id,avg(eod_pending_amount_usd_million) AS simulated_pending_usd_million FROM synthetic_dtc_runs GROUP BY simulation_id,scenario_id');a=p.parse_args()
    print(json.dumps(query(a.sql),ensure_ascii=False,indent=2))
