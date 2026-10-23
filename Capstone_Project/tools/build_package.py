"""Build one self-contained ZIP with a single top-level Capstone_Project folder."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,subprocess,zipfile

PROJECT=Path(__file__).resolve().parents[1]
REPO=PROJECT.parent
PACKAGE_NAME='Capstone_Project_Complete.zip'
DATABASE_RELATIVE='Capstone_Project/capstone_database/data/'

def build(output=None):
    output=Path(output) if output else REPO/'distribution'/PACKAGE_NAME
    output.parent.mkdir(parents=True,exist_ok=True)
    names=subprocess.check_output(['git','ls-files','-z','--','Capstone_Project'],cwd=REPO).decode().split('\0')
    names=sorted(x for x in names if x and (REPO/x).is_file())
    # These files are generated during each cloud update and may not exist in an
    # earlier checkout. Include them explicitly, with paths confined to the bundle.
    for folder in [PROJECT/'capstone_database/data',PROJECT/'capstone_database/exports',PROJECT/'capstone_database/logs']:
        for p in folder.iterdir():
            if p.name in ['capstone.sqlite3.gz','snapshot_manifest.json','latest_update.json','validation.json','dataset_inventory.json','latest_reviewed_batch_sync.json','latest_github_sync.json','latest_research_import.json','research_repeat_import_check.json'] or (folder.name=='exports' and p.suffix=='.csv'):
                names.append(str(p.relative_to(REPO)))
    names=sorted(set(names))
    if not names:raise ValueError('No tracked project files to package')
    inventory=[]
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in names:
            p=REPO/name
            if p.is_symlink() or any(x in {'.git','.venv','node_modules','__pycache__'} for x in p.relative_to(REPO).parts):raise ValueError('Unexpected package path '+name)
            if p.suffix in ['.sqlite3','.sqlite'] and 'capstone_database/data/' in name:raise ValueError('Live database must not be distributed')
            if p.name.startswith('local_'):continue
            z.write(p,name)
            inventory.append({'file':name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
        manifest={'generated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO).decode().strip(),
                  'files':inventory,'structure':'One top-level Capstone_Project folder; archived studies retain their original analysis dates.'}
        z.writestr('Capstone_Project/PACKAGE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(output) as z:
        if z.testzip() is not None:raise ValueError('ZIP integrity failure')
        if any(not x.startswith('Capstone_Project/') for x in z.namelist()):raise ValueError('Package contains multiple top-level roots')
    return {'file':str(output),'files':len(inventory)+1,'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}

if __name__=='__main__':print(json.dumps(build(),indent=2))
