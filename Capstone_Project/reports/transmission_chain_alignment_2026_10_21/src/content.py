"""Bilingual chain definitions and explicit mappings from the frozen v1 records."""

def bi(cn, en):
    return {'CN': cn, 'EN': en}

CHAINS = []

def add(cid, legacy, world, mechanism, process, indicator, group=None):
    CHAINS.append(dict(chain_id=cid, namespace='team' if cid.startswith('TEAM-') else 'supplied_reference',
        legacy_ids=legacy, world_event=world, mechanism=mechanism, dtcc_process=process,
        indicator_to_watch=indicator, display_group=group or cid))

# FICC. Actual default and clearing-bank failures are split from their broader v1 parents.
add('FICC-GSD-01', ['FICC-GSD-01'],
    bi('国债抛售或收益率剧烈波动。', 'Treasury selloff or sharp yield swings.'),
    bi('会员已清算头寸的价格变动加大，改变其所需保证金。', "Larger price moves on members' cleared positions change required margin."),
    bi('GSD 保证金要求。', 'GSD margin requirements.'),
    bi('十年期国债收益率日变动绝对值；GSD PQD 6.1.1 环比。', 'Absolute daily changes in the 10-year Treasury yield; GSD PQD 6.1.1 quarter-over-quarter.'))
add('FICC-GSD-02', ['FICC-GSD-02'],
    bi('回购利率飙升或短期融资收紧。', 'Repo rates spike or short-term funding tightens.'),
    bi('会员融资成本上升，每日结算支付更难筹集资金。', "Members' funding costs rise, making daily settlement payments harder to fund."),
    bi('GSD 结算支付和流动性。', 'GSD settlement payments and liquidity.'),
    bi('季末校正 SOFR−EFFR；OFR GCF−DVP 仅作间接市场反应。', 'Quarter-end-adjusted SOFR−EFFR; OFR GCF−DVP is an indirect market response only.'))
add('FICC-GSD-03', ['FICC-GSD-03'],
    bi('国债集中清算合规节点临近、延期或调整。', 'Treasury central clearing deadlines approach, are extended, or change.'),
    bi('机构为满足规则接入清算，包括通过 Sponsored 模式接入，改变接入工作量和业务量。', 'Firms onboard to meet the rule, including through Sponsored clearing, changing onboarding demand and volume.'),
    bi('GSD 客户接入和 Sponsored 业务量。', 'GSD onboarding and Sponsored volume.'),
    bi('SEC 官方节点；Sponsored 活动；实际接入数量。', 'Official SEC milestones; Sponsored activity; actual onboarding counts.'))
add('FICC-GSD-04', ['FICC-GSD-04'],
    bi('银行或交易商会员被降级、出现亏损或信用恶化，尚未确认违约。', 'A bank or dealer member is downgraded, reports losses, or deteriorates in credit without a confirmed default.'),
    bi('会员违约风险上升，增加风险监测和违约管理准备需求；实际违约另归 GSD-06。', 'Higher member default risk increases surveillance and default-management preparedness; an actual default routes to GSD-06.'),
    bi('FICC 会员信用监测及违约管理准备。', 'FICC member credit surveillance and default-management preparedness.'),
    bi('具名会员评级、展望及公告；Baa 利差只作宏观背景。', 'Named-member ratings, outlooks, and disclosures; Baa spreads provide macro context only.'))
add('FICC-GSD-06', ['FICC-GSD-04'],
    bi('GSD 清算会员实际违约或 FICC 宣布停止为其提供服务。', 'A GSD clearing member actually defaults or FICC ceases to act for it.'),
    bi('FICC 按违约程序动用违约会员资源；剩余缺口才按损失分摊规则处理，可能涉及存续会员清算基金。', "FICC applies the defaulting member's resources; any remaining shortfall is handled under loss-allocation rules and may involve surviving members' Clearing Fund deposits."),
    bi('GSD 损失分摊与清算基金互助机制。', 'GSD loss allocation and Clearing Fund mutualization.'),
    bi('具名会员违约及停止服务公告；实际资源使用和缺口。', 'Named-member default and cease-to-act notices; actual resource use and shortfalls.'))
