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
    lease_equity,
    lease_parts,
    loan_equity,
    money,
    money_factor_to_apr,
    monthly_rate,
    pct,
    simulate,
)
from app.services.context import BUYOUT_FEE, DecisionContext, account_numbers, load_context, tracker_numbers
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
    Question("explain-apr", "Explain this APR", ("apr", "explain this apr", "explain apr", "interest rate on my loan"), "automotive_finance", "auto-loan"),
    Question("why-refi", "Why does refinancing change interest?", ("refinanc", "why does refinancing", "change interest"), "interest_rate_risk", "rate-refi"),
    Question("residual-value", "What is residual value?", ("residual",), "lease_vs_buy", "lvb-structures"),
    Question("why-depreciation", "Why does depreciation matter?", ("depreciat",), "automotive_finance", "auto-equity"),
    Question("what-is-equity", "What is equity?", ("equity", "upside down", "negative equity"), "automotive_finance", "auto-equity"),
    Question("money-factor", "What is a money factor?", ("money factor", "money-factor"), "lease_vs_buy", "lvb-structures"),
    Question("explain-amortization", "How does amortization work?", ("amort",), "loan_amortization", "amort-payment"),
    Question(
        "lease-vs-buy",
        "How do I compare lease and buy?",
        ("lease versus", "lease vs", "lease or buy", "lease versus buy", "lease and buy"),
        "lease_vs_buy",
        "lvb-compare",
    ),
    Question("interest-rate-risk", "What is interest-rate risk?", ("interest-rate risk", "interest rate risk", "rate risk"), "interest_rate_risk", "rate-fixed"),
    Question("credit-utilization", "What is credit utilization?", ("utilization",), "credit", "credit-utilization"),
    Question("missed-payment", "Why does a missed payment matter?", ("missed payment", "late payment"), "credit", "credit-score"),
    Question("payoff-quote", "What is a payoff quote?", ("payoff",), "automotive_finance", "auto-loan"),
    Question("explain-cd", "What is a CD?", ("certificate of deposit", "what is a cd", " cds", "cd "), "cds_iras", "cd-ladder"),
    Question("explain-ira", "What is an IRA?", ("ira", "roth", "traditional ira"), "cds_iras", "ira-types"),
    Question("mortgage-rate", "Explain this mortgage rate", ("mortgage",), "mortgages", "mtg-payment"),
    Question("time-value", "What is the time value of money?", ("time value", "present value", "discount"), "quant_fundamentals", "quant-tvm"),
    Question("emergency-fund", "What is an emergency fund?", ("emergency fund", "emergency"), "personal_finance", "pf-emergency"),
    Question("extra-principal", "What if I pay extra principal?", ("extra principal", "pay extra", "additional principal"), "loan_amortization", "amort-extra"),
    Question("diversify", "Why does diversification matter?", ("diversif",), "stock_markets", "stock-diversify"),
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
    if ctx.vulnerable:
        return " This explanation is educational. It is not an offer. A person can walk through it with you."
    return ""


