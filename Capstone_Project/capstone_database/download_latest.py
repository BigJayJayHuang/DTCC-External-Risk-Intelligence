"""Download the current public team snapshot and verify it before replacing a copy."""
from pathlib import Path
import argparse, gzip, json, shutil, sqlite3, subprocess, tempfile, zipfile
import db

REPOSITORY='BigJayJayHuang/DTCC-External-Risk-Intelligence'

def get(url,target):
    subprocess.run(['curl','--proto','=https','--proto-redir','=https','--fail','--location',
                    '--silent','--show-error','--connect-timeout','10','--max-time','600',
                    '--output',str(target),url],check=True)

def download(repository=REPOSITORY,target=db.DEFAULT_DB):
    # No token is needed for the current public repository. A private repository
    # should use authenticated `gh release download` instead of embedding tokens.
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    with db.writer_lock(target),tempfile.TemporaryDirectory(dir=target.parent,prefix='snapshot-') as tmp:
        tmp=Path(tmp);release=tmp/'release.json'
        get(f'https://api.github.com/repos/{repository}/releases/tags/data-latest',release)
        assets={x['name']:x['browser_download_url'] for x in json.loads(release.read_text())['assets']}
        package='Capstone_Project_Complete.zip'
        if package in assets:
            get(assets[package],tmp/package)
            with zipfile.ZipFile(tmp/package) as archive:
                for name in ['capstone.sqlite3.gz','snapshot_manifest.json']:
                    (tmp/name).write_bytes(archive.read('Capstone_Project/capstone_database/data/'+name))
        else:
            for name in ['capstone.sqlite3.gz','snapshot_manifest.json']:
                get(assets[name],tmp/name)
        manifest=json.loads((tmp/'snapshot_manifest.json').read_text());packed=tmp/'capstone.sqlite3.gz'
        if db.sha(packed.read_bytes())!=manifest['sha256']:
            raise ValueError('Snapshot changed during download or failed checksum. Existing copy was kept; run again.')
        database=tmp/'capstone.sqlite3'
        with gzip.open(packed,'rb') as src,database.open('wb') as dst:shutil.copyfileobj(src,dst)
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as c:
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Invalid database snapshot')
        if any(Path(str(target)+suffix).exists() for suffix in ['-wal','-shm']):
            raise RuntimeError('Close the local collector/database connections before replacing the database copy.')
        database.replace(target);packed.replace(target.with_suffix('.sqlite3.gz'))
        (tmp/'snapshot_manifest.json').replace(target.parent/'snapshot_manifest.json')
    print('Downloaded and verified the shared snapshot:',target)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',default=REPOSITORY);p.add_argument('--db',type=Path,default=db.DEFAULT_DB)
    args=p.parse_args();download(args.repo,args.db)