add('FICC-MBSD-01', ['FICC-MBSD-01'],
    bi('房贷利率骤变或 MBS 利差扩大。', 'Mortgage rates jump or MBS spreads widen.'),
    bi('TBA 价格波动改变会员头寸的盯市价值，带动变动保证金和保证金要求变化。', 'TBA price swings change marked-to-market positions and affect variation margin and margin requirements.'),
    bi('MBSD 保证金及变动保证金。', 'MBSD margin and variation margin.'),
    bi('PMMS 房贷利率减国债收益率的周变化代理；MBSD PQD 6.7.1。', 'Weekly changes in the PMMS mortgage-rate-minus-Treasury proxy; MBSD PQD 6.7.1.'))
add('FICC-GSD-08', ['FICC-GSD-06'],
    bi('承担 GSD 结算职能的清算银行出现运营或信用问题。', 'A clearing bank performing a GSD settlement role has an operational or credit problem.'),
    bi('经该银行完成的证券交收与 Fedwire 付款无法按时衔接，使对应 GSD 结算受阻。', 'Securities delivery and Fedwire payment through that bank cannot complete on time, interrupting the affected GSD settlement.'),
    bi('GSD 经清算银行进行的证券结算。', 'GSD securities settlement via clearing banks.'),
    bi('清算银行角色和故障公告；Fedwire 状态；GSD 直接结算证据。', 'Verified clearing-bank role and incident notices; Fedwire status; direct GSD settlement evidence.'))
add('TEAM-FICC-01', ['FICC-GSD-05'],
    bi('CME、ICE 等竞争对手推出国债清算服务、功能或客户接入。', 'A competitor such as CME or ICE launches Treasury clearing services, features, or onboarding.'),
    bi('同一客户群可选择其他服务；只有客户迁移或可比业务量证据才能判断 FICC 份额变化。', 'Customers may choose competing services; migration or comparable volume evidence is needed to assess changes in FICC share.'),
    bi('GSD 新增业务获取与竞争地位。', 'GSD new-business acquisition and competitive position.'),
    bi('竞争对手官方公告、实际清算量及客户迁移；非审批消息本身。', 'Competitor disclosures, actual cleared volumes, and customer migration; approval alone is insufficient.'))
add('TEAM-FICC-02', ['FICC-GSD-06'],
    bi('GSD 会员或其供应商发生网络攻击或系统故障。', 'A GSD member or its vendor suffers a cyberattack or system outage.'),
    bi('若故障确实影响该会员的 GSD 连接、提交或履约能力，交易提交或结算可能延迟。', 'If the incident impairs that member\'s GSD connection, submissions, or obligations, trade submission or settlement may be delayed.'),
    bi('GSD 会员交易提交及结算；银行结算通道问题另归 GSD-08。', 'GSD member submissions and settlement; clearing-bank disruptions route separately to GSD-08.'),
    bi('具名会员故障与 GSD 依赖证据；直接服务通知。', 'Named-member incidents and evidence of GSD dependencies; direct service notices.'))
add('TEAM-FICC-03', ['FICC-MBSD-02'],
    bi('GSE 托管、私有化或机构 MBS 担保安排出现实质变化。', 'A substantive change occurs in GSE conservatorship, privatization, or agency-MBS guarantees.'),
    bi('担保预期或交易约定变化可能改变机构 MBS 定价和 TBA 活动，进而影响 MBSD 清算及风险参数。', 'Changes in guarantee expectations or trading conventions may alter agency-MBS pricing and TBA activity, affecting MBSD clearing and risk parameters.'),
    bi('MBSD TBA 清算活动及相关风险参数。', 'MBSD TBA clearing activity and related risk parameters.'),
    bi('官方改革节点、TRACE 机构 MBS 活动及 MBSD 直接反应。', 'Official reform milestones, TRACE agency-MBS activity, and direct MBSD responses.'))

# ECS. Distinct processes remain separate even when they share an external event.
add('ECS-NSCC-01', ['ECS-NSCC-01B'],
    bi('股市急跌或价格剧烈波动。', 'A sharp equity selloff or large price swings.'),
    bi('每日盯市现金流大幅变化，会员需要当日调动更多现金。', 'Daily mark-to-market payments change sharply, requiring members to move more cash that day.'),
    bi('NSCC 变动保证金。', 'NSCC variation margin.'),
    bi('VIX；VM 单日峰值与日均值之比；VIX jump 只作探索。', 'VIX; peak-to-average daily VM; VIX jump remains exploratory.'), 'NSCC_VM_LIQUIDITY')