def _vehicle_name(ctx: DecisionContext) -> str:
    if not ctx.vehicle:
        return "the vehicle"
    year = ctx.vehicle.get("model_year", "")
    model = ctx.vehicle.get("model", "")
    return f"the {year} {model}".strip()


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
    nums = account_numbers(ctx)
    if nums.get("contract_type") == "lease" and nums.get("money_factor") is not None:
        factor = nums["money_factor"]
        approx = money_factor_to_apr(factor)
        return _levels(
            f"This contract is a lease, so it has a money factor ({factor:.5f}) instead of a loan APR. "
            f"That factor is roughly a {pct(approx)} APR.",
            "A lease does not amortize like a loan. The rent charge each month is (cap cost + residual) × money factor. "
            f"Multiplying the factor by 2400 is the usual way to quote it as an APR: {factor:.5f} × 2400 = {pct(approx)}.",
            f"APR ≈ 2400 × f = 2400 × {factor:.5f} = {approx:.2f}%. "
            "This approximation is conventional in auto leasing. It is not the savings APY formula, and it is not a promise of a refinance rate."
            + _support(ctx),
        )
    if nums.get("apr") is not None and nums.get("current_balance") is not None:
        apr = nums["apr"]
        balance = nums["current_balance"]
        r = monthly_rate(apr)
        interest = balance * r
        payment = nums.get("monthly_payment") or 0.0
        principal = payment - interest if payment else None
        name = _vehicle_name(ctx)
        principal_sentence = (
            f" The scheduled payment is {money(payment)}, so about {money(principal)} of it reduces principal."
            if principal is not None
            else ""
        )
        return _levels(
            f"APR is the yearly rate on the money you still owe. Yours on {name} is {pct(apr)}.",
            f"Each month the rate used is {pct(apr)} / 12 = {r * 100:.3f}% of the unpaid balance. "
            f"On {money(balance)} that is about {money(interest)} of interest this month."
            + principal_sentence,
            f"r = APR/12 = {apr:.4f}/100/12 = {r:.6f}. "
            f"I = B × r = {balance:.2f} × {r:.6f} = {interest:.2f}. "
            f"Principal slice Π = M − I"
            + (f" = {payment:.2f} − {interest:.2f} = {principal:.2f}." if principal is not None else ".")
            + " The APR stays fixed on this contract. A refinance would replace it with a new rate."
            + _support(ctx),
        )
    return _levels(
        "APR is the yearly price of borrowing. Each month you are charged one-twelfth of that rate on what you still owe.",
        "Monthly interest = balance × APR / 12. The payment covers that interest first. The rest reduces the balance. Pass a customer id to use their Toyota contract.",
        "I_t = B_{t−1} × (APR/12). For a fully amortizing loan, M = P · r · (1+r)^n / ((1+r)^n − 1) with r = APR/12. "
        "A lease in this data pack stores a money factor instead of an APR."
        + _support(ctx),
    )


def _explain_refi(ctx: DecisionContext) -> dict[str, str]:
    nums = account_numbers(ctx)
    if ctx.is_lease:
        return _levels(
            "Refinancing is a loan idea: a new loan pays off an old loan. This contract is a lease, so there is no loan APR to replace. Ending it early is a different set of fees.",
            "A lease does not amortize down to zero. You can return the car, buy it for the residual, or look at a loyalty replacement. Those are not the same math as replacing a 12% loan with a 7% loan.",
            "A loan refinance compares Σ interest under the old (r, n, M) with a new (r', n', M'). "
            "A lease payment is d + ρ with d = (C − R)/n and ρ = (C + R)·f. Changing f or R rewrites the lease; it is not an installment refinance."
            + _support(ctx),
        )
    if nums.get("payoff_quote") and nums.get("apr") and nums.get("months_remaining") and ctx.refi_apr:
        payoff = nums["payoff_quote"]
        old_apr = nums["apr"]
        months = int(nums["months_remaining"])
        old_payment = nums.get("monthly_payment") or 0.0
        new_apr = ctx.refi_apr
        old_path = simulate(payoff, old_apr, old_payment) if old_payment else amortize(payoff, old_apr, months)
        new_loan = amortize(payoff, new_apr, months)
        delta = old_path.total_interest - new_loan.total_interest
        return _levels(
            f"Refinancing pays off this loan with a new one. A lower rate on the same months charges less interest. Stretching the months can erase that savings.",
            f"Today's payoff is {money(payoff)} at {pct(old_apr)}, with {months} months left and a payment of {money(old_payment)}. "
            f"The synthetic rate sheet lists {pct(new_apr)} for tier {nums.get('credit_tier_now')} at a {ctx.refi_term_months}-month term. "
            f"Priced on the same {months} months, the new payment would be about {money(new_loan.payment)}. "
            f"Interest would change by about {money(delta)} before fees. A credit check and fees decide whether this exists.",
            f"Keep path: start at payoff Q = {payoff:.2f}, pay M = {old_payment:.2f} at r = {old_apr:.4f}%/12, "
            f"simulated interest ≈ {old_path.total_interest:.2f} over {old_path.months} months. "
            f"New path: M' = Q r' (1+r')^{months} / ((1+r')^{months} − 1) at r' corresponding to {new_apr:.2f}%, "
            f"M' = {new_loan.payment:.2f}, interest = {new_loan.total_interest:.2f}. "
            f"Difference ≈ {delta:.2f} before origination fees. "
            f"The sheet term used to pick the quote is {ctx.refi_term_months} months; the comparison holds the remaining term at {months} so a longer term does not sneak in."
            + _support(ctx),
        )
    return _levels(
        "Refinancing replaces the old rate and the old term with new ones. Interest changes when either one changes.",
        "Same balance, same months, lower APR: you pay less interest. A longer term lowers the payment and can raise total interest. Fees come off the savings.",
        "M = Q r (1+r)^n / ((1+r)^n − 1). Interest on a fresh schedule is nM − Q. "
        "Compare that sum at the old rate and the new rate, then subtract fees. Pass a customer id to run it on their payoff."
        + _support(ctx),
    )


