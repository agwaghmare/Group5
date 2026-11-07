# Toyota "Smartest Next Move" Data Pack (UTD Hackathon)

**Challenge prompt:** *Given my situation today, what's the smartest next move for me and my Toyota?*

Everything here is **synthetic**. No real customers, rates, or Toyota Financial Services pricing. Rates, fees, and loyalty rules are made-up for the hackathon and are marked as assumptions.

## What's inside

| File | What it is |
|---|---|
| `data/customers.csv` | 20 simulated DFW customers: income, credit tier then and now, debt load, autopay, digital habits, preferred channel, consent, vulnerable flag, stress score |
| `data/vehicles.csv` | One Toyota each: model, mileage, estimated market value, Toyota Care and warranty dates, service due, open recall |
| `data/accounts.csv` | 15 loans and 5 leases (APR or money factor, payment, balance, months left, residual, estimated equity, missed payments) |
| `data/situations.csv` | Each customer's "today" in their own words plus a one-line context summary |
| `data/option_scenarios.csv` | 142 precomputed options (keep, refinance, extend, extra payment, deferral, trade-in, lease return, buyout, renewal, service) with new payment, cost vs. keeping as is, eligibility, plain-language summary, assumption, and trade-off |
| `data/offers_catalog.csv` | 14 offers with eligibility rules, next-step type (self-service, follow-up, offer), and business value |
| `data/rate_sheet.csv` | Synthetic APRs by credit tier and term |
| `data/value_drivers.csv` | Dollar assumptions for revenue, retention, and cost-to-serve |
| `data/golden_answers.csv` | A reference "best next move" per customer for judging, with plain-language message, why not the others, guardrails, and expected value |
| `customer_profiles.json` | All of the above joined per customer, ready to feed an LLM or app |
| `toyota_next_move_data_pack.xlsx` | Same tables as one workbook |
| `starter_system_prompt.txt` | A starting prompt with responsible-AI rules |

## How it maps to the challenge

- **Personalize:** 20 profiles across life moments: new grad, hardship, lease end, relocation, baby on the way, negative equity, retiree, rideshare driver, EV decision.
- **Simplify:** every option has a `plain_language_summary`, `key_assumption`, and `tradeoff`.
- **Guide:** every golden answer ends in one of three `next_step_type` values: **Self-service**, **Follow-up**, or **Offer**.
- **Value:** `value_drivers.csv` and `golden_answers.csv` (`expected_value_usd` = value if completed x assumed take rate) show relationship, revenue, and service-effort effects.
- **Expectation:** build a working prototype on this data (chat, dashboard, app), use AI responsibly, and show a reimagined customer experience with real business value.

## Quick data notes

- Today in the dataset is **2026-11-07**.
- Loan payments use standard amortization. Lease payments use depreciation + rent charge (money factor); taxes and registration are excluded.
- For leases, `payoff_quote` is residual plus remaining payments (a rough lease-end obligation), `est_equity` = market value minus (residual + $350 buyout fee).
- `financial_stress_score` (0-100) blends payment-to-income, missed payments, no autopay, and vulnerable flag. It is a demo signal, not a real credit model.
- Refinance eligibility rules: 12+ months left, balance of $8,000+, no missed payments in 12 months, LTV <= 125%, and a rate drop of at least 1.0 point.

## Suggested test cases

| Customer | Tests whether the app... |
|---|---|
| C001, C008 | finds a refinance and explains savings |
| C002, C014 | switches to a human and does not upsell |
| C003, C006, C017 | compares lease buyout, return, and renewal |
| C012, C016 | is honest about negative equity or "no offer" |
| C009 | leads with safety (recall) |
| C018 | picks the simple self-service fix |
| C005, C020 | avoids pushing a product when waiting is best |
| C011 | respects the phone-only, no-marketing customer |

## Responsible AI checklist for teams

1. Numbers come from the data (no invented rates or payments).
2. Assumptions and estimates are stated plainly.
3. Vulnerable or distressed customers get a person, not a pitch.
4. Marketing consent is respected.
5. Trade-offs are shown (lower payment now vs. more interest later).
6. A clear "no eligible offer" answer is allowed.
7. No real personal data is used or stored.
