"""Shape every Learn explanation into the Skill.md Section 6 sequence.

Order the reader sees:
1. one sentence that defines the term and spells out acronyms
2. an everyday analogy
3. a worked example, labeled as the user's numbers or as toy numbers
4. what this means for you, plus one safe next step
5. a go-deeper control (the formula stays behind it until opened)
6. check my understanding, in lesson mode
"""

from __future__ import annotations

import re

# Longer forms first so "CDs" is not partially treated as "CD".
_ACRONYMS: tuple[tuple[str, str], ...] = (
    ("APY", "APY (annual percentage yield)"),
    ("APR", "APR (annual percentage rate)"),
    ("IRAs", "IRAs (individual retirement accounts)"),
    ("IRA", "IRA (individual retirement account)"),
    ("CDs", "CDs (certificates of deposit)"),
    ("CD", "CD (certificate of deposit)"),
    ("DTI", "DTI (debt-to-income)"),
    ("NPV", "NPV (net present value)"),
    ("LTV", "LTV (loan-to-value)"),
    ("FDIC", "FDIC (Federal Deposit Insurance Corporation)"),
    ("FICO", "FICO (Fair Isaac Corporation)"),
)

_ANALOGY: dict[str, str] = {
    "pf-cashflow": "Cash flow is a bathtub. Pay is the faucet and spending is the drain. The water rises only when the faucet beats the drain.",
    "pf-budget": "A budget is putting cash into labeled envelopes before the month starts, so the rent envelope is not the same pile as the concert envelope.",
    "pf-emergency": "An emergency fund is a spare tire. You keep it for a blowout, and you do not use it for a scenic drive.",
    "bank-accounts": "Checking is the wallet in your pocket. Savings is a jar on a high shelf: harder to spend by accident, and able to earn interest.",
    "bank-apy": "Annual percentage yield is a sourdough starter. Interest earns its own interest, so the jar grows faster once something is already in it.",
    "credit-score": "A credit score is a report card about borrowed money. It does not grade your salary, any more than a driving record grades your height.",
    "credit-utilization": "Utilization is how full a glass is. A $300 drink in a $1,000 glass is 30 percent full, even if you plan to finish it later.",
    "amort-payment": "A loan payment is rent on a melting snowball. Early on you mostly pay rent on a big snowball. Later the snowball is smaller, so more of each payment melts it.",
    "amort-extra": "Extra principal knocks a chunk off the snowball today, so every later month charges rent on less snow.",
    "inv-return": "Return is the extra pizza compared with what you paid, not the number of slices alone. Ten more dollars on a small pizza matters more than ten dollars on a huge one.",
    "inv-risk": "Risk is how wide the dartboard is, not the bullseye you hope for. A wide board can have a fine average and still send one dart into the wall.",
    "stock-price": "A stock price is the last handshake between a buyer and a seller. The next handshake can be for a different amount.",
    "stock-diversify": "One company is one field of crops. A mix is several fields, so one hailstorm does not take the whole year. A storm over the whole county can still hit every field.",
    "cd-ladder": "A certificate of deposit is a coat check with a pickup time. You get the rate you were promised if you wait. A ladder is several coat checks with different pickup times.",
    "ira-types": "An individual retirement account is a labeled box. Traditional and Roth are two stickers about when tax is paid. The sticker does not stop whatever is inside the box from falling in value.",
    "mtg-payment": "A mortgage is the same melting-snowball payment as a car loan, on a much longer hill. Escrow is a side pocket for the tax and insurance bills.",
    "mtg-equity": "Home equity is the slice of the house you would keep after paying off the loan. It is not cash sitting in a kitchen drawer.",
    "auto-loan": "An auto loan is paying for the car in slices, plus rent on the slice you have not paid yet. The car ages on its own clock.",
    "auto-equity": "Vehicle equity is a tug-of-war. Depreciation pulls the car's value down. Principal payments pull the balance down. You are ahead only when the balance falls faster.",
    "lvb-structures": "A lease is paying for the drop in the car's value plus a finance charge, then handing the keys back. A loan keeps going until the keys are yours.",
    "lvb-compare": "Choosing on the monthly payment alone is like comparing rent and a mortgage by the size of the check and ignoring who holds the keys at the end.",
    "rate-fixed": "A fixed rate is a locked door. A variable rate is a door someone else can reopen. A bond you already hold is an old ticket that gets cheaper when new tickets pay more.",
    "rate-refi": "Refinancing trades in the loan, not the car. You swap the rate and the calendar. A longer calendar can cost more even when each month looks cheaper.",
    "quant-tvm": "A dollar today is a seed and a dollar next year is the flower. You do not add seeds and flowers as if they were the same object.",
    "quant-ev": "Expected value is the average of many spins of a wheel, not the one spin you are about to take. A pleasant average can still hide a spin that empties your pocket.",
    "unmatched": "This is a menu, not a guess. Pick a dish that is on the card instead of asking the kitchen to invent one.",
}