def _explain_residual(ctx: DecisionContext) -> dict[str, str]:
    nums = account_numbers(ctx)
    if ctx.is_lease and nums.get("residual_value") is not None:
        residual = nums["residual_value"]
        market = nums.get("market_value")
        equity = lease_equity(market, residual, BUYOUT_FEE) if market is not None else None
        cap = nums.get("amount_financed")
        term = nums.get("term_months")
        factor = nums.get("money_factor")
        parts = ""
        if cap and term and factor is not None:
            dep, rent, pay = lease_parts(cap, residual, int(term), factor)
            parts = (
                f" Depreciation portion = ({cap:.2f} − {residual:.2f}) / {int(term)} = {dep:.2f}. "
                f"Rent charge = ({cap:.2f} + {residual:.2f}) × {factor:.5f} = {rent:.2f}. "
                f"Base payment ≈ {pay:.2f}."
            )
        ahead = ""
        if equity is not None and market is not None:
            ahead = (
                f" Market value is about {money(market)}. Buying at the residual plus a {money(BUYOUT_FEE)} fee "
                f"would leave about {money(equity)} of room versus that market value."
            )
        return _levels(
            f"Residual value is the price the lease already set for {_vehicle_name(ctx)} at the end: {money(residual)}.",
            "The residual does two jobs. It sets how much of the car's value you are prepaying through the payment, and it is the starting price if you buy the car at the end."
            + ahead,
            f"R = {residual:.2f}." + parts + (
                f" Lease-end equity versus the pack's assumption = V − (R + {BUYOUT_FEE:.0f}) = {equity:.2f}."
                if equity is not None
                else ""
            )
            + " Taxes and a real inspection are outside this figure."
            + _support(ctx),
        )
    if nums.get("contract_type") == "loan":
        return _levels(
            f"Residual value is a lease term, and this contract is a loan, so {_vehicle_name(ctx)} has no residual.",
            "On a loan you already own the car subject to the lien. There is no preset end price. Equity is market value minus what you owe.",
            "A lease residual R enters d = (C − R)/n and the buyout. A loan sets the balance path with B_t = B_{t−1} − (M − B_{t−1} r) and has no R. "
            "Use est_equity or V − payoff for the loan."
            + _support(ctx),
        )
    return _levels(
        "Residual value is the car's value at the end of a lease, written into the contract on day one.",
        "You use it to compute the depreciation piece of a lease payment, and again if you want to buy the car when the lease ends.",
        "d = (C − R) / n and rent = (C + R) × money factor. Buyout starts at R plus any purchase-option fee. A loan contract does not have an R."
        + _support(ctx),
    )


