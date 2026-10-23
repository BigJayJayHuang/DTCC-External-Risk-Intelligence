from pathlib import Path
import sys,os,json,nbformat
from nbclient import NotebookClient
R=Path(__file__).resolve().parents[1];q=R/'.qa/jupyter/kernels/capstone_chain';q.mkdir(parents=True,exist_ok=True)
(q/'kernel.json').write_text(json.dumps({'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],'display_name':'Capstone chain research','language':'python'}))
os.environ['IPYTHONDIR']=str(R/'.qa/ipython')
os.environ['JUPYTER_RUNTIME_DIR']=str(R/'.qa/jupyter_runtime')
os.environ['MPLCONFIGDIR']=str(R/'.qa/matplotlib')
os.environ['JUPYTER_PATH']=str(R/'.qa/jupyter')+os.pathsep+os.environ.get('JUPYTER_PATH','')
p=R/'Transmission_Chain_Validation.ipynb';n=nbformat.read(p,as_version=4)
NotebookClient(n,timeout=180,kernel_name='capstone_chain',resources={'metadata':{'path':str(R)}}).execute()
nbformat.validate(n);nbformat.write(n,p)
print('Executed',len([c for c in n.cells if c.cell_type=='code']),'code cells, errors',sum(o.output_type=='error' for c in n.cells if c.cell_type=='code' for o in c.outputs))
