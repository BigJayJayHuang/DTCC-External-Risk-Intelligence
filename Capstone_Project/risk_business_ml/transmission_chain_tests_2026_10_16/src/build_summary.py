from pathlib import Path
import pandas as pd,json
R=Path(__file__).resolve().parents[1];q=pd.read_csv(R/'results/quarterly_test_results.csv');primary=q[q.label=='primary'].set_index('chain_id');ev=pd.read_csv(R/'results/event_test_summary.csv').set_index('test_key');ofr=json.loads((R/'results/ofr_funding_hac.json').read_text());ftd=json.loads((R/'results/equity_volume_ftd_hac.json').read_text());spon=pd.read_csv(R/'results/sponsored_node_descriptives.csv')
def e(key):
 r=ev.loc[key];return f"{'通过' if r.status=='PASS' else '未通过'}；命中{int(r.events_hit)}/{int(r.events_available)}，非事件报警{r.non_event_alarm_proxy:.1%}"
def qr(cid):
 r=primary.loc[cid];return f"{'达标' if r.pass_card else '未达标'}；ρ={r.rho:.3f}，95%区间[{r.ci_low:.3f}, {r.ci_high:.3f}]，n={int(r.n)}"
rows=[]
def add(cid,name,scope,t1,t2,conf,note,gap='',role=''):
 rows.append({'编号':cid,'名称':name,'执行范围':scope,'检验一':t1,'检验二':t2,'卡片置信度':conf,'版本':'v1执行版2026-10-16','备注':note,'仍需补充':gap,'角色':role})
