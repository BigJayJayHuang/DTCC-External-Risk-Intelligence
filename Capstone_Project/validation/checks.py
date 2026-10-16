"""Data unit checks: date coverage, missing values, PQD quarter alignment.

    python -m validation.checks
Writes results/chain_tests/data_checks.json; raises on structural failures.
"""
import json

import pandas as pd

from . import data as D
from .paths import RAW, RESULTS

PQD_QUARTERS = [str(q) for q in pd.period_range('2020Q4', '2026Q2', freq='Q')]


def run():
    checks, failures = [], []

    def check(name, ok, detail, critical=True):
        checks.append({'check': name, 'ok': bool(ok), 'critical': critical, 'detail': detail})
        if critical and not ok:
            failures.append(name)

    signals = {'ust10_abs_change': (D.ust10_abs_change(), '2018-01-31'), 'sofr_effr_adjusted': (D.sofr_effr_adjusted(), '2018-12-31'),
               'baa_widen20': (D.baa_widen20(), '2018-02-28'), 'vix_jump': (D.vix_jump(), '2018-02-28'),
               'mbs_spread_abs_wchg': (D.mbs_spread_abs_weekly_change(), '2018-01-31'),
               'consolidated_shares': (D.consolidated_volume(), '2018-01-31')}
    for name, (s, latest_start) in signals.items():
        check(f'{name}: coverage', s.index.min() <= pd.Timestamp(latest_start) and s.index.max() >= pd.Timestamp('2026-06-30'),
              f'{s.index.min().date()}–{s.index.max().date()}, n={len(s)}')
        check(f'{name}: no missing/inf after transform', s.notna().all() and (s.abs() < 1e15).all(), f'missing={int(s.isna().sum())}')
        weekly = name == 'mbs_spread_abs_wchg'
        q = s.groupby(s.index.to_period('Q')).size()
        need = 10 if weekly else 45
        short = [x for x in PQD_QUARTERS if q.get(pd.Period(x, 'Q'), 0) < need]
        check(f'{name}: ≥{need} obs in every PQD quarter', not short, f'short quarters: {short}')

    vol = D.cboe_consolidated_shares()
    month_median = vol.venues.groupby(vol.index.to_period('M')).transform('median')
    short_days = vol.index[vol.venues < month_median - 1]
    check('cboe: no day missing >1 venue vs its month', len(short_days) == 0,
          f'venues/day {int(vol.venues.min())}–{int(vol.venues.max())}; short days: {[str(d.date()) for d in short_days][:10]}')
    yrs = vol.groupby(vol.index.year).size()
    check('cboe: trading days per full year 245–255', yrs.loc[2018:2025].between(245, 255).all(), yrs.to_dict())

    ftd = D.sec_ftd_daily()
    files = sorted(p.name for p in (RAW / 'sec_ftd').glob('cnsfails*.zip'))
    expected = [f'cnsfails{p.strftime("%Y%m")}{h}.zip' for p in pd.period_range('2018-01', ftd.index.max().strftime('%Y-%m'), freq='M') for h in 'ab']
    missing_files = sorted(set(expected) - set(files))
    check('sec_ftd: half-month files contiguous', not missing_files, f'{len(files)} files; missing: {missing_files}')
    check('sec_ftd: daily coverage', ftd.index.min() <= pd.Timestamp('2018-01-05') and ftd.index.max() >= pd.Timestamp('2026-06-30'),
          f'{ftd.index.min().date()}–{ftd.index.max().date()}, n={len(ftd)} settlement dates')
    share_no_price = ftd.records_no_price.sum() / ftd.records.sum()
    check('sec_ftd: share of records without price < 1%', share_no_price < .01, f'{share_no_price:.4%} of {int(ftd.records.sum())} records dropped from value', critical=False)

    ofr = D.ofr_spread()
    by_year = ofr.groupby(ofr.index.year).size().to_dict()
    check('ofr: GCF−DVP overnight overlap', len(ofr) > 0, f'n={len(ofr)} days {ofr.index.min().date()}–{ofr.index.max().date()}; by year {by_year}', critical=False)
    for label, a, b in [('Sept 2019', '2019-09-16', '2019-09-20'), ('Mar 2020', '2020-03-09', '2020-03-23'), ('Apr 2025', '2025-04-02', '2025-04-11')]:
        check(f'ofr: obs in {label} window', len(ofr[a:b]) > 0, f'{len(ofr[a:b])} days', critical=False)

    sp = D.sponsored_total()
    check('sponsored: coverage around 2023-12-13 and 2025-02-25 (±60 obs)',
          (sp[:'2023-12-12'].size >= 60) and (sp['2025-02-25':].size >= 60), f'{sp.index.min().date()}–{sp.index.max().date()}, n={len(sp)}')

    p = D.pqd_panel()
    for e in ['GSD', 'MBSD', 'NSCC']:
        qs = p[p.entity == e].quarter.tolist()
        check(f'pqd {e}: quarters 2020Q4–2026Q2 contiguous', qs == PQD_QUARTERS, f'{len(qs)} quarters')
    for e, col in [('GSD', 'im_qoq'), ('MBSD', 'vm_peak_qoq'), ('NSCC', 'vm_peak_to_avg'), ('GSD', 'peak_payment_to_qlr'),
                   ('NSCC', 'peak_payment_to_qlr'), ('GSD', 'top5_client_share'), ('GSD', 'top5_open_share'), ('NSCC', 'top5_open_share'),
                   ('GSD', 'stress_loss_to_im'), ('MBSD', 'stress_loss_to_im')]:
        s = p[p.entity == e].set_index('quarter')[col]
        check(f'pqd {e}.{col}: non-missing quarters', s.notna().sum() > 0,
              f'{int(s.notna().sum())}/{len(s)} non-missing; missing: {s[s.isna()].index.tolist()}', critical=False)
    check('pqd: vm_peak ≥ vm_avg', (p.vm_peak_usd >= p.vm_avg_usd).all(), 'all rows')
    check('pqd: 7.3.4 ratio positive', (p.peak_payment_to_qlr.dropna() > 0).all(), 'all rows')

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / 'data_checks.json').write_text(json.dumps({'checks': checks, 'critical_failures': failures}, indent=2, default=str))
    if failures:
        raise SystemExit(f'Critical data checks failed: {failures}')
    return checks


if __name__ == '__main__':
    for c in run():
        print(('OK  ' if c['ok'] else ('FAIL' if c['critical'] else 'WARN')), c['check'], '|', c['detail'])
