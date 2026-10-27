"""56-chain source precedence, independent of any simulated success/failure."""
from pathlib import Path
from collections import Counter
import json
import pandas as pd
from source_policy import ROOT,sha

LABELS={
 'REAL_ONLY':('沿用真实数据，不生成替代值','Use real data; no synthetic replacement'),
 'REAL_PLUS_MISSING_LINK_SIMULATION':('保留真实部分，只模拟缺失环节','Preserve real components; simulate missing steps only'),
 'GAP_SIMULATION_CANDIDATE':('缺专属数据，可做条件机制模拟','Missing service data; conditional simulation candidate'),
 'NOT_READY':('先补事实／定义，不能随机生成触发依据','Resolve facts/definitions; do not generate trigger evidence'),
}
def esc(x):return str(x).replace('|',' / ').replace('\n',' ')
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(esc(x) for x in r)+' |' for r in rows])

def main():
    records=[]
    for name in ['existing_chain_routes.json','new_chain_routes.json']:
        records+=json.loads((ROOT/'inputs'/name).read_text())
    catalog=json.loads((ROOT/'inputs/chain_registry_v3.json').read_text())
    by_id={r['chain_id']:r for r in records}
    assert len(records)==len(by_id)==56
    assert set(by_id)=={r['chain_id'] for r in catalog['chains']}
    records=[by_id[r['chain_id']] for r in catalog['chains']]
    counts=Counter(r['route'] for r in records)
    base=ROOT.parents[1]
    evidence=[]
    for r in records:
        assert r['route'] in LABELS
        for rel in r['evidence_paths']:
            p=base/rel.split('#')[0]
            assert p.exists(),str(p)
            if p.is_file():evidence.append({'file':rel,'sha256':sha(p)})
        assert not r.get('simulation_is_empirical_validation',False)
    frame=pd.DataFrame([{k:r.get(k,'') for k in ['catalog_version','chain_id','route','real_test_available','real_steps_cn','real_steps_en','missing_steps_cn','missing_steps_en','do_not_simulate_cn','do_not_simulate_en','permissible_simulation_cn','permissible_simulation_en']} for r in records])
    frame.to_csv(ROOT/'results/source_priority_bilingual.csv',index=False)
    (ROOT/'results/source_priority_full.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'results/scope_counts.json').write_text(json.dumps(dict(counts),indent=2)+'\n')
    (ROOT/'results/evidence_manifest.json').write_text(json.dumps(list({r['file']:r for r in evidence}.values()),indent=2)+'\n')
    for language in ['CN','EN']:
        lang=language.lower()
        columns=['catalog_version','chain_id','route','real_test_available','real_steps_'+lang,'missing_steps_'+lang,'do_not_simulate_'+lang,'permissible_simulation_'+lang]
        frame[columns].to_csv(ROOT/'results'/f'source_priority_{language}.csv',index=False)
        rows=[[r['chain_id'],LABELS[r['route']][0 if language=='CN' else 1],r['real_steps_'+lang],r['missing_steps_'+lang],r['permissible_simulation_'+lang]] for r in records]
        headers=['链编号','数据处理方式','已有真实部分','缺失部分','允许的模拟范围'] if language=='CN' else ['Chain ID','Source route','Observed components','Missing components','Permitted simulation']
        intro='# 56条链：真实数据优先、仅模拟缺口\n\n分类针对当前可用证据和检验规格，不是“整条链已经验证”的评级。统计不显著、样本短或未过门槛不构成生成替代数据的理由。未在已采集资料中找到，不等于已证明公开数据不存在。\n\n' if language=='CN' else '# 56 chains: real data first, simulation only for gaps\n\nRoutes reflect current evidence/specifications, not full-chain validation. Insignificance, a short sample or a failed threshold does not justify replacing observations. Not found in collected files does not prove public data are unavailable.\n\n'
        status_rows=[[LABELS[k][0 if language=='CN' else 1],v] for k,v in counts.items()]
        intro+=table(['处理方式','数量'] if language=='CN' else ['Route','Count'],status_rows)+'\n\n'
        (ROOT/f'SOURCE_PRIORITY_{language}.md').write_text(intro+table(headers,rows)+'\n')
    print(json.dumps({'catalog':56,'routes':dict(counts),'evidence_files':len({r['file'] for r in evidence})},ensure_ascii=False));return records

if __name__=='__main__':main()
