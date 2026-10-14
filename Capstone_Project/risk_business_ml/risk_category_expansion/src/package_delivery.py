from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT.parent/'Twelve_Risk_Families_FICC_ECS_2026-10-05.zip'

def package():
    validation=json.loads((ROOT/'results/validation_checks.json').read_text())
    assert validation['notebook_runtime_errors']==0 and validation['notebook_embedded_figures']==3
    review=json.loads((ROOT/'results/visual_review.json').read_text())
    assert len(review['reviewed_figures'])==3 and review['layout_issues_remaining']==0
    excluded={'.cache','__pycache__','.ipynb_checkpoints','.venv','.git'}
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and not excluded.intersection(p.relative_to(ROOT).parts))
    with zipfile.ZipFile(ARCHIVE,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files:archive.write(path,arcname='risk_category_expansion/'+str(path.relative_to(ROOT)))
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert archive.testzip() is None
        names=archive.namelist()
        required=['十二类风险关联分析_中文说明.md','Twelve_Risk_Families_FICC_ECS.ipynb',
                  'source_manifest.json','reused_input_manifest.json','README.md','requirements.txt',
                  'results/expanded_risk_business_associations.csv','results/validation_checks.json',
                  'data/expanded_risk_observations.csv','results/figures/twelve_family_revenue_heatmap.png']
        for name in required:assert 'risk_category_expansion/'+name in names
        assert len([n for n in names if '/raw/pqd_sources/' in n and n.endswith('.xlsx')])==22
        assert all(not excluded.intersection(Path(name).parts) for name in names)
    evidence={'archive':ARCHIVE.name,'files':len(files),'bytes':ARCHIVE.stat().st_size,
              'sha256':hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),'zip_integrity':'passed',
              'required_entries':'passed','PQD_workbooks_included':22,
              'packaged_at_utc':datetime.now(timezone.utc).isoformat()}
    (ROOT.parent/'Twelve_Risk_Families_FICC_ECS_2026-10-05_package_check.json').write_text(json.dumps(evidence,indent=2))
    print(json.dumps(evidence,indent=2))

if __name__=='__main__':package()
