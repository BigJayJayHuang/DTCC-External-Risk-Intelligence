from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from zipfile import ZipFile
import json
import subprocess
import xml.etree.ElementTree as ET
from pypdf import PdfReader

root = Path('/Users/shanpeiyuan/Capstone Project/public_performance_data/2026-10-05')
root.mkdir(parents=True, exist_ok=True)
financial_listing = 'https://www.dtcc.com/legal/financial-statements'
quant_listing = 'https://www.dtcc.com/legal/policy-and-compliance'
base = 'https://files.dtcc.com/download/assets/'
records = []
def financial(entity, period, date, suffix, scope):
    records.append(dict(file=f'financial_statements/{entity}_{period}.pdf', title=f'{entity} Financial Statements {period}', entity=entity, business_line='FICC' if entity=='FICC' else 'ECS-related legal entity', reporting_scope=scope, listed_date=date, source_page=financial_listing, download_url=base+suffix, kind='financial_statements', expected_format='pdf'))
for entity, suffix in [
 ('FICC','FICC+Q2+2026+Financial+Statements/f63281b6957a11f1bc7b8a63c041fd82'),
 ('NSCC','NSCC+Q2+2026+Financial+Statements/1143c522957c11f1ac53c258faf12821'),
 ('DTC','DTC+Q2+2026+Financial+Statements/a509d01e957a11f1bfa08a63c041fd82')]:
    financial(entity,'Q2_2026','2026-07-30',suffix,'Three and six months ended June 30, 2026 and 2025; balance sheets June 30, 2026 and December 31, 2025. Entity-wide, not an ECS-only segment statement.')
for entity, suffix in [
 ('FICC','FICC-Q1-2026-Financial-Statements.pdf/32e6ce008c1b11f1adced2e68063bdff'),
 ('NSCC','NSCC-Q1-2026-Financial-Statements.pdf/32bd4e908c1b11f1b385da7b8d447cd5'),
 ('DTC','DTC-Q1-2026-Financial-Statements/ad89ee5e957a11f1a15a4ec37e043074')]:
    financial(entity,'Q1_2026','2026-04-30',suffix,'Three months ended March 31, 2026 and 2025; balance sheets March 31, 2026 and December 31, 2025. Entity-wide, not an ECS-only segment statement.')
financial('FICC','Annual_2025_2024','2026-02-27','FICC-Financial-Statements-Annual-2025/068fecf6957b11f190ec6a7a18072738','Audited financial statements for 2025 and 2024.')
financial('DTC','Annual_2025_2024','2026-02-27','DTC-Financial-Statements-Annual-2025/adbc48e0957a11f1bc7b8a63c041fd82','Audited financial statements for 2025 and 2024; DTC also covers services outside ECS.')
financial('NSCC','Annual_2024_2023','2025-02-28','NSCC-Financial-Statements-Annual-2024/a256a1ce369b11f0b16f526112f6cc5f','Audited financial statements for 2024 and 2023; older baseline. A 2025 NSCC annual report was indexed at a now-unavailable legacy URL but not present in the current NSCC financial listing inspected.')
for quarter, date, xlsx, pdf in [
 ('2026_Q2','2026-09-01','DTCC-PQD-2026Q2.xlsx/b6842b5aa85d11f18303c6529a108655','CPMI-IOSCO-Public-Quantitative+Disclosures-Q2-2026.pdf/b5a58e7ca85d11f1b801464272346ad0'),
 ('2026_Q1','2026-05-28','DTCC-PQD-026Q1.xlsx/6f3986768c1c11f1897116f61497a0ac','CPMI-IOSCO-Public-Quantitative-Disclosures-Q1-2026.pdf/6ee26a948c1c11f19d00da7b8d447cd5'),
 ('2025_Q4','2026-03-09','CPMI-IOSCO+Public+Quantitative+Disclosures+-+Q4+2025+excel/7c70ac18957a11f1ab3f4ec37e043074','CPMI-IOSCO+Public+Quantitative+Disclosures+-+Q4+2025/7ce632c6957a11f197c9fe5809e33e04')]:
    for extension, suffix in [('xlsx',xlsx),('pdf',pdf)]:
        records.append(dict(file=f'quantitative_disclosures/DTCC_PQD_{quarter}.{extension}',title=f'CPMI IOSCO Quantitative Disclosure Results {quarter}',entity='FICC and NSCC',business_line='FICC and ECS-related NSCC',reporting_scope='Public quantitative disclosure for central counterparties. Retain original GSD, MBSD and NSCC scopes and each metric observation window. Not a DTC quantitative statement or monthly dataset.',listed_date=date,source_page=quant_listing,download_url=base+suffix,kind='public_quantitative_disclosure',expected_format=extension))

def download(record):
    path=root/record['file']
    path.parent.mkdir(parents=True,exist_ok=True)
    result=subprocess.run(['/usr/bin/curl','--fail','--location','--max-time','45','--silent','--show-error',record['download_url'],'--output',str(path)],capture_output=True,text=True)
    record['collected_at_utc']=datetime.now(timezone.utc).isoformat()
    if result.returncode:
        record['status']='download_failed'
        record['error']=result.stderr.strip()
        print('FAILED',record['file'],record['error'],flush=True)
        return record
    content=path.read_bytes()
    record['bytes']=len(content)
    record['sha256']=sha256(content).hexdigest()
    try:
        if record['expected_format']=='pdf':
            assert content.startswith(b'%PDF-'),'Not a PDF'
            reader=PdfReader(path)
            record['pages']=len(reader.pages)
            first_text='\n'.join(page.extract_text() or '' for page in reader.pages[:min(5,len(reader.pages))])
            record['first_pages_text']=first_text[:1500]
            assert len(first_text)>100,'Empty or unreadable first pages'
        else:
            assert content.startswith(b'PK'),'Not an XLSX ZIP'
            with ZipFile(path) as package:
                assert package.testzip() is None
                ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                workbook=ET.fromstring(package.read('xl/workbook.xml'))
                record['sheet_names']=[sheet.attrib['name'] for sheet in workbook.findall('s:sheets/s:sheet',ns)]
                assert record['sheet_names'],'No worksheets'
        record['status']='downloaded_and_format_verified'
        print('OK',record['file'],record['bytes'],flush=True)
    except Exception as error:
        record['status']='verification_failed'
        record['error']=str(error)
        print('VERIFY FAILED',record['file'],str(error),flush=True)
    return record

with ThreadPoolExecutor(max_workers=4) as pool:
    verified=list(pool.map(download,records))
manifest={'collection_date_local':'2026-10-05','timezone':'America/New_York','source_restriction':'Public official DTCC data only','discovery_method':'Official DTCC pages inspected in browser; direct links copied from visible download tables. Old /-/media/ paths returned 404; current links use files.dtcc.com.','scope_warning':'ECS is a business line mapped to NSCC and DTC, not an independently reported financial entity. DTC financial statements include asset services and other activities. Keep entities separate and do not sum their headline figures as ECS-only profit.','release_time_note':'listed_date is the date displayed on the official listing. It is not independently verified to be the first public release timestamp.','gaps':['NSCC Annual 2025/2024 report appears in a legacy search result, but the legacy URL is unavailable and the current financial listing did not show it; the verified 2024/2023 report is included as an older baseline.'],'files':verified}
(root/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
failures=[record['file'] for record in verified if record['status']!='downloaded_and_format_verified']
print(json.dumps({'files':len(verified),'verified':len(verified)-len(failures),'failed':failures,'folder':str(root)}),flush=True)
if failures: raise SystemExit(1)