_CLOSING: dict[str, tuple[str, str]] = {
    "pf-cashflow": (
        "If more money leaves than arrives, the gap comes from savings or from new borrowing.",
        "Write down one month of pay and one month of spending before you change a loan or a card.",
    ),
    "pf-budget": (
        "A plan that does not add up to your pay will fail in the first week, even if the percentages look tidy.",
        "Assign savings and the expensive debt before wants, and keep the shares adding up to your take-home pay.",
    ),
    "pf-emergency": (
        "Cash set aside for a shock keeps a repair or a missed paycheck from becoming high-interest debt.",
        "Name one month of necessary bills as a starter target, then put extra money on any debt that costs far more than your savings earn.",
    ),
    "bank-accounts": (
        "The balance you can safely spend is the available balance, and savings is where cash waits.",
        "Check the available balance before a card purchase, and keep emergency cash in savings rather than in the stock market.",
    ),
    "bank-apy": (
        "The same annual percentage yield grows a deposit the same way over a year. A loan's annual percentage rate is a cost, not a yield.",
        "Compare savings accounts by the annual percentage yield, and do not treat that number as the rate on a loan.",
    ),
    "credit-score": (
        "Paying on time moves the score more than a raise does, because the score never sees your wages.",
        "Make the payments you already owe before you apply for a new loan.",
    ),
    "credit-utilization": (
        "A high statement balance can show a full glass even when you pay the card off a few weeks later.",
        "If you have the cash, pay the card down before the statement date and still pay whatever remains by the due date.",
    ),
    "amort-payment": (
        "Early payments are mostly interest because the balance they are charged on is still large.",
        "Look at one statement and separate the interest dollars from the principal dollars before you decide to refinance or to pay extra.",
    ),
    "amort-extra": (
        "Money posted to principal shortens the loan and cuts later interest. A pushed-out due date does not do that by itself.",
        "Ask the servicer to apply any extra dollars to principal, then check that the principal balance actually fell.",
    ),
    "inv-return": (
        "A dollar gain is not a return until you divide it by the money you put in, and inflation can erase a small gain.",
        "Write the gain as a percent of what you invested before you compare it with a savings yield.",
    ),
    "inv-risk": (
        "A higher average comes with a wider range, including losses. The average is not a promise for this year.",
        "Decide whether you can live with the bad case before you chase the average.",
    ),
    "stock-price": (
        "You are not owed the last price. Your result is the price change plus any dividend, after it happens.",
        "Measure a holding with the holding-period return. Do not treat a lesson as a forecast.",
    ),
    "stock-diversify": (
        "A mix shrinks the damage from one company failing. It does not stop a drop that hits the whole market.",
        "If one company is most of the account, look at spreading it before you add more of the same name.",
    ),
    "cd-ladder": (
        "The locked rate protects you if new rates fall and frustrates you if new rates rise. Breaking it early can cost a penalty.",
        "Only put money in a certificate of deposit if you can leave it there until the maturity date.",
    ),
    "ira-types": (
        "The account changes when tax is paid. It does not choose the investment, and it does not guarantee a return.",
        "Pick the investment inside the account separately from the Traditional or Roth sticker, and check the current legal limit before you contribute.",
    ),
    "mtg-payment": (
        "The loan payment reduces the balance. Tax and insurance escrow does not.",
        "Split the draft into principal, interest, and escrow before you compare it with another loan.",
    ),
    "mtg-equity": (
        "Equity falls when the home's value falls, even if every payment was on time. You can spend it only by selling or by borrowing.",
        "Treat equity as value, not as checking cash, until a sale or a new loan actually produces the money.",
    ),
    "auto-loan": (
        "This month's interest is the unpaid balance times one-twelfth of the annual percentage rate. The payoff to close the loan today can be a little higher than the balance on the screen.",
        "Use the payoff quote, not a guessed balance, before you talk about paying the loan off or trading the car.",
    ),
    "auto-equity": (
        "If the car is worth less than the balance, a trade or a total loss can leave a gap you still owe.",
        "Compare the estimated market value with the payoff before you roll this car into another contract.",
    ),
    "lvb-structures": (
        "The residual is a lease's preset end value. A loan does not have one. The money factor is the lease's finance charge, not a savings yield.",
        "Read the residual and the money factor off the contract. If a field is blank, leave it blank.",
    ),
    "lvb-compare": (
        "A lower payment is cheaper only after you subtract what you own at the end and add fees and extra miles.",
        "Put both paths on the same number of months, then compare money out minus the value you keep.",
    ),
    "rate-fixed": (
        "A fixed loan stays put when market rates move. A variable payment can rise. A bond you hold can fall in price when yields rise.",
        "Check whether your rate can reset before you assume a news headline about rates changes your payment.",
    ),
    "rate-refi": (
        "The same months and a lower rate cut interest. Extra months can add interest back. A rate on a sheet is not an approval.",
        "Compare total interest and fees on the same months first. Talk to a person before you replace the contract.",
    ),
    "quant-tvm": (
        "Money later is not the same as money now, because today's money can earn a return in between.",
        "Put future amounts on a timeline before you add them to a bill that is due today.",
    ),
    "quant-ev": (
        "The average is what you would see over many repeats. You live through one outcome, including the bad one.",
        "Ask whether the bad case fits in your emergency cash before you act on the average.",
    ),
    "unmatched": (
        "There is no formula for a question this lesson set does not teach.",
        "Choose one of the listed questions so the numbers come from the calculator instead of a guess.",
    ),
}