add('ECS-NSCC-02', ['ECS-NSCC-03B'],
    bi('短期融资紧张，券商筹资成本上升。', 'Short-term funding tightens and brokers face higher funding costs.'),
    bi('券商可用于每日付款的现金减少，变动保证金和结算付款更难筹集。', 'Brokers have less spare cash for daily payments, making variation margin and settlement payments harder to fund.'),
    bi('NSCC 变动保证金和流动性。', 'NSCC variation margin and liquidity.'),
    bi('校正 SOFR−EFFR；直接 VM 或流动性反应；IM 追缴仅为相关代理。', 'Adjusted SOFR−EFFR; direct VM or liquidity responses; IM calls are a related proxy only.'), 'NSCC_VM_LIQUIDITY')
add('ECS-NSCC-03', ['ECS-NSCC-02A'],
    bi('市场股票成交量异常激增。', 'Equity-market trading volume surges.'),
    bi('交付需求和证券可得性压力加大，可能留下更多尚未完成交收的头寸。', 'Higher delivery demand and securities-availability pressures may leave more positions undelivered.'),
    bi('NSCC CNS 证券交收及未交割余额。', 'NSCC CNS settlement and outstanding fails.'),
    bi('Cboe 成交量；SEC CNS FTD 未交割余额，不是失败率。', 'Cboe volume; SEC CNS outstanding FTD balances, not a fail rate.'))
add('ECS-SET-01', ['ECS-NSCC-04', 'ECS-DTC-01'],
    bi('结算周期缩短或交易时段延长，例如 T+1、T+0 或 24x5。', 'A shorter settlement cycle or longer trading hours, such as T+1, T+0, or 24x5.'),
    bi('处理、确认和筹资窗口变化，迟到或手工步骤可能成为瓶颈；是否增加失败须看实际结果。', 'Changed processing, affirmation, and funding windows may make late or manual steps bottlenecks; any increase in fails requires evidence.'),
    bi('NSCC 与 DTC 结算；分别记录 CNS 和非 CNS 结果。', 'NSCC and DTC settlement; retain separate CNS and non-CNS outcomes.'),
    bi('官方实施节点；两套连续月度失败率。', 'Official implementation milestones; two distinct continuous monthly fail-rate series.'))
add('ECS-NSCC-06', ['ECS-NSCC-03A'],
    bi('NSCC 清算会员实际违约或 NSCC 停止为其提供服务。', 'An NSCC clearing member actually defaults or NSCC ceases to act for it.'),
    bi('NSCC 处理该会员未平仓 CNS 多空头寸，面临买入及平仓期间的市场价格风险。', "NSCC closes out the member's open CNS long and short positions, facing market-price risk during buy-ins and liquidation."),
    bi('NSCC 停止服务后的 CNS 平仓。', 'NSCC CNS close-out after ceasing to act.'),
    bi('具名会员违约、停止服务及 CNS 平仓的直接证据。', 'Direct evidence of named-member default, cease-to-act action, and CNS close-out.'))
add('ECS-DTC-02', ['ECS-DTC-04'],
    bi('DTC 结算银行出现融资、信用或运营问题。', 'A DTC settling bank has a funding, credit, or operational problem.'),
    bi('若该银行拒绝或无法通过 Fedwire 完成汇总净额支付，其所代表参与者的日终资金结算不能按时完成。', 'If the bank refuses or fails to settle its aggregate net-net balance over Fedwire, end-of-day money settlement cannot complete on time for the participants it represents.'),
    bi('DTC 结算银行日终资金结算。', 'DTC settling-bank money settlement.'),
    bi('具名结算银行及 Fedwire 通知；CP−国库券利差仅作背景。', 'Named settling-bank and Fedwire notices; the CP-minus-bill spread is context only.'))
add('ECS-DTC-05', ['ECS-DTC-02A'],
    bi('大型 DTC 参与者遭遇网络攻击或重大系统故障。', 'A large DTC participant suffers a cyber event or major system outage.'),
    bi('参与者与 DTC 的连接或指令传输受损，使其账簿划转和结算受阻，可涉及参与者系统中断处理。', 'Impaired participant connectivity or instruction transmission disrupts book-entry transfers and settlement, potentially invoking participant-system-disruption handling.'),
    bi('DTC 参与者系统中断及相关指令处理。', 'DTC participant system disruption and affected instructions.'),
    bi('具名参与者故障、适用软件及 DTC 服务证据；KEV 计数仅作线索。', 'Named-participant incidents, applicable software, and DTC service evidence; KEV counts are leads only.'))
