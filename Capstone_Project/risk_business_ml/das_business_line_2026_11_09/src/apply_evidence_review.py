"""Recorded reviewer corrections to AWS candidates; original API output stays intact."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from validate_outputs import load_bound_sources, validate_understanding

ROOT=Path(__file__).resolve().parents[1]

def main():
    source=ROOT/'aws_reading_reviewed/understanding.json'
    original=json.loads(source.read_text()); result=copy.deepcopy(original); changes=[]
    def setfield(obj,key,value,label):
        old=obj[key]
        if old!=value:
            changes.append(dict(field=label+'.'+key,before=old,after=value))
            obj[key]=value
    facts={f['fact_id']:f for f in result['facts']}; cards={c['card_id']:c for c in result['chains']}
    fact_quotes={
        'F03':'the Staff would not recommend enforcement',
        'F05':'No Collateral or Settlement Value',
        'F06':'a maximum of a four-hour recovery time objective',
        'F07':'Tokens are only transferrable to Registered Wallets',
        'F08':'orders) may be submitted to DTC Monday through Friday between 2:00 a.m. and 6:00 p.m.',
    }
    for fid,q in fact_quotes.items():setfield(facts[fid],'evidence_quote',q,fid)
    chain_quotes={
        'DAS-01':'a maximum of a four-hour recovery time objective',
        'DAS-02':'would constitute DTC’s official books and records.',
        'DAS-03':'Tokens are only transferrable to Registered Wallets',
        'DAS-04':'without further action three years from the date DTC launches operation of the Preliminary Base',
        'DAS-05':'make a cash payment from a corporate action event',
    }
    for cid,q in chain_quotes.items():setfield(cards[cid],'mechanism_evidence_quote',q,cid)
    setfield(facts['F04'],'statement_en','Eligible securities include Russell1000 constituents at pilot launch and later additions (including subsequent index removals), U.S. Treasury bills/bonds/notes, and ETFs tracking major indices.','F04')
    setfield(facts['F04'],'statement_zh','合格证券包括试点上线时的罗素1000成分股及其后新增证券（即使其后被移出指数）、美国国债及追踪主要指数的ETF。','F04')
    setfield(facts['F04'],'limitation','The letter expressly preserves eligibility despite subsequent Russell1000 index removal; index removal alone must not be coded as loss of eligibility.','F04')
    setfield(cards['DAS-01'],'transmission_pathway_en','Network or DTS system unavailability may delay conversion orders or token transfers; participants relying on timely conversion or collateral movement could experience operational delays. System separation is a control intended to limit propagation; core-DTC disruption or participant losses are not automatic and have not been observed here.','DAS-01')
    setfield(cards['DAS-01'],'transmission_pathway_zh','网络或DTS系统不可用可能延迟转换指令或代币转移，使依赖及时转换或抵押品移动的参与者出现运营延误。系统隔离旨在限制影响扩散；不能直接推定核心DTC系统中断或参与者发生损失。','DAS-01')
    setfield(cards['DAS-02'],'transmission_pathway_en','A mismatch between LedgerScan records and on-chain state could require reconciliation or controlled correction; unresolved backlog could delay entitlement processing and affect DTC quarterly reporting to SEC staff. This is a conditional hypothesis; DTC bears the reporting commitment and published outcomes were not obtained.','DAS-02')
    setfield(cards['DAS-02'],'transmission_pathway_zh','LedgerScan记录与链上状态不一致可能需要对账或受控更正；积压可能延迟权益处理，并影响DTC向SEC工作人员提交的季度报告。这是条件性假设；报告承诺由DTC承担，尚未取得公开实测结果。','DAS-02')
    setfield(cards['DAS-04'],'external_shock','SEC staff changes its no-action position or the service authorization approaches expiry; actual violations of permitted asset/participant conditions could also trigger review. Subsequent Russell1000 index removal alone is not a disqualifying event.','DAS-04')
    setfield(cards['DAS-04'],'transmission_pathway_en','A change in applicable regulatory conditions could require service restrictions, rule filings or contingency conversion, depending on official instructions. Capacity relative to affected positions determines the hypothetical adjustment burden. Neither forced conversion nor an enforcement action is assumed to occur automatically.','DAS-04')
    setfield(cards['DAS-04'],'transmission_pathway_zh','适用监管条件改变，可能按官方要求触发服务限制、规则备案或应急转换；转换能力相对于受影响头寸的规模决定假设中的调整负担。不能直接认定会强制转换或发生执法行动。','DAS-04')
    setfield(cards['DAS-05'],'transmission_pathway_en','Peak conversion demand above processing capacity could produce queues and delay participant workflows. Corporate-action payment errors could require correction. The letter permits two limited interfaces to core DTC: securities movements to/from the Digital Omnibus Account and corporate-action cash payments; cash payment is not the sole permitted interface. No processing failure has been established by this research.','DAS-05')
    setfield(cards['DAS-05'],'transmission_pathway_zh','峰值转换需求超过处理能力可能形成队列并延迟参与者工作流；公司行动支付错误可能需要更正。函件允许两类与DTC核心系统的有限接口：数字总括账户证券转入转出，以及公司行动现金支付，后者并非唯一接口。本次研究未证实已经发生处理失败。','DAS-05')
    setfield(result['scope'],'date_limitations',[
        'SEC staff letter dated December11,2025; stated relief expires three years from launch of the Preliminary Base Version, subject to the letter conditions.',
        'Public limited-production milestone: July15,2026; broader DTS launch announcement: October28,2026. These are distinct milestones.',
        'No continuous DAS internal vulnerability/outcome series was obtained from the supplied documents; prelaunch simulation is counterfactual.',
        'Original SEC PDF download returned403. A partial web-reader representation through approximately page10 was used, not the full39-page document.',
    ],'scope')
    setfield(result,'recommended_next_steps_en',[
        'Request actual Factory/LedgerScan capacity, DR-test results, conversion demand and reconciliation records; these populate the five protective-buffer ratios.',
        'Confirm Registered Wallet control attestations and approved infrastructure directly with DTC; named collaborators do not establish deployment or approval.',
        'Confirm the formal Preliminary Base Version commencement date and relief expiry with DTC rather than deriving expiry from a production milestone.',
        'Assess actual public-proxy series separately from internal measurements. Do not substitute market stress or generic crypto prices automatically for DAS V.',
        'Use assumption-based functional/sensitivity tests only with explicit labels; these do not calibrate or empirically validate real DAS risk.',
        'Extend a dedicated reviewed DAS news/card schema before any production classification; preserve the original final16 catalog.',
    ],'recommendations')
    setfield(result,'recommended_next_steps_zh',[
        '索取Factory/LedgerScan处理能力、灾难恢复测试、转换需求和对账记录，用来填写五条链的保护性缓冲比率。',
        '向DTC确认已注册钱包控制证明与实际部署的基础设施；合作机构名单不代表部署或批准清单。',
        '向DTC确认初步基础版本的正式启动日及不采取行动立场的到期日，不从单次生产演示直接推定。',
        '把真实公开代理序列与内部实测数据分开评估；不能直接把市场冲击或泛化币价用作DAS的V。',
        '假设模拟仅用于流程和敏感性测试，须明确标注，不能据此声称已校准或实证验证DAS风险。',
        '先建立可审核的DAS新闻与卡片schema，再接入生产分类；保留原有final16目录。',
    ],'recommendations')
    docs=load_bound_sources(ROOT);errors=validate_understanding(result,docs)
    if errors:raise ValueError(errors)
    if any(c['risk_direction']!='decrease' for c in result['chains']):raise ValueError('Higher protective buffer must imply lower vulnerability')
    out=ROOT/'results';out.mkdir(exist_ok=True)
    (out/'reviewed_understanding.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    receipt=dict(reviewed_at_utc=datetime.now(timezone.utc).isoformat(),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                 source='AWS_BEDROCK_DOCUMENT_UNDERSTANDING',review_method='Exact source excerpt checks and conditional-claim corrections; original API output preserved',
                 changes=changes,quote_errors=errors,validation_scope='Provenance and source consistency only; mechanisms remain hypotheses, not empirically validated',
                 api_paid_calls_in_this_step=0)
    (out/'source_review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'reviewed_facts':len(result['facts']),'reviewed_chains':len(result['chains']),'recorded_corrections':len(changes),'errors':errors}))

if __name__=='__main__':main()
