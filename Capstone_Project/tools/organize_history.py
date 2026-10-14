"""Copy prior Capstone work into the unified folder, preserving source bytes."""
from pathlib import Path
import argparse, hashlib, json, shutil

PROJECT=Path(__file__).resolve().parents[1]
SKIP_DIRS={'.git','.venv','node_modules','__pycache__','.next','.pytest_cache',
           '.ipynb_checkpoints','.data-app-offline','.build'}
SKIP_NAMES={'.DS_Store','.manifest.lock'}

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def organize(source):
    source=Path(source).resolve();copied=[];omitted=[]
    directories=['public_news_prototype','public_performance_data','risk_business_ml','data_refresh_2026_10_14']
    for name in directories:
        for path in sorted((source/name).rglob('*')):
            relative=path.relative_to(source)
            if not path.is_file() or any(x in SKIP_DIRS for x in relative.parts):continue
            if path.is_symlink():raise ValueError('Review symlink before packaging: '+str(relative))
            if path.name in SKIP_NAMES or path.suffix in ['.zip','.lock','.part'] or path.name.endswith(('.headers.txt','-wal','-shm')):
                omitted.append({'file':str(relative),'reason':'Redundant archive, runtime lock/cache, partial download or transport headers'});continue
            if path.name.startswith('.env') or path.name in ['credentials','id_rsa','id_ed25519']:
                raise ValueError('Credential/config file requires review: '+str(relative))
            dest=PROJECT/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
            h=digest(path);assert h==digest(dest)
            copied.append({'source_relative_path':str(relative),'bundle_relative_path':str(relative),'bytes':path.stat().st_size,'sha256':h})
    artifacts=[source/'FICC_九条逻辑链_中英对照.docx']
    artifacts+=list((source/'outputs').rglob('*.xlsx'))
    artifacts+=list((source/'midpoint_presentation/output').glob('*.md'))
    artifacts+=list((source/'midpoint_presentation/output').glob('*.txt'))
    artifacts+=list((source/'midpoint_presentation/output').glob('*.png'))
    for path in sorted(artifacts):
        relative=path.relative_to(source)
        dest=PROJECT/'reports'/path.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(path,dest)
        h=digest(path);assert h==digest(dest)
        copied.append({'source_relative_path':str(relative),'bundle_relative_path':str(dest.relative_to(PROJECT)),'bytes':path.stat().st_size,'sha256':h})
    manifest={'scope':'Previous public-source collection, analysis, generated reports and speaking materials. Existing values and research conclusions are unchanged.',
              'files':copied,'omitted_redundant_files':omitted,
              'retained_only_in_original_workspace':['Project-supplied kickoff/requirements/taxonomy documents and complete source/edited presentation decks.','Virtual environments, installed dependencies, credentials, transport headers and temporary build caches.'],
              'note':'Historical studies are exploratory archived snapshots, not newly validated live risk models.'}
    (PROJECT/'HISTORICAL_FILE_INDEX.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'copied_files':len(copied),'bytes':sum(x['bytes'] for x in copied),'omitted_redundant_files':len(omitted)},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,required=True);args=p.parse_args();organize(args.source_root)
