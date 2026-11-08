"""Answer a click on the current decision with three levels of explanation.

Levels
------
simple: everyday words.
learner: the mechanism, with this contract's numbers when we have them.
detailed: the formula, the variables, and the same numbers plugged in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.content.curriculum import LESSON_INDEX
from app.finance_math import (
    amortize,
    future_value,
    money,
    monthly_rate,
    pct,
    simulate,
)
from app.services.context import DecisionContext, account_numbers, load_context, tracker_numbers
from app.services.section6 import present_explanation


def _levels(simple: str, learner: str, detailed: str) -> dict[str, str]:
    return {"simple": simple, "learner": learner, "detailed": detailed}


@dataclass(frozen=True)
class Question:
    id: str
    label: str
    aliases: tuple[str, ...]
    topic_id: str
    lesson_id: str


QUESTIONS: tuple[Question, ...] = (
    Question("explain-apy", "Explain APY", ("apy", "annual percentage yield", "explain apy"), "banking", "bank-apy"),
    Question("explain-apr", "Explain this APR", ("apr", "explain this apr", "explain apr", "interest rate on my loan"), "loan_amortization", "amort-payment"),
    Question("why-refi", "Why does refinancing change interest?", ("refinanc", "why does refinancing", "change interest"), "interest_rate_risk", "rate-refi"),
    Question("explain-amortization", "How does amortization work?", ("amort",), "loan_amortization", "amort-payment"),
    Question("interest-rate-risk", "What is interest-rate risk?", ("interest-rate risk", "interest rate risk", "rate risk"), "interest_rate_risk", "rate-fixed"),
    Question("credit-utilization", "What is credit utilization?", ("utilization",), "credit", "credit-utilization"),
    Question("missed-payment", "Why does a missed payment matter?", ("missed payment", "late payment"), "credit", "credit-score"),
    Question("explain-cd", "What is a CD?", ("certificate of deposit", "what is a cd", " cds", "cd "), "cds_iras", "cd-ladder"),
    Question("explain-ira", "What is an IRA?", ("ira", "roth", "traditional ira"), "cds_iras", "ira-types"),
    Question("mortgage-rate", "Explain this mortgage rate", ("mortgage",), "mortgages", "mtg-payment"),
    Question("time-value", "What is the time value of money?", ("time value", "present value", "discount"), "quant_fundamentals", "quant-tvm"),
    Question("emergency-fund", "What is an emergency fund?", ("emergency fund", "emergency"), "personal_finance", "pf-emergency"),
    Question("extra-principal", "What if I pay extra principal?", ("extra principal", "pay extra", "additional principal"), "loan_amortization", "amort-extra"),
    Question("diversify", "Why does diversification matter?", ("diversif",), "stock_markets", "stock-diversify"),
    Question("what-is-equity", "What is equity?", ("equity", "home equity"), "personal_finance", "pf-emergency"),
)

QUESTION_INDEX = {item.id: item for item in QUESTIONS}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9% ]+", " ", text.lower()).strip()


def match_question(text: str | None, question_id: str | None) -> Question | None:
    if question_id:
        return QUESTION_INDEX.get(question_id)
    if not text:
        return None
    norm = f" {_normalize(text)} "
    best: Question | None = None
    best_score = 0
    for question in QUESTIONS:
        score = 0
        for alias in question.aliases:
            if alias in norm or alias in _normalize(text):
                score = max(score, len(alias))
        if score > best_score:
            best = question
            best_score = score
    return best


def _support(ctx: DecisionContext) -> str:
    return ""


def _explain_apy(ctx: DecisionContext) -> dict[str, str]:
    tracker = tracker_numbers(ctx)
    apy = tracker.get("savings_apy")
    balance = tracker.get("savings_balance")
    if apy is not None and balance is not None:
        grown = future_value(balance, apy, 1)
        interest = grown - balance
        simple = (
            f"APY is the yearly growth rate on savings after compounding. "
            f"Your latest tracker row shows {pct(apy)} APY."
        )
        learner = (
            f"On a savings balance of {money(balance)}, one year at {pct(apy)} APY, with no new deposits, "
            f"grows the balance to about {money(grown)}. That is about {money(interest)} of interest. "
            f"APY already includes compounding, so you do not divide it by 12 and call that the whole story."
        )
        detailed = (
            f"A nominal rate i compounded n times a year has APY = (1 + i/n)^n − 1. "
            f"The tracker stores the APY itself ({pct(apy, 3)}), so one-year growth is "
            f"B × (1 + APY) = {balance:.2f} × (1 + {apy / 100:.6f}) = {grown:.2f}. "
            f"A loan APR is a different quote: it is a borrowing rate, not this yield."
        )
    else:
        simple = "APY is how much a deposit grows in a year after the bank compounds interest."
        learner = (
            "If two savings accounts show the same APY, a deposit grows the same amount over a year. "
            "That is the number to compare. A loan APR is the price of borrowing, not a savings yield."
        )
        detailed = (
            "APY = (1 + i/n)^n − 1, where i is the nominal annual rate and n is the number of compounds per year. "
            "A balance B becomes B × (1 + APY) after one year if nothing is added and the APY does not change. "
            "Open a tracker user to see this with that user's savings_apy and savings_balance."
        )
    return _levels(simple, learner, detailed + _support(ctx))


def _explain_apr(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "APR is the yearly price of borrowing. Each month you are charged one-twelfth of that rate on what you still owe.",
        "Monthly interest = balance × APR / 12. The payment covers that interest first. The rest reduces the balance.",
        "I_t = B_{t−1} × (APR/12). For a fully amortizing loan, M = P · r · (1+r)^n / ((1+r)^n − 1) with r = APR/12."
        + _support(ctx),
    )


def _explain_refi(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "Refinancing replaces the old rate and the old term with new ones. Interest changes when either one changes.",
        "Same balance, same months, lower APR: you pay less interest. A longer term lowers the payment and can raise total interest. Fees come off the savings.",
        "M = Q r (1+r)^n / ((1+r)^n − 1). Interest on a fresh schedule is nM − Q. "
        "Compare that sum at the old rate and the new rate, then subtract fees."
        + _support(ctx),
    )


def _explain_amort(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "Amortization splits a fixed payment into interest and principal so the loan ends on schedule.",
        "Interest = balance × APR / 12. Principal = payment − interest. The interest slice shrinks as the balance shrinks.",
        "M = P r (1+r)^n / ((1+r)^n − 1), r = APR/12. Then I_t = B_{t−1} r and B_t = B_{t−1} − (M − I_t)."
        + _support(ctx),
    )


def _explain_rate_risk(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "Interest-rate risk is what changes when market rates move. A variable payment can rise. A bond you already hold can fall in price.",
        "Fixed borrowers are protected from a rate increase and may want to refinance if rates fall. Bond prices move the other way: higher yields, lower prices. A rough estimate is minus duration times the yield change.",
        "Variable loan: r_t = index_t + margin, and M is recomputed. Fixed loan: r is contractual. "
        "Bond: ΔP/P ≈ −D Δy. The borrower's variable-rate exposure and the bondholder's price exposure have opposite signs."
        + _support(ctx),
    )


def _explain_utilization(ctx: DecisionContext) -> dict[str, str]:
    tracker = tracker_numbers(ctx)
    if tracker.get("credit_utilization") is not None and tracker.get("credit_limit_total"):
        util = tracker["credit_utilization"]
        limit = tracker["credit_limit_total"]
        balance = util * limit
        return _levels(
            f"Utilization is how much of your credit limits you are using. The latest tracker month shows {util:.1%}.",
            f"A limit of {money(limit)} and utilization of {util:.1%} implies reported balances near {money(balance)}. Under about 30% is a common guideline, not a cliff.",
            f"U = balances / limits = {balance:.2f} / {limit:.2f} = {util:.4f}. "
            "Amounts owed are about 30% of the classic FICO weighting, so U can move a score even when payments are on time. "
            "Interest, if you revolve a balance, is a separate APR calculation."
            + _support(ctx),
        )
    return _levels(
        "Utilization is card balances divided by credit limits. Lower is usually better for a score.",
        "A common guideline is to stay under about 30% of the limit that will be reported. Paying before the statement can change what gets reported.",
        "U = Σ B / Σ L. Pass a tracker user id to compute it from credit_utilization and credit_limit_total."
        + _support(ctx),
    )


def _explain_missed(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "A missed payment can be reported on your credit file and can raise the rate you are offered later. It can also trigger a late fee.",
        "Payment history is the largest piece of a typical credit score. One late payment does not erase principal you already paid, but it can block a cheap refinance and raise insurance or borrowing costs.",
        "The event updates the credit file H and therefore the score s(H). "
        "A missed payment does not reverse prior principal."
        + _support(ctx),
    )


def _explain_cd(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "A CD is a bank deposit that locks a yield until a date. Taking the money out early can cost a penalty.",
        "The trade is rate certainty versus access. If new rates rise, you are stuck at the old rate unless you pay the penalty. A ladder spreads maturity dates so some cash frees up sooner.",
        "Maturity value = P × (1 + APY)^T if you hold to maturity. An early withdrawal subtracts the penalty in the contract and can consume principal if you exit immediately. FDIC insurance can apply because it is a deposit, up to the legal limit."
        + _support(ctx),
    )


def _explain_ira(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "An IRA is a retirement account with tax rules. Traditional often deducts contributions now and taxes withdrawals later. Roth is the reverse for qualified withdrawals.",
        "The account is a wrapper. Whatever you hold inside can still lose money. Limits change by year and can phase out with income, so this lesson does not quote a legal cap.",
        "With equal tax rates now and later, a simple model gives the same ending wealth for Traditional and Roth. They diverge when the tax rate changes. Penalties on early withdrawal sit outside that identity."
        + _support(ctx),
    )


def _explain_mortgage(ctx: DecisionContext) -> dict[str, str]:
    tracker = tracker_numbers(ctx)
    rate = tracker.get("mortgage_interest_rate")
    balance = tracker.get("mortgage_balance")
    value = tracker.get("home_value") or 0
    if rate and balance and value > 0:
        interest = balance * monthly_rate(rate)
        return _levels(
            f"This mortgage rate is {pct(rate, 3)}. One month of interest is the balance times that rate divided by 12.",
            f"On a balance of {money(balance)}, this month's interest is about {money(interest)}. Escrow for taxes and insurance can make the draft larger without reducing principal. Home equity in this row is about {money(tracker.get('home_equity') or (value - balance))}.",
            f"I = B × APR/12 = {balance:.2f} × ({rate:.4f}/100/12) = {interest:.2f}. "
            "The full payment also includes principal, and may include escrow E, but E is not in the amortizing M. "
            "These tracker rates are synthetic."
            + _support(ctx),
        )
    return _levels(
        "A mortgage rate is the APR on a home loan. Monthly interest is the balance times that rate divided by 12.",
        "The payment uses the same amortization formula as any installment loan, usually for 15 or 30 years. Escrow is extra and does not reduce principal.",
        "M = P r (1+r)^n / ((1+r)^n − 1), r = APR/12, n often 180 or 360. Pass a tracker user who has a mortgage to plug in their rate."
        + _support(ctx),
    )


def _explain_tvm(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "A dollar today is worth more than a dollar later, because today's dollar can earn a return in the meantime.",
        "Grow money forward by multiplying by (1 + rate) each year. Bring a future amount back by dividing. Use a higher rate for riskier money.",
        "FV = PV (1+r)^T and PV = FV / (1+r)^T. The loan payment is the annuity whose present value equals the amount borrowed."
        + _support(ctx),
    )


def _explain_emergency(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "An emergency fund is cash you keep for a job loss or an urgent repair so you do not have to borrow at a high rate.",
        "A common target is 3 to 6 months of necessary bills. If a card charges a very high APR, a smaller starter fund plus aggressive card payments can make sense before the full target.",
        "Target B* = m × essential monthly spending. While card rate r_c is well above savings yield r_s, a dollar paid to the card saves about r_c − r_s, after a starter cash buffer exists."
        + _support(ctx),
    )


def _explain_extra(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "Paying extra principal reduces what you owe, so later months charge less interest, and the loan ends sooner.",
        "The scheduled payment already covers this month's interest. The extra should be posted to principal. A longer term is a different choice and can raise total interest.",
        "Π_t = M + X − I_t. Interest saved is the difference in Σ I_t versus X = 0. Watch prepayment penalties."
        + _support(ctx),
    )


def _explain_diversify(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "Diversification means you do not bet everything on one company. If that company fails, it is only a piece of the account.",
        "A mix does not stop the whole market from falling. It reduces the damage from one company's own problems. An index fund is one way to own the mix.",
        "Portfolio variance includes a covariance term. Idiosyncratic variance falls as independent risks are combined. A common market factor does not. Correlation of 1 means mixing does not reduce risk below the weighted average of the risks."
        + _support(ctx),
    )


def _explain_equity(ctx: DecisionContext) -> dict[str, str]:
    tracker = tracker_numbers(ctx)
    if tracker.get("home_value") and tracker.get("mortgage_balance") is not None and tracker["home_value"] > 0:
        equity = tracker["home_value"] - tracker["mortgage_balance"]
        return _levels(
            f"Home equity is the home's value minus the mortgage. In the latest tracker month it is about {money(equity)}.",
            "You cannot spend equity like checking. Selling or borrowing against the house is what turns it into cash, and both have costs.",
            f"E = V − B = {tracker['home_value']:.2f} − {tracker['mortgage_balance']:.2f} = {equity:.2f}. "
            f"LTV = B/V. The tracker also stores home_equity = {tracker.get('home_equity')}."
            + _support(ctx),
        )
    return _levels(
        "Equity is value minus the debt on that thing. Positive means you could clear the debt and have value left. Negative means you owe more than it is worth.",
        "On a house, use home value minus the mortgage. It is not a checking balance.",
        "E = V − B. A sale nets about E minus costs."
        + _support(ctx),
    )


HANDLERS = {
    "explain-apy": _explain_apy,
    "explain-apr": _explain_apr,
    "why-refi": _explain_refi,
    "explain-amortization": _explain_amort,
    "interest-rate-risk": _explain_rate_risk,
    "credit-utilization": _explain_utilization,
    "missed-payment": _explain_missed,
    "explain-cd": _explain_cd,
    "explain-ira": _explain_ira,
    "mortgage-rate": _explain_mortgage,
    "time-value": _explain_tvm,
    "emergency-fund": _explain_emergency,
    "extra-principal": _explain_extra,
    "diversify": _explain_diversify,
    "what-is-equity": _explain_equity,
}


def highlighted(question: Question, ctx: DecisionContext) -> bool:
    tracker = tracker_numbers(ctx)
    if question.id == "explain-apy":
        return tracker.get("savings_apy") is not None
    if question.id == "mortgage-rate":
        return bool(tracker.get("home_value"))
    if question.id == "credit-utilization":
        return tracker.get("credit_utilization") is not None
    return False


def prompt_label(question: Question, ctx: DecisionContext) -> str:
    return question.label


def prompts_for(ctx: DecisionContext) -> list[dict]:
    rows = []
    for question in QUESTIONS:
        rows.append(
            {
                "id": question.id,
                "label": prompt_label(question, ctx),
                "topic_id": question.topic_id,
                "lesson_id": question.lesson_id,
                "highlighted": highlighted(question, ctx),
            }
        )
    rows.sort(key=lambda row: (not row["highlighted"], row["label"]))
    return rows


def explain(
    question_id: str | None,
    text: str | None,
    customer_id: str | None,
    tracker_user_id: int | None,
    go_deeper: bool = False,
) -> dict:
    question = match_question(text, question_id)
    ctx = load_context(customer_id, tracker_user_id)
    if question is None:
        return {
            "matched": False,
            "explanation": present_explanation(
                "unmatched",
                _levels(
                    "Pick one of the questions on this decision.",
                    "The learning agent answers the curriculum's questions.",
                    "Unmatched text is not given a made-up formula. Choose a question id from the prompt list.",
                ),
                number_source="toy",
                go_deeper=go_deeper,
                go_deeper_path="/learn/context/explain",
            ),
            "prompts": prompts_for(ctx),
            "notes": ctx.notes,
        }
    lesson = LESSON_INDEX[question.lesson_id]
    numbers = {"tracker": tracker_numbers(ctx)}
    has_yours = bool(numbers["tracker"])
    return {
        "matched": True,
        "question_id": question.id,
        "label": prompt_label(question, ctx),
        "topic_id": question.topic_id,
        "lesson_id": question.lesson_id,
        "lesson_title": lesson["title"],
        "explanation": present_explanation(
            question.lesson_id,
            HANDLERS[question.id](ctx),
            number_source="yours" if has_yours else "toy",
            go_deeper=go_deeper,
            go_deeper_path="/learn/context/explain",
            check_my_understanding={
                "lesson_id": question.lesson_id,
                "path": f"/learn/lessons/{question.lesson_id}/check-my-understanding",
            },
        ),
        "your_numbers": numbers,
        "notes": ctx.notes,
        "related_lesson_ids": [question.lesson_id],
    }
