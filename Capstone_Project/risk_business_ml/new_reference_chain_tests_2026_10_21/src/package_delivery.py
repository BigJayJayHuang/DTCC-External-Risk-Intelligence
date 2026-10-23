"""One local delivery ZIP: current chain tests and the checked database snapshot."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,zipfile

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parents[1]

def build():
    output=PROJECT/'risk_business_ml/New_Chain_Tests_and_Database_2026-10-21.zip'
    forbidden={'.qa','__pycache__','.ipynb_checkpoints','.venv','node_modules','.DS_Store'}
    files=[]
    for folder in [ROOT,PROJECT/'capstone_database']:
        for p in folder.rglob('*'):
            rel=p.relative_to(PROJECT)
            if not p.is_file() or p.is_symlink() or any(x in forbidden for x in rel.parts):continue
            if p.name.endswith(('.sqlite3','.sqlite3-wal','.sqlite3-shm','.lock','.tmp','.pyc')):continue
            if p.name.startswith('local_'):continue
            files.append((p,'Capstone_Project/'+rel.as_posix()))
    files.sort(key=lambda item:item[1])
    manifest={'generated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'scope':'Current 31-chain evidence review and local database snapshot. Not the complete historical project or a GitHub publication.','files':[{'file':name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p,name in files]}
    start='''# 新增传导链与数据库 / New chain tests and database

本包包含2026-10-21新增31条链的检验材料，以及更新后的数据库快照。
10条仅完成部分数值检验，4条仅完成案例/条件核对，17条缺专属数据；完整验证0条。
数据库新增12,714条记录，共55,436条。新增来源是批次导入，尚未接入每日自动采集。

Start with risk_business_ml/new_reference_chain_tests_2026_10_21/Concise_Test_Summary_EN.md
or Concise_Test_Summary_CN.md. DATABASE_UPDATE_CN_EN.md explains data coverage and import checks.
To use the included database, run `python3 query.py` inside capstone_database/.
The snapshot is current for this local import; the GitHub release has not been updated.
Do not download the older remote snapshot over this copy when checking these new inputs.

This package contains the current study and database, not all historical project reports.
The notebook is executed; all numeric results are exploratory, not calibrated risk scores.
Source bodies are included in the research raw/ folder; the database snapshot itself retains
structured records and evidence hashes without bundled raw bodies. PACKAGE_MANIFEST.json
lists every disk-backed file and SHA-256 checksum. No cloud upload is performed.
'''
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,name in files:z.write(p,name)
        z.writestr('Capstone_Project/START_HERE_CN_EN.md',start)
        z.writestr('Capstone_Project/PACKAGE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(set(z.namelist()))
        assert all(n.startswith('Capstone_Project/') for n in z.namelist())
        for item in manifest['files']:
            assert hashlib.sha256(z.read(item['file'])).hexdigest()==item['sha256']
    receipt={'file':str(output),'files':len(files)+2,'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'zip_integrity':'passed','all_packaged_file_hashes':'passed'}
    (output.parent/'New_Chain_Tests_and_Database_2026-10-21_manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

if __name__=='__main__':print(json.dumps(build(),indent=2))
