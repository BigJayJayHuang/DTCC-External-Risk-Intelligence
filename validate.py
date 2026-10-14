"""Check the stored data and every embedded source file before distribution."""
from pathlib import Path
import argparse, json, sqlite3, zlib
import db

def validate(path):
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        assert c.execute('SELECT count(*) FROM business_lines').fetchone()[0]==10
        assert c.execute('SELECT count(*) FROM records').fetchone()[0]>0
        bundled=0
        for h,n,data,compression in c.execute('SELECT sha256,byte_count,content,compression FROM evidence_blobs'):
            if compression=='not_bundled':
                assert data==b'';continue
            assert compression=='zlib'
            content=zlib.decompress(data);assert len(content)==n and db.sha(content)==h;bundled+=1
        assert not c.execute('SELECT dataset_id,record_key,count(*) FROM records GROUP BY dataset_id,record_key HAVING count(*)>1').fetchall()
        assert not c.execute('SELECT DISTINCT entity FROM pqd_quarterly WHERE entity NOT IN (\'GSD\',\'MBSD\',\'NSCC\')').fetchall()
        quarters=c.execute('SELECT count(DISTINCT quarter) FROM pqd_quarterly').fetchone()[0]
        assert quarters>=23
        # The operational columns remain typed nullable numerics for downstream work.
        assert not c.execute("SELECT value FROM market_daily WHERE value IS NOT NULL AND typeof(value) NOT IN ('integer','real') LIMIT 1").fetchall()
        result={'integrity':'ok','foreign_keys':'ok','business_lines':10,'pqd_quarters':quarters,
                'records':c.execute('SELECT count(*) FROM records').fetchone()[0],
                'versions':c.execute('SELECT count(*) FROM record_versions').fetchone()[0],
                'evidence_hash_references':c.execute('SELECT count(*) FROM evidence_blobs').fetchone()[0],
                'verified_bundled_public_evidence_blobs':bundled,
                'dataset_counts':dict(c.execute('SELECT dataset_id,count(*) FROM records GROUP BY dataset_id'))}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=db.DEFAULT_DB);args=p.parse_args();db.restore(args.db)
    result=validate(args.db);folder=db.ROOT/'logs';folder.mkdir(exist_ok=True)
    (folder/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
