"""Parallel Chinese/English workflow explanation; shared facts are frozen separately."""

CN = [
{'title':'项目目标与交付边界', 'paras':[
'我们要建立的是一套能够解释外部事件如何影响 DTCC 不同业务的风险情报流程。输入包括公开新闻、市场时间序列和业务披露；输出应是一张张有证据支持的“事件 × 业务线”影响卡片，说明影响可能经哪条路径发生、需要监测什么，以及哪些关键事实仍然未知。',
'同一条新闻不应直接转成所有业务共同的风险分数。我们先确认事件，再核实它与具体业务、资产、会员或服务提供商的联系，然后区分外部冲击、业务暴露、内部脆弱度和实际业务反应。已有模型与统计检验用于约束这些判断，不能替代业务机制和事件证据。',
'本报告整理日期为 2026 年 10 月 15 日。模型及 PQD 检验仍使用截至 2026Q2 的冻结数据；公开采集与共享数据库在 10 月 14 日已更新并完成云端运行验证。报告日期不代表所有数据都观察到 10 月 15 日，也不代表今天重新训练了模型。'],
'table':(['环节','目前完成的工作','仍需补齐的部分'],[
['公开数据','采集原型、共享数据库、来源记录、十业务线来源映射与每日 GitHub 工作流','动态披露目录和部分网页仍需人工复核'],
['业务逻辑','FICC 九条传导链及十业务线数据需求和范围','事件级真实暴露、处理量与服务质量证据'],
['训练与检验','Ridge 对照模型、风险类别扩展、事件检验、PQD 关联和补充检验','新时期数据上的稳定表现与因果识别'],
['影响评估','可解释的监测框架与候选指标','可靠的跨业务统一评分及自动化事件归因']]),
'note':'阅读顺序：先看总流程，再看数据和模型如何支持判断，最后看跨业务比较与事件示例。'},

{'title':'端到端流程图','figure':True,'note':'蓝色表示已有的数据或研究环节；灰色虚线表示仍需整合或验证的业务评估模块。历史检验已经执行，不等于指标、传导路径或风险分数已经验证通过。'},

{'title':'从什么数据开始以及如何处理','paras':[
'我们将信息分成四类，并保留各自的观察频率。新闻说明发生了什么；市场数据说明外部环境如何变化；业务数据说明业务如何反应；风险缓冲数据描述业务在冲击来临前的承受能力。四类数据不能互相替代。[P1–P4]'],
'table':(['数据层','已使用或收集的输入','处理后的用途'],[
['公开信息','美联储、SEC、CFTC、ECB、BIS；DTCC 通知；ESMA、FCA、Federal Register 等','保留标题、摘要、来源和时间；形成待复核事件与候选业务标签'],
['外部市场','FRED 的 SOFR、EFFR、国债收益率、VIX、信用利差等；另有行业与公开技术事件资料','按经济含义构造资金、利率、信用、股市等通道特征'],
['业务反应','PQD、财务披露、FICC 日度/月度活动、ECS/ITP 月度快照、承销和 RDS 报告','按法律实体、服务、期间和单位建立结果序列'],
['内部状态','已公开且当时可用的保证金、支付义务、流动性资源和会员集中度','构建业务专属的脆弱度候选；未公开项目保留缺失']]),
'subsections':[
('清洗与存储规则',[
'同一公开来源采集一次，通过关联表服务多个业务。文章去重与事件合并分开：相同网址一般对应同一文档；不同报道只有在实体、时间和事件事实一致时，才合并到同一事件 ID，不能只凭关键词自动合并。',
'分别保存发布时间、事件时间、生效时间、观察期间、首次采集和后续版本。只有日期时不制造 UTC 时点。缺失不填零，季度值不前向填充成日度业务标签。',
'统一金额单位，区分单季与累计财务值；计算环比前补齐日历季度索引。保留原值、字段定义、单元格或页码、下载链接和哈希。历史修订形成新版本，不覆盖证据。']),
('时间可用性',[
'日度特征只能使用当天之前已经公开的信息。季度结果可用于事后研究，但整个季度的最大冲击只有季度结束后才能确定，不能放进季度中某一天的实时预测。'])]},

{'title':'逻辑链与传导路径如何落地','paras':[
'逻辑链回答“为什么可能有关”；传导路径回答“冲击经过哪些具体对象和业务步骤，最终改变什么结果”。完整链条应写成：事件 → 风险通道 → 受影响的会员或资产 → 具体服务流程 → 可观察结果，并在每一个箭头旁标注支持证据与缺口。逻辑先于变量选择与训练，不能在看到相关性后再补一个因果故事。',
'例如：回购资金压力 → 相关会员筹资更困难 → 支付保证金或结算款的压力上升 → 若出现支付延误或违约，GSD 可能需要更多应急流动性。市场利差只能支持第一步；会员关系、付款能力和实际应急需求仍要分别核实。[S1, P1]'],
'table':(['FICC 原有九条链','业务与中间传导环节','应核实的业务结果'],[
['1 国债市场波动','GSD：价格重估 → 头寸与违约平仓风险 → 保证金调整','保证金要求、追缴、压力暴露；不能直接称为亏损'],
['2 回购资金压力','GSD：会员融资 → 保证金与结算支付','支付义务、资金来源及覆盖情况'],
['3 机构财务恶化','GSD/MBSD：先核实会员或清算关系 → 履约能力','真实敞口、付款失败和违约处理证据'],
['4 机构 MBS 变化','MBSD：价格、久期、凸性和提前还款 → MBS 暴露','MBS 专属价格信号与保证金反应'],
['5 监管规则变化','GSD 等：适用范围和生效日 → 清算接入与流程调整','业务量、实施负担与合规准备'],
['6 业务及会员增长','GSD/MBSD：清算规模和集中度 → 资源与容量需求','量、集中度、处理质量与资源变化'],
['7 关键服务中断','GSD/MBSD：核实依赖 → 交易处理或结算受阻','可用性、延迟、积压和恢复时间'],
['8 MBS 数据或通知问题','MBSD：数据/贷款池通知 → 匹配与交割步骤','更正、未匹配、通知时效和结算失败'],
['9 清算服务竞争','GSD：客户采用和替代选择 → 份额、价格和规模','实际客户迁移、份额和收入证据']]),
'note':'九条链是机制清单，不是九个已训练成功的模型。业务增长、规则变化或竞争新闻也不天然意味着损失。'},

{'title':'历史模型是怎样训练的','paras':[
'第一阶段训练的是业务指标的关联模型，而不是新闻文本分类器。我们按实体和目标分别训练 Ridge 回归，即带收缩约束的线性回归，以减少小样本和相关特征造成的不稳定。它能比较加入风险代理后误差是否改善，但不能证明某一新闻造成了业务损失。[P2, S3]',
'基准模型使用上一季度的业务指标变化和季度季节项；增强模型在同一基础上加入六个风险代理：波动变化、利率重定价、信用环境变化、资金利差、监管公告活动和货币政策公告活动。公告计数只衡量信息活动，不等于风险严重度。',
'共设置 13 个实体—目标序列：FICC、NSCC、DTC 的收入增长及利润率变化，以及 GSD、MBSD 的清算交易边和名义金额增长。NSCC 与 DTC 是法律实体口径，不能把它们合并成一个虚构的 ECS 分部收入。'],
'table':(['训练步骤','实际做法','目的'],[
['确定标签','真实业务指标的环比增长或百分点变化；不补造缺失目标','让模型回答明确且可观测的问题'],
['按时间划分','训练截至 2025Q2；2025Q3–2026Q2 为原模型保留期','避免随机打散时间序列'],
['选择参数','训练期内四个顺序验证窗口；alpha 候选为 1、10、100','调参不查看最终保留期误差'],
['训练预处理','标准化和必要的滞后控制值填补只在各训练折拟合','防止未来信息泄漏'],
['同样本比较','增强模型与相同目标、相同期间的基准模型比较 MAE','判断新增风险特征是否提供增量信息']]),
'paras_after':[
'13 个目标中有 5 个在原保留期内降低了平均绝对误差（MAE），但每个目标只有 2–4 个可用测试季度。该实验使用当前下载的历史版本和同季度风险特征，因此属于事后条件关联实验，不能称为严格的实时预测回测。相关的后续资料已被查看，也不能再把它当作新的盲测集。',
'下一阶段若训练事件级影响模型，需要人工复核的事件—业务标签、当时可用的暴露与脆弱度、明确的结果窗口和更多高频业务结果。现阶段尚未训练并验证覆盖十条业务线的新闻影响分类器或损失预测模型。']},

{'title':'指标验证做到了哪一步','paras':[
'我们使用两类检验：事件检验看候选指标能否识别已知压力窗口；业务关联检验看指标是否与相应业务结果共同变化。二者回答不同问题，不能用“市场指标亮了”代替“业务确实受损”。[P3–P5]'],
'table':(['研究阶段','已核对的结果','应如何解读'],[
['12 类风险扩展','20 个风险特征、482 个同季或滞后关联；0 项通过探索性 FDR 5%','数据覆盖扩大；仍未建立稳定统计关系'],
['日度事件检验','7 个候选中 4 个通过原事件初筛','候选对指定窗口有反应，不等于业务影响验证'],
['原下一季 PQD 检验','GSD、MBSD 无候选通过双门槛；NSCC 两项资金候选仅过初筛','NSCC 区间跨零，BH 校正不通过，不能确认传导'],
['补充业务反应检验','共 882 条记录；全样本 48 项通过普通 BH 5%，较早样本为 0','事后扩展且时期不稳定；普通 p 值未充分处理序列依赖'],
['冲击与脆弱度乘积','NSCC 校正资金例：筛选期 rho 0.430，后续为 -0.143','乘积尚未证明优于单独压力或脆弱度']]),
'subsections':[
('怎样减少误判',[
'原事件报警使用此前 252 个有效观察的 90% 分位数，至少 126 个历史值，阈值排除当天；季度压力取预先定义指标的最大值，至少 45 个有效日。非指定事件期间的报警比例只是误报代理，因为没有覆盖所有真实压力事件。',
'同季度和下一季度分别分析：前者更接近业务反应的同期诊断，后者检查持续性或领先关系。Spearman 秩相关、BH 多重检验、四季度区块 bootstrap 和差分/分期检查用于评估稳定性；它们本身不识别因果。',
'原门槛与事件窗口在本轮分析前固定，但历史事件早已公开，不是当年预注册。补充检验又是在看过原结果后设计的；不能因为新增结果更好，就把它包装成一次独立验证。'])]},

{'title':'业务反应和内部脆弱度必须分开','paras':[
'业务反应是冲击后需求、负担或服务表现的变化；内部脆弱度是冲击发生前的缓冲与承受能力。保证金增加可能意味着风险管理在响应，也可能反映规模或模型变化。它既不自动证明业务变差，也不自动证明风控成功。[P3, P5]'],
'table':(['指标或字段','主要用途','不能直接推导的结论'],[
['6.1.1 季末初始保证金要求及环比','业务规模与保证金需求反应','不是事件日损失；增长也可能来自业务量或规则变化'],
['6.6.1 日均 VM 与 6.7.1 最大单日 VM','季度支付流与峰值负担；可同时看峰值/日均','不是 DTCC 收入、亏损或服务失败'],
['6.8.1 最大单日 IM 追缴','相对已存抵押品的最大汇总缺口及实际追缴，含日内','不是保证金要求总量的最大增幅'],
['4.4.3 / 6.1.1','超过初始保证金的压力损失相对季末保证金的脆弱度候选','分子不是总压力损失；常有 T12m 与季末时点错配'],
['压力支付义务 / 已量化资源','流动性脆弱度候选，另列现金及承诺资源子集','资源不是全为现金；跨时点比值大于 1 不证明真实缺口'],
['18.2.2 前五会员持仓份额','会员集中度候选，反映潜在集中暴露','不是市场份额，也不是已发生的会员违约']]),
'paras_after':[
'选择脆弱度必须按“当时已公开”而不是机械取 t−1 季度。例如 2026Q1 PQD 的目录列示日期为 2026 年 5 月 28 日，在 Q2 开始时尚不能据此声称该报告已可用。目录日期仍只是首次公开时间的代理，历史原始版本尚未完整核实。',
'对 ITP、RDS、Asset Services、DAS、DDA、Data Services 和 Consulting，应优先考虑延迟、失败率、数据质量、系统容量、供应商依赖或客户集中度，不能借用清算业务的保证金比率来填补其脆弱度。']},

{'title':'同一事件如何形成不同业务的评估','paras':[
'同一事件先形成多个通道的冲击向量 S，而不是一个“万能严重度”。例如银行事件可能同时影响利率、信用和资金，但各通道必须分别有市场或事实证据。业务暴露 E 决定通道是否接得到该业务；脆弱度 V 决定在给定暴露下业务是否更难承受。',
'在输入具备共同尺度、适用范围和足够证据时，可研究通道层面的优先级 P(e,b,c)=100×S(e,c)×E(e,b,c)×V(b,c; a)。e 是事件，b 是业务，c 是通道，a 是截至评估时已公开的最近状态。这个式子是待验证的监测框架，不是已拟合的概率模型。S×E 可合称业务特定的外部冲击，从而保留“外部冲击×内部脆弱度”的原框架；若冲击中已含暴露，不应再乘一次 E。'],
'table':(['评估项','具体问题','当前处理规则'],[
['相关性与暴露门槛','事件是否涉及该业务资产、会员、地区、客户、系统或供应商？','区分已核实、逻辑相关待核实、证据不足、不适用；未知不当作零'],
['外部冲击 S','对应通道相对自身历史有多异常，方向和持续时间如何？','采用预先定义的指标与仅用过去数据的尺度；新闻条数不能代替冲击'],
['内部脆弱度 V','冲击发生前有哪些已知缓冲不足或操作弱点？','只使用当时可用的业务专属字段；缺失则不生成该路径分数'],
['业务后果向量','可能影响财务、保证金/流动性、处理质量还是战略机会？','不同维度分开报方向、幅度、时间窗与单位，不随意相加'],
['证据质量','每个箭头是否有事实、暴露和实际结果支持？','单独报告证据等级、数据覆盖及区间，不与压力混成一个分数']]),
'paras_after':[
'即使各业务都算出 0–100 分，也不天然可比较。用每条业务自己的历史百分位，比较的是各自异常程度，不能说 80 分对应相同经济损失。只有暴露定义、脆弱度尺度与结果标尺经过跨业务校准后，才研究统一排序。当前更稳妥的输出是按业务展示原指标、方向与证据，不给十条业务硬排风险名次。',
'同一事件经多条路径或多篇报道进入系统时，应先合并事件，再检查通道重叠。通道权重不能直接设为相关系数，尤其不能按全样本最高相关反复挑选。']},

{'title':'十条业务线需要不同的结果标尺 一','paras':['下表是业务路径与数据需求的比较，不是本项目已确认的事件影响。公开业务范围支持机制解释；事件的适用性和实际后果仍须另证。[P1, P4, S1, S4, S5]'],
'table':(['业务线与范围','典型传导路径','结果与脆弱度应看什么'],[
['FICC 固定收益清算\nGSD 与 MBSD 分开','国债/回购或机构 MBS 冲击 → 会员头寸、融资和支付 → 清算资源需求','结果：保证金、追缴、支付负担、失败与处理量。脆弱度：可用资源、集中度；MBSD 还需 MBS 专属暴露。'],
['ECS 股票清算结算\nNSCC 与 DTC 分开','股票/ETF 活动、波动或结算规则变化 → 清算支付与证券交收','结果：NSCC 保证金与量；DTC 交收失败/延迟。脆弱度按清算与交收分别定义；实体财务并非纯 ECS 分部。'],
['RDS 报告与衍生品服务','规则/字段变化或交易活动 → 交易报告、校验与生命周期处理','结果：报告拒绝、更正、及时性和服务可用性。脆弱度：数据质量、客户/地区/系统集中度；公开仓储总量只是活动代理。'],
['WIS 财富与投资服务','基金流量、保险或私募市场变化 → 申购赎回与结算处理','结果：处理量、拒绝、现金/指令积压、产品收入。脆弱度：渠道和客户集中度、操作容量；行业基金资产不是 WIS 业务量。'],
['ITP 机构交易处理','T+1、交易激增或 SSI 问题 → 分配、匹配、确认和截止时间','结果：匹配/确认率、例外率、延迟与积压。脆弱度：手工处理、SSI 质量及连接依赖；不适用 CCP 保证金。']]),
'note':'收入或处理量上升可能是商业机会，同时也可能增加操作负担。两种方向应分开记录，不能把量增长统一归为“风险更高”或“表现更好”。'},

{'title':'十条业务线需要不同的结果标尺 二','table':(['业务线与范围','典型传导路径','结果与脆弱度应看什么'],[
['Asset Services 资产服务','发行、公司行动、税务或托管变化 → 资格、保管记录、支付与通知','结果：发行处理、截止时间履约、支付/税务差错和对账。脆弱度：代理/发行人集中度、处理积压；承销金额不是收入。'],
['DAS DTC 数字资产服务','证券代币化规则或网络变化 → 传统与链上资产转换和交收衔接','结果：代币化证券量、转换/赎回失败、对账及可用性。脆弱度：链、托管和接口依赖；BTC/ETH 价格不能替代其证券暴露。'],
['DDA 数字资产技术平台','平台漏洞、互操作或供应商问题 → 平台/API 与智能合约工作流','结果：错误、延迟、中断及客户留存。脆弱度：组件、链与供应商集中度；公开漏洞不证明平台实际受影响。'],
['Data Services 数据服务','上游来源或数据规则变化 → 产品加工、接口与交付','结果：完整性、错误/修订、发布延迟、可用性及订阅留存。脆弱度：上游依赖和校验能力；底层市场量不是数据销售额。'],
['Consulting 咨询服务','监管生效、T+1 或数字资产采用 → 客户准备与咨询需求','结果：项目订单、积压、交付周期、利用率和利润。脆弱度：客户集中度和人员容量；监管新闻可能带来机会，不等于风险损失。']]),
'paras_after':[
'目前公开资料不足以为十条业务全部建立同质量的监督学习标签。我们有 FICC、NSCC、DTC 的历史财务与部分运营数据，但多数非清算业务缺少独立收入、错误率、容量、服务依赖及客户暴露的连续数据。这里列的是后续需要补齐的字段，不是已经拿到的内部数据。',
'扩展工作应按业务结果决定数据优先级：先取得经批准的汇总业务指标与暴露，再检查能否与事件时间对齐。没有真实结果标签的业务，先保留机制分析与证据卡片，不能用其他实体的指标代填。']},

{'title':'用同一个历史事件演示分业务判断','paras':[
'以 2023 年 3 月银行压力中的 SVB 事件为例。我们的固定研究窗口是 3 月 8 日至 17 日，并非对该事件唯一有效的窗口。以下是冻结市场数据的实测窗口摘要，不是 DTCC 业务损失。[P3]'],
'table':(['通道候选','窗口内实测峰值','相对原历史阈值'],[
['10 年国债收益率日变动绝对值','23 bp','报警；8 个有效日中 50% 的日报警'],
['Baa 利差 20 日扩大幅度','41 bp','报警；8 个有效日中 50% 的日报警'],
['SOFR−EFFR 原始利差','0 bp','相对自身负的历史基线仍可报警；不等于严重回购融资短缺'],
['VIX','26.52','此窗口未越过原先的滚动 90% 阈值，不代表股市没有风险']]),
'paras_after':['这些结果说明，一个事件可以在利率和信用变动上明显，在原始资金利差或所用 VIX 阈值上却不呈同等强度。不能从“银行出事”直接推出“所有业务发生同样资金危机”。'],
'table2':(['业务','应追踪的路径','当前能给出的判断'],[
['GSD','国债重估 → 保证金与会员支付；另查资金证据','通道有关；实际头寸与事件日追缴仍缺，不能归因具体损失'],
['MBSD','利率变化 → MBS 久期/凸性与价格 → 保证金','机制相关；缺 MBS 专属信号和暴露，不给与 GSD 相同权重'],
['ECS','股票活动与会员支付 → NSCC 清算/DTC 交收','另查股票及业务结果；不能借用国债指标证明 ECS 受损'],
['ITP 与 RDS','波动与交易调整 → 确认、匹配或报告负担','需要例外、积压或报告质量数据；量增长本身不证明失败'],
['其余六条业务','按各自资产、流程、客户或平台依赖逐项核实','无相关事件级结果时保留待核实，而非统一给零分或高分']]),
'note':'PQD 的季度峰值和 T12m 指标无法单独定位到 SVB 事件日。即便同季业务指标变化，也仍可能包含其他事件、规模和模型调整。'},

{'title':'如何呈现可比较的影响与证据','paras':[
'每条事件—业务记录至少保存：事件 ID、业务及法律实体、通道、链条各步的证据、实际暴露、评估时可用的脆弱度、结果维度、方向、单位、观察窗口、参考基线、数据版本和待核实项。证据状态用“已知事实／机制推断／模型估计／尚未观测”区分，不给未经校准的置信概率。',
'衡量业务变化时，先报告本业务相对基线的变化，例如保证金环比、失败率增加的百分点、平均延迟或峰值追缴占已知规模的比例。若有可靠的历史模型，可再报告实际变化减去条件基准估计；这一残差仍不是事件的因果效应。不同单位的量不可直接相加。'],
'subsections':[('仅用于解释算术的教学示例',[
'假设同一利率通道的冲击 S=0.80，且暂时拥有按共同规则定义的 E 与 V。以下输入完全是假设，既不是实际 DTCC 数据，也不是本项目训练出的参数；只演示为什么同一事件可能出现不同优先级。'])],
'table':(['假设业务','S','E','V','示例优先级 100×S×E×V'],[
['GSD','0.80','0.90','0.60','43.2'],['MBSD','0.80','0.70','0.80','44.8'],['ECS NSCC','0.80','0.40','0.50','16.0']]),
'paras_after':[
'在这组假设中，MBSD 暴露较低，但脆弱度较高，因此乘积略高。这只是一道框架算术题，不能据此断言 MBSD 的实际风险高于 GSD，也不能将 44.8 解读成 44.8% 的损失概率。真实 E 或 V 缺失时，真实系统应显示“暂不评分”。',
'实际交付卡片应同时展示方向与证据：例如“保证金需求可能上升，事件日业务证据不足，待核实会员暴露”，而不是只给一个总分。财务负担、操作压力、服务质量和商业机会分栏呈现，避免把有利收入与不利运行压力互相抵消。']},

{'title':'落地顺序与证据索引','subsections':[
('下一阶段实施顺序',[
'第一步，维护现有共享数据库与每日采集，补齐事件 ID 和人工业务相关性复核。第二步，按十条业务清单索要经批准的汇总暴露、服务质量和业务结果，并保留当时可用的历史版本。',
'第三步，冻结结果变量、窗口和门槛，在新增未见数据上做时间顺序验证，分别比较基准、仅外部、仅脆弱度、相加与交互项。先检验是否有稳定增量价值，再讨论权重和跨业务尺度。第四步，只有达标的路径进入量化监测，其他路径继续保留定性证据和缺口。',
'日常更新与研究训练是两个作业。GitHub 每天更新数据并重发完整项目包；它不会自动重训练历史模型，也不会把新新闻自动变成已确认的业务影响。']),
('本地证据文件',[
'[P1] reports/FICC_九条逻辑链_中英对照.docx；data_refresh_2026_10_14/business_requirements.json。',
'[P2] risk_business_ml/models/model_manifest.json；results/model_comparison.csv；Analysis_Results_and_Usage_Guide_EN.md。',
'[P3] risk_business_ml/event_vulnerability_tests_2026_10_06/analysis_plan.json；results/event_detail.csv、event_screen.csv、pqd_lagged_spearman.csv 与 interaction_vs_persistence_baseline.csv。',
'[P4] risk_business_ml/risk_category_expansion/results/expanded_analysis_summary.json；data/risk_taxonomy.csv。',
'[P5] risk_business_ml/feedback_revision_report_2026_10_06/results/analysis_summary.json；report_content.json；data/response_cell_evidence.csv。',
'[P6] capstone_database/schema.sql、update.py、sources.json；仓库 .github/workflows/daily-data.yml。以上相对路径以 Capstone_Project 为根目录。'])],
'sources':True,'note':'本报告的数字来自上述既有文件的复核，没有因撰写报告而重新训练模型或重新选择结果。'}
]

