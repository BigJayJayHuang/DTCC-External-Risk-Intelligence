from pathlib import Path
import json
import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter
from jupyter_client import KernelManager

R=Path(__file__).resolve().parents[1]
build=R/'.build';build.mkdir(exist_ok=True)
n=nbformat.read(R/'Public_Data_Refresh_Quality_Checks_CN.ipynb',as_version=4)
manager=KernelManager(kernel_name='python3',ip='127.0.0.1')
manager.kernel_spec.argv=[str(R.parent/'risk_business_ml/.venv/bin/python'),'-m','ipykernel_launcher','-f','{connection_file}']
client=NotebookClient(n,km=manager,timeout=90,startup_timeout=30,resources={'metadata':{'path':str(R)}})
client.execute()
nbformat.write(n,R/'Public_Data_Refresh_Quality_Checks_CN.ipynb')
errors=[o for c in n.cells if c.cell_type=='code' for o in c.get('outputs',[]) if o.get('output_type')=='error']
assert not errors
html,_=HTMLExporter().from_notebook_node(n)
(build/'quality_notebook_preview.html').write_text(html)
(R/'notebook_execution.json').write_text(json.dumps({'code_cells':sum(c.cell_type=='code' for c in n.cells),'execution_counts':[c.execution_count for c in n.cells if c.cell_type=='code'],'error_outputs':len(errors),'executed_top_to_bottom':True},indent=2))
print((R/'validation_results.json').read_text())
