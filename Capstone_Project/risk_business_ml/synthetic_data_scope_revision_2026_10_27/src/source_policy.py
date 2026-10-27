"""Real observations cannot be generated or overwritten by a gap experiment."""
from pathlib import Path
import hashlib,json
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def assert_generation_allowed(requested_fields,observed_fields):
    conflict=set(requested_fields)&set(observed_fields)
    if conflict:raise ValueError('Observed fields must not be generated: '+', '.join(sorted(conflict)))

def assert_observed_unchanged(before,after,fields):
    """Missing observations remain missing; assumptions belong in separate fields."""
    pd.testing.assert_frame_equal(before[list(fields)].reset_index(drop=True),after[list(fields)].reset_index(drop=True),check_exact=True)

def verify_frozen_sources():
    rows=json.loads((ROOT/'inputs/observed_source_manifest.json').read_text())
    for r in rows:
        if sha(ROOT/r['frozen_path'])!=r['sha256']:raise ValueError('Frozen observed source changed: '+r['file'])
    return rows

def protect_originals():
    result=[]
    for r in json.loads((ROOT/'inputs/protected_real_artifacts.json').read_text()):
        p=Path(r['path']);present=p.exists()
        ok=sha(p)==r['sha256'] if present else True
        result.append({'path':str(p),'present':present,'unchanged':ok})
    if not all(r['unchanged'] for r in result):raise AssertionError('Original empirical evidence changed')
    return result
