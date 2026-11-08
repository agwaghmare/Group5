"""Model A: monthly net cash-flow (surplus) forecasting with leakage-safe rolling-origin backtests.

Candidates: last value, 3- and 6-month mean, seasonal naive (12 months), and an optional global LightGBM. LightGBM is
selected only if it beats the best baseline MAE by >= 5% in the backtest; otherwise the best baseline is used.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.core.db import db_session
from app.pnc.errors import Unavailable
from app.pnc.ml.tracking import dataset_fingerprint, log_run

SEED = 20261110
LGB_MARGIN = 0.05
MIN_ORIGIN, MAX_ORIGIN = 12, 22        # months of history available when forecasting (24 months total)


def load_panel() -> pd.DataFrame:
    with db_session() as s:
        rows = s.execute(text("SELECT customer_id, month, income, consumption_spending, debt_payments FROM gold_monthly_cashflow "
                              "ORDER BY customer_id, month")).mappings().all()
    df = pd.DataFrame(rows)
    for c in ("income", "consumption_spending", "debt_payments"):
        df[c] = df[c].astype(float)
    df["surplus"] = df.income - df.consumption_spending - df.debt_payments
    df["t"] = df.groupby("customer_id").cumcount()
    df["moy"] = pd.to_datetime(df["month"]).dt.month
    return df


def _features(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("customer_id")["surplus"]
    f = df.copy()
    f["lag0"] = df["surplus"]
    f["lag1"], f["lag2"] = g.shift(1), g.shift(2)
    f["mean3"] = g.transform(lambda s: s.rolling(3, min_periods=3).mean())
    f["mean6"] = g.transform(lambda s: s.rolling(6, min_periods=6).mean())
    f["std6"] = g.transform(lambda s: s.rolling(6, min_periods=6).std())
    f["target_next"] = g.shift(-1)
    return f


FEATS = ["lag0", "lag1", "lag2", "mean3", "mean6", "std6", "income", "consumption_spending", "moy"]


def baseline_predictions(df: pd.DataFrame, origin: int) -> dict[str, pd.Series]:
    """Predict month origin+1 for every customer using only data with t <= origin."""
    hist = df[df.t <= origin]
    out = {}
    last = hist[hist.t == origin].set_index("customer_id")["surplus"]
    out["last_value"] = last
    out["mean_3m"] = hist[hist.t > origin - 3].groupby("customer_id")["surplus"].mean()
    out["mean_6m"] = hist[hist.t > origin - 6].groupby("customer_id")["surplus"].mean()
    seas = hist[hist.t == origin - 11].set_index("customer_id")["surplus"]
    if len(seas):
        out["seasonal_naive_12m"] = seas
    return out


def fit_lgbm(train: pd.DataFrame):
    import lightgbm as lgb
    m = lgb.LGBMRegressor(n_estimators=150, learning_rate=0.05, num_leaves=8, min_child_samples=10, subsample=0.8,
                          subsample_freq=1, colsample_bytree=0.8, random_state=SEED, verbose=-1, n_jobs=1)
    m.fit(train[FEATS], train["target_next"])
    return m


def backtest(df: pd.DataFrame | None = None) -> dict:
    df = load_panel() if df is None else df
    feat = _features(df)
    errs: dict[str, list[tuple[int, float, float]]] = {}
    for origin in range(MIN_ORIGIN, MAX_ORIGIN + 1):
        actual = df[df.t == origin + 1].set_index("customer_id")["surplus"]
        for name, pred in baseline_predictions(df, origin).items():
            e = (pred.reindex(actual.index) - actual).dropna()
            errs.setdefault(name, []).extend((origin, float(x), float(a)) for x, a in zip(e, actual.reindex(e.index)))
        # LightGBM: train rows use feature month t' and target t'+1 with t'+1 <= origin (target known by then)
        train = feat[(feat.t + 1 <= origin)].dropna(subset=FEATS + ["target_next"])
        test = feat[(feat.t == origin)].dropna(subset=FEATS).set_index("customer_id")
        if len(train) >= 60 and len(test):
            model = fit_lgbm(train)
            pred = pd.Series(model.predict(test[FEATS]), index=test.index)
            e = (pred.reindex(actual.index) - actual).dropna()
            errs.setdefault("lightgbm", []).extend((origin, float(x), float(a)) for x, a in zip(e, actual.reindex(e.index)))
    metrics = {}
    for name, rows in errs.items():
        arr = np.array([r[1] for r in rows])
        act = np.array([r[2] for r in rows])
        # 80% interval half-width = 1.2816 x std of PRIOR-origin errors (no peeking at the evaluated origin)
        covered, n_cov = 0, 0
        for origin in sorted({r[0] for r in rows}):
            prior = np.array([r[1] for r in rows if r[0] < origin])
            if len(prior) < 20:
                continue
            hw = 1.2816 * prior.std()
            now = [r for r in rows if r[0] == origin]
            covered += sum(abs(r[1]) <= hw for r in now)
            n_cov += len(now)
        metrics[name] = {"mae": float(np.abs(arr).mean()), "rmse": float(np.sqrt((arr ** 2).mean())), "bias": float(arr.mean()),
                         "n_predictions": int(len(arr)), "interval_80_coverage": (covered / n_cov) if n_cov else None,
                         "mean_abs_actual": float(np.abs(act).mean())}
    baselines = {k: v for k, v in metrics.items() if k != "lightgbm"}
    best_base = min(baselines, key=lambda k: baselines[k]["mae"])
    chosen, reason = best_base, f"best baseline by MAE ({baselines[best_base]['mae']:.2f})"
    if "lightgbm" in metrics and metrics["lightgbm"]["mae"] <= baselines[best_base]["mae"] * (1 - LGB_MARGIN):
        chosen, reason = "lightgbm", f"beat best baseline '{best_base}' MAE by >= {LGB_MARGIN:.0%}"
    elif "lightgbm" in metrics:
        reason += f"; LightGBM MAE {metrics['lightgbm']['mae']:.2f} did not beat it by {LGB_MARGIN:.0%}, so it is not used"
    return {"metrics": metrics, "chosen_model": chosen, "selection_reason": reason, "origins": [MIN_ORIGIN, MAX_ORIGIN],
            "evaluation": "rolling-origin one-step-ahead, expanding window, features use only data <= origin",
            "dataset_fingerprint": dataset_fingerprint(df[["customer_id", "month", "surplus"]]), "seed": SEED,
            "n_customers": int(df.customer_id.nunique()), "n_months": int(df.t.max() + 1)}


def train_and_log() -> dict:
    df = load_panel()
    rep = backtest(df)
    metrics = {f"{m}_{k}": v for m, d in rep["metrics"].items() for k, v in d.items() if isinstance(v, (int, float)) and v is not None}
    info = log_run("pnc_cashflow", "backtest", {"seed": SEED, "chosen_model": rep["chosen_model"], "margin": LGB_MARGIN}, metrics, rep)
    return {**rep, "tracking": info}


def load_report() -> dict:
    """Read the backtest report written by the offline training job (`pnc ml train-cashflow`)."""
    from app.pnc.ml.tracking import artifact_dir
    path = artifact_dir() / "pnc_cashflow_backtest.json"
    if not path.exists():
        raise Unavailable("cash-flow model has not been trained; run `pnc ml train-cashflow`")
    return json.loads(path.read_text(encoding="utf-8"))


def forecast_from_series(surplus: list[float], months_ahead: int = 3, report: dict | None = None) -> dict:
    """Forecast from ONE customer's own history using the model selected by the offline backtest.

    Only baseline models are served. If a future backtest selects LightGBM, serving falls back to the best baseline and
    says so (no silent substitution).
    """
    report = report or load_report()
    chosen, note = report["chosen_model"], None
    if chosen == "lightgbm":
        base = {k: v for k, v in report["metrics"].items() if k != "lightgbm"}
        chosen = min(base, key=lambda k: base[k]["mae"])
        note = "LightGBM was selected by the backtest but is not wired for serving; the best baseline is used instead."
    if len(surplus) < 3:
        raise ValueError("not enough history to forecast")
    series, preds = list(surplus), []
    for _ in range(months_ahead):
        if chosen == "mean_6m":
            p = float(np.mean(series[-6:]))
        elif chosen == "mean_3m":
            p = float(np.mean(series[-3:]))
        elif chosen == "seasonal_naive_12m" and len(series) >= 12:
            p = float(series[-12])
        else:
            p = float(series[-1])
        preds.append(p)
        series.append(p)
    rmse = report["metrics"][chosen]["rmse"]
    hw = 1.2816 * rmse * np.sqrt(np.arange(1, months_ahead + 1))
    return {"model": chosen, "selection_reason": report["selection_reason"], "serving_note": note,
            "backtest_mae": report["metrics"][chosen]["mae"], "backtest_interval_80_coverage": report["metrics"][chosen]["interval_80_coverage"],
            "unit": "USD net monthly surplus",
            "forecast": [{"month_ahead": i + 1, "point": round(p, 2), "low_80": round(p - h, 2), "high_80": round(p + h, 2)}
                         for i, (p, h) in enumerate(zip(preds, hw))],
            "interval_note": "80% interval = point +/- 1.28 x backtest RMSE x sqrt(horizon); empirical coverage is in the backtest report.",
            "disclaimer": "A statistical projection from 24 months of synthetic data; not a prediction or advice."}