_SYMBOLS: dict[str, list[str]] = {
    "amort-payment": [
        "P means the amount borrowed.",
        "APR means the annual percentage rate.",
        "r means the monthly rate, which is APR divided by 12.",
        "n means the number of months left.",
        "M means the fixed monthly payment.",
        "I means that month's interest.",
        "B means the balance still owed.",
    ],
    "amort-extra": [
        "M means the scheduled payment.",
        "X means extra money applied to principal.",
        "I means that month's interest.",
        "B means the balance still owed.",
    ],
    "bank-apy": [
        "i means the nominal annual rate, as a decimal.",
        "n means how many times a year interest is compounded.",
        "APY means the annual percentage yield, the effective yearly growth.",
        "B means the deposit balance.",
    ],
    "auto-loan": [
        "B means the unpaid balance.",
        "APR means the annual percentage rate.",
        "r means APR divided by 12.",
        "I means this month's interest, B times r.",
        "M means the monthly payment.",
    ],
    "lvb-structures": [
        "C means the capitalized cost, the amount the lease is based on.",
        "R means the residual, the preset end value.",
        "n means the number of months in the lease.",
        "f means the money factor.",
        "d means the depreciation portion of the payment.",
    ],
    "rate-refi": [
        "Q means today's payoff.",
        "r means the monthly rate on the contract you keep.",
        "r-prime means the monthly rate on the replacement contract.",
        "n means the number of months.",
        "M means the monthly payment.",
    ],
    "quant-tvm": [
        "PV means present value, what an amount is worth today.",
        "FV means future value, what an amount is worth later.",
        "r means the yearly rate, as a decimal.",
        "T means the number of years.",
    ],
    "quant-ev": [
        "p means the probability of an outcome.",
        "x means the dollar result of that outcome.",
        "E[X] means the expected value, the probability-weighted average.",
    ],
}