def _explain_depreciation(ctx: DecisionContext) -> dict[str, str]:
    nums = account_numbers(ctx)
    price = nums.get("purchase_price")
    market = nums.get("market_value")
    months = None
    if ctx.account:
        elapsed = ctx.account.get("months_elapsed")
        months = int(float(elapsed)) if elapsed else None
    if price is not None and market is not None:
        drop = price - market
        per_year = drop / months * 12 if months else None
        yearly = f" That is about {money(per_year)} per year over {months} months." if per_year is not None else ""
        return _levels(
            f"{_vehicle_name(ctx).capitalize()} has fallen from {money(price)} to about {money(market)}. That drop of {money(drop)} is depreciation, and it is why owing more than the car is worth is possible.",
            f"The loan or lease balance follows the contract. The car's value follows the market. Depreciation so far is {money(drop)}. If it outruns the paydown, equity turns negative and a trade-in means bringing cash."
            + yearly,
            f"Depreciation to date = V_0 − V_t = {price:.2f} − {market:.2f} = {drop:.2f} ({money(drop)})."
            + (f" Annualized ≈ {drop:.2f} / {months} × 12 = {per_year:.2f}." if per_year is not None else "")
            + " Equity changes by −depreciation − Δbalance. V_t is an estimate, not a dealer offer."
            + _support(ctx),
        )
    return _levels(
        "Depreciation is the car losing value as it ages and gains miles. It matters because you might owe more than the car is worth.",
        "A sale or a trade uses the car's value. Insurance after a total loss often does too. If the balance is higher than that value, the gap is cash you still owe.",
        "ΔV < 0 from depreciation reduces equity one-for-one: ΔE includes ΔV. On a lease, contracted depreciation is (C − R), which is what the payment's depreciation piece collects. Actual market depreciation can be larger or smaller than that contract assumption."
        + _support(ctx),
    )


def _explain_equity(ctx: DecisionContext) -> dict[str, str]:
    nums = account_numbers(ctx)
    market = nums.get("market_value")
    if ctx.is_lease and market is not None and nums.get("residual_value") is not None:
        equity = lease_equity(market, nums["residual_value"], BUYOUT_FEE)
        return _levels(
            f"Equity here means the car is worth about {money(equity)} more than the cost to buy it out of the lease (residual plus a {money(BUYOUT_FEE)} fee).",
            "You do not own the car yet. The 'equity' is only real if you buy it for the residual and the car is worth more than that, or if a loyalty program gives you credit for it. If the number is negative, buying it costs more than the estimated market value.",
            f"E = V − (R + fee) = {market:.2f} − ({nums['residual_value']:.2f} + {BUYOUT_FEE:.0f}) = {equity:.2f}. "
            "The pack's est_equity uses this $350 fee assumption."
            + _support(ctx),
        )
    if market is not None and nums.get("current_balance") is not None:
        equity = loan_equity(market, nums["current_balance"])
        payoff = nums.get("payoff_quote")
        versus_payoff = loan_equity(market, payoff) if payoff is not None else None
        extra = (
            f" Against the payoff quote of {money(payoff)}, the gap is {money(versus_payoff)}."
            if versus_payoff is not None
            else ""
        )
        return _levels(
            f"Equity is the car's value minus what you owe. On the statement balance that is about {money(equity)}.",
            f"Market value about {money(market)} minus balance {money(nums['current_balance'])} is {money(equity)}."
            + extra
            + " Negative equity rolled into a next car raises the next amount financed.",
            f"E_balance = V − B = {market:.2f} − {nums['current_balance']:.2f} = {equity:.2f}. "
            + (
                f"E_payoff = V − payoff = {market:.2f} − {payoff:.2f} = {versus_payoff:.2f}. "
                if versus_payoff is not None and payoff is not None
                else ""
            )
            + "The data pack's est_equity matches E_balance."
            + _support(ctx),
        )
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
        "On a car, use market value minus the loan balance or the lease buyout. On a house, use home value minus the mortgage. It is not a checking balance.",
        "E = V − B. A sale nets about E minus costs. Rolling a negative E into a new loan increases the next principal."
        + _support(ctx),
    )


