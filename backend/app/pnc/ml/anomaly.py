"""Model B + rules: transaction anomaly detection. An anomaly is a statistical oddity worth a human look, NOT fraud.

* Rules: large amount vs the customer's own trailing category median, same-day burst, near-duplicate charge.
* IsolationForest trained on the earlier period (temporal split); contamination fixed and logged.
* Evaluation uses SYNTHETIC injected anomalies, reported separately; there are no real fraud labels, so no
  precision/recall for "fraud" is ever claimed.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy import text

from app.core.db import db_session
from app.pnc.ml.tracking import dataset_fingerprint, log_run

SEED = 20261111
TRAIN_END = pd.Timestamp("2026-04-30")
CONTAMINATION = 0.01
MODEL_VERSION = f"iforest-v1-seed{SEED}-c{CONTAMINATION}"
SPEND_CATS = ["groceries", "dining", "fuel", "shopping", "entertainment", "healthcare", "travel", "education"]
FEATS = ["log_amount", "ratio_to_median", "day_of_month", "cat_code", "same_day_count", "days_since_prev"]


def load_spend() -> pd.DataFrame:
    with db_session() as s:
        rows = s.execute(text(
            "SELECT transaction_id, posted_date, customer_id, account_id, category, description, amount FROM pnc_transactions "
            "WHERE flow_class = 'expense' AND category = ANY(:c) ORDER BY customer_id, posted_date, transaction_id"),
            {"c": SPEND_CATS}).mappings().all()
    df = pd.DataFrame(rows)
    df["posted_date"] = pd.to_datetime(df["posted_date"])
    df["amount"] = df["amount"].astype(float)
    return df


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time features: medians use only that customer's PRIOR transactions in the category."""
    d = df.sort_values(["customer_id", "posted_date", "transaction_id"]).copy()
    glob = d.groupby("category")["amount"].median()
    d["prior_median"] = d.groupby(["customer_id", "category"])["amount"].transform(lambda s: s.shift(1).expanding(min_periods=3).median())
    d["prior_median"] = d["prior_median"].fillna(d["category"].map(glob))
    d["ratio_to_median"] = d["amount"] / d["prior_median"].clip(lower=1.0)
    d["log_amount"] = np.log1p(d["amount"])
    d["day_of_month"] = d["posted_date"].dt.day
    d["cat_code"] = d["category"].map({c: i for i, c in enumerate(SPEND_CATS)}).astype(int)
    d["same_day_count"] = d.groupby(["customer_id", "posted_date"])["amount"].transform("count")
    d["days_since_prev"] = d.groupby("customer_id")["posted_date"].diff().dt.days.fillna(30).clip(upper=60)
    return d