add('TEAM-ECS-01', ['ECS-NSCC-01A'],
    bi('股市急跌或价格剧烈波动。', 'A sharp equity selloff or large price swings.'),
    bi('头寸风险重估可能改变 Clearing Fund 要求，引发追加保证金需求。', 'Reassessment of position risk may change Clearing Fund requirements and generate additional margin calls.'),
    bi('NSCC Clearing Fund 追缴；区别于每日 VM 付款。', 'NSCC Clearing Fund calls, distinct from daily VM payments.'),
    bi('VIX；追缴额除以上季 IM。', 'VIX; margin calls divided by prior-quarter IM.'))
add('TEAM-ECS-02', ['ECS-NSCC-01C'],
    bi('股市波动超过保证金模型覆盖预期。', 'Equity-market moves exceed the margin model\'s expected coverage.'),
    bi('部分历史头寸损失超过模型所需保证金，产生回测突破并提示覆盖偏差。', 'Losses on some historical positions exceed model-required margin, producing backtesting breaches that indicate coverage gaps.'),
    bi('NSCC 保证金模型覆盖及回测。', 'NSCC margin-model coverage and backtesting.'),
    bi('VIX；回测突破数；保留过去十二个月重叠口径。', 'VIX; backtesting breach counts; retain the overlapping trailing-12-month definition.'))
add('TEAM-ECS-03', ['ECS-NSCC-02B'],
    bi('股票成交量异常激增。', 'Equity trading volume surges.'),
    bi('若交易捕获和净额处理负荷接近实际容量，可能出现延迟或故障；须有独立运营证据。', 'If trade-capture and netting loads approach actual capacity, delays or outages may occur; separate operational evidence is required.'),
    bi('NSCC 交易捕获及净额处理系统。', 'NSCC trade-capture and netting systems.'),
    bi('复用 Cboe 成交量；另需 NSCC 独立延迟或故障序列。', 'Reuse Cboe volume; obtain separate NSCC-specific latency or outage data.'))
add('TEAM-ECS-04', ['ECS-NSCC-03A'],
    bi('具名券商或银行会员信用恶化，尚未确认违约。', 'A named broker or bank member deteriorates in credit without a confirmed default.'),
    bi('信用风险增加可能触发会员监测或风险措施；实际违约后的 CNS 平仓另归 NSCC-06。', 'Higher credit risk may prompt surveillance or risk measures; CNS close-out following actual default routes to NSCC-06.'),
    bi('NSCC 会员信用监测与风险措施。', 'NSCC member credit surveillance and risk measures.'),
    bi('具名会员评级及风险措施；Baa 利差仅作背景。', 'Named-member ratings and risk actions; Baa spreads provide context only.'))
add('TEAM-ECS-05', ['ECS-NSCC-05'],
    bi('三巫日、Russell 调整或 S&P 指数再平衡等已知高峰日期。', 'Known peaks such as triple witching, Russell reconstitution, or S&P index rebalances.'),
    bi('活动集中到可预知日期，增加当日处理负荷；额外失败或故障需单独验证。', 'Activity bunches on predictable dates, raising processing load; additional fails or outages require separate validation.'),
    bi('NSCC 高峰日交易处理和后续交收。', 'NSCC peak-date processing and subsequent settlement.'),
    bi('权威事件日历；复用成交量与 FTD；不等同补充流动性存款。', 'Authoritative event calendars; reuse volume and FTD; distinct from supplemental liquidity deposits.'))
add('TEAM-ECS-06', ['ECS-DTC-02B'],
    bi('云、网络或共享供应商发生广泛故障。', 'A cloud, network, or shared vendor has a widespread outage.'),
    bi('只有确认 DTC 或参与者依赖该服务、且相关连接或指令受阻，才能判断其向 DTC 传导。', 'Transmission requires a verified DTC or participant dependency and evidence that relevant connections or instructions were impaired.'),
    bi('DTC 依赖服务及指令处理；参与者中断与 DTC-05 关联去重。', 'DTC service dependencies and instructions; link participant disruptions to DTC-05 without duplication.'),
    bi('供应商历史及持续时长、依赖关系和 DTC 直接通知。', 'Vendor incident histories and durations, dependencies, and direct DTC notices.'))
