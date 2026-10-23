import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { Workbook } from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = path.join(root, 'results/chain_status_CN.csv');
const target = path.join(root, 'results/chain_status_EN.csv');
const originalBytes = await fs.readFile(source);
const originalHash = crypto.createHash('sha256').update(originalBytes).digest('hex');
const wb = await Workbook.fromCSV(originalBytes.toString('utf8').replace(/^\uFEFF/, ''), { sheetName: 'Chain status' });
const sheet = wb.worksheets.getItemAt(0);
const original = sheet.getRange('A1:J23').values;

// Translations follow the original row and column order. Numerical results are not recalculated.
const scopes = {
  '两项统计已跑': 'Both statistical tests executed',
  '事件与描述核对': 'Event and descriptive review',
  '信号与历史案例核对': 'Signal screening and historical case review',
  '事件核对完成 结果待补': 'Event confirmed; outcome evidence missing',
  '案例与PQD字段部分完成': 'Partial case review and PQD extraction',
  '来源核对 结果未跑': 'Source checks completed; outcome test not run',
  '检验一已跑 检验二未跑': 'Test 1 executed; Test 2 not run',
  '事件及即时证据核对': 'Event and immediate-outcome evidence reviewed',
  '数据补齐 检验未跑': 'Data obtained; tests not run',
  '数据与案例核对 未完整跑': 'Data and case checks; testing incomplete',
  '输入核对 检验未跑': 'Inputs reviewed; tests not run',
  '检验一已跑 案例待补': 'Test 1 executed; case evidence missing',
};
const confidence = {
  '证据不足': 'Insufficient evidence',
  'Medium 机制及描述': 'Medium: mechanism and descriptive evidence',
  'Medium 案例': 'Medium: case evidence',
  'Low': 'Low',
  'Low 直接证据不足': 'Low: insufficient direct evidence',
  'High 按卡片门槛': 'High: card thresholds met',
  'Medium 仅信号': 'Medium: signal only',
  'Low 至 Medium': 'Low to Medium',
  '待定': 'Pending',
  '修改候选': 'Candidate for revision',
};
const roles = {
  '': '', 'R1主链': 'R1 primary chain', 'R1次链': 'R1 secondary chain',
  'R2主链': 'R2 primary chain', 'R2次链': 'R2 secondary chain',
  'R3信用通道': 'R3 credit channel', 'R3流动性通道': 'R3 liquidity channel',
  'R6主链': 'R6 primary chain', 'R6次链': 'R6 secondary chain',
};
// Each entry contains: name, Test 1, Test 2, notes, remaining requirements.
const translations = {
  'FICC-GSD-01': [
    'Treasury market volatility',
    'Passed; 3/3 events detected; non-event alert rate 12.2%',
    'Did not meet threshold; ρ=0.408, 95% interval [-0.014, 0.764], n=22',
    'The direction is positive, but the interval crosses zero. Correlation in changes: ρ=0.186. The chain cannot be described as validated.',
    '',
  ],
  'FICC-GSD-02': [
    'Repo funding stress',
    'Passed; 3/3 events detected; non-event alert rate 12.4%',
    'Did not meet threshold; GCF−DVP shock-day coefficient 0.021 bp, HAC p=0.976, n=246',
    'OFR lacks the required DVP percentile series. The same-tenor overnight GCF−DVP alternative permitted by the card was selected and recorded before results were inspected. Valid GCF observations are sparse, and the spread does not measure actual FICC liquidity needs.',
    'More comparable cleared-repo rates or evidence of GSD payment responses',
  ],
  'FICC-GSD-03': [
    'Treasury central clearing mandate',
    'SEC rule and extension dates verified',
    'Change in mean Sponsored activity over 20 observations before and after each milestone: +17.5% in 2023 and +4.9% in 2025; descriptive support',
    'Sponsored volume data already exist and do not need to be collected again. A post-announcement change does not establish that the announcement caused it. Survey forecasts are not realized volumes.',
    'Actual onboarding and outcomes around future compliance milestones; only the latest 5 quarters contain numeric values for vulnerability field 19.1.3',
  ],
  'FICC-GSD-04': [
    'Member credit deterioration',
    'Passed; 2/2 events detected; non-event alert rate 11.1%',
    'Supported by the 2008 Lehman FICC default-management case; not a regression on current quarterly data',
    'Supports the default-management pathway. It does not show that Baa identifies individual members or imply losses to the mutualized clearing fund.',
    'More recent member events and direct business evidence',
  ],
  'FICC-MBSD-01': [
    'MBS spread shock',
    'Passed; 2/3 events detected; non-event alert rate 11.5%',
    'Did not meet threshold; ρ=0.150, 95% interval [-0.157, 0.594], n=22',
    "Mortgage rates were added from Freddie Mac's original PMMS data. The mortgage-rate spread is not MBS OAS. The 2022 window was fixed in advance as the second half of the year; PMMS methodology changed in November.",
    '',
  ],
  'FICC-GSD-05': [
    'Competitor entry',
    'CME approval and ICE service materials verified',
    'Incomplete; customer migration or comparable market shares have not been verified',
    'An approval or launch announcement alone does not establish that FICC lost business.',
    'Customer migration, consistently defined market shares, and a vulnerability definition',
  ],
  'FICC-GSD-06': [
    'Operational or cyber event',
    'Official sources document the ICBC cyber event',
    'Not fully established; Treasury market and BNY effects are documented, but direct GSD outcomes are missing',
    'Fields 17.2/17.3 were extracted. Shared-system measures cannot be treated as separate outage series for each business.',
    'Direct GSD service effects, member dependencies, and comparable operational measures',
  ],
  'FICC-MBSD-02': [
    'GSE reform',
    'A historical UMBS milestone was identified; it cannot substitute for a conservatorship-exit or privatization event',
    'Incomplete; the FINRA endpoint returned HTTP 401, and the v1 milestone was not frozen',
    'Historical UMBS materials support a related mechanism only; they do not establish that the current hypothesis passed.',
    'A clearly defined reform milestone, FINRA authorization or an official export, and MBSD response data',
  ],
  'ECS-NSCC-01A': [
    'Equity volatility to margin calls',
    'Passed; 3/4 events detected; non-event alert rate 7.7%',
    'Did not meet threshold; ρ=0.195, 95% interval [-0.241, 0.609], n=22',
    'Uses prior-quarter margin as the denominator, as specified in the card, rather than the current-quarter denominator used in an earlier trial.',
    '',
  ],
  'ECS-NSCC-01B': [
    'Equity volatility to variation-margin cash fluctuations',
    'Passed; 3/4 events detected; non-event alert rate 7.7%',
    'Did not meet threshold; ρ=0.081, 95% interval [-0.359, 0.493], n=23',
    'The primary test retains the VIX level and same-quarter alignment. Better results from a modified signal do not replace the primary result.',
    '',
  ],
  'ECS-NSCC-01C': [
    'Equity volatility to margin backtesting breaches',
    'Passed; 3/4 events detected; non-event alert rate 7.7%',
    'Did not meet threshold; ρ=0.414, 95% interval [-0.067, 0.689], n=23',
    'Correlation in changes: ρ=0.095. The outcome is a trailing-12-month count, so quarterly observations overlap.',
    '',
  ],
  'ECS-NSCC-02A': [
    'Volume surge to outstanding settlement fails',
    'Passed; 4/4 events detected; non-event alert rate 13.4%',
    'Met threshold; high-volume weeks were associated with 30.4 million more outstanding FTD shares, HAC p=1.3e-05, n=413 weeks',
    'This is an association between market volume and CNS outstanding FTD balances. It does not measure new fail flows, fail rates, system outages, or DTCC losses. Month-end and quarter-end controls do not eliminate all confounding.',
    'A capacity-vulnerability measure and controls for common trends and other confounders',
  ],
  'ECS-NSCC-02B': [
    'Volume surge to system stress',
    'Passed; 4/4 events detected; non-event alert rate 13.4%',
    'Not run; there is no continuous, comparable NSCC-only series for field 17.3',
    'Reuses volume data from 02A. Shared core-system measures and trailing-12-month reporting cannot directly represent quarterly NSCC outage counts.',
    'NSCC-specific outage and capacity measures',
  ],
  'ECS-NSCC-03A': [
    'Broker credit deterioration to default management',
    'Passed; 2/2 events detected; non-event alert rate 11.1%',
    'Supported by the Lehman NSCC default-management case; price-driven margin calls in 2021 are not treated as a default',
    "A macro credit proxy does not establish deterioration in a particular member's credit. A case study is not quantitative causal validation.",
    '',
  ],
  'ECS-NSCC-03B': [
    'Funding stress to NSCC payments and margin calls',
    'Passed; 4/4 events detected; non-event alert rate 11.9%',
    'Met threshold; ρ=0.454, 95% interval [0.197, 0.680], n=23',
    'Correlation in changes: ρ=0.154; from 2025Q1 onward: ρ=0.086. Across the six primary quarterly tests, BH q=0.119. This does not yet support a claim of robustness or reliable risk scoring.',
    '',
  ],
  'ECS-NSCC-04': [
    'T+1 and other rule changes to the NSCC fail rate',
    'T+1 implementation on 2024-05-28 verified',
    'The specified 3-month-before/after test was not run; immediate official data do not support an inevitable increase',
    'First-day CNS fail rate: 1.90%, versus the May T+2 average of 2.01%. This is not a continuous three-month event study.',
    'A continuous monthly NSCC fail-rate history, V, and other rule-change milestones',
  ],
  'ECS-NSCC-05': [
    'Known peak dates to processing load',
    'Not run; the event calendar and pass criteria were not frozen',
    'Not run; SEC FTD data are now available',
    'Triple witching, Russell, and S&P events each require fixed dates and comparison windows. Dates must not be selected after inspecting results.',
    'An authoritative event calendar, success criteria, and V',
  ],
  'ECS-DTC-01': [
    'T+1 and other rule changes to the DTC fail rate',
    'Reuses the same event as NSCC-04',
    'The specified 3-month-before/after test was not run; first-day non-CNS observations are available',
    'First-day DTC non-CNS fail rate: 2.92%, versus the May T+2 average of 3.24%. SEC CNS FTD data cannot substitute for the DTC non-CNS fail rate.',
    'A continuous monthly DTC non-CNS fail-rate history and V',
  ],
  'ECS-DTC-02A': [
    'Newly listed exploited vulnerabilities to DTC disruption',
    'Incomplete; a KEV catalog addition date is not the date an attack occurred',
    'Not run; direct effects on DTC services have not been verified',
    'The repository contains KEV data, but these are not a list of DTC exposures. The ICBC Treasury-market incident does not directly establish damage to DTC systems.',
    'Applicable event windows, software dependencies, DTC service evidence, and V',
  ],
  'ECS-DTC-02B': [
    'Cloud or vendor outages to DTC disruption',
    'Incomplete; historical coverage and outage-duration data are insufficient',
    'Not run; DTC dependencies and direct service evidence are missing',
    'The repository contains only some Google-related events, not a complete history covering major cloud providers.',
    'Complete vendor outage histories, DTC dependency/service evidence, and V',
  ],
  'ECS-DTC-03': [
    'Issuance surge to new-issue processing',
    'Not run; market-wide 424B filing counts have not been collected',
    'Not run; monthly DTC issuance counts are available',
    'DTC issuance data are available from 2011 onward. Definitions of 424B subtypes, duplicate amendments, and dates are still needed. Business classification provisionally remains under ECS.',
    'Market-wide 424B history, event windows, and V',
  ],
  'ECS-DTC-04': [
    'Funding stress to DTC end-of-day money settlement',
    'Failed; 1/2 events detected; non-event alert rate 10.1%',
    'Incomplete; no direct DTC money-settlement case has been verified',
    'Daily rates corresponding to DCPF3M/DTB3 were added from original Federal Reserve XML files. DGS3MO was not used as a substitute for DTB3.',
    'Direct settlement cases and a definition of how the Participants Fund acts as a buffer',
  ],
};