def rule_flags(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["rule_large"] = (d["amount"] >= 250) & (d["ratio_to_median"] >= 4.0)
    d["rule_burst"] = d["same_day_count"] >= 5
    key = d.groupby(["customer_id", "category", "amount"])["posted_date"]
    d["rule_duplicate"] = (key.diff().dt.days.abs() <= 2) | (key.diff(-1).dt.days.abs() <= 2)
    return d


def fit_forest(train: pd.DataFrame) -> IsolationForest:
    return IsolationForest(n_estimators=200, contamination=CONTAMINATION, random_state=SEED, n_jobs=1).fit(train[FEATS])


def inject_synthetic(d_full: pd.DataFrame, k: int = 60) -> tuple[pd.DataFrame, set]:
    """Add k synthetic anomalous purchases (5-15x the customer's usual amount) to a COPY of the full history,
    placed on real dates inside the test period, then recompute point-in-time features over the combined frame."""
    rng = np.random.default_rng(SEED)
    test = d_full[d_full.posted_date > TRAIN_END]
    base = test.sample(k, random_state=SEED)
    synth = base[df_cols()].copy()
    synth["amount"] = (base["prior_median"].clip(lower=20) * rng.uniform(5, 15, size=k)).round(2).to_numpy()
    synth["transaction_id"] = [f"SYN{i:04d}" for i in range(k)]
    synth["description"] = "SYNTHETIC injected anomaly"
    return add_features(pd.concat([d_full[df_cols()], synth], ignore_index=True)), set(synth["transaction_id"])

def df_cols() -> list[str]:
    return ["transaction_id", "posted_date", "customer_id", "account_id", "category", "description", "amount"]


def evaluate(df: pd.DataFrame | None = None) -> dict:
    raw = load_spend() if df is None else df
    d = add_features(raw)
    train, test = d[d.posted_date <= TRAIN_END], d[d.posted_date > TRAIN_END]
    model = fit_forest(train)
    nat_flag = model.predict(test[FEATS]) == -1
    syn_frame, syn_ids = inject_synthetic(d)
    syn_only = syn_frame[syn_frame.transaction_id.isin(syn_ids)]
    syn_flag = model.predict(syn_only[FEATS]) == -1
    syn_rules = rule_flags(syn_frame)
    syn_rules = syn_rules[syn_rules.transaction_id.isin(syn_ids)]
    nat_rules = rule_flags(test)
    return {
        "model_version": MODEL_VERSION, "seed": SEED, "contamination": CONTAMINATION, "train_end": str(TRAIN_END.date()),
        "n_train": int(len(train)), "n_test_natural": int(len(test)), "features": FEATS,
        "natural_test": {"isolation_forest_flag_rate": float(nat_flag.mean()), "rule_large_flag_rate": float(nat_rules.rule_large.mean()),
                         "rule_burst_flag_rate": float(nat_rules.rule_burst.mean()), "rule_duplicate_flag_rate": float(nat_rules.rule_duplicate.mean())},
        "synthetic_injection": {"n_injected": int(len(syn_only)), "isolation_forest_detection_rate": float(syn_flag.mean()),
                                "rule_large_detection_rate": float(syn_rules.rule_large.mean()),
                                "either_detector_detection_rate": float((syn_flag | syn_rules.rule_large.to_numpy()).mean()),
                                "note": "Injected anomalies are synthetic; this measures sensitivity to large unusual purchases only."},
        "disclaimer": "No real fraud labels exist. Flags are anomalies for human review, not fraud determinations.",
        "dataset_fingerprint": dataset_fingerprint(raw[["transaction_id", "amount"]]),
        "_natural_score_threshold": float(model.offset_),
    }


def score_and_persist(df: pd.DataFrame | None = None) -> dict:
    """Flag natural transactions (rules or forest) and store them as review items (idempotent)."""
    raw = load_spend() if df is None else df
    d = rule_flags(add_features(raw))
    train = d[d.posted_date <= TRAIN_END]
    model = fit_forest(train)
    d["iforest_score"] = -model.decision_function(d[FEATS])
    d["iforest_flag"] = model.predict(d[FEATS]) == -1
    flagged = d[d.iforest_flag | d.rule_large | d.rule_burst]
    rows = []
    for r in flagged.itertuples():
        detectors = ([("isolation_forest", float(r.iforest_score))] if r.iforest_flag else []) + \
                    ([("rule:large_amount", float(r.ratio_to_median))] if r.rule_large else []) + \
                    ([("rule:same_day_burst", float(r.same_day_count))] if r.rule_burst else [])
        for det, score in detectors:
            rows.append({"c": r.customer_id, "t": r.transaction_id, "d": r.posted_date.date(), "det": det, "sc": round(score, 6),
                         "mv": MODEL_VERSION if det == "isolation_forest" else "rules-v1",
                         "f": json.dumps({"amount": r.amount, "category": r.category, "ratio_to_prior_median": round(float(r.ratio_to_median), 2),
                                          "same_day_count": int(r.same_day_count), "prior_median": round(float(r.prior_median), 2)})})
    with db_session() as s:
        n = 0
        for row in rows:
            n += s.execute(text(
                "INSERT INTO pnc_fraud_events(customer_id, transaction_id, posted_date, detector, anomaly_score, model_version, "
                "supporting_factors, source_type) VALUES (:c,:t,:d,:det,:sc,:mv,CAST(:f AS jsonb),'synthetic_demo_detection') "
                "ON CONFLICT (transaction_id, detector, model_version) DO NOTHING"), row).rowcount
    return {"flagged_transactions": int(len(flagged)), "events_inserted": n, "events_total_candidates": len(rows)}


def train_and_log() -> dict:
    rep = evaluate()
    metrics = {**{f"natural_{k}": v for k, v in rep["natural_test"].items()},
               **{f"synthetic_{k}": v for k, v in rep["synthetic_injection"].items() if isinstance(v, float)}}
    rep["tracking"] = log_run("pnc_anomaly", "isolation_forest", {"seed": SEED, "contamination": CONTAMINATION, "train_end": str(TRAIN_END.date())},
                              metrics, rep)
    return rep