def _first_sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    parts = cleaned.split(". ")
    sentence = parts[0] if len(parts) > 1 else cleaned
    if not sentence.endswith((".", "!", "?")):
        sentence += "."
    return sentence


def _sentences(text: str) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    parts = [part.strip() for part in cleaned.split(". ") if part.strip()]
    sentences = []
    for part in parts:
        if not part.endswith((".", "!", "?")):
            part += "."
        sentences.append(part)
    return sentences


def _worked_lines(text: str) -> list[str]:
    lines = []
    for sentence in _sentences(text):
        if any(token in sentence for token in ("$", "=", "%", "×")):
            lines.append(sentence)
    return lines


def _spell(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    spelled: list[str] = []
    for text in parts:
        for acronym, expansion in _ACRONYMS:
            if acronym in seen or not text:
                continue
            pattern = re.compile(rf"\b{acronym}\b")
            if pattern.search(text):
                text = pattern.sub(expansion, text, count=1)
                seen.add(acronym)
        spelled.append(text)
    return spelled


def present_explanation(
    key: str,
    levels: dict[str, str],
    *,
    example: dict | None = None,
    number_source: str = "toy",
    go_deeper: bool = False,
    go_deeper_path: str = "",
    check_my_understanding: dict | None = None,
) -> dict:
    """Build the Section 6 sequence. `number_source` is `toy` or `yours`."""
    analogy = _ANALOGY.get(key) or _ANALOGY["unmatched"]
    means, nxt = _CLOSING.get(key) or _CLOSING["unmatched"]
    simple = levels.get("simple", "")
    learner = levels.get("learner", "")
    detailed = levels.get("detailed", "")
    if "not an offer" in detailed.lower() and "not an offer" not in nxt.lower():
        nxt = nxt.rstrip(".") + ". This explanation is educational. It is not an offer."

    if number_source == "yours":
        steps = _sentences(learner) + [line for line in _worked_lines(detailed) if line not in _sentences(learner)]
        worked = {
            "label": "your numbers",
            "disclaimer": "These figures come from your synthetic contract or tracker row. They are not a live offer.",
            "title": "Using your numbers",
            "steps": steps or _sentences(simple),
            "result": (steps[-1] if steps else _first_sentence(simple)),
        }
    elif example:
        worked = {
            "label": "toy numbers",
            "disclaimer": "These are toy numbers for practice. They are not your contract and not an offer.",
            "title": example.get("title", "Worked example"),
            "steps": list(example.get("steps") or []),
            "result": example.get("result", ""),
        }
    else:
        steps = _sentences(learner) or _sentences(simple)
        worked = {
            "label": "toy numbers",
            "disclaimer": "These are toy numbers for practice. They are not your contract and not an offer.",
            "title": "Worked example",
            "steps": steps,
            "result": steps[-1] if steps else "",
        }

    # Spell acronyms in reading order, once each, before the reader hits a bare abbreviation.
    one_sentence, analogy, *step_slots, result, means, nxt = _spell(
        [_first_sentence(simple), analogy, *worked["steps"], worked["result"], means, nxt]
    )
    step_count = len(worked["steps"])
    worked["steps"] = step_slots[:step_count]
    worked["result"] = result

    payload = {
        "sequence": [
            "one_sentence",
            "analogy",
            "worked_example",
            "what_this_means_for_you",
            "safe_next_step",
            "go_deeper",
            "check_my_understanding",
        ],
        "one_sentence": one_sentence,
        "analogy": analogy,
        "worked_example": worked,
        "what_this_means_for_you": means,
        "safe_next_step": nxt,
        "go_deeper": {
            "control": "go_deeper",
            "expanded": go_deeper,
            "path": go_deeper_path,
        },
    }
    if go_deeper:
        payload["go_deeper"]["symbols"] = _SYMBOLS.get(
            key,
            ["Each letter below is defined in the sentence that uses it."],
        )
        payload["go_deeper"]["detail"] = detailed
    if check_my_understanding is not None:
        payload["check_my_understanding"] = {
            "control": "check_my_understanding",
            **check_my_understanding,
        }
    return payload
