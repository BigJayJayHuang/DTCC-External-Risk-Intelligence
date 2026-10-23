"""Independent source check for PQD23.2.1 against FICC guarantee-note tables."""
from pathlib import Path
from pypdf import PdfReader
import json,re,hashlib,shutil
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parents[1]/'public_performance_data/2026-10-05/financial_statements'
def main():
    (ROOT/'inputs/financials').mkdir(exist_ok=True)
    manifest=json.loads((ROOT/'input_manifest.json').read_text());rows=[]
    for period in pd.period_range('2020Q4','2026Q2',freq='Q'):
        name=(f'FICC_Annual_{period.year}_{period.year-1}.pdf' if period.quarter==4 else f'FICC_Q{period.quarter}_{period.year}.pdf')
        source=SOURCE/name;dest=ROOT/'inputs/financials'/name
        if not dest.exists():shutil.copy2(source,dest)
        digest=hashlib.sha256(dest.read_bytes()).hexdigest()
        if not any(row['frozen_copy']==str(dest.relative_to(ROOT)) for row in manifest):manifest.append(dict(original_path=str(source),frozen_copy=str(dest.relative_to(ROOT)),sha256=digest))
        found=[]
        for page_no,page in enumerate(PdfReader(dest).pages,1):
            text=re.sub(r'\s+',' ',page.extract_text())
            if 'open positions' not in text.lower() or 'in billions' not in text.lower():continue
            match=re.search(r'Division\s+(\d{4})\s+(\d{4})\s+GSD\s+\$?\s*([\d,]+)\s+\$?\s*([\d,]+)\s+MBSD\s+([\d,]+)\s+([\d,]+)',text)
            if match:
                year1,year2,gsd1,gsd2,mbsd1,mbsd2=match.groups()
                assert int(year1)==period.year
                for entity,val in [('GSD',gsd1),('MBSD',mbsd1)]:
                    found.append(dict(quarter=str(period),entity=entity,financial_billions_usd=float(val.replace(',','')),financial_usd=float(val.replace(',',''))*1e9,source_file=name,page=page_no,table_text=match.group(),sha256=digest))
        assert len(found)==2,(name,len(found))
        rows+=found
    f=pd.DataFrame(rows);raw=pd.read_csv(ROOT/'data/new_pqd_fields.csv')[['quarter','entity','unsettled_notional_usd_as_reported']].rename(columns={'unsettled_notional_usd_as_reported':'pqd_as_reported'})
    f=f.merge(raw,on=['quarter','entity'],how='left',validate='one_to_one')
    f['financial_to_pqd_ratio']=f.financial_usd/f.pqd_as_reported
    # Finance notes are rounded to billions. Reconcile at that stated precision.
    f['within_rounding_tolerance']=(f.pqd_as_reported-f.financial_usd).abs()<=.501e9
    f['chosen_usd']=f.pqd_as_reported.where(f.within_rounding_tolerance,f.financial_usd)
    f['chosen_source']=f.within_rounding_tolerance.map({True:'PQD numeric cell reconciles to financial note within 0.501 billion USD',False:'financial statement guarantee note in billions; unaligned PQD retained for audit'})
    f.to_csv(ROOT/'data/financial_guarantee_reconciliation.csv',index=False)
    (ROOT/'input_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'data_quality_amendment.json').write_text(json.dumps(dict(reason='Independent source reconciliation found early PQD23.2.1 values about1000times smaller than FICC financial guarantee notes; no threshold change.',affected_test='TBA_PIPELINE',repair='Use financial note USD when PQD does not reconcile within its rounding precision; retain exact source, page and raw value. Fill2024Q4 from actual financial note, explicitly not inferred PQD.',valid_comparison_tolerance_usd=501000000,cleared_notional_repair=dict(periods=['2021Q3','2022Q3'],field='MBSD23.1.2',interpretation='million-USD encoding supported by independently collected monthly clearing-par totals divided by64 Treasury-observation dates in each quarter',factor=1000000,match_tolerance_usd=501000,uncertainty='Treasury observation-day count is a calendar proxy; retain sensitivity excluding both repaired cells',separate_exclusion_sensitivity=True),results_unchanged_elsewhere=True,not_a_new_hypothesis=True,quarterly_fund_flows_source='Federal Reserve September11 2026 Z1 archive, same FU series as FRED; retrieved after FRED failures'),ensure_ascii=False,indent=2)+'\n')
    print(f.loc[~f.within_rounding_tolerance,['quarter','entity','pqd_as_reported','financial_usd','financial_to_pqd_ratio']].to_string(index=False))
if __name__=='__main__':main()