add('TEAM-ECS-07', ['ECS-DTC-03'],
    bi('IPO 或债券发行量显著增加。', 'IPO or bond issuance rises sharply.'),
    bi('新券资格审查和首次交收需求增加；是否形成积压取决于容量与实际处理情况。', 'More issues increase eligibility-review and initial-settlement demand; backlogs depend on capacity and observed processing.'),
    bi('DTC 新券资格及初始交收；业务归属暂沿用 ECS。', 'DTC new-issue eligibility and initial settlement; provisionally classified under ECS.'),
    bi('市场范围 424B 计数；DTC 月度发行数量及处理延迟。', 'Market-wide 424B counts; monthly DTC issuance counts and processing delays.'))

add('TEAM-ECS-08', ['ECS-DTC-02A'],
    bi('网络攻击或重大故障直接影响 DTC 自身的相关系统。', 'A cyberattack or major outage directly affects relevant DTC systems.'),
    bi('若 DTC 的指令接收、处理或连接服务确实不可用，相关参与者的账簿划转与结算可能延迟。', 'If DTC instruction intake, processing, or connectivity is unavailable, affected participants may experience delayed book-entry transfers and settlement.'),
    bi('DTC 自身服务连续性；区别于 DTC-05 的参与者系统中断。', 'DTC service continuity, distinct from participant system disruption under DTC-05.'),
    bi('DTC 直接服务及恢复通知；不得仅凭行业漏洞数量推断。', 'Direct DTC service and restoration notices; sector vulnerability counts alone are insufficient.'))

MAPPINGS = []
def mapping(old, new, action_cn, action_en, transfer):
    MAPPINGS.append(dict(legacy_id=old, revised_ids=new, action=bi(action_cn,action_en), validation_transfer=transfer))