add('FICC-GSD-01','国债市场波动','两项统计已跑',e('FICC-GSD-01'),qr('FICC-GSD-01'),'证据不足','方向正，但区间跨零；变化量ρ=0.186，不能宣称链已验证。')
add('FICC-GSD-02','回购资金压力','两项统计已跑',e('FICC-GSD-02'),f"未达标；GCF−DVP冲击日系数{ofr['coefficient_bp']:.3f}bp，HAC p={ofr['hac_p']:.3f}，n={ofr['n']}",'证据不足','OFR没有所需DVP百分位序列，按卡片备选选同期限隔夜GCF−DVP；选择记录早于结果。GCF有效值稀疏，且利差并非FICC实际流动性需要。','更多可比清算回购利率或GSD支付反应证据')
add('FICC-GSD-03','国债清算强制令','事件与描述核对','SEC规则及延期节点已核实',f"Sponsored节点前后各20个观测均值变化：2023年+{spon.iloc[0].change_pct:.1f}%，2025年+{spon.iloc[1].change_pct:.1f}%；描述支持",'Medium 机制及描述','已有Sponsored业务量，不需要重抓。公告后变化不等于公告造成；调查的预计量不是已实现量。','真实接入与未来合规节点结果；V的19.1.3仅近5季度有数值')
add('FICC-GSD-04','会员信用恶化','信号与历史案例核对',e('FICC-GSD-04'),'2008雷曼FICC处置案例支持；不是当前季度回归','Medium 案例','支持违约处置路径；不证明Baa能识别具体会员，也不意味着共同基金发生损失。','更近的会员事件与业务直接证据')
add('FICC-MBSD-01','MBS利差冲击','两项统计已跑',e('FICC-MBSD-01'),qr('FICC-MBSD-01'),'证据不足','已从Freddie Mac原始PMMS补取房贷利率；房贷利差不是MBS OAS。2022窗口预先按下半年处理，且11月存在PMMS方法变更。')
add('FICC-GSD-05','竞争对手进入','事件核对完成 结果待补','CME批准与ICE服务材料已核实','未完成；未核实客户迁移或可比份额','Low','批准或上线消息本身不能证明FICC丢失业务。','客户迁移、同口径份额；脆弱度定义')
add('FICC-GSD-06','运营或网络事件','案例与PQD字段部分完成','ICBC网络事件有官方来源','未完整通过；有国债市场及BNY影响，缺GSD直接结果','Low 直接证据不足','17.2/17.3已补提取；共享系统口径不能当成各业务独立故障序列。','GSD直接服务影响、会员依赖和可比运营口径')
add('FICC-MBSD-02','GSE改革','来源核对 结果未跑','找到历史UMBS节点，不能替代退出托管/私有化事件','未完成；FINRA接口401，且v1节点未冻结','Low','UMBS历史材料仅支持相邻机制，不冒充当前假设已通过。','明确改革节点、FINRA授权或官方导出、MBSD反应')
add('ECS-NSCC-01A','股市波动到保证金追缴','两项统计已跑',e('ECS-R1'),qr('ECS-NSCC-01A'),'证据不足','按卡片用上季保证金分母；不是旧试跑中的当季分母。',role='R1主链')
add('ECS-NSCC-01B','股市波动到变动保证金现金波动','两项统计已跑',e('ECS-R1'),qr('ECS-NSCC-01B'),'证据不足','主检验保留VIX水平及同季度；不拿改信号后的较好结果替换。',role='R1次链')
add('ECS-NSCC-01C','股市波动到保证金回测突破','两项统计已跑',e('ECS-R1'),qr('ECS-NSCC-01C'),'证据不足','变化量ρ=0.095；该结果变量为过去12个月累计，季度重叠。',role='R1次链')
add('ECS-NSCC-02A','成交量激增到交割失败余额','两项统计已跑',e('ECS-R2'),f"达标；高量周多{ftd['coefficient_million_outstanding_shares']:.1f}百万股未交割余额，HAC p={ftd['hac_p']:.2g}，n={ftd['n_weeks']}周",'High 按卡片门槛','只是市场量与CNS未交割余额关联；不是新增失败流量、失败率、系统故障或DTCC损失。月季末控制不能排除所有混杂。','容量脆弱度与共同趋势/其他混杂控制',role='R2主链')
add('ECS-NSCC-02B','成交量激增到系统压力','检验一已跑 检验二未跑',e('ECS-R2'),'未跑；没有连续可比NSCC独立17.3序列','Medium 仅信号','成交量数据复用02A；共享核心系统及T12m口径不能直接当作NSCC季度故障次数。','NSCC独立故障及容量指标',role='R2次链')
add('ECS-NSCC-03A','券商信用恶化到违约处置','信号与历史案例核对',e('ECS-NSCC-03A'),'雷曼NSCC处置案例支持；不把2021价格驱动追缴当成违约','Medium 案例','宏观信用代理不等于具体会员信用恶化；个案不构成量化因果验证。',role='R3信用通道')
add('ECS-NSCC-03B','资金紧张到NSCC支付与追缴','两项统计已跑',e('ECS-NSCC-03B'),qr('ECS-NSCC-03B'),'High 按卡片门槛','变化量ρ=0.154，2025Q1后ρ=0.086；六项季度主检验BH q=0.119。暂不称稳健或可靠风险评分。',role='R3流动性通道')
add('ECS-NSCC-04','T加1等制度变更到NSCC失败率','事件及即时证据核对','2024-05-28 T+1实施已核实','未跑指定前后3个月；即时官方数据不支持必然上升','Low 至 Medium','首日CNS为1.90%，对应5月T+2平均2.01%；不是连续三个月事件研究。','连续NSCC月度失败率、V与其他制度节点')
add('ECS-NSCC-05','已知高峰日期到处理负荷','数据补齐 检验未跑','未跑；事件日历与通过规则未冻结','未跑；SEC FTD现已备好','待定','Triple witching、Russell和S&P事件需分别固定日期与比较窗口，不能事后挑日期。','权威事件日历、成功标准及V')
add('ECS-DTC-01','T加1等制度变更到DTC失败率','事件及即时证据核对','与NSCC-04复用同一事件','未跑指定前后3个月；有首日非CNS观察','Low 至 Medium','首日DTC非CNS为2.92%，对应5月T+2平均3.24%；SEC CNS FTD不能代替DTC非CNS失败率。','连续DTC非CNS月度失败率与V')
add('ECS-DTC-02A','新增已利用漏洞到DTC中断','数据与案例核对 未完整跑','未完整跑；KEV入库日期不是攻击发生日期','未跑；未核实DTC直接服务影响','Low','仓库有KEV数据，但不是DTC暴露清单。ICBC国债事件不能直接证明DTC系统受损。','适用事件窗口、软件依赖、DTC服务证据与V',role='R6主链')
add('ECS-DTC-02B','云或供应商故障到DTC中断','数据与案例核对 未完整跑','未完整跑；历史和持续时长不足','未跑；缺DTC依赖与直接服务证据','Low','仓库只有Google相关部分事件，不能说已覆盖主要云厂商完整历史。','完整供应商故障历史、DTC依赖/服务证据与V',role='R6次链')
add('ECS-DTC-03','发行激增到新券处理','输入核对 检验未跑','未跑；未采集市场范围424B计数','未跑；DTC月度发行数量已具备','待定','2011年起DTC发行数据已有；仍需定义424B子类型、重复修订与日期口径。业务归属暂沿用ECS。','市场范围424B历史、事件窗口与V')
add('ECS-DTC-04','融资压力到DTC日终资金结算','检验一已跑 案例待补',e('ECS-DTC-04'),'未完成；未核实DTC直接资金结算案例','修改候选','已从美联储原始XML补取与DCPF3M/DTB3对应的日度利率；未拿DGS3MO冒充DTB3。','直接结算案例；Participants Fund的缓冲定义')
f=pd.DataFrame(rows);assert len(f)==22 and f['编号'].is_unique
f.to_csv(R/'results/chain_status_CN.csv',index=False,encoding='utf-8-sig')
for name,prefix in [('FICC','FICC-'),('ECS','ECS-')]:
 a=f[f['编号'].str.startswith(prefix)][['编号','检验一','检验二','卡片置信度','版本','备注','仍需补充']].rename(columns={'卡片置信度':'置信度'})
 a.to_csv(R/'results'/f'{name}_检验结果汇总.csv',index=False,encoding='utf-8-sig')
