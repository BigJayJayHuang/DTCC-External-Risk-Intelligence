"""Exploratory associations and chronologically evaluated ridge models.

This is a retrospective same-quarter association experiment, not a causal model
or a verified point-in-time forecast. Never pool entities as independent dates.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
from sklearn.linear_model import Ridge
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
SEED = 10405
RISK_FEATURES = ["vix_change_pct", "rate_change_pp", "credit_change_index", "funding_basis_max_bps",
                 "fed_regulatory_announcements", "fed_monetary_announcements"]
RISK_LABELS = {
    "vix_change_pct": "Market volatility change",
    "rate_change_pp": "Treasury yield repricing",
    "credit_change_index": "Credit conditions change",
    "funding_basis_max_bps": "Funding basis pressure",
    "fed_regulatory_announcements": "Fed regulatory communication",
    "fed_monetary_announcements": "Fed monetary communication",
}
CHINESE_RISK_LABELS = {
    "vix_change_pct": "市场波动变化", "rate_change_pp": "利率重新定价",
    "credit_change_index": "信用条件变化", "funding_basis_max_bps": "资金市场压力代理",
    "fed_regulatory_announcements": "美联储监管公告数量", "fed_monetary_announcements": "美联储货币政策公告数量",
}
TARGET_LABELS = {
    "revenue_growth_pct": "Revenue QoQ growth (%)",
    "operating_margin_change_pp": "Operating margin QoQ change (pp)",
    "net_margin_change_pp": "Net margin QoQ change (pp)",
    "daily_notional_growth_pct": "Daily cleared notional QoQ growth (%)",
    "daily_sides_growth_pct": "Daily cleared sides QoQ growth (%)",
}
HOLDOUT_START = pd.Period("2025Q3", freq="Q")
HOLDOUT_END = pd.Period("2026Q2", freq="Q")
CV_WINDOWS = [("2023Q3", "2023Q4"), ("2024Q1", "2024Q2"),
              ("2024Q3", "2024Q4"), ("2025Q1", "2025Q2")]
ALPHAS = [1.0, 10.0, 100.0]


def ridge_pipeline(alpha):
    # Only the optional previous-quarter control is imputed. Real business
    # outcomes and risk observations remain missing and are never invented.
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), Ridge(alpha=alpha))


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n")


def make_panel():
    risk = pd.read_csv(ROOT / "data/risk_quarterly.csv", index_col="quarter")
    risk.index = pd.PeriodIndex(risk.index, freq="Q")
    financial = pd.read_csv(ROOT / "data/business_quarterly_financials.csv")
    operations = pd.read_csv(ROOT / "data/business_quarterly_operations.csv")
    targets = []
    for entity, group in financial.groupby("entity"):
        group = group.set_index(pd.PeriodIndex(group.quarter, freq="Q")).sort_index()
        group = group.reindex(pd.period_range("2019Q4", "2026Q2", freq="Q"))
        group["revenue_growth_pct"] = 100 * (group.revenue_usd / group.revenue_usd.shift(1) - 1)
        group["operating_margin_change_pp"] = group.operating_margin_pct.diff()
        group["net_margin_change_pp"] = group.net_margin_pct.diff()
        for name in ["revenue_growth_pct", "operating_margin_change_pp", "net_margin_change_pp"]:
            targets.append((entity, name, group[name]))
    eligible = operations[operations.eligible_for_model]
    for (division, metric), group in eligible.groupby(["division", "metric"]):
        values = group.set_index(pd.PeriodIndex(group.quarter, freq="Q")).value.sort_index()
        values = values.reindex(pd.period_range("2020Q4", "2026Q2", freq="Q"))
        name = "daily_notional_growth_pct" if metric == "daily_notional_usd" else "daily_sides_growth_pct"
        targets.append((f"FICC/{division}", name, 100 * (values / values.shift(1) - 1)))
    rows = []
    for entity, metric, target in targets:
        # Reindex before differencing/lagging. A missing quarter cannot silently
        # turn a two-quarter change into a one-quarter observation.
        table = risk.join(target.rename("target"), how="right")
        table["target_lag1"] = table.target.shift(1)
        for q in [2, 3, 4]:
            table[f"quarter_{q}"] = (table.index.quarter == q).astype(float)
        table = table.loc[(table.index >= pd.Period("2020Q1")) & (table.index <= HOLDOUT_END)]
        table["entity"], table["metric"] = entity, metric
        table.index.name = "quarter"
        rows.append(table.reset_index())
    panel = pd.concat(rows, ignore_index=True)
    panel.quarter = panel.quarter.astype(str)
    panel["target_units"] = np.where(panel.metric.str.endswith("_pp"), "percentage points", "percent QoQ")
    panel["mapping"] = "same-quarter retrospective association"
    panel.to_csv(ROOT / "data/analysis_panel.csv", index=False)
    return panel


def pearson(x, y):
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 8 or np.std(x[mask]) < 1e-12 or np.std(y[mask]) < 1e-12:
        return np.nan
    return float(np.corrcoef(x[mask], y[mask])[0, 1])


def partial_correlation(frame, risk_feature):
    ok = frame[[risk_feature, "target"]].notna().all(axis=1)
    d = frame.loc[ok]
    controls = np.column_stack([np.ones(len(d)), d[["quarter_2", "quarter_3", "quarter_4"]].values,
                                pd.PeriodIndex(d.quarter, freq="Q").asi8.astype(float)])
    values = d[[risk_feature, "target"]].values
    residual = values - controls @ np.linalg.lstsq(controls, values, rcond=None)[0]
    return pearson(residual[:, 0], residual[:, 1])


def bootstrap_corr(x, y, rng, n_boot=2000, block=4):
    """Paired circular moving blocks, keeping missing calendar positions."""
    n = len(x)
    starts = rng.integers(0, n, size=(n_boot, int(np.ceil(n / block))))
    indices = ((starts[:, :, None] + np.arange(block)) % n).reshape(n_boot, -1)[:, :n]
    bx, by = x[indices], y[indices]
    valid = np.isfinite(bx) & np.isfinite(by)
    counts = valid.sum(axis=1)
    mx = np.where(valid, bx, 0).sum(axis=1) / np.maximum(counts, 1)
    my = np.where(valid, by, 0).sum(axis=1) / np.maximum(counts, 1)
    dx, dy = np.where(valid, bx - mx[:, None], 0), np.where(valid, by - my[:, None], 0)
    denominator = np.sqrt((dx * dx).sum(axis=1) * (dy * dy).sum(axis=1))
    corr = np.divide((dx * dy).sum(axis=1), denominator, out=np.full(n_boot, np.nan), where=denominator > 1e-12)
    corr[counts < 8] = np.nan
    return np.nanquantile(corr, [0.025, 0.975])


def circular_shift_p(x, y, observed):
    """Exploratory time-preserving shift reference; stationarity is not assured."""
    values = []
    for k in range(1, len(x)):
        shifted = np.roll(x, k)
        ok = np.isfinite(shifted) & np.isfinite(y)
        if ok.sum() >= 8:
            values.append(abs(float(spearmanr(shifted[ok], y[ok]).statistic)))
    return (1 + sum(v >= abs(observed) - 1e-12 for v in values)) / (len(values) + 1)


def fdr_bh(p):
    p = np.asarray(p)
    order = np.argsort(p)
    adjusted = p[order] * len(p) / np.arange(1, len(p) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1].clip(0, 1)
    result = np.empty_like(adjusted)
    result[order] = adjusted
    return result


def association_analysis(panel):
    rng = np.random.default_rng(SEED)
    rows = []
    for (entity, metric), group in panel.groupby(["entity", "metric"], sort=True):
        group = group.sort_values("quarter")
        y = group.target.values.astype(float)
        for feature in RISK_FEATURES:
            x = group[feature].values.astype(float)
            ok = np.isfinite(x) & np.isfinite(y)
            n = int(ok.sum())
            if n < 12:
                continue
            rho = float(spearmanr(x[ok], y[ok]).statistic)
            corr = pearson(x, y)
            lo, hi = bootstrap_corr(x, y, rng)
            years = pd.PeriodIndex(group.quarter, freq="Q").year
            yearly = [pearson(x[years != yr], y[years != yr]) for yr in sorted(set(years))]
            rows.append({"entity": entity, "metric": metric, "risk_feature": feature,
                         "risk_label": RISK_LABELS[feature], "n_quarters": n,
                         "first_quarter": group.loc[ok, "quarter"].min(), "last_quarter": group.loc[ok, "quarter"].max(),
                         "pearson_r": corr, "spearman_rho": rho,
                         "pearson_block_bootstrap_ci_low": lo, "pearson_block_bootstrap_ci_high": hi,
                         "season_trend_adjusted_pearson_r": partial_correlation(group, feature),
                         "circular_shift_p_exploratory": circular_shift_p(x, y, rho),
                         "leave_one_year_out_min_r": float(np.nanmin(yearly)),
                         "leave_one_year_out_max_r": float(np.nanmax(yearly)),
                         "leave_one_year_out_same_sign_fraction": float(np.mean(np.sign(yearly) == np.sign(corr))),
                         "excluding_2020_pearson_r": pearson(x[years != 2020], y[years != 2020]),
                         "causal_effect_estimated": False})
    result = pd.DataFrame(rows)
    result["fdr_q_exploratory"] = fdr_bh(result.circular_shift_p_exploratory)
    result["passes_exploratory_fdr_5pct"] = result.fdr_q_exploratory < 0.05
    result["abs_spearman"] = result.spearman_rho.abs()
    result.sort_values("abs_spearman", ascending=False).to_csv(ROOT / "results/risk_business_associations.csv", index=False)
    return result


def choose_alpha(train, features, entity, metric, model_name):
    scores, details = {}, []
    periods = pd.PeriodIndex(train.quarter, freq="Q")
    for alpha in ALPHAS:
        absolute_errors = []
        for start, end in CV_WINDOWS:
            before = periods < pd.Period(start)
            validation = (periods >= pd.Period(start)) & (periods <= pd.Period(end))
            if before.sum() < 8 or validation.sum() < 1:
                continue
            fit = ridge_pipeline(alpha)
            fit.fit(train.loc[before, features], train.loc[before, "target"])
            pred = fit.predict(train.loc[validation, features])
            errors = abs(pred - train.loc[validation, "target"].values)
            absolute_errors.extend(errors)
            details.append({"entity": entity, "metric": metric, "model": model_name, "alpha": alpha,
                            "train_first": train.loc[before, "quarter"].min(), "train_last": train.loc[before, "quarter"].max(),
                            "train_n": int(before.sum()), "validation_start": start, "validation_end": end,
                            "validation_n": int(validation.sum()), "mae": float(np.mean(errors))})
        assert absolute_errors, (entity, metric, model_name)
        scores[alpha] = float(np.mean(absolute_errors))
    # Tie-breaking uses stronger regularization, set before inspecting test data.
    best = min(ALPHAS, key=lambda a: (round(scores[a], 10), -a))
    return best, scores[best], details


def fit_models(panel):
    metrics_rows, predictions, coefficient_rows, cv_rows, schemas = [], [], [], [], []
    controls = ["target_lag1", "quarter_2", "quarter_3", "quarter_4"]
    for (entity, metric), group in panel.groupby(["entity", "metric"], sort=True):
        group = group.sort_values("quarter")
        eligible = group.dropna(subset=["target", *RISK_FEATURES]).copy()
        periods = pd.PeriodIndex(eligible.quarter, freq="Q")
        train = eligible.loc[periods < HOLDOUT_START]
        test = eligible.loc[(periods >= HOLDOUT_START) & (periods <= HOLDOUT_END)]
        assert len(train) >= 12 and len(test) >= 2, (entity, metric, len(train), len(test))
        base_name = f"{entity.replace('/', '_')}_{metric}"
        features = controls + RISK_FEATURES
        fits = {}
        for name, chosen_features in [("controls_only", controls), ("controls_plus_risks", features)]:
            alpha, cv_mae, details = choose_alpha(train, chosen_features, entity, metric, name)
            cv_rows.extend(details)
            fit = ridge_pipeline(alpha)
            fit.fit(train[chosen_features], train.target)
            path = ROOT / f"models/{base_name}_{name}.joblib"
            joblib.dump(fit, path)
            fitted_predictions = fit.predict(test[chosen_features])
            fits[name] = (fit, fitted_predictions, alpha, cv_mae)
            schemas.append({"entity": entity, "metric": metric, "model": name, "path": str(path.relative_to(ROOT)),
                            "features": chosen_features, "alpha": alpha,
                            "training_quarters": train.quarter.tolist(), "test_quarters": test.quarter.tolist(),
                            "meaning": "same-quarter conditional association, current-vintage retrospective experiment"})
        mean_pred = np.repeat(train.target.mean(), len(test))
        zero_pred = np.zeros(len(test))
        methods = {"controls_only": fits["controls_only"][1], "controls_plus_risks": fits["controls_plus_risks"][1],
                   "training_mean": mean_pred, "no_change": zero_pred}
        baseline_mae = float(np.mean(abs(methods["controls_only"] - test.target.values)))
        for name, pred in methods.items():
            err = pred - test.target.values
            denom = float(np.sum((test.target.values - test.target.mean()) ** 2))
            mae = float(np.mean(abs(err)))
            rows = {"entity": entity, "metric": metric, "model": name, "train_n": len(train), "test_n": len(test),
                    "train_first": train.quarter.min(), "train_last": train.quarter.max(),
                    "test_first": test.quarter.min(), "test_last": test.quarter.max(),
                    "target_units": test.target_units.iloc[0], "test_mae": mae, "test_rmse": float(np.sqrt(np.mean(err ** 2))),
                    "test_r2": 1 - float(np.sum(err ** 2)) / denom if denom > 0 else None,
                    "mae_improvement_vs_controls_pct": 100 * (baseline_mae - mae) / baseline_mae,
                    "cv_selected_alpha": fits[name][2] if name in fits else None,
                    "validation_mae": fits[name][3] if name in fits else None}
            metrics_rows.append(rows)
            for quarter, actual, value in zip(test.quarter, test.target, pred):
                predictions.append({"entity": entity, "metric": metric, "quarter": quarter, "model": name,
                                    "actual": actual, "predicted": value, "error": value - actual,
                                    "target_units": test.target_units.iloc[0]})
        fit, _, alpha, _ = fits["controls_plus_risks"]
        coef = fit.named_steps["ridge"].coef_
        transformed_features = fit.named_steps["simpleimputer"].get_feature_names_out(features)
        for name, value, mean, scale in zip(transformed_features, coef, fit.named_steps["standardscaler"].mean_, fit.named_steps["standardscaler"].scale_):
            coefficient_rows.append({"entity": entity, "metric": metric, "feature": name,
                                     "feature_kind": "risk_proxy" if name in RISK_FEATURES else "control",
                                     "conditional_coefficient_per_training_sd": float(value),
                                     "coefficient_per_raw_unit": float(value / scale),
                                     "training_mean": float(mean), "training_sd": float(scale),
                                     "selected_alpha": alpha,
                                     "warning": "Regularized descriptive coefficient; not causal or a calibrated risk probability"})
    metrics = pd.DataFrame(metrics_rows)
    metrics.to_csv(ROOT / "results/model_comparison.csv", index=False)
    pd.DataFrame(predictions).to_csv(ROOT / "results/holdout_predictions.csv", index=False)
    pd.DataFrame(coefficient_rows).to_csv(ROOT / "results/ridge_conditional_coefficients.csv", index=False)
    pd.DataFrame(cv_rows).to_csv(ROOT / "results/chronological_validation.csv", index=False)
    write_json(ROOT / "models/model_manifest.json", schemas)
    return metrics


def main():
    for folder in ["models", "results"]:
        (ROOT / folder).mkdir(exist_ok=True)
    panel = make_panel()
    associations = association_analysis(panel)
    metrics = fit_models(panel)
    risk_models = metrics[metrics.model == "controls_plus_risks"]
    summary = {"completed_at_utc": datetime.now(timezone.utc).isoformat(), "objective": "Association between risk types and business metrics",
               "method": "Quarter-aligned changes, Spearman/Pearson correlations, paired 4-quarter block bootstrap, calendar rolling validation and Ridge",
               "risk_proxy_count": len(RISK_FEATURES), "business_target_series": len(risk_models),
               "association_comparisons": len(associations),
               "associations_passing_exploratory_fdr_5pct": int(associations.passes_exploratory_fdr_5pct.sum()),
               "risk_models_beating_controls_on_test_mae": int((risk_models.mae_improvement_vs_controls_pct > 0).sum()),
               "holdout_calendar_window": [str(HOLDOUT_START), str(HOLDOUT_END)],
               "model_training_max_calendar_quarter": "2025Q2",
               "validation_calendar_windows": CV_WINDOWS, "alpha_candidates": ALPHAS,
               "forecast_claim": False, "causal_claim": False, "risk_severity_labels_available": False,
               "strongest_descriptive_associations": associations.sort_values("abs_spearman", ascending=False).head(8).to_dict("records"),
               "risk_model_comparison": risk_models.to_dict("records")}
    write_json(ROOT / "results/analysis_summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in {"strongest_descriptive_associations", "risk_model_comparison"}}, indent=2))
    print(risk_models[["entity", "metric", "train_n", "test_n", "test_mae", "test_r2", "mae_improvement_vs_controls_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()