mapping('FICC-GSD-01',['FICC-GSD-01'],'相似，按示例收敛到保证金；保留原检验。','Aligned to margin requirements; retain the original test.','same_specification')
mapping('FICC-GSD-02',['FICC-GSD-02'],'相似，按示例写结算流动性；利差结果仅为间接代理。','Aligned to settlement liquidity; the spread result remains an indirect proxy.','proxy_only')
mapping('FICC-GSD-03',['FICC-GSD-03'],'相似，保留接入和 Sponsored；移除必然集中于少数担保会员的结论。','Aligned to onboarding and Sponsored activity; remove inevitable sponsor-concentration claims.','descriptive_only')
mapping('FICC-GSD-04',['FICC-GSD-04','FICC-GSD-06'],'按示例拆分信用恶化与实际违约；不再把降级直接写成共同分摊损失。','Split credit deterioration from actual default; a downgrade does not directly imply mutualized losses.','split_event_stages')
mapping('FICC-MBSD-01',['FICC-MBSD-01'],'相似，按示例保留 TBA 价格到保证金；保留代理及检验限制。','Aligned to TBA prices and margin; retain proxy and test limitations.','same_specification')
mapping('FICC-GSD-05',['TEAM-FICC-01'],'不同机制且不冲突，保留竞争链；新 GSD-05 专指 GCF 履约。','Retain competition as a separate extension; reference GSD-05 concerns GCF obligations.','unrun_outcome')
mapping('FICC-GSD-06',['FICC-GSD-08','TEAM-FICC-02'],'清算银行分支按示例 GSD-08；会员或供应商分支另保留。旧编号让给实际违约。','Align the clearing-bank branch to GSD-08; retain member/vendor operations separately. Reference GSD-06 means actual default.','split_actor_roles')
mapping('FICC-MBSD-02',['TEAM-FICC-03'],'保留 GSE 改革；示例 MBSD-02 是池交付失败，不能按同号替换。','Retain GSE reform; reference MBSD-02 concerns pool-delivery fails, a different mechanism.','unrun_outcome')
mapping('ECS-NSCC-01A',['TEAM-ECS-01'],'IM 追缴与 VM 是不同流程，不冲突，单独保留。','Retain IM calls separately because they differ from VM payments.','same_specification')
mapping('ECS-NSCC-01B',['ECS-NSCC-01'],'与示例股市波动到 VM 相同，采用其编号与流程。','Align equity volatility to VM using the reference ID and process.','same_specification')
mapping('ECS-NSCC-01C',['TEAM-ECS-02'],'回测覆盖是不同流程，保留；不把突破等同实际损失。','Retain backtesting coverage separately; breaches do not establish realized loss.','same_specification')
mapping('ECS-NSCC-02A',['ECS-NSCC-03'],'与示例成交量到 CNS 失败相似，改号；FTD 仍是未交割余额。','Align volume to CNS fails and renumber; FTD remains an outstanding balance.','same_specification')
mapping('ECS-NSCC-02B',['TEAM-ECS-03'],'系统容量与交割失败不同，不冲突，保留容量链。','Retain capacity separately from settlement fails.','unrun_outcome')
mapping('ECS-NSCC-03A',['TEAM-ECS-04','ECS-NSCC-06'],'保留违约前信用链；实际违约按示例 CNS 平仓链。','Retain pre-default credit risk; align actual default to the reference CNS close-out chain.','split_event_stages')
mapping('ECS-NSCC-03B',['ECS-NSCC-02'],'按示例定位 VM 和流动性；旧 IM 比例通过不等于新目标已通过。','Align to VM and liquidity; a legacy IM-ratio pass does not validate the revised target.','target_changed')
mapping('ECS-NSCC-04',['ECS-SET-01'],'与旧 DTC-01 合并事件链，NSCC 结果单独保留；不预设失败增加。','Merge the shared event with legacy DTC-01, retaining a separate NSCC outcome; do not presume rising fails.','merged_separate_outcomes')
mapping('ECS-NSCC-05',['TEAM-ECS-05'],'已知高峰日不等于示例的补充流动性存款，不冲突，保留并改号。','Retain known peak dates separately from the reference supplemental-liquidity-deposit mechanism.','unrun_outcome')
mapping('ECS-DTC-01',['ECS-SET-01'],'并入共同制度事件链，但 DTC 非 CNS 结果不与 NSCC 混合。','Merge the rule-change event while retaining the separate DTC non-CNS outcome.','merged_separate_outcomes')
mapping('ECS-DTC-02A',['ECS-DTC-05','TEAM-ECS-08'],'参与者分支按示例 DTC-05；DTC 自身系统分支另保留。KEV 入库不证明暴露。','Align the participant branch to DTC-05 and retain DTC-owned system disruption separately. KEV additions do not establish exposure.','split_actor_roles')
mapping('ECS-DTC-02B',['TEAM-ECS-06'],'供应商根因不冲突，保留；若归入同一参与者中断，仅链接一次事件。','Retain vendor causes; link once when they lead to the same participant disruption.','unrun_outcome')
mapping('ECS-DTC-03',['TEAM-ECS-07'],'新券处理与示例的市场中断不同，不冲突，保留并改号。','Retain new-issue processing separately from market disruption and renumber.','unrun_outcome')
mapping('ECS-DTC-04',['ECS-DTC-02'],'按结算银行付款链改写；删除 DTC 必须补缺口的断言，须先证实银行角色。','Align to settling-bank payments; remove automatic DTC gap-funding claims and verify the bank role first.','scope_changed')

INTRO = {
 'CN': [
  '本版把原有 FICC 和 ECS 传导链与 DTCC 提供的三步示例对齐：相似链采用示例机制，有冲突的表述以示例为准，不冲突的独立机制保留为团队扩展。原有 22 条均可追溯，没有因为检验未通过而删除。',
  '修订后为 25 条路线，其中 14 条沿用示例编号，11 条使用 TEAM 编号。两条制度变更链合并，四处宽泛假设按事件阶段或机构角色拆分。TEAM 编号表示团队扩展，不代表 DTCC 已确认该假设。',
  '链的正文只回答外部事件、传导机制和具体流程。市场指标是监测线索，检验结果是另一个证据层，均不直接证明某条新闻已造成业务损失。',
  '框架继续使用外部冲击 S 与内部脆弱度 V 的乘积，不新增 E。业务相关性在链匹配时确认；V 缺失保留缺失。本文于 2026 年 10 月 21 日修订，统计证据沿用 10 月 16 日快照，未新增采集或重跑模型。',
 ],
 'EN': [
  'The 22 original FICC and ECS entries are aligned with the supplied DTCC examples. Similar chains follow the reference, conflicts defer to it, and distinct mechanisms without conflicts remain. All original entries are mapped, including failed or incomplete tests.',
  'The 25 revised routes comprise 14 reference IDs and 11 TEAM extensions. Two rule-change entries are merged, and four broader hypotheses are split by event stage or institutional role. TEAM identifies a project extension, not a DTCC-confirmed hypothesis.',
  'Each row states the world event, mechanism, and specific process. Indicators and historical tests provide separate evidence; they do not establish event-specific business loss.',
  'Risk priority remains external shock S multiplied by internal vulnerability V, without E. Check relevance at chain matching and preserve missing V. Definitions were revised on October 21, 2026; evidence remains the October 16 snapshot. No new collection or model run was performed.',
 ]
}