def _explain_money_factor(ctx: DecisionContext) -> dict[str, str]:
    nums = account_numbers(ctx)
    if nums.get("money_factor") is not None:
        factor = nums["money_factor"]
        approx = money_factor_to_apr(factor)
        return _levels(
            f"The money factor on this lease is {factor:.5f}. Think of it as the lease's version of an interest rate, about {pct(approx)}.",
            "Monthly rent charge = (capitalized cost + residual) × money factor. A lower factor means a lower rent charge. Multiply by 2400 if you want the rough APR.",
            f"ρ = (C + R) × {factor:.5f}. APR ≈ 2400 × {factor:.5f} = {approx:.2f}%. "
            "The factor is not divided by 12 again after that conversion."
            + _support(ctx),
        )
    return _levels(
        "A money factor is the lease version of an interest rate. Multiply it by 2400 for a rough APR.",
        "It is a small decimal, often near 0.00 something. The rent charge each month uses it. Loan contracts in this pack show an APR instead.",
        "Rent ρ = (C + R) × f, and APR ≈ 2400 f. Pass a lease customer id to plug in their factor."
        + _support(ctx),
    )


def _explain_amort(ctx: DecisionContext) -> dict[str, str]:
    nums = account_numbers(ctx)
    if not ctx.is_lease and nums.get("apr") and nums.get("current_balance") and nums.get("monthly_payment"):
        interest = nums["current_balance"] * monthly_rate(nums["apr"])
        principal = nums["monthly_payment"] - interest
        return _levels(
            "Amortization means each payment pays this month's interest and then knocks down the balance. Early payments are mostly interest.",
            f"This month, interest is about {money(interest)} and the principal slice is about {money(principal)} of the {money(nums['monthly_payment'])} payment.",
            f"I = {nums['current_balance']:.2f} × ({nums['apr']:.4f}/100/12) = {interest:.2f}. "
            f"Π = {nums['monthly_payment']:.2f} − {interest:.2f} = {principal:.2f}. "
            f"Next balance ≈ {nums['current_balance'] - principal:.2f} if the extra is not added and the payment posts in full."
            + _support(ctx),
        )
    return _levels(
        "Amortization splits a fixed payment into interest and principal so the loan ends on schedule.",
        "Interest = balance × APR / 12. Principal = payment − interest. The interest slice shrinks as the balance shrinks.",
        "M = P r (1+r)^n / ((1+r)^n − 1), r = APR/12. Then I_t = B_{t−1} r and B_t = B_{t−1} − (M − I_t)."
        + _support(ctx),
    )


def _explain_lease_vs_buy(ctx: DecisionContext) -> dict[str, str]:
    nums = account_numbers(ctx)
    if ctx.is_lease and nums.get("monthly_payment") and nums.get("months_remaining") is not None:
        remaining_cost = nums["monthly_payment"] * nums["months_remaining"]
        return _levels(
            "A lease pays for using the car and usually ends with you giving it back. A loan costs more per month when the term matches, and it ends with you owning the car.",
            f"You have about {int(nums['months_remaining'])} payments left, roughly {money(remaining_cost)} before fees and extra miles. "
            "Returning the car ends the payments and leaves you without the car. Buying it means paying the residual plus a fee, which is worth it only if the car is worth at least that much to you.",
            "Lease net over the remaining term ≈ n_left × payment + turn-in fees + excess mileage − value you keep. "
            "Buyout net ≈ residual + fee + taxes − market value, if you fund the buyout with cash. "
            "Compare those nets. A lower payment is not the comparison."
            + _support(ctx),
        )
    return _levels(
        "Compare total money out and what you own at the end. The lower payment often just means you do not own the car.",
        "Lease cost is payments plus fees plus extra miles, and you own nothing if you return it. Loan cost is payments minus the car's value at the end.",
        "Lease net = n P_lease + fees − owned value. Loan net = n M + down − (V_n − B_n). Pick a horizon, a mileage, and a value, then compare. There is no universal winner."
        + _support(ctx),
    )


