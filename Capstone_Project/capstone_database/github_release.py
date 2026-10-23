"""GitHub runner helper: restore durable state and publish one shared release."""
from pathlib import Path
import argparse, gzip, json, os, shutil, subprocess, sys, tempfile, zipfile
import db

TAG='data-latest'
PACKAGE='Capstone_Project_Complete.zip'
DATA_PREFIX='Capstone_Project/capstone_database/data/'

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
        release=json.loads(value)
        if PACKAGE in {x['name'] for x in release['assets']}:
            with tempfile.TemporaryDirectory(prefix='restore-project-') as tmp:
                gh('release','download',TAG,'--repo',repository,'--pattern',PACKAGE,'--dir',tmp,'--clobber')
                with zipfile.ZipFile(Path(tmp)/PACKAGE) as archive:
                    for name in ['capstone.sqlite3.gz','snapshot_manifest.json']:
                        Path('data',name).write_bytes(archive.read(DATA_PREFIX+name))
        else:
            # Migration compatibility with the earlier release's separate assets.
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

def import_reviewed(repository=None, *, bundle=None, database=None, log_dir=None):
    """Add a committed frozen batch to restored durable state, once per content.

    Never restore the repository seed over remote state or rerun frozen analysis.
    The successful marker also prevents an old frozen batch from overwriting
    later revisions to its keys when the daily workflow runs again.
    """
    from import_chain_research import DEFAULT_BUNDLE, import_bundle
    bundle=Path(bundle) if bundle is not None else DEFAULT_BUNDLE
    path=Path(database) if database is not None else db.DEFAULT_DB
    log_dir=Path(log_dir) if log_dir is not None else db.ROOT/'logs'
    inputs=['fetch_manifest.json','input_manifest.json',
            'data/treasury_auction_observations.csv','results/auction_filter_audit.json',
            'data/mmf_repo_flow_million_usd.csv','data/mutual_fund_net_issuance_million_usd.csv',
            'data/financial_guarantee_reconciliation.csv','data/mbsd_cleared_notional_reconciliation.csv',
            'data/new_pqd_cell_evidence.csv','data/new_pqd_fields.csv']
    hashes={name:db.sha((bundle/name).read_bytes()) for name in inputs}
    fingerprint=db.sha(db.dumps(hashes))
    c=db.connect(path)
    try:
        prior=c.execute("SELECT summary FROM runs WHERE kind='reviewed_batch_sync' AND status='success' AND CASE WHEN json_valid(summary) THEN json_extract(summary,'$.batch_fingerprint') END=? ORDER BY finished_at DESC LIMIT 1",(fingerprint,)).fetchone()
        if prior:
            result={'status':'already_applied','bundle':bundle.name,'batch_fingerprint':fingerprint,'checked_at_utc':db.now(),'reason':'Frozen batch already integrated; preserve subsequent remote revisions.'}
        else:
            rid=db.start_run(c,'reviewed_batch_sync')
            try:
                receipt=import_bundle(bundle=bundle,path=path,make_snapshot=False)
                result={'status':'success','bundle':bundle.name,'batch_fingerprint':fingerprint,'input_hashes':hashes,'applied_at_utc':db.now(),'import':receipt}
                with c:c.execute('UPDATE runs SET finished_at=?,status=?,summary=? WHERE run_id=?',(db.now(),'success',db.dumps(result),rid))
            except Exception as exc:
                with c:c.execute('UPDATE runs SET finished_at=?,status=?,summary=? WHERE run_id=?',(db.now(),'failed',db.dumps({'batch_fingerprint':fingerprint,'error':str(exc)}),rid))
                raise
    finally:c.close()
    log_dir.mkdir(parents=True,exist_ok=True)
    (log_dir/'latest_reviewed_batch_sync.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Reviewed research batch: '+result['status']+'; normal incremental update follows.')
    return result

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
    notes='Download one file: Capstone_Project_Complete.zip. It contains one Capstone_Project folder with the current database, earlier public-data collection, historical analysis, notebooks, bilingual reports and speaking materials. Start with Capstone_Project/README.md. The daily workflow refreshes the database and republishes this complete package; historical research is unchanged. Review the included database logs for failures and manual-review sources. No calibrated risk scores or verified DTCC incident exposure.'
    if value is None:
        gh('release','create',TAG,'--repo',repository,'--target',os.environ.get('GITHUB_SHA','main'),'--title','Complete Capstone project package','--notes',notes,'--prerelease')
    sys.path.insert(0,str(db.ROOT.parent/'tools'))
    from build_package import build
    package=build()
    gh('release','upload',TAG,'--repo',repository,'--clobber',package['file'])
    published=json.loads(gh('api',f'repos/{repository}/releases/tags/{TAG}'))
    asset=next(x for x in published['assets'] if x['name']==PACKAGE)
    if asset['size']!=package['bytes']:raise ValueError('Uploaded complete package size mismatch')
    if asset.get('digest') and asset['digest']!='sha256:'+package['sha256']:raise ValueError('Uploaded complete package digest mismatch')
    # Remove only assets from our superseded separate-file delivery after the new
    # complete package has been uploaded and checked. Other team assets are untouched.
    legacy={'capstone.sqlite3.gz','snapshot_manifest.json','latest_update.json','validation.json',
            'dataset_inventory.json','market_daily.csv','news.csv','pqd_quarterly.csv','source_health.csv'}
    for old in published['assets']:
        if old['name'] in legacy:gh('release','delete-asset',TAG,old['name'],'--repo',repository,'--yes')
    gh('release','edit',TAG,'--repo',repository,'--title','Complete Capstone project package','--notes',notes)
    print('Published one complete project package to '+repository+'/releases/tag/'+TAG)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['restore','import-reviewed','publish']);p.add_argument('--repo',default=os.environ.get('GITHUB_REPOSITORY','BigJayJayHuang/DTCC-External-Risk-Intelligence'))
    args=p.parse_args();globals()[args.command.replace('-','_')](args.repo)
