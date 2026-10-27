"""One organized portable package: originalv1 plus expandedv2, synthetic only."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,json,shutil,zipfile
from run_expansion import sha,write_json

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT.parent/'synthetic_chain_simulations_2026_10_27'

def main():
    source=ROOT/'data/synthetic_scenarios.sqlite3';packed=source.with_suffix('.sqlite3.gz')
    with source.open('rb') as src,packed.open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as dst:shutil.copyfileobj(src,dst)
    receipt=json.loads((ROOT/'results/execution_receipt.json').read_text())
    snapshot={'source_type':'synthetic','simulation_id':receipt['simulation_id'],'records':receipt['database_store']['records_in_batch'],
              'database_sha256':sha(source),'compressed_sha256':sha(packed),'compressed_bytes':packed.stat().st_size,
              'note':'Synthetic store only; original empirical database is separate and unchanged.'}
    write_json(ROOT/'data/snapshot_manifest.json',snapshot)
    verify=json.loads((ROOT/'results/verification.json').read_text())
    assert verify['passed'] and verify['simulation_id']==receipt['simulation_id']
    forbidden={'.qa','__pycache__','.ipynb_checkpoints','.DS_Store'}
    files=[]
    for folder in [OLD,ROOT]:
        for path in folder.rglob('*'):
            if path.is_file() and not path.is_symlink() and not forbidden.intersection(path.relative_to(folder).parts) and not path.name.endswith(('.sqlite3','.pyc','.tmp','.lock')):
                files.append((folder.name+'/'+str(path.relative_to(folder)),path))
    files.sort();inventory=[{'file':name,'bytes':p.stat().st_size,'sha256':sha(p)} for name,p in files]
    top='Synthetic_Chain_Models_2026-10-27'
    output=ROOT.parent/(top+'.zip')
    readme='# Synthetic Chain Models / 传导链模拟合集\n\nSIMULATED ONLY / 全部为假设模拟。No empirical validation or calibrated real-world probabilities.\n\n- [Latest expansion / 本轮扩展]('+ROOT.name+'/README.md)\n- [Original DTC/EPN/TBA / 前轮原型]('+OLD.name+'/README.md)\n\nRead results and limitations before using generated data. Compressed synthetic databases can be restored through each folder src/query_store.py. The real public-data database and original empirical statuses are not included or changed.\n'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,path in files:z.write(path,top+'/'+name)
        z.writestr(top+'/README.md',readme)
        z.writestr(top+'/PACKAGE_MANIFEST.json',json.dumps({'generated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'source_type':'synthetic','files':inventory},indent=2)+'\n')
    import hashlib
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        for r in inventory:assert hashlib.sha256(z.read(top+'/'+r['file'])).hexdigest()==r['sha256']
    result={'file':str(output),'files':len(files)+2,'bytes':output.stat().st_size,'sha256':sha(output),
            'zip_integrity':'passed','all_file_checksums':'passed','snapshot':snapshot,
            'content':'One top-level folder; originalv1 and expandedv2 each retain organized subfolders.'}
    write_json(output.parent/(top+'_package_receipt.json'),result)
    print(json.dumps(result,indent=2));return result

if __name__=='__main__':main()
