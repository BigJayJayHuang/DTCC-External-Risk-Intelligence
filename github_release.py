"""GitHub runner helper: restore durable state and publish one shared release."""
from pathlib import Path
import argparse, gzip, json, os, shutil, subprocess, sys, tempfile
import db

TAG='data-latest'

def gh(*args,optional=False):
    p=subprocess.run(['gh',*args],capture_output=True,text=True)
    if p.returncode:
        if optional and '(HTTP 404)' in p.stderr:return None
        raise RuntimeError('GitHub command failed: '+p.stderr[:1500])
    return p.stdout

def restore(repository):
    value=gh('api',f'repos/{repository}/releases/tags/{TAG}',optional=True)
    initial=value is None
    if value is None:
        # A deleted release must not silently reset the accumulated history.
        existing=gh('api',f'repos/{repository}/git/ref/tags/{TAG}',optional=True)
        if existing is not None:raise RuntimeError('Snapshot release is missing but its tag exists. Restore the release from a previous Actions artifact; refusing to reset history.')
        if not db.DEFAULT_DB.with_suffix('.sqlite3.gz').exists():raise RuntimeError('No initial seed snapshot')
        print('First run: using the reviewed repository seed snapshot.')
    else:
        gh('release','download',TAG,'--repo',repository,'--pattern','capstone.sqlite3.gz','--pattern','snapshot_manifest.json','--dir','data','--clobber')
        manifest=json.loads(Path('data/snapshot_manifest.json').read_text())
        packed=Path('data/capstone.sqlite3.gz')
        if db.sha(packed.read_bytes())!=manifest['sha256']:raise ValueError('Published snapshot checksum mismatch')
        print('Restored the latest shared snapshot and verified its checksum.')
    db.restore()
    if initial:
        c=db.connect()
        with c:c.execute('UPDATE sources SET last_checked=NULL WHERE enabled=1')
        c.close()

def publish(repository):
    from validate import validate
    source_result=validate(db.DEFAULT_DB)
    with tempfile.TemporaryDirectory(prefix='verify-shared-') as tmp:
        shared=Path(tmp)/'shared.sqlite3'
        with gzip.open('data/capstone.sqlite3.gz','rb') as src,shared.open('wb') as dst:shutil.copyfileobj(src,dst)
        result=validate(shared)
    manifest=json.loads(Path('logs/latest_update.json').read_text())['snapshot']
    manifest.update(generated_at_utc=db.now(),database=result,repository=repository,distribution='Structured data and evidence hashes; raw source bodies are not bundled in the public release.')
    manifest['source_validation']=source_result
    Path('data/snapshot_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    value=gh('api',f'repos/{repository}/releases/tags/{TAG}',optional=True)
    notes='Latest public-source Capstone database. See latest_update.json for partial failures, reporting lags, manual-review sources, and update time. Download capstone.sqlite3.gz and snapshot_manifest.json together. No calibrated risk scores or verified DTCC incident exposure.'
    if value is None:
        gh('release','create',TAG,'--repo',repository,'--target',os.environ.get('GITHUB_SHA','main'),'--title','Latest shared public-data snapshot','--notes',notes,'--prerelease')
    assets=['data/capstone.sqlite3.gz','data/snapshot_manifest.json','logs/latest_update.json','logs/validation.json']
    assets+=list(map(str,Path('exports').glob('*')))
    gh('release','upload',TAG,'--repo',repository,'--clobber',*assets)
    print('Published shared snapshot assets to '+repository+'/releases/tag/'+TAG)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['restore','publish']);p.add_argument('--repo',default=os.environ.get('GITHUB_REPOSITORY','BigJayJayHuang/DTCC-External-Risk-Intelligence'))
    args=p.parse_args();globals()[args.command](args.repo)