lines=['# FICC 与 ECS 候选传导链检验汇总','', '执行日期：2026年10月16日。范围：你提供的两份v1文件，共22条链。','', '**结果：8条完成两项统计检验，其中2条达到卡片门槛；其他链分别完成了信号筛选、字段提取、事件或案例核对，尚未全部完成检验。** 通过门槛不等于已证明因果、已校准风险分数或已证明发生业务损失。','', '本轮框架按你的意见改为 **风险优先级＝外部冲击S × 内部脆弱度V**。新闻先匹配适用的传导链并核对业务关联，不再乘E。V衡量缓冲与弱点；缺少V时不能把它填成零。本轮未生成最终风险分数，也未重训原有Ridge模型。','', '## FICC 八条链','', '| 编号与名称 | 执行范围 | 检验一 | 检验二 | 仍需处理 |','|---|---|---|---|---|']
for a in rows[:8]:lines.append('| '+' | '.join([a['编号']+' '+a['名称'],a['执行范围'],a['检验一'],a['检验二'],a['仍需补充'] or a['备注']])+' |')
lines+=['','## ECS 十四条链','','| 编号与名称 | 执行范围 | 检验一 | 检验二 | 仍需处理 |','|---|---|---|---|---|']
for a in rows[8:]:lines.append('| '+' | '.join([a['编号']+' '+a['名称'],a['执行范围'],a['检验一'],a['检验二'],a['仍需补充'] or a['备注']])+' |')
lines+=['','## 最值得你调整的地方','', '1. **NSCC-02A有新增数据支持。** Cboe成交量与SEC CNS未交割余额已对齐。高量周与更高的存量未交割余额相关，但这不是交割失败率或系统容量不足的直接证明。SEC明确该字段是未交割余额，不能跨日相加当成新失败。','2. **NSCC-03B仅按卡片暂时达标。** 同季度ρ=0.454，区间为正；差分后关联和后期样本均弱，季度主检验BH未过5%。原文件建议改成VM比例后，下一季度ρ约0.711；这已改变结果变量和时滞，保留为次要探索，不能替换v1主检验。','3. **GSD-01与MBSD-01先保留研究候选。** 前者ρ=0.408但区间跨零；后者房贷利差代理与MBSD最大VM环比ρ=0.150，未达门槛。不能把未通过解释成没有风险传导。','4. **ECS文本须统一定义。** 本轮按卡片同季度为主；01A用上季IM分母。末尾旧试跑的下一季度与当季IM分母单独列为对照。R1新事件集下VIX命中3/4并通过；这不推翻旧事件集的失败，也不应比较为模型改善。','5. **无市场指标的链继续用证据卡。** 强制令、竞争、网络事件与GSE改革的打分规则尚待团队设计。T+1还缺连续月度历史；官方首日资料提示失败率未必上升。不要强行补出统一量化评分。','', '## 这次补到了什么','', '- Cboe美国股票市场2018年至2026年的成交量原始文件，一次采集，供NSCC-02A/02B复用。','- SEC FTD共210个半月压缩文件，保留原始证据，清洗后覆盖2018年1月至2026年9月；进入主回归的完整周为413个。','- OFR隔夜GCF与DVP终值利率；公开目录不含所需DVP P99/P1，所以在看结果前登记改用卡片允许的GCF−DVP。GCF有效值稀疏，配对回归仅246日，HAC以有效观测序列为序，不能把结果当连续完整日度证据。','- Freddie Mac原始PMMS房贷利率；美联储CP及H.15原始XML中的DCPF3M和DTB3对应序列。FRED接口失败时没有伪称下载成功。PMMS在2022年11月有方法变更，房贷报价差不是MBS OAS。','- 22份可读PQD表格的17.2、17.3和19.1.3字段及单元格证据；2024Q4的PDF保留了第19/22页文本。17.3大多是共享系统及过去12个月口径；GSD 19.1.3仅2025Q2起5个季度有数值，最新平均约69.82%、峰值约75.72%。','', '## 检验口径与可追溯性','', '统计主检验固定一个信号、一个结果、同季度；Spearman门槛ρ≥0.3且四季度区块bootstrap的95%区间下限>0。回购与FTD使用卡片规定的正向HAC回归门槛。周度信号只与此前52周阈值比较；事件窗口边界不使用窗口之后的观测。ECS R1/R2沿用其标准段落的日度252日阈值。所有阈值都是项目研究规则，并非DTCC或监管标准。','', '历史结果已被看过；这是一轮探索性执行，不是新盲测。完整期间与次要时滞、信号替换分别保存在结果表，不用事后最优结果替代主卡片。后期检验仅6季度，不能凭一个新增季度就确认相关性。PQD4.4.3是超出初始保证金后的压力损失，不是总损失或已实现损失。','', 'CSV中的High只表示按卡片的两道门槛达标，不是概率，也不是稳健因果证据；稳健性限制见备注。本轮未给任意相关系数赋予业务评分权重。','', '可复跑入口：[Transmission_Chain_Validation.ipynb](Transmission_Chain_Validation.ipynb)。逐链表：[chain_status_CN.csv](results/chain_status_CN.csv)。逐项数值：[quarterly_test_results.csv](results/quarterly_test_results.csv)、[event_test_summary.csv](results/event_test_summary.csv)、[OFR回归](results/ofr_funding_hac.json)、[FTD回归](results/equity_volume_ftd_hac.json)。','', '## 关键公开依据','', '- [SEC FTD定义与下载](https://www.sec.gov/data/foiadocsfailsdatahtm)：CNS未交割余额的范围与含义。','- [Cboe历史成交量](https://www.cboe.com/markets/us/equities/market-statistics/historical-market-volume)：各市场中心日度股数汇总来源。','- [OFR接口及元数据](https://www.financialresearch.gov/short-term-funding-monitor/api/)：清算回购利率、缺失值与期限定义。','- [DTCC T加1进展2024年5月30日](https://www.dtcc.com/press-releases/2024/dtcc-comments-on-industrys-t1-progress)：首个T+1结算日的CNS/非CNS观察。','- [DTCC2008年报](https://www.dtcc.com/-/media/Files/Downloads/About/Annual-Reports/2008_report.pdf)：雷曼处置路径，官方网页索引文摘已核对，旧PDF直链返回404；未声称完整PDF已下载。','- [美国财政部ICBC事件说明](https://home.treasury.gov/news/press-releases/jy2114)和[OFR2024年报](https://www.financialresearch.gov/annual-reports/files/OFR-AR-2024_web.pdf)：国债市场及BNY影响；不足以直接认定DTC中断。','', '其他案例与未完成项见[case_evidence.json](results/case_evidence.json)和[remaining_data_gaps.csv](data/remaining_data_gaps.csv)。方法纪律参考Quant_tech的Statistical Inference与Machine Learning3笔记；具体检验按你提供的候选卡片执行。']
(R/'精简检验汇总_CN.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
sumry={'date':'2026-10-16','candidate_chains':22,'ficc':8,'ecs':14,'complete_two_numeric_tests':int((f['执行范围']=='两项统计已跑').sum()),'pass_both_numeric_card_gates':['ECS-NSCC-02A','ECS-NSCC-03B'],'not_a_validated_risk_score':True,'framework':'S*V; chain relevance gate, no E multiplier','full_rows':rows}
assert sumry['complete_two_numeric_tests']==8
(R/'results/execution_summary.json').write_text(json.dumps(sumry,ensure_ascii=False,indent=2)+'\n')
print('22-chain summary generated;8two-test numerical executions;2card-gate passes')
