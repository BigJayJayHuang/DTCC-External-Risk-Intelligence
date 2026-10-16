"""Test 1 (signal vs event windows) and Test 2 (quarterly Spearman, event studies) per TEST_SPEC.md v1."""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import spearmanr

from .data import block_ci

SEED = 20261016          # D9
BDAY = pd.offsets.BDay()


def required_hit_fraction(n_windows):
    """D4: 2 windows -> 2/2, 3 -> 2/3, 4 -> 3/4."""
    return {2: 1.0, 3: 2 / 3, 4: 3 / 4}.get(n_windows, 2 / 3)


# ------------------------------------------------------------------ Test 1
def daily_alerts(s):
    """Alert when value > 90th pct of prior 252 obs (current excluded, ≥126 prior)."""
    thresh = s.shift(1).rolling(252, min_periods=126).quantile(.90)
    alert = (s > thresh).astype(float).where(thresh.notna())
    return pd.DataFrame({'value': s, 'threshold': thresh, 'alert': alert})


def weekly_peaks(s):
    w = s.resample('W-FRI').max()
    n = s.resample('W-FRI').count()
    return w[n > 0]


def weekly_alerts(s, already_weekly=False):
    """D5 / GSD-01 rule: weekly peak > 90th pct of prior 52 weeks (current excluded, ≥26 prior)."""
    w = s if already_weekly else weekly_peaks(s)
    if already_weekly:   # weekly observations dated on survey day -> label by week-ending Friday
        w = w.groupby(w.index + pd.to_timedelta((4 - w.index.dayofweek) % 7, unit='D')).max()
    thresh = w.shift(1).rolling(52, min_periods=26).quantile(.90)
    alert = (w > thresh).astype(float).where(thresh.notna())
    return pd.DataFrame({'value': w, 'threshold': thresh, 'alert': alert})


def test1(alerts, windows, weekly, use_median_share):
    """Evaluate alerts against card windows. Returns dict with per-window detail and pass flag."""
    idx = alerts.index
    excluded = pd.Series(False, index=idx)
    detail = []
    for w in windows:
        a, b = pd.Timestamp(w['start']), pd.Timestamp(w['end'])
        lo, hi = a - 20 * BDAY, b + 20 * BDAY
        if weekly:   # week labelled by Friday covers [Fri-6d, Fri]
            in_win = (idx - pd.Timedelta(days=6) <= b) & (idx >= a)
            excluded |= (idx - pd.Timedelta(days=6) <= hi) & (idx >= lo)
        else:
            in_win = (idx >= a) & (idx <= b)
            excluded |= (idx >= lo) & (idx <= hi)
        win = alerts[in_win].dropna(subset=['alert'])
        testable = len(win) >= (1 if weekly else 2)
        detail.append({'window': w['label'], 'start': w['start'], 'end': w['end'],
                       'testable_obs': int(len(win)), 'hit': bool(win.alert.eq(1).any()) if testable else None,
                       'alert_share': float(win.alert.mean()) if len(win) else None,
                       'peak_value': float(win.value.max()) if len(win) else None})
    outside = alerts[~excluded].dropna(subset=['alert'])
    valid = [d for d in detail if d['hit'] is not None]
    need = required_hit_fraction(len(windows))
    hit_frac = np.mean([d['hit'] for d in valid]) if valid else np.nan
    med = float(np.median([d['alert_share'] for d in valid])) if valid else np.nan
    out_rate = float(outside.alert.mean()) if len(outside) else np.nan
    crit = {'hit_fraction': (hit_frac, f'>= {need:.3f}', bool(len(valid) == len(windows) and hit_frac >= need - 1e-9)),
            'outside_alert_rate': (out_rate, '<= 0.15', bool(out_rate <= .15))}
    if use_median_share:
        crit['median_in_window_alert_share'] = (med, '>= 0.25', bool(med >= .25))
    passed = all(c[2] for c in crit.values())
    reasons = [k for k, c in crit.items() if not c[2]]
    if len(valid) < len(windows):
        reasons.append(f'{len(windows) - len(valid)} window(s) not testable')
    return {'frequency': 'weekly' if weekly else 'daily', 'windows': detail,
            'criteria': {k: {'value': None if pd.isna(v) else float(v), 'rule': r, 'pass': p} for k, (v, r, p) in crit.items()},
            'outside_obs': int(len(outside)), 'sample_start': str(alerts.dropna(subset=['alert']).index.min().date()),
            'sample_end': str(alerts.index.max().date()), 'result': 'PASS' if passed else 'FAIL', 'fail_reasons': reasons}