GUIDANCE = {
 'CN': [
  ('同一流程的展示', 'ECS-NSCC-01 与 ECS-NSCC-02 按示例放在同一张 NSCC 变动保证金与流动性卡中，保留价格和融资两条路线。原 IM 追缴与回测链仍独立保留，不与 VM 混为同一指标。'),
  ('相同编号不代表相同机制', '新 GSD-05 为 GCF 履约，新 GSD-06 为实际违约，新 MBSD-02 为池交付，新 NSCC-04 为集中头寸，新 NSCC-05 为补充流动性存款，新 DTC-01 为 MMI 确认，新 DTC-03 为市场中断，新 DTC-04 为加拿大链接。旧结果只能通过下表映射，不得按编号直接关联。'),
  ('不冲突的扩展保留', '竞争、GSE 改革、会员运营、IM 追缴、回测覆盖、容量、违约前信用、高峰日、供应商、新券发行及 DTC 自身系统中断均保留。更具体的示例不自动否定这些不同机制。'),
 ],
 'EN': [
  ('Display by process', 'Following the reference, ECS-NSCC-01 and ECS-NSCC-02 share one NSCC variation-margin and liquidity card, with separate price and funding routes. IM calls and backtesting remain separate processes rather than interchangeable VM measures.'),
  ('Matching IDs do not imply matching mechanisms', 'Reference GSD-05 is GCF obligations, GSD-06 actual default, MBSD-02 pool delivery, NSCC-04 concentrated positions, NSCC-05 supplemental liquidity deposits, DTC-01 MMI acknowledgment, DTC-03 market disruption, and DTC-04 the Canadian link. Map legacy evidence explicitly rather than joining on ID alone.'),
  ('Retain distinct extensions', 'Competition, GSE reform, member operations, IM calls, backtesting, capacity, pre-default credit, peak dates, vendors, new issuance, and DTC-owned system disruption remain in scope. A more specific reference example does not invalidate a different mechanism.'),
 ]
}