const output = [[
  'chain_id', 'chain_name', 'execution_scope', 'test_1', 'test_2',
  'card_confidence', 'version', 'notes', 'remaining_requirements', 'route_role',
]];
for (const row of original.slice(1)) {
  const [id, , scope, , , conf, version, , , role] = row.map(v => v ?? '');
  assert(translations[id], `No translation for ${id}`);
  assert(Object.hasOwn(scopes, scope), `Unknown scope ${scope}`);
  assert(Object.hasOwn(confidence, conf), `Unknown confidence ${conf}`);
  assert(Object.hasOwn(roles, role), `Unknown role ${role}`);
  const [name, test1, test2, notes, requirements] = translations[id];
  assert.equal(version, 'v1执行版2026-10-16');
  output.push([id, name, scopes[scope], test1, test2, confidence[conf],
    'v1 execution 2026-10-16', notes, requirements, roles[role]]);
}
assert.equal(output.length, 23);
assert.equal(new Set(output.slice(1).map(row => row[0])).size, 22);
assert.equal(output.slice(1).filter(row => row[2] === 'Both statistical tests executed').length, 8);
assert.equal(output.slice(1).filter(row => row[5] === 'High: card thresholds met').length, 2);
assert(!/[\u4E00-\u9FFF]/u.test(JSON.stringify(output)));
// Compare numerical tokens in both test columns. Reordering prose must not change values.
const tokens = text => (String(text).match(/[+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?/gi) ?? []).sort();
for (let i = 1; i < output.length; i++) {
  for (const j of [3, 4]) {
    assert.deepEqual(tokens(output[i][j]), tokens(original[i][j]), `Changed test numbers: ${output[i][0]} col ${j}`);
  }
  for (let j = 0; j < output[i].length; j++) {
    assert.equal(output[i][j] === '', (original[i][j] ?? '') === '', `Changed blank field: row ${i}, col ${j}`);
  }
}
sheet.getRange('A1:J23').values = output;
wb.recalculate();
const verified = sheet.getRange('A1:J23').values.map(row => row.map(v => v ?? ''));
assert.deepEqual(verified, output);
console.log((await wb.inspect({kind: 'table', range: "'Chain status'!A1:F4", tableMaxRows: 4, tableMaxCols: 6, tableMaxCellChars: 100, maxChars: 2200})).ndjson);

// CSV has no visual formatting. Serialize the verified workbook values as RFC 4180 CSV.
const quote = value => /[",\r\n]/.test(value) ? '"' + value.replaceAll('"', '""') + '"' : value;
const csv = verified.map(row => row.map(quote).join(',')).join('\r\n') + '\r\n';
const imported = await Workbook.fromCSV(csv, {sheetName: 'Verified export'});
assert.deepEqual(imported.worksheets.getItemAt(0).getRange('A1:J23').values.map(row => row.map(v => v ?? '')), output);
assert.equal(crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex'), originalHash);
await fs.writeFile(target, '\uFEFF' + csv, 'utf8');
console.log(JSON.stringify({output: target, rows: 22, columns: 10, numerical_test_values_preserved: true, blank_fields_preserved: true, chinese_source_unchanged: true}));