# ------------------------------------------------------------------ Test 2: quarterly Spearman
def quarterly_max(s, min_obs):
    q = s.groupby(s.index.to_period('Q')).agg(['max', 'count'])
    q.loc[q['count'] < min_obs, 'max'] = np.nan
    out = q['max']
    out.index = out.index.astype(str)
    return out


def spearman_block(x, y, label):
    """x, y: Series indexed by quarter string, aligned. Spearman + 4-quarter block bootstrap CI."""
    j = pd.concat([x.rename('x'), y.rename('y')], axis=1).dropna().sort_index()
    n = len(j)
    out = {'label': label, 'n': n, 'quarters': f"{j.index.min()}–{j.index.max()}" if n else ''}
    if n < 5:
        return {**out, 'rho': None, 'p': None, 'ci95': [None, None], 'status': 'INSUFFICIENT'}
    r = spearmanr(j.x, j.y)
    try:
        lo, hi = block_ci(j.x.values, j.y.values, SEED, list(j.index))
    except ValueError:   # no run of 4 consecutive quarters
        lo, hi = np.nan, np.nan
    rho = float(r.statistic)
    if rho >= .3 and lo > 0:
        status = 'PASS'
    elif rho <= -.3 and hi < 0:
        status = 'WRONG_DIRECTION'
    else:
        status = 'INCONCLUSIVE'
    return {**out, 'rho': rho, 'p': float(r.pvalue), 'ci95': [float(lo), float(hi)], 'status': status,
            'pairs': [{'quarter': q, 'x': float(a), 'y': float(b)} for q, a, b in zip(j.index, j.x, j.y)]}


def consecutive_diff(s):
    """Quarter-on-quarter difference, only between consecutive quarters."""
    s = s.dropna().sort_index()
    gap = pd.Series([pd.Period(q, 'Q').ordinal for q in s.index], index=s.index).diff()
    return s.diff().where(gap == 1)


def shift_quarter(s, k):
    p = pd.PeriodIndex(s.index, freq='Q') - k
    return pd.Series(s.values, index=p.astype(str))


# ------------------------------------------------------------------ Test 2: event studies
def nw_lags(T):
    return int(np.floor(4 * (T / 100) ** (2 / 9)))


def event_study(y, shock, controls, maxlags, label):
    """OLS y ~ 1 + shock + controls with Newey–West HAC; pass = coef > 0 and p < .05."""
    X = pd.concat([shock.rename('shock')] + controls, axis=1)
    j = pd.concat([y.rename('y'), X], axis=1).dropna()
    Xc = sm.add_constant(j.drop(columns='y').astype(float), has_constant='add')
    fit = sm.OLS(j.y.astype(float), Xc).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})
    b, p = float(fit.params['shock']), float(fit.pvalues['shock'])
    status = 'PASS' if (b > 0 and p < .05) else ('WRONG_DIRECTION' if (b < 0 and p < .05) else 'INCONCLUSIVE')
    return {'label': label, 'n': int(len(j)), 'shock_obs': int(j.shock.sum()), 'hac_maxlags': maxlags,
            'coef_shock': b, 'se_shock': float(fit.bse['shock']), 'p': p,
            'ci95': [float(x) for x in fit.conf_int().loc['shock']],
            'mean_y_shock': float(j.y[j.shock == 1].mean()) if j.shock.sum() else None,
            'mean_y_other': float(j.y[j.shock == 0].mean()),
            'coefficients': {k: float(v) for k, v in fit.params.items()},
            'sample': f"{j.index.min().date()}–{j.index.max().date()}", 'status': status}
