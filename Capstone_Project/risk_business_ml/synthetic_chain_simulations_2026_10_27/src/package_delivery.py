"""Compress the synthetic store and deliver one labelled, self-contained folder."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,hashlib,json,shutil,zipfile

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def build():
    source=ROOT/'data/synthetic_scenarios.sqlite3';packed=source.with_suffix('.sqlite3.gz')
    with source.open('rb') as src,packed.open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as dst:shutil.copyfileobj(src,dst)
    receipt=json.loads((ROOT/'results/execution_receipt.json').read_text())
    snapshot={'source_type':'synthetic','simulation_id':receipt['simulation_id'],'records':receipt['database_store']['records_in_batch'],'database_sha256':sha(source),'compressed_sha256':sha(packed),'compressed_bytes':packed.stat().st_size,'note':'Separate synthetic store; does not update the empirical public-data database.'}
    (ROOT/'data/snapshot_manifest.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    forbidden={'.qa','__pycache__','.ipynb_checkpoints','.DS_Store'}
    names=[p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink() and not any(x in forbidden for x in p.relative_to(ROOT).parts) and not p.name.endswith(('.sqlite3','.pyc','.tmp','.lock'))]
    names.sort()
    inventory=[{'file':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in names]
    output=ROOT.parent/'Synthetic_Chain_Prototypes_2026-10-27.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in names:z.write(p,ROOT.name+'/'+str(p.relative_to(ROOT)))
        z.writestr(ROOT.name+'/PACKAGE_MANIFEST.json',json.dumps({'generated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'scope':'Synthetic scenario prototypes only; no empirical validation','files':inventory},indent=2)+'\n')
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        for item in inventory:assert hashlib.sha256(z.read(ROOT.name+'/'+item['file'])).hexdigest()==item['sha256']
    result={'file':str(output),'files':len(names)+1,'bytes':output.stat().st_size,'sha256':sha(output),'zip_integrity':'passed','all_file_checksums':'passed','synthetic_snapshot':snapshot}
    (output.parent/'Synthetic_Chain_Prototypes_2026-10-27_package_receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));return result
if __name__=='__main__':build()
