from pathlib import Path
import zipfile,xml.etree.ElementTree as ET,json,pandas as pd
R=Path(__file__).resolve().parents[1];rows=[];meta=[]
# Original Federal Reserve daily series corresponding to FRED DCPF3M and DTB3.
for name,source,pattern in [('DCPF3M','fed_cp_xml.zip','RIFSPPFAAD90_N.B'),('DTB3','fed_h15_xml.zip','RIFSGFSM03_N.B')]:
 with zipfile.ZipFile(R/'raw'/source) as z:
  file=next(n for n in z.namelist() if n.endswith('_data.xml'))
  active=False;data=[]
  with z.open(file) as f:
   for ev,el in ET.iterparse(f,events=['start','end']):
    tag=el.tag.rsplit('}',1)[-1]
    if ev=='start' and tag=='Series':
     active=el.attrib.get('SERIES_NAME')==pattern
     if active:meta.append({'series_id':name,'source_zip':source,'xml_file':file,'attributes':dict(el.attrib)})
    elif ev=='end' and tag=='Obs':
     if active and '2018-01-01'<=el.attrib.get('TIME_PERIOD','')<='2026-10-15':
      a=dict(el.attrib);value=float(a['OBS_VALUE']) if a.get('OBS_STATUS')=='A' and float(a['OBS_VALUE'])>-999 else None;data.append({'observation_date':a['TIME_PERIOD'],name:value,'observation_status':a.get('OBS_STATUS')})
     el.clear()
    elif ev=='end' and tag=='Series':el.clear();active=False
 if data:
  df=pd.DataFrame(data);assert not df.observation_date.duplicated().any();df.to_csv(R/'data'/f'{name}.csv',index=False);print(name,len(df),df[name].notna().sum(),flush=True)
 else:print('No exact matching series',name,pattern,flush=True)
(R/'fed_rate_source_definitions.json').write_text(json.dumps(meta,indent=2)+'\n')