EN = [
{'title':'Project purpose and delivery boundary','paras':[
'We are building a risk-intelligence workflow that explains how external events may affect different DTCC businesses. Public news, market series and business disclosures are the inputs. The intended output is an evidence-backed event-by-business assessment: the potential transmission route, the outcome to monitor and the facts that remain unknown.',
'A headline should not immediately become the same risk score for every business. We first establish the event, check its connection to a specific business, asset, member or provider, and separate the external shock, business exposure, internal vulnerability and observed business response. Models and statistical tests constrain those judgments; they do not replace business mechanisms or event evidence.',
'Prepared October 15, 2026. Model and PQD tests still use frozen observations through 2026Q2. The public-data refresh and shared database were updated and verified in the cloud on October 14. The preparation date does not mean all data extend through October 15 or that models were retrained today.'],
'table':(['Stage','Work already completed','What remains'],[
['Public data','Collection prototype, shared database, provenance, source mappings for ten businesses and daily GitHub workflow','Manual checks for dynamic disclosure directories and some webpages'],
['Business logic','Nine FICC transmission chains; business scope and data requirements for ten lines','Event-level exposure, workload and service-quality evidence'],
['Training and testing','Ridge comparisons, risk-family expansion, event screening, PQD associations and supplemental tests','Stable performance on genuinely new periods and causal identification'],
['Impact assessment','Interpretable monitoring framework and candidate indicators','Reliable cross-business calibration and automated event attribution']]),
'note':'Read the overall workflow first, then the supporting data and models, and finally the cross-business comparison and event example.'},

{'title':'End to end workflow','figure':True,'note':'Blue denotes existing data or research steps. Dashed gray denotes assessment modules still requiring integration or validation. Tests have been run; that does not mean the indicators, transmission pathways or risk scores have passed validation.'},

{'title':'Data inputs and processing','paras':[
'We separate four types of input and preserve their actual frequencies. News describes what happened; markets describe changes in the external environment; business outcomes describe the response; risk buffers describe capacity before the shock. These layers cannot substitute for one another. [P1–P4]'],
'table':(['Layer','Inputs used or collected','Processed output'],[
['Public information','Federal Reserve, SEC, CFTC, ECB and BIS; DTCC notices; ESMA, FCA and Federal Register','Titles, summaries, sources and times; events and business tags awaiting review'],
['External markets','FRED funding rates, Treasury yields, VIX and credit spreads; industry and public technology-event inputs','Economically defined funding, rates, credit, equity and other channel features'],
['Business responses','PQD and financial disclosures, FICC daily/monthly activity, ECS/ITP monthly snapshots, underwriting and RDS reports','Outcome series separated by entity, service, period and unit'],
['Internal state','Already-public margin, payment obligations, liquidity resources and member concentration','Business-specific vulnerability candidates; unavailable fields remain missing']]),
'subsections':[
('Cleaning and storage rules',[
'Fetch each shared source once and link it to multiple businesses. Document deduplication and event consolidation are separate: one canonical URL usually identifies one document; different reports should share an event ID only after matching the entity, time and event facts, not merely keywords.',
'Keep publication, event, effective, observation, first-collection and revision times separate. A date-only source must not receive an invented UTC timestamp. Missing is not zero; quarterly values do not become daily business labels through forward filling.',
'Standardize monetary units and distinguish quarterly flows from cumulative financial totals. Align calendar quarters before calculating changes. Preserve raw values, definitions, cells/pages, URLs and hashes. Revisions create new versions rather than erase evidence.']),
('Information availability',[
'A daily feature can use only information already public at assessment time. A complete quarterly maximum is known only after quarter-end; it cannot be inserted into an event-day forecast within that quarter.'])]},

{'title':'Logic chains and transmission pathways','paras':[
'A logic chain explains why a relationship is plausible. A transmission pathway identifies the specific objects and operational steps through which a shock could change an outcome. Use: event → risk channel → affected member or asset → service process → observable outcome. Attach evidence and gaps to every arrow. Define this logic before feature selection and training; do not create a causal story after seeing a correlation.',
'For example, repo funding pressure may make financing harder for a relevant member, increase margin or settlement-payment pressure, and, if payment delay or default occurs, increase GSD contingency-liquidity needs. A market spread supports only the first step. Membership, payment capacity and actual resource demands require separate evidence. [S1, P1]'],
'table':(['Existing FICC chain','Business and intermediate route','Outcome to verify'],[
['1 Treasury volatility','GSD: repricing → positions and liquidation exposure → margin response','Margin, calls and stress exposure; not automatically a loss'],
['2 Repo funding pressure','GSD: member financing → margin and settlement payments','Payment obligations, funding sources and coverage'],
['3 Institution deterioration','GSD/MBSD: verify clearing relationship → ability to perform','Actual exposure, failed payments and default-management evidence'],
['4 Agency MBS changes','MBSD: prices, duration, convexity and prepayment → MBS exposure','MBS-specific signals and margin response'],
['5 Rule changes','GSD and others: scope/effective date → access and processing changes','Activity, implementation workload and readiness'],
['6 Activity/member growth','GSD/MBSD: scale and concentration → capacity/resource needs','Volumes, concentration, quality and resources'],
['7 Critical service disruption','GSD/MBSD: verify dependency → processing or settlement disruption','Availability, latency, backlog and recovery time'],
['8 MBS data/notice problems','MBSD: data or pool notices → matching and delivery','Corrections, unmatched items, timeliness and fails'],
['9 Clearing competition','GSD: customer adoption and alternatives → pricing/share/scale','Actual migration, market share and revenue evidence']]),
'note':'These are nine mechanism hypotheses, not nine successfully trained models. Growth, rule changes and competitor news are not inherently losses.'},

{'title':'How the historical models were trained','paras':[
'The first-stage models examine business-metric associations; they are not news-text classifiers. We trained separate Ridge regressions by entity and target. Ridge is a linear model with coefficient shrinkage, used to reduce instability from small samples and correlated features. It tests whether risk proxies add information, not whether a news item caused a loss. [P2, S3]',
'The baseline uses the previous quarter’s business change and quarter-of-year controls. The augmented model adds six risk proxies: volatility change, rate repricing, credit-condition change, funding spread, regulatory-announcement activity and monetary-policy-announcement activity. Counts measure communication activity rather than severity.',
'There are 13 entity–target series: revenue growth and margin changes for FICC, NSCC and DTC, plus clearing trade-side and notional growth for GSD and MBSD. NSCC and DTC are legal-entity measures; they must not be pooled into invented standalone ECS revenue.'],
'table':(['Step','Implementation','Purpose'],[
['Define targets','Observed quarterly growth or percentage-point changes; no fabricated missing targets','Ask a specific observable question'],
['Time split','Training ends 2025Q2; original holdout is 2025Q3–2026Q2','Preserve temporal order'],
['Tune parameters','Four ordered validation windows inside training; alpha candidates 1, 10, 100','Keep holdout errors out of tuning'],
['Fit preprocessing','Scaling and necessary lag-control imputation fitted within each training fold','Prevent future-information leakage'],
['Compare fairly','Augmented and baseline models use the same target and periods; evaluate MAE','Measure incremental information']]),
'paras_after':[
'Five of 13 targets had lower holdout mean absolute error (MAE), but each target had only 2–4 usable test quarters. Current-vintage histories and same-quarter risk features make this a retrospective conditional-association experiment, not a verified real-time forecasting backtest. Later periods already examined cannot become a new blind test set.',
'Event-level modeling would require reviewed event–business labels, exposure and vulnerability available at the time, defined outcome windows and more frequent business results. A validated news-impact classifier or loss predictor covering all ten businesses has not yet been trained.']},

{'title':'What the validation establishes','paras':[
'Event tests ask whether an indicator responds during known stress windows. Business-association tests ask whether it co-moves with the corresponding business outcome. A market alarm is not evidence of actual business damage. [P3–P5]'],
'table':(['Study','Verified result','Interpretation'],[
['12-family expansion','20 features; 482 same/next-quarter associations; none pass exploratory FDR 5%','Broader coverage, without stable established relationships'],
['Daily event screening','Four of seven candidates pass the original event gate','Detection in selected windows, not business-impact validation'],
['Original next-quarter PQD test','No GSD/MBSD candidate passes both gates; two NSCC funding candidates pass only initial screening','NSCC intervals cross zero and BH does not pass'],
['Supplemental response tests','882 records; 48 full-sample ordinary-BH passes, but zero in the earlier sample','Post-result extension with instability; ordinary p-values do not fully handle serial dependence'],
['Shock × vulnerability','NSCC adjusted-funding example: selection rho 0.430; later rho -0.143','The product has not shown a stable advantage']]),
'subsections':[
('Controls against misleading conclusions',[
'The original daily threshold is the 90th percentile of 252 preceding valid observations, with at least 126 values, excluding today. Quarterly stress uses the prespecified maximum with at least 45 valid days. Non-designated-event alarms are only a false-alarm proxy because event labels are incomplete.',
'Same-quarter and next-quarter relationships are separate. The former is closer to contemporaneous response; the latter examines persistence or lead relationships. Spearman ranks, BH adjustment, four-quarter block bootstrap, differences and sample splits assess robustness; none identifies causality.',
'Original windows and gates were fixed before this analysis, after the historical events were already public; they were not preregistered at event time. Supplemental tests were designed after reviewing earlier results and must not be described as an independent validation because they look better.'])]},

{'title':'Separate business response from vulnerability','paras':[
'A response is a change in demand, workload or service performance after a shock. Vulnerability describes buffers and capacity beforehand. Higher margin can reflect risk management, scale or model changes. It does not automatically mean worse performance or successful risk control. [P3, P5]'],
'table':(['Measure','Use','What it does not establish'],[
['6.1.1 quarter-end IM and its change','Margin demand and scale response','Not an event-day loss; activity/rules can change it'],
['6.6.1 average VM; 6.7.1 peak daily VM','Quarterly payment flow and peak burden; inspect peak/average too','Not DTCC revenue, realized loss or service failure'],
['6.8.1 peak daily IM call','Largest aggregate deficit over deposited collateral and actual calls, including intraday','Not the largest increase in total margin required'],
['4.4.3 / 6.1.1','Stress loss beyond IM relative to quarter-end IM; a vulnerability candidate','Not total gross stress loss; T12m/quarter-end timing can differ'],
['Stress payments / quantified resources','Liquidity-vulnerability candidate; retain cash/commitment subset','Resources are not all cash; a cross-date ratio above one is not an actual shortfall'],
['18.2.2 top-five open-position share','Member-concentration candidate','Not market share or observed member default']]),
'paras_after':[
'Use the latest disclosure already public at assessment time, not automatically quarter t−1. For example, the 2026Q1 PQD listing date is May 28, 2026, so its availability cannot be assumed at the start of Q2. Listing dates remain proxies for first availability; original historical vintages are not fully verified.',
'ITP, RDS, Asset Services, DAS, DDA, Data Services and Consulting require measures such as delays, errors, capacity, data quality, provider dependence or customer concentration. CCP margin ratios cannot substitute for their missing vulnerabilities.']},

{'title':'Assess one event differently by business','paras':[
'First represent the event as a vector of channel shocks S rather than a universal severity number. A banking event can affect rates, credit and funding differently; each channel requires evidence. Exposure E determines whether the channel connects to the business. Vulnerability V describes capacity to absorb the shock, conditional on exposure.',
'Where scope, evidence and common scales are sufficient, a candidate channel-level priority is P(e,b,c)=100×S(e,c)×E(e,b,c)×V(b,c; a). Here e is the event, b the business, c the channel and a the latest state public by assessment time. This is a framework to test, not a fitted probability model. S×E can represent the business-specific external shock, preserving the original shock×vulnerability framework. Do not multiply by E again if exposure is already embedded in the shock.'],
'table':(['Component','Question','Current rule'],[
['Relevance and exposure gate','Does the event involve the business’s assets, members, geography, customers, systems or providers?','Separate verified, plausibly relevant, insufficient evidence and not applicable; unknown is not zero'],
['External shock S','How unusual, directional and persistent is the channel movement?','Use prespecified measures and past-only scales; article counts are not severity'],
['Vulnerability V','What known pre-event buffer or operational weakness matters?','Use business-specific, already-available fields; no score if a required input is missing'],
['Outcome vector','Financial burden, margin/liquidity, service quality or strategic opportunity?','Report directions, magnitudes, horizons and units separately'],
['Evidence quality','What supports each arrow and the actual outcome?','Report evidence status, coverage and uncertainty separately from pressure']]),
'paras_after':[
'A 0–100 range does not make scores comparable. Within-business percentiles describe relative unusualness, not equal economic losses. Cross-business ranking requires calibrated exposure definitions, vulnerability scales and outcome anchors. For now, report business-specific measures, directions and evidence rather than force a ranking of all ten.',
'Consolidate multiple reports into an event and check overlapping pathways before aggregation. Do not assign channel weights directly from correlations or repeatedly select the highest full-sample association.']},

{'title':'Business specific pathways and measures Part one','paras':['These are mechanism and data-requirement comparisons, not established event impacts. Official business scope supports interpretation; event relevance and consequences need separate evidence. [P1, P4, S1, S4, S5]'],
'table':(['Business and scope','Typical pathway','Outcomes and vulnerabilities'],[
['FICC fixed income\nGSD/MBSD separate','Treasury/repo or agency MBS shock → positions, financing and payments → clearing resources','Outcomes: margin, calls, payment burden, fails and volume. Vulnerability: resources and concentration; MBSD also needs MBS exposure.'],
['ECS equity clearing/settlement\nNSCC/DTC separate','Equity/ETF activity, volatility or settlement-rule change → payments and securities delivery','NSCC margin/activity; DTC fails/delays. Define clearing and settlement vulnerability separately; entity financials are not pure ECS results.'],
['RDS repository and derivatives','Rule/field change or trading activity → reporting, validation and lifecycle processing','Rejections, corrections, timeliness and uptime. Vulnerability: data quality and customer/jurisdiction/system concentration; public aggregates are activity proxies.'],
['WIS wealth and investment','Fund flows, insurance/private-market change → subscription/redemption and settlement processing','Volumes, rejects, cash/instruction backlog and product revenue. Vulnerability: channel/customer concentration and capacity; industry assets are not WIS volume.'],
['ITP institutional processing','T+1, a trading surge or SSI errors → allocation, matching, affirmation and deadlines','Match/affirmation rates, exceptions, latency and backlog. Vulnerability: manual processes, SSI quality and connectivity; CCP margin is inapplicable.']]),
'note':'Revenue or volume growth can create commercial opportunity and operational workload at the same time. Record these directions separately.'},

{'title':'Business specific pathways and measures Part two','table':(['Business and scope','Typical pathway','Outcomes and vulnerabilities'],[
['Asset Services','Issuance, corporate actions, tax or custody change → eligibility, records, payments and notices','Processing volume, deadline compliance, payment/tax errors and reconciliation. Vulnerability: issuer/agent concentration and backlog; underwriting value is not revenue.'],
['DAS DTC digital asset solutions','Tokenized-securities rules/network change → conversion and connection to traditional settlement','Tokenized securities volume, conversion/redemption fails, reconciliation and uptime. Vulnerability: chain/custody/interfaces; BTC/ETH do not measure these securities’ exposure.'],
['DDA digital asset technology','Vulnerability, interoperability or provider issue → platform/API and smart-contract workflow','Errors, latency, interruption and retention. Vulnerability: component, chain and provider concentration; a public CVE does not prove exposure.'],
['Data Services','Upstream source or data-rule change → product processing, APIs and delivery','Completeness, errors/revisions, delay, uptime and retention. Vulnerability: upstream dependence and validation capacity; market volume is not data sales.'],
['Consulting','Regulatory deadlines, T+1 or digital adoption → client readiness and advisory demand','Orders, backlog, delivery time, utilization and profit. Vulnerability: client concentration/staff capacity; regulatory news may be opportunity rather than loss.']]),
'paras_after':[
'Public information does not supply equally strong supervised-learning labels for all ten businesses. Historical FICC, NSCC and DTC financials and selected operations are available, but most other lines lack continuous independent revenue, quality, capacity, dependency and exposure measures. The table identifies requested fields, not internal data already obtained.',
'Prioritize approved aggregate business outcomes and exposure, then test alignment with event time. Where actual labels are unavailable, retain mechanisms and evidence cards; do not substitute another entity’s measures.']},

{'title':'One historical event with different business implications','paras':[
'Consider SVB-related banking stress in March 2023. Our fixed research window is March 8–17, not the only defensible window. These are observed market summaries from the frozen inputs, not DTCC business losses. [P3]'],
'table':(['Candidate channel','Observed window peak','Original historical threshold'],[
['Absolute daily 10-year yield change','23 bp','Alarm on 50% of eight valid days'],
['20-day Baa spread widening','41 bp','Alarm on 50% of eight valid days'],
['Raw SOFR−EFFR spread','0 bp','Can alarm against its own negative historical baseline; not evidence of severe repo funding scarcity'],
['VIX','26.52','Does not cross the original rolling 90th-percentile threshold in this window; not proof of no equity risk']]),
'paras_after':['One event can register strongly in rates and credit changes without equivalent intensity in the raw funding spread or selected VIX threshold. A bank failure does not establish the same funding crisis for every business.'],
'table2':(['Business','Route to investigate','Current evidence boundary'],[
['GSD','Treasury repricing → margin and member payments; examine funding separately','Relevant channel; event-day positions/calls are missing, so no attributed loss'],
['MBSD','Rates → MBS duration/convexity and prices → margin','Plausible mechanism; MBS-specific signals/exposure are missing; no identical GSD weight'],
['ECS','Equity activity and payments → NSCC clearing/DTC settlement','Need equity and business outcomes; Treasury indicators do not establish ECS harm'],
['ITP and RDS','Volatility/trade adjustments → processing or reporting workload','Need exceptions, backlog or reporting-quality evidence; volume alone is not failure'],
['Other six lines','Check their own assets, processes, customers or platform dependencies','Retain unresolved relevance where event-level results are absent; no automatic zero or high score']]),
'note':'Quarterly peaks and T12m PQD measures cannot isolate the SVB event day. Same-quarter changes can include other events, scale and model adjustments.'},

{'title':'Report comparable outcomes and evidence','paras':[
'Each event–business record should retain the event ID, business/entity, channel, evidence for every step, actual exposure, vulnerability available at assessment time, outcome dimension, direction, units, horizon, baseline, data vintage and open questions. Distinguish observed fact, mechanism inference, model estimate and not yet observed; do not invent confidence probabilities.',
'Start with changes relative to that business’s baseline: margin growth, percentage-point changes in failure rates, latency, or peak calls divided by a known scale. If a reliable conditional model exists, also report observed minus baseline-estimated change. That residual is not a causal event effect. Incompatible units cannot be added.'],
'subsections':[('Illustrative arithmetic only',[
'Assume a common rate-channel shock S=0.80 and hypothetical E/V values defined on a common scale. These are invented teaching inputs, not actual DTCC observations or fitted parameters. They only show why one event can produce different candidate priorities.'])],
'table':(['Hypothetical business','S','E','V','100×S×E×V'],[
['GSD','0.80','0.90','0.60','43.2'],['MBSD','0.80','0.70','0.80','44.8'],['ECS NSCC','0.80','0.40','0.50','16.0']]),
'paras_after':[
'Under these assumptions, MBSD’s lower exposure is outweighed by higher vulnerability. This is framework arithmetic only: it does not establish that actual MBSD risk exceeds GSD risk, and 44.8 is not a 44.8% loss probability. Missing real E or V should produce “not scored.”',
'A practical card should say, for example, “margin demand may increase; event-day business evidence is insufficient; member exposure needs verification,” rather than show only a total score. Financial burden, operational pressure, service quality and commercial opportunity belong in separate fields.']},

{'title':'Implementation sequence and evidence index','subsections':[
('Next implementation steps',[
'First maintain the database/daily collection and add event IDs and reviewed business relevance. Next obtain approved aggregate exposure, service-quality and business-outcome histories for each line, preserving versions actually available at the time.',
'Then freeze outcomes, windows and gates. Use genuinely new periods for chronological comparisons of baseline, external-only, vulnerability-only, additive and interaction models. Establish stable incremental value before choosing weights or a common cross-business scale. Quantify only supported pathways; retain qualitative evidence and gaps for the rest.',
'Daily refresh and research training are different jobs. GitHub updates the data and republishes the complete package; it does not automatically retrain models or turn new headlines into confirmed impacts.']),
('Local evidence files',[
'[P1] reports/FICC_九条逻辑链_中英对照.docx; data_refresh_2026_10_14/business_requirements.json.',
'[P2] risk_business_ml/models/model_manifest.json; results/model_comparison.csv; Analysis_Results_and_Usage_Guide_EN.md.',
'[P3] risk_business_ml/event_vulnerability_tests_2026_10_06/analysis_plan.json; results/event_detail.csv, event_screen.csv, pqd_lagged_spearman.csv and interaction_vs_persistence_baseline.csv.',
'[P4] risk_business_ml/risk_category_expansion/results/expanded_analysis_summary.json; data/risk_taxonomy.csv.',
'[P5] risk_business_ml/feedback_revision_report_2026_10_06/results/analysis_summary.json; report_content.json; data/response_cell_evidence.csv.',
'[P6] capstone_database/schema.sql, update.py and sources.json; repository .github/workflows/daily-data.yml. Relative paths use Capstone_Project as root.'])],
'sources':True,'note':'Figures above were checked against existing artifacts. Preparing this report did not retrain models or reselect results.'}
]