def _explain_rate_risk(ctx: DecisionContext) -> dict[str, str]:
    nums = account_numbers(ctx)
    locked = ""
    if nums.get("apr") and not ctx.is_lease:
        locked = f" Your auto APR of {pct(nums['apr'])} stays put if the contract is fixed, even if new loans get cheaper or more expensive."
    return _levels(
        "Interest-rate risk is what changes when market rates move. A variable payment can rise. A bond you already hold can fall in price."
        + locked,
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
    nums = account_numbers(ctx)
    count = nums.get("missed_payments_12m")
    extra = ""
    if count is not None:
        extra = f" This contract shows {int(count)} missed payment(s) in the last 12 months."
    return _levels(
        "A missed payment can be reported on your credit file and can raise the rate you are offered later. It can also trigger a late fee."
        + extra,
        "Payment history is the largest piece of a typical credit score. One late auto payment does not erase principal you already paid, but it can block a cheap refinance and raise insurance or borrowing costs.",
        "The event updates the credit file H and therefore the score s(H). Rate sheets in this pack map tier(s) to an APR. "
        "A missed payment does not change a lease residual and does not reverse prior principal."
        + _support(ctx),
    )


def _explain_payoff(ctx: DecisionContext) -> dict[str, str]:
    nums = account_numbers(ctx)
    if nums.get("payoff_quote") is not None and nums.get("current_balance") is not None:
        gap = nums["payoff_quote"] - nums["current_balance"]
        return _levels(
            f"A payoff quote is the amount that would close the loan today: {money(nums['payoff_quote'])}.",
            f"The statement balance is {money(nums['current_balance'])}. The payoff is {money(gap)} higher, which is accrued interest and any contractual fee through the payoff date.",
            f"Payoff − balance = {nums['payoff_quote']:.2f} − {nums['current_balance']:.2f} = {gap:.2f}. "
            "A useful approximation between due dates is B × (APR/12) × (days/30), plus a fee if the contract charges one. "
            "Use the pack's payoff_quote for this customer rather than inventing a second number."
            + _support(ctx),
        )
    return _levels(
        "A payoff quote is what the lender will take to close the loan today. It can be a bit more than the balance in the app.",
        "Interest keeps accruing between statements. The quote includes interest through the day you would pay it off.",
        "Payoff ≈ B + accrued interest + contractual fee. Accrued ≈ B · (APR/12) · (days since payment / 30)."
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
            f"This mortgage rate is {pct(rate, 3)}. Like a car loan, one month of interest is the balance times that rate divided by 12.",
            f"On a balance of {money(balance)}, this month's interest is about {money(interest)}. Escrow for taxes and insurance can make the draft larger without reducing principal. Home equity in this row is about {money(tracker.get('home_equity') or (value - balance))}.",
            f"I = B × APR/12 = {balance:.2f} × ({rate:.4f}/100/12) = {interest:.2f}. "
            "The full payment also includes principal, and may include escrow E, but E is not in the amortizing M. "
            "These tracker rates are synthetic."
            + _support(ctx),
        )
    return _levels(
        "A mortgage rate is the APR on a home loan. Monthly interest is the balance times that rate divided by 12.",
        "The payment uses the same amortization formula as an auto loan, usually for 15 or 30 years. Escrow is extra and does not reduce principal.",
        "M = P r (1+r)^n / ((1+r)^n − 1), r = APR/12, n often 180 or 360. Pass a tracker user who has a mortgage to plug in their rate."
        + _support(ctx),
    )


def _explain_tvm(ctx: DecisionContext) -> dict[str, str]:
    return _levels(
        "A dollar today is worth more than a dollar later, because today's dollar can earn a return in the meantime.",
        "Grow money forward by multiplying by (1 + rate) each year. Bring a future amount back by dividing. Use a higher rate for riskier money.",
        "FV = PV (1+r)^T and PV = FV / (1+r)^T. The loan payment is the annuity whose present value equals the amount borrowed. A lease residual is a future amount, so it is not added one-for-one to today's cash."
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
    nums = account_numbers(ctx)
    if not ctx.is_lease and nums.get("current_balance") and nums.get("apr") and nums.get("monthly_payment") and nums.get("months_remaining"):
        base = simulate(nums["current_balance"], nums["apr"], nums["monthly_payment"])
        faster = simulate(nums["current_balance"], nums["apr"], nums["monthly_payment"], extra=50)
        saved = base.total_interest - faster.total_interest
        return _levels(
            "Extra principal reduces what you owe, so later months charge less interest, and the loan ends sooner.",
            f"Adding $50 a month to this contract, on top of {money(nums['monthly_payment'])}, would finish in about {faster.months} months instead of {base.months} and save about {money(saved)} of interest, if the servicer posts it to principal and there is no prepayment penalty.",
            f"Simulate M = {nums['monthly_payment']:.2f} and M+50 on B = {nums['current_balance']:.2f} at {nums['apr']:.2f}%. "
            f"Interest falls from {base.total_interest:.2f} to {faster.total_interest:.2f}. "
            "Confirm the statement principal, not only a pushed-out due date."
            + _support(ctx),
        )
    return _levels(
        "Paying extra principal cuts the balance immediately. You pay less interest and finish sooner.",
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


HANDLERS = {
    "explain-apy": _explain_apy,
    "explain-apr": _explain_apr,
    "why-refi": _explain_refi,
    "residual-value": _explain_residual,
    "why-depreciation": _explain_depreciation,
    "what-is-equity": _explain_equity,
    "money-factor": _explain_money_factor,
    "explain-amortization": _explain_amort,
    "lease-vs-buy": _explain_lease_vs_buy,
    "interest-rate-risk": _explain_rate_risk,
    "credit-utilization": _explain_utilization,
    "missed-payment": _explain_missed,
    "payoff-quote": _explain_payoff,
    "explain-cd": _explain_cd,
    "explain-ira": _explain_ira,
    "mortgage-rate": _explain_mortgage,
    "time-value": _explain_tvm,
    "emergency-fund": _explain_emergency,
    "extra-principal": _explain_extra,
    "diversify": _explain_diversify,
}


def highlighted(question: Question, ctx: DecisionContext) -> bool:
    nums = account_numbers(ctx)
    tracker = tracker_numbers(ctx)
    if question.id == "explain-apy":
        return tracker.get("savings_apy") is not None
    if question.id in {"explain-apr", "explain-amortization", "payoff-quote", "extra-principal"}:
        return bool(nums) and not ctx.is_lease
    if question.id == "why-refi":
        return bool(nums) and not ctx.is_lease
    if question.id in {"residual-value", "money-factor"}:
        return ctx.is_lease
    if question.id in {"why-depreciation", "what-is-equity", "lease-vs-buy"}:
        return bool(nums.get("market_value"))
    if question.id == "mortgage-rate":
        return bool(tracker.get("home_value"))
    if question.id == "credit-utilization":
        return tracker.get("credit_utilization") is not None
    if question.id == "missed-payment":
        return nums.get("missed_payments_12m") is not None
    return False


def prompt_label(question: Question, ctx: DecisionContext) -> str:
    if question.id == "explain-apr" and ctx.is_lease:
        return "Explain this money factor"
    if question.id == "what-is-equity" and ctx.is_lease:
        return "What is my lease equity?"
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
    numbers = {"contract": account_numbers(ctx), "tracker": tracker_numbers(ctx)}
    has_yours = bool(numbers["contract"] or numbers["tracker"])
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