VALIDATION = {
 'CN': [
  ('FTD 结果可保留但不扩大解释', '旧 NSCC-02A 对应新 NSCC-03：高量周与多 30.4 百万股未交割余额相关，HAC p=1.3e-05，n=413 周。旧卡门槛通过；这不是新增失败流量、失败率、系统容量不足或 DTCC 损失的证明。'),
  ('融资链不移植旧通过标签', '旧 NSCC-03B 的 IM 追缴比例同季度 ρ=0.454，95% 区间 [0.197, 0.680]，n=23，旧卡门槛通过；变化量 ρ=0.154，后期 ρ=0.086，BH q=0.119。新 NSCC-02 关注 VM 和流动性，因此旧结果仅作相关证据。下一季度 VM 比例约 0.711 是改结果和时滞后的探索，不能当作新链已通过。'),
  ('其余完整统计保留', 'GSD-01：ρ=0.408、区间跨零；GSD-02：系数 0.021bp、p=0.976；MBSD-01：ρ=0.150、区间跨零。旧 NSCC-01A、01B、01C 的同季度 ρ 分别为 0.195、0.081、0.414，区间均跨零。原八项完整执行与两个旧卡门槛通过，仍只是旧规格结论。'),
  ('案例按阶段和机构归属', '雷曼材料保留为违约管理案例，不能证明任一被降级会员已经违约，也不证明存续会员遭受分摊损失。拆出的 GSD-06、NSCC-06 还需核对具体损失分摊或 CNS 平仓步骤。ICBC 的市场和 BNY 影响不能自动变成 GSD 或 DTC 服务中断。'),
  ('制度事件分别取结果', '新 SET-01 共用实施日，但 NSCC CNS 与 DTC 非 CNS 失败率分别分析。指定前后三个月仍缺连续历史，不能用两个快照替代；原首日资料也不支持必然上升。'),
 ],
 'EN': [
  ('Retain the FTD result within its scope', 'Legacy NSCC-02A maps to revised NSCC-03: high-volume weeks were associated with 30.4 million more outstanding FTD shares, HAC p=1.3e-05, n=413 weeks. It met the legacy card threshold. This does not establish new fail flows, a fail rate, inadequate system capacity, or DTCC loss.'),
  ('Do not transfer the funding pass label', 'The legacy NSCC-03B IM-call ratio had same-quarter ρ=0.454, 95% interval [0.197, 0.680], n=23, meeting its legacy card threshold. Correlation in changes was 0.154, later-period correlation 0.086, and BH q=0.119. Revised NSCC-02 concerns VM and liquidity, so the old result is related evidence only. The approximately 0.711 next-quarter VM result changed both outcome and lag and remains exploratory.'),
  ('Preserve the other complete tests', 'GSD-01: ρ=0.408 with an interval crossing zero; GSD-02: coefficient 0.021 bp and p=0.976; MBSD-01: ρ=0.150 with an interval crossing zero. Legacy NSCC-01A, 01B, and 01C had same-quarter ρ of 0.195, 0.081, and 0.414, all with intervals crossing zero. Eight completed statistical tests and two card-threshold passes remain conclusions about the legacy specifications only.'),
  ('Assign cases by stage and actor', 'Retain Lehman materials as default-management evidence. They do not establish that a downgraded member has defaulted or that surviving members suffered mutualized losses. The split GSD-06 and NSCC-06 routes still require evidence for the specific loss-allocation or CNS close-out step. Treasury-market and BNY effects from the ICBC incident do not automatically establish a GSD or DTC service disruption.'),
  ('Separate rule-change outcomes', 'Revised SET-01 shares the implementation event but analyzes NSCC CNS and DTC non-CNS fail rates separately. Continuous history for the specified three months before and after is still missing; two snapshots are not a substitute. First-day evidence also does not support an inevitable increase.'),
 ]
}

DATA_GUIDANCE = {
 'CN': [
  ('共享一次采集', '同一新闻、事件、市场序列和 PQD 单元格只存一份，通过链编号关联。Cboe 成交量供 CNS、容量和高峰日复用；SEC FTD 供 CNS 和高峰日复用；融资与信用序列在相关业务间共用。'),
  ('指标并非业务触达证明', '每条链的可选监测指标见配套结构化清单。对会员信用、银行、网络和供应商事件，必须核对具名机构、角色、依赖与直接流程证据。KEV 入库、行业信用利差或全市场故障不能代替这些信息。'),
  ('V 保留前一期公开可用口径', '保证金路线可研究压力缺口相对 IM，支付路线可研究支付义务相对合格流动性资源，会员路线可研究集中度。PQD 4.4.3 是超出 IM 的压力损失，不是总损失；指标发布日期须早于评估时点。'),
  ('V 与缺失值', '共享系统 17.2/17.3 不能当 NSCC 或 GSD 独立容量；DTC 缺少相应脆弱度时保留缺失，不能填 0，也不能把外部冲击单独标成完整风险分数。'),
 ],
 'EN': [
  ('Collect shared inputs once', 'Store each document, event, market series, and PQD cell once and link it to chain IDs. Reuse Cboe volume across CNS, capacity, and peak-date routes; reuse SEC FTD across CNS and peak dates; share funding and credit series across relevant businesses.'),
  ('Indicators are not proof of process impact', 'Optional monitoring indicators are listed in the accompanying structured catalog. Member-credit, bank, cyber, and vendor events require a named entity, its role, relevant dependencies, and direct process evidence. KEV additions, broad credit spreads, and market-wide outages are not substitutes.'),
  ('Use previously published V', 'Margin routes may examine stress shortfalls relative to IM; payment routes may examine obligations relative to qualifying liquid resources; member routes may examine concentration. PQD 4.4.3 is stress loss exceeding IM, not gross loss. Publication dates must precede the assessment time.'),
  ('Preserve missing vulnerability', 'Shared-system fields 17.2/17.3 are not independent NSCC or GSD capacity measures. Missing DTC vulnerability stays missing rather than zero. A shock-only indicator is not a complete risk score.'),
 ]
}