SOURCES=[
 ('S1','DTCC Clearing and Settlement Services','https://www.dtcc.com/products-and-services/clearing-settlement-services'),
 ('S2','CPMI IOSCO Public Quantitative Disclosure Standards','https://www.bis.org/publications/public-quantitative-disclosure-standards-central-counterparties'),
 ('S3','scikit learn Ridge documentation','https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html'),
 ('S4','DTCC Trade Processing Solutions','https://www.dtcc.com/products-and-services/trade-processing-solutions'),
 ('S5','DTCC Repository and Derivatives Services','https://www.dtcc.com/products-and-services/repository-derivatives-services'),
 ('S6','DTCC Asset Services','https://www.dtcc.com/products-and-services/asset-services'),
]

GLOSSARY=[
['DTCC','Depository Trust and Clearing Corporation','存托与清算机构集团'],
['FICC','Fixed Income Clearing Corporation','固定收益清算公司'],
['GSD','Government Securities Division','政府证券清算部门'],
['MBSD','Mortgage Backed Securities Division','抵押贷款支持证券清算部门'],
['ECS','Equity Clearing and Settlement','股票清算与结算业务口径'],
['NSCC','National Securities Clearing Corporation','全国证券清算公司'],
['DTC','Depository Trust Company','存托信托公司'],
['RDS','Repository and Derivatives Services','交易报告与衍生品服务'],
['WIS','Wealth and Investment Solutions','财富与投资服务'],
['ITP','Institutional Trade Processing','机构交易处理'],
['DAS','DTC Digital Asset Solutions','DTC 数字资产服务'],
['DDA','DTCC Digital Assets','数字资产技术平台业务'],
['FRED','Federal Reserve Economic Data','美联储经济数据平台'],
['PQD','Public Quantitative Disclosures','公开量化披露'],
['CCP','Central Counterparty','中央对手方'],
['IM / VM','Initial Margin / Variation Margin','初始保证金与变动保证金'],
['SOFR','Secured Overnight Financing Rate','有担保隔夜融资利率'],
['EFFR','Effective Federal Funds Rate','有效联邦基金利率'],
['VIX','Cboe Volatility Index','股票期权隐含波动率指数'],
['MBS / SSI','Mortgage Backed Securities / Standing Settlement Instructions','抵押贷款支持证券与常设结算指令'],
['MAE / BH','Mean Absolute Error / Benjamini Hochberg','平均绝对误差与多重检验校正方法'],
]
CN.append({'title':'缩写与术语','table':(['缩写','英文全称','本报告中的含义'],GLOSSARY),
           'note':'十条业务线、十二类风险候选、九条 FICC 逻辑链和七个市场指标是不同层级的分类，不能混为一个数量。'})
EN.append({'title':'Abbreviations and terminology','table':(['Term','Full name','Meaning in this report'],[
 [r[0],r[1],{'DTCC':'Group','FICC':'Fixed-income CCP','GSD':'Government securities clearing','MBSD':'Agency MBS clearing','ECS':'Business-line scope','NSCC':'Equity clearing entity','DTC':'Settlement/custody entity','RDS':'Repository/derivatives business','WIS':'Wealth/fund services','ITP':'Trade-processing business','DAS':'DTC digital-securities service','DDA':'Digital-asset technology business','FRED':'Market data platform','PQD':'Quantitative disclosure','CCP':'Central counterparty','IM / VM':'Margin/payment measures','SOFR':'Secured overnight benchmark','EFFR':'Federal funds benchmark','VIX':'Equity implied volatility','MBS / SSI':'Asset / settlement instructions','MAE / BH':'Prediction error / test adjustment'}[r[0]]] for r in GLOSSARY]),
           'note':'Ten businesses, twelve risk families, nine FICC logic chains and seven market indicators describe different classification levels.'})
