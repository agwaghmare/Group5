"""Versioned synthetic policy. Only ALLOWED fields enter evaluation."""
import hashlib
import json
import math
from copy import deepcopy

from app.finance_math import payment

POLICY = {
    "id": "pnc-demo-v1", "version": "pnc-demo-v1", "synthetic": True,
    "label": "Team-authored prototype; not PNC policy or a credit offer",
    "rules": {
        "utilization": [0.30, 0.60], "dti": [0.36, 0.43],
        "delinquencies_24m": [0, 1], "inquiries_6m": [2, 4],
        "personal_loan_income_share": [0.40, 0.60],
        "credit_card_income_share": [0.25, 0.40], "history_months": 24,
    },
    "products": {
        "personal_loan": {"apr_percent": 12.0, "min_term": 12, "max_term": 60},
        "credit_card": {"apr_percent": 22.0, "minimum_payment_rate": 0.03},
    },
}
ALLOWED = (
    "product", "annual_income", "income_verified", "credit_band",
    "revolving_balance", "revolving_limit", "existing_monthly_debt",
    "delinquencies_24m", "history_months", "inquiries_6m",
    "requested_amount", "requested_limit", "term_months",
)
OUTCOMES = {"MEETS_POLICY": "Proceed to next step (simulated)",
            "REFER": "Refer to senior review", "INSUFFICIENT_DATA": "Request more information",
            "DOES_NOT_MEET": "Decline as entered (with reason codes)"}


def evaluate(profile, policy=None, counterfactuals=True, validate=True):
    policy = deepcopy(policy or POLICY)
    data = {key: profile.get(key) for key in ALLOWED}
    missing, evidence = [], []
    rules = policy["rules"]

    def num(key, positive=False):
        value = data.get(key)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0 or (positive and value == 0)):
            if key not in missing:
                missing.append(key)
            return None
        return value

    def row(key, value, meets, watch, reverse=False):
        if isinstance(value, float):
            value = round(value, 12)  # Keep exact policy boundaries stable under float division.
        if value is None:
            state = "missing"
        elif reverse:
            state = "pass" if value >= meets else "watch"
        else:
            state = "pass" if value <= meets else "watch" if value <= watch else "fail"
        evidence.append({"rule": key, "value": value, "meets_threshold": meets,
                         "watch_threshold": watch, "status": state, "reason_code": f"{key.upper()}_{state.upper()}"})

    product = data["product"]
    if product not in policy["products"]:
        raise ValueError("Unsupported product")
    annual = num("annual_income", True)
    balance, limit = num("revolving_balance"), num("revolving_limit", True)
    debt = num("existing_monthly_debt")
    band = data["credit_band"]
    if band not in ("Excellent", "Good", "Fair", "Poor"):
        missing.append("credit_band")
    evidence.append({"rule": "credit_band", "value": band,
                     "meets_threshold": ["Excellent", "Good"], "watch_threshold": "Fair",
                     "status": "missing" if "credit_band" in missing else
                     "pass" if band in ("Excellent", "Good") else "watch" if band == "Fair" else "fail",
                     "reason_code": "CREDIT_BAND"})
    row("utilization", balance / limit if balance is not None and limit else None, *rules["utilization"])
    spec = policy["products"][product]
    amount_key = "requested_amount" if product == "personal_loan" else "requested_limit"
    amount = num(amount_key, True)
    new_payment = None
    if product == "personal_loan":
        term = num("term_months", True)
        if term is not None and (int(term) != term or not spec["min_term"] <= term <= spec["max_term"]):
            missing.append("valid_term_months")
            term = None
        if amount and term:
            new_payment = payment(amount, spec["apr_percent"], int(term))
    elif amount:
        new_payment = amount * spec["minimum_payment_rate"]
    row("dti", (debt + new_payment) / (annual / 12)
        if annual and debt is not None and new_payment is not None else None, *rules["dti"])
    for key in ("delinquencies_24m", "inquiries_6m"):
        row(key, num(key), *rules[key])
    row("history_months", num("history_months"), rules["history_months"], None, reverse=True)
    row("income_share", amount / annual if amount and annual else None, *rules[f"{product}_income_share"])
    verified = data["income_verified"] in (True, "Y")
    if not verified:
        missing.append("income_verified")
    evidence.append({"rule": "income_verified", "value": verified, "meets_threshold": True,
                     "watch_threshold": None, "status": "pass" if verified else "missing",
                     "reason_code": "INCOME_VERIFICATION"})
    states = {r["status"] for r in evidence}
    outcome = ("DOES_NOT_MEET" if "fail" in states else "INSUFFICIENT_DATA" if missing
               else "REFER" if "watch" in states else "MEETS_POLICY")
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()
    result = {"policy_version": policy["version"], "policy_snapshot": policy,
              "input_snapshot": data, "input_hash": fingerprint, "outcome": outcome,
              "recommended_human_action": OUTCOMES[outcome], "rules": evidence,
              "strengths": [r["rule"] for r in evidence if r["status"] == "pass"],
              "concerns": [r["rule"] for r in evidence if r["status"] in ("watch", "fail")],
              "missing_inputs": sorted(set(missing)), "new_payment": round(new_payment, 2) if new_payment is not None else None,
              "indicative_pricing": {"apr_percent": spec["apr_percent"],
                  "label": "Indicative, synthetic, not an offer"}, "counterfactuals": [],
              "synthetic": True, "validation": {"passed": True, "checks": ["finite_numbers", "allowed_inputs", "policy_evidence"]}}
    # Report a change only when rerunning the entire engine proves a better outcome.
    if counterfactuals and outcome != "MEETS_POLICY":
        target = deepcopy(data)
        changes = {}
        if annual:
            amount_ceiling = annual * rules[f"{product}_income_share"][0]
            if amount and amount > amount_ceiling:
                changes[amount_key] = round(amount_ceiling, 2)
        if balance is not None and limit and balance > limit * rules["utilization"][0]:
            changes["revolving_balance"] = round(limit * rules["utilization"][0], 2)
        target.update(changes)
        if changes:
            after = evaluate(target, policy, counterfactuals=False, validate=False)
            rank = {"DOES_NOT_MEET": 0, "INSUFFICIENT_DATA": 1, "REFER": 2, "MEETS_POLICY": 3}
            if rank[after["outcome"]] > rank[outcome]:
                result["counterfactuals"].append({"changes": changes, "verified_outcome": after["outcome"],
                                                "label": "Recomputed scenario, not a promise"})
    if validate:
        validate_result(result)
    return result


def validate_result(result):
    """Reject nonfinite numbers, excluded inputs, or claims inconsistent with replay."""
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Nonfinite value in policy evidence")
        if isinstance(value, dict):
            for item in value.values():
                finite(item)
        elif isinstance(value, list):
            for item in value:
                finite(item)
    finite(result)
    if set(result["input_snapshot"]) != set(ALLOWED):
        raise ValueError("Input snapshot includes excluded or missing fields")
    replay = evaluate(result["input_snapshot"], result["policy_snapshot"], counterfactuals=False, validate=False)
    for key in ("outcome", "rules", "input_hash", "new_payment", "indicative_pricing", "missing_inputs"):
        if result[key] != replay[key]:
            raise ValueError(f"Policy result does not match evidence: {key}")
    for scenario in result["counterfactuals"]:
        changed = {**result["input_snapshot"], **scenario["changes"]}
        after = evaluate(changed, result["policy_snapshot"], counterfactuals=False, validate=False)
        if after["outcome"] != scenario["verified_outcome"]:
            raise ValueError("Counterfactual outcome is not supported by recomputation")
