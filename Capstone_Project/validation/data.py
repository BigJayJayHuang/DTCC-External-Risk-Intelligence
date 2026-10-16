"""Load and transform the inputs named on the chain cards.

Existing project files are read only. Derived tables are cached in data/derived/.
"""
import importlib.util, io, json, zipfile
from functools import lru_cache

import numpy as np
import pandas as pd
import openpyxl

from .paths import (RAW, DERIVED, MARKET_DAILY, OLD_TESTS, PQD_RAW_DIR, PQD_MANIFEST, PQD_PANEL, FICC_DAILY_OPS)


def _old():
    """The 10/6 analysis module (reused helpers; importing it runs no analysis)."""
    spec = importlib.util.spec_from_file_location('run_analysis_2026_10_06', OLD_TESTS / 'src' / 'run_analysis.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OLD = _old()
quarter_end_weekdays, block_ci, bh, spearman_rho = OLD.quarter_end_weekdays, OLD.block_ci, OLD.bh, OLD.rho


# ---------------------------------------------------------------- market series
@lru_cache(None)
def fred(series_id):
    if series_id == 'MORTGAGE30US':
        d = pd.read_csv(RAW / 'fred' / 'MORTGAGE30US.csv')
        d.columns = ['observation_date', 'value']
    else:
        d = pd.read_csv(MARKET_DAILY)
        d = d[d.series_id == series_id][['observation_date', 'value']]
    d['observation_date'] = pd.to_datetime(d.observation_date)
    s = pd.to_numeric(d.value, errors='coerce')
    s.index = d.observation_date
    s = s[~s.index.duplicated(keep='last')].sort_index().dropna()
    s.name = series_id
    return s


def sofr_effr_adjusted():
    """Same algorithm as load_daily() in the 10/6 code (past calendar-group median removed)."""
    joined = pd.concat([fred('SOFR'), fred('EFFR')], axis=1).dropna()
    basis = (joined.SOFR - joined.EFFR) * 100
    flags = np.array([quarter_end_weekdays(d) for d in basis.index])
    adjusted = []
    for i, value in enumerate(basis):
        past = basis.iloc[max(0, i - 252):i]
        pastflags = flags[max(0, i - 252):i]
        if len(past) < 126:
            adjusted.append(np.nan); continue
        group = past.iloc[np.flatnonzero(pastflags == flags[i])]
        baseline = group.median() if len(group) >= 6 else past.median()
        adjusted.append(value - baseline)
    return pd.Series(adjusted, index=basis.index, name='sofr_effr_adjusted').dropna()


def ust10_abs_change():
    return ((fred('DGS10').diff() * 100).abs()).dropna().rename('ust10_abs_change')


def baa_widen20():
    return (fred('BAA10Y').diff(20) * 100).clip(lower=0).dropna().rename('baa_widen20')


def vix_jump():
    v = fred('VIXCLS')
    return (v / v.rolling(20, min_periods=20).mean()).dropna().rename('vix_jump')


def mbs_spread_abs_weekly_change():
    """|Δ(MORTGAGE30US − DGS10)| between consecutive weekly survey dates, bp.
    DGS10 is taken on the survey date or the last available day before it."""
    m = fred('MORTGAGE30US')
    t = fred('DGS10').reindex(fred('DGS10').index.union(m.index)).ffill().reindex(m.index)
    spread = (m - t).dropna() * 100
    spread = spread[spread.index >= '2018-01-01']
    return spread.diff().abs().dropna().rename('mbs_spread_abs_wchg')


def cboe_consolidated_shares():
    out = DERIVED / 'cboe_consolidated_daily.csv'
    frames = []
    for p in sorted((RAW / 'cboe').glob('market_history_*.csv')):
        d = pd.read_csv(p, usecols=['Day', 'Market Participant', 'Total Shares'])
        frames.append(d)
    d = pd.concat(frames)
    d['Day'] = pd.to_datetime(d.Day)
    g = d.groupby('Day').agg(total_shares=('Total Shares', 'sum'), venues=('Market Participant', 'nunique'))
    DERIVED.mkdir(parents=True, exist_ok=True)
    g.to_csv(out)
    return g


@lru_cache(None)
def consolidated_volume():
    return cboe_consolidated_shares().total_shares.rename('consolidated_shares')


@lru_cache(None)
def sec_ftd_daily():
    """Daily Σ QUANTITY × PRICE over all CNS fail records of a settlement date."""
    out = DERIVED / 'sec_ftd_daily.csv'
    rows = []
    for p in sorted((RAW / 'sec_ftd').glob('cnsfails*.zip')):
        z = zipfile.ZipFile(p)
        raw = z.read(z.namelist()[0]).decode('latin-1')
        d = pd.read_csv(io.StringIO(raw), sep='|', dtype=str, on_bad_lines='skip')
        d.columns = [c.strip().upper() for c in d.columns]
        d = d[d['SETTLEMENT DATE'].str.match(r'^\d{8}$', na=False)]
        q = pd.to_numeric(d['QUANTITY (FAILS)'], errors='coerce')
        px = pd.to_numeric(d['PRICE'], errors='coerce')
        d = d.assign(q=q, px=px, value=q * px)
        for date, g in d.groupby('SETTLEMENT DATE'):
            rows.append({'date': pd.Timestamp(date), 'fail_value_usd': g.value.sum(min_count=1),
                         'fail_shares': g.q.sum(), 'records': len(g), 'records_no_price': int(g.px.isna().sum()),
                         'source_file': p.name})
    f = pd.DataFrame(rows).groupby('date', as_index=False).agg(
        fail_value_usd=('fail_value_usd', 'sum'), fail_shares=('fail_shares', 'sum'), records=('records', 'sum'),
        records_no_price=('records_no_price', 'sum'), source_file=('source_file', 'first')).sort_values('date')
    DERIVED.mkdir(parents=True, exist_ok=True)
    f.to_csv(out, index=False)
    return f.set_index('date')


def ofr_spread(gcf='REPO-GCF_AR_OO-F'):
    """(GCF − DVP_AR_OO) × 100 bp, OFR Final series. v1 (D1): GCF_AR_OO; GSD-02 post-hoc v2: GCF_AR_T."""
    s = {}
    for mn in [gcf, 'REPO-DVP_AR_OO-F']:
        d = json.loads((RAW / 'ofr' / f'{mn}.json').read_text())
        s[mn] = pd.Series({pd.Timestamp(a): b for a, b in d if b is not None}).sort_index()
    j = pd.concat(s, axis=1).dropna()
    return ((j[gcf] - j['REPO-DVP_AR_OO-F']) * 100).rename(f'{gcf}_minus_dvp_oo_bp')


def sponsored_total():
    d = pd.read_csv(FICC_DAILY_OPS, parse_dates=['date'])
    d = d[(d.metric == 'TOTAL_AMOUNT') & (d.source_id == 'ficc_sponsoredvolume')]
    return d.set_index('date').value.sort_index().rename('sponsored_total_usd')


# ---------------------------------------------------------------- PQD
@lru_cache(None)
def pqd_panel():
    """Existing 2020Q4–2026Q2 panel (read only) plus the new fields named in D2 and 6.7.1 growth."""
    p = pd.read_csv(PQD_PANEL)
    p = p.sort_values(['entity', 'quarter']).reset_index(drop=True)
    # D2: PQD 7.3.4 ÷ quantified 7.1 sum; 7.3.1-based payment_to_qlr stays as is.
    p['peak_payment_to_qlr'] = p.actual_peak_payment_t12m_usd / p.qlr_quantified_sum_usd
    p['vm_peak_qoq'] = p.vm_peak_usd / p.groupby('entity').vm_peak_usd.shift() - 1
    top = top5_client_share()
    p = p.merge(top, on=['quarter', 'entity'], how='left')
    return p


def top5_client_share():
    """PQD 19.1.3.2 (top-5 share of client transactions, average). Blank/N/A kept as NaN."""
    manifest = json.loads(PQD_MANIFEST.read_text())
    ent = {'FICC/GSD': 'GSD', 'FICC/MBSD': 'MBSD', 'NSCC': 'NSCC'}
    rows = []
    for m in manifest:
        path = OLD_TESTS / m['local_file']
        if 'pqd' not in m['local_file'] or not path.exists():
            continue
        q = f"{m['reporting_year']}Q{m['reporting_quarter']}"
        if path.suffix == '.pdf':   # 2024Q4: page 22 shows N/A for all three CCPs (checked 2026-10-16)
            rows += [{'quarter': q, 'entity': e, 'top5_client_share': np.nan, 'top5_client_share_raw': 'N/A (PDF p.22)'} for e in ent.values()]
            continue
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for r in wb['DTCC_ConsolidatedDataFile'].values:
            if len(r) < 2 or str(r[1]) != '19.1.3.2':
                continue
            for i, c in enumerate(r):
                if c in ent:
                    raw = r[i + 4]
                    v, _ = OLD.number(raw, percent=True)
                    rows.append({'quarter': q, 'entity': ent[c], 'top5_client_share': v, 'top5_client_share_raw': str(raw)})
        wb.close()
    return pd.DataFrame(rows).drop_duplicates(['quarter', 'entity'])
