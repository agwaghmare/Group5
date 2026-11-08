"""Lessons, quizzes, scenarios, and the knowledge-map graph.

Every lesson explanation has three levels: simple, learner, and detailed.
Numerical examples are specs rendered by app.examples so the arithmetic stays
tied to the formulas in app.finance_math.
"""

from __future__ import annotations

from app.finance_math import amortize, money, payment

TOPICS: list[dict] = [
    {"id": "personal_finance", "title": "Personal finance", "summary": "Cash flow, budgets, and a cash buffer."},
    {"id": "banking", "title": "Banking", "summary": "Checking, savings, and how quoted yields work."},
    {"id": "credit", "title": "Credit", "summary": "Scores, utilization, and why payment history matters."},
    {"id": "loan_amortization", "title": "Loan amortization", "summary": "How a fixed payment splits into interest and principal."},
    {"id": "investments", "title": "Investments", "summary": "Return, risk, and what a result actually measures."},
    {"id": "stock_markets", "title": "Stock markets", "summary": "Prices, dividends, and diversification."},
    {"id": "cds_iras", "title": "CDs and IRAs", "summary": "Locked-in yields and tax-advantaged retirement accounts."},
    {"id": "mortgages", "title": "Mortgages", "summary": "Home loans, equity, and long amortization."},
    {"id": "automotive_finance", "title": "Automotive finance", "summary": "Auto loans, payoff, and vehicle value."},
    {"id": "lease_vs_buy", "title": "Lease versus buy", "summary": "Residual value, money factor, and what you own at the end."},
    {"id": "interest_rate_risk", "title": "Interest-rate risk", "summary": "What happens to payments and bond prices when rates move."},
    {"id": "quant_fundamentals", "title": "Quantitative finance fundamentals", "summary": "Time value of money, expected value, and spread of outcomes."},
]


def _levels(simple: str, learner: str, detailed: str) -> dict[str, str]:
    return {"simple": simple, "learner": learner, "detailed": detailed}


def _quiz(qid: str, prompt: str, choices: list[str], answer: int, simple: str, learner: str, detailed: str) -> dict:
    return {
        "id": qid,
        "prompt": prompt,
        "choices": choices,
        "answer_index": answer,
        "explanation": _levels(simple, learner, detailed),
    }


_PMT_18K = round(payment(18000, 6.0, 48), 2)
_LOAN_18K = amortize(18000, 6.0, 48)


LESSONS: list[dict] = [
    {
        "id": "pf-cashflow",
        "topic_id": "personal_finance",
        "title": "Cash flow is what is left",
        "minutes": 4,
        "summary": "Income minus spending is the only money you can save or use to pay debt faster.",
        "prerequisites": [],
        "explanation": _levels(
            "Cash flow is money in minus money out. If more comes in than goes out, you can save or pay debt. If more goes out, the gap comes from savings or new borrowing.",
            "Monthly cash flow = take-home income − spending and debt payments. A positive number is surplus. A negative number means the account falls unless you transfer savings in or borrow. Tracking a month of actual transactions beats a guessed budget, because the surplus is a measured remainder, not a hope.",
            "Let I be after-tax income and S the sum of outflows over the same period. Net cash flow C = I − S. Over months t = 1…T, ending cash ≈ starting cash + Σ C_t, ignoring transfers between your own accounts (those move cash, they do not create it). A debt payment is an outflow; the principal portion also reduces a liability, which is why cash flow and net worth can move differently in the same month.",
        ),
        "example": {"title": "One month of cash flow", "kind": "budget", "income": 4200, "needs": 2300, "wants": 700, "savings": 500},
        "quiz": [
            _quiz(
                "q1",
                "Your take-home pay is $4,000 and your spending plus debt payments are $3,600. What is your cash flow?",
                ["$400 surplus", "$400 shortfall", "$7,600 surplus", "$0, because debt payments do not count"],
                0,
                "You have $400 left. That is a surplus.",
                "Cash flow = 4000 − 3600 = 400. Debt payments are outflows, so they are already inside the $3,600.",
                "C = I − S = 4000 − 3600 = 400. The principal part of a debt payment still leaves the cash account; it reduces a liability at the same time.",
            ),
            _quiz(
                "q2",
                "Which event creates cash flow, rather than only moving your own money?",
                ["Transferring $200 from savings to checking", "Receiving a paycheck", "Moving a card balance to another card you already have", "Looking at your balance"],
                1,
                "A paycheck is new money in. A transfer between your accounts is not.",
                "Transfers change where cash sits. Income increases cash. Moving a balance between cards you own does not pay the debt off.",
                "A transfer is a pair of entries that sum to zero across your accounts. Income is an external inflow, so it increases Σ cash.",
            ),
        ],
    },
    {
        "id": "pf-budget",
        "topic_id": "personal_finance",
        "title": "A budget assigns the cash",
        "minutes": 5,
        "summary": "A budget is a plan that gives every dollar a job before the month spends it for you.",
        "prerequisites": ["pf-cashflow"],
        "explanation": _levels(
            "A budget decides ahead of time how much goes to needs, wants, and savings. It is a plan, not a punishment.",
            "One starting map is 50/30/20 of take-home pay: about 50% needs (housing, food, insurance, minimum debt payments), 30% wants, 20% savings and extra debt payments. If rent already uses more than half, the map will not fit. Shrink wants first, then negotiate needs. The useful test is whether the plan's total equals take-home pay, so nothing is left unassigned.",
            "Let income be I. Choose shares n, w, s with n + w + s = 1. Planned amounts are nI, wI, sI. Actual variance for a category is (actual − plan) / plan. A budget is feasible when planned needs ≤ I and sI is at least the emergency-fund or debt goal for that month. 50/30/20 is one feasible point, not an optimum. Someone paying 15% interest on a card may rationally set s higher and w lower until that balance is gone.",
        ),
        "example": {"title": "Assigning $4,200 of take-home pay", "kind": "budget", "income": 4200, "needs": 2300, "wants": 900, "savings": 840},
        "quiz": [
            _quiz(
                "q1",
                "Why assign savings in the budget instead of saving 'whatever is left'?",
                ["Because leftover cash is usually already spent by the end of the month", "Because banks require a budget", "Because wants must be 30%", "Because needs are optional"],
                0,
                "If savings is the leftover, spending tends to use it up.",
                "Unassigned money has no job, so ordinary wants absorb it. Paying savings first makes the surplus real.",
                "If savings is defined as the residual max(0, I − needs − wants), wants expand until the residual is near zero. Setting sI as a planned outflow reverses that order.",
            ),
            _quiz(
                "q2",
                "Needs already take 60% of pay. What is the honest next step?",
                ["Ignore the 50% idea and rewrite the plan so the shares still sum to 100%", "Force needs down to 50% on paper", "Stop tracking", "Put wants at 30% anyway"],
                0,
                "Change the plan so it matches real bills. The 50% figure is only a starting idea.",
                "A budget that does not add up will fail immediately. Fit wants and savings around the needs you actually have, and look for needs you can lower over time.",
                "Feasibility requires the category amounts to sum to I. Forcing a textbook share that violates the rent bill creates a plan with a hidden deficit.",
            ),
        ],
    },
    {
        "id": "pf-emergency",
        "topic_id": "personal_finance",
        "title": "An emergency fund is a shock absorber",
        "minutes": 4,
        "summary": "Cash set aside for a job loss or a repair keeps you from borrowing at a high rate.",
        "prerequisites": ["pf-budget"],
        "explanation": _levels(
            "An emergency fund is cash you do not spend on ordinary wants, so a surprise bill does not become credit-card debt.",
            "A common target is 3 to 6 months of necessary bills, held in a savings account you can reach in a day or two. If a credit card charges a very high APR, some people keep a smaller cash starter (about one month of bills) and put extra money on that card, then finish the full cash fund. The fund is for income shocks and urgent repairs, not for planned vacations.",
            "Let E be monthly essential spending and m the number of months you want to cover. Target cash B* = mE. While a card balance D carries monthly rate r_c and savings earns r_s < r_c, every dollar moved to the card saves about r_c − r_s per month, but it also lowers liquid cash. A practical rule used in this curriculum: build a starter B0 ≈ E, then direct surplus to any debt with APR well above the savings yield, then resume funding until B ≥ 3E or 6E depending on how stable pay is.",
        ),
        "example": {"title": "Three months of needs", "kind": "budget", "income": 4200, "needs": 2300, "wants": 0, "savings": 6900},
        "quiz": [
            _quiz(
                "q1",
                "Which use matches an emergency fund?",
                ["A surprise car repair that keeps you from getting to work", "A planned holiday flight", "A new phone because the old one is boring", "Investing it all in one stock the same day"],
                0,
                "A repair you did not plan for is the kind of shock the cash is for.",
                "Planned wants belong in the budget. The fund is for sudden necessary costs or a gap in pay.",
                "An emergency drawdown is an unplanned essential outflow. A vacation is a scheduled want and should be a sinking fund, a separate savings goal.",
            ),
            _quiz(
                "q2",
                "Savings earns 4% and a card charges 22%. Where does the next dollar reduce cost the most, after a small cash starter exists?",
                ["The credit card", "More savings", "A new subscription", "It makes no difference"],
                0,
                "The card costs much more than the savings account earns.",
                "Paying the card avoids about 22% interest. The savings account only earns about 4%. After a small cash buffer, the card is the expensive one.",
                "The spread is r_c − r_s ≈ 0.18 per year on that dollar. Liquidity has value, which is why a starter cash balance comes first, but once it exists the high APR dominates.",
            ),
        ],
    },
    {
        "id": "bank-accounts",
        "topic_id": "banking",
        "title": "Checking holds spending. Savings holds a yield.",
        "minutes": 4,
        "summary": "Checking is for bills. Savings is for cash you want to keep and earn interest on.",
        "prerequisites": ["pf-cashflow"],
        "explanation": _levels(
            "Checking is the account bills leave from. Savings is where cash sits so it is harder to spend by accident and can earn interest.",
            "A checking balance can look larger than the amount you can safely spend, because pending card charges have not posted. Available balance is the safer 'what can I spend' number. Savings and high-yield savings accounts pay interest and are often limited in how you use them day to day. Deposit accounts at banks are eligible for FDIC insurance up to the legal limit per depositor, per bank, per ownership category. That protects the deposit if the bank fails. It does not stop you from spending the money.",
            "Available balance ≈ ledger balance − pending debits + pending credits the bank has chosen to make available. Interest credited on a savings balance B over a day is approximately B × (APY) / 365 when the APY is the effective annual yield and the bank accrues daily. Insurance coverage is a legal cap, not a property of the APY. Balances above the cap at one bank are not fully insured unless the ownership structure qualifies for additional coverage.",
        ),
        "example": {"title": "What a 4% savings APY does to $2,000", "kind": "apy", "nominal_apr": 3.93, "compounds": 365, "deposit": 2000},
        "quiz": [
            _quiz(
                "q1",
                "Which balance should you use before a debit card purchase?",
                ["Available balance", "The highest balance you remember from last month", "Your credit limit", "Your savings APY"],
                0,
                "Available balance already subtracts charges that are about to post.",
                "The ledger can still include money that pending purchases will take. Available balance is the cautious figure.",
                "Spending the ledger balance while pending debits are outstanding can overdraw the account when those debits post.",
            ),
            _quiz(
                "q2",
                "FDIC insurance on a bank deposit protects you from which event?",
                ["The bank fails", "You overspend", "The stock market falls", "Inflation"],
                0,
                "It protects insured deposits if the bank fails.",
                "Deposit insurance is about the bank, not about market losses or your own spending. Inflation can still shrink buying power.",
                "Insurance covers deposits up to the legal limit if the insured institution fails. It is not a hedge against CPI inflation or against investment losses outside the deposit.",
            ),
        ],
    },
    {
        "id": "bank-apy",
        "topic_id": "banking",
        "title": "APY includes compounding. APR often does not.",
        "minutes": 5,
        "summary": "APY is the effective yearly yield after compounding. A loan APR is the quoted yearly borrowing rate.",
        "prerequisites": ["bank-accounts"],
        "explanation": _levels(
            "APY tells you how much a deposit grows in a year after the bank compounds interest. A higher APY grows the same deposit more.",
            "A nominal rate (sometimes also called APR on a savings disclosure) is the rate before you count compounding. If the bank adds interest every month, those interest dollars start earning interest too. APY folds that effect into one yearly number, so two accounts with the same APY grow a deposit the same way over a year even if they compound on different schedules. APY is for deposits. A loan's APR is a cost to you, not a yield.",
            "If the nominal annual rate is i and interest compounds n times a year, APY = (1 + i/n)^n − 1. Daily compounding uses n = 365 (some banks use 365.25 or 360; the contract controls). A balance B becomes B × (1 + APY) after one year if no money is added or removed and the APY stays constant. The monthly additive version is not B × APY / 12 when you want the effective result; that ignores compounding within the year. On loans, the Truth in Lending APR is a disclosed annual borrowing cost and is not computed by this savings formula.",
        ),
        "example": {"title": "4.80% nominal, compounded monthly", "kind": "apy", "nominal_apr": 4.80, "compounds": 12, "deposit": 10000},
        "quiz": [
            _quiz(
                "q1",
                "Two savings accounts both advertise 4.50% APY. What can you say?",
                ["A deposit grows the same over a year if the APY stays in force and you add nothing", "The one that compounds daily always pays more", "APY is a loan rate", "They must have the same monthly fee"],
                0,
                "The same APY means the same one-year growth.",
                "APY already includes how often interest compounds. Matching APYs match the year of growth. Fees are a separate line.",
                "By definition both multiply a constant balance by 1.045 over the year. The nominal rates can differ if n differs, because APY = (1 + i/n)^n − 1 is what was equalized.",
            ),
            _quiz(
                "q2",
                "Which statement about a loan APR is right?",
                ["It is the quoted yearly borrowing rate, not the yield on your savings", "It is always higher than APY on the same loan by the compounding formula", "It includes your taxes", "It is the residual value"],
                0,
                "Loan APR is the price of borrowing.",
                "Do not mix it up with savings APY. Residual value is a lease term, and taxes are extra.",
                "The savings identity APY = (1 + i/n)^n − 1 does not define a closed-end loan's disclosed APR. Loan interest here is computed on the unpaid balance with monthly rate APR/12.",
            ),
        ],
    },
    {
        "id": "credit-score",
        "topic_id": "credit",
        "title": "A credit score compresses your history",
        "minutes": 5,
        "summary": "The score is a model of how you have borrowed and repaid. It is not your income.",
        "prerequisites": ["pf-budget"],
        "explanation": _levels(
            "A credit score is a number lenders use to estimate the chance a borrower pays them back. Paying on time helps. Missing payments hurts.",
            "Major scores look at payment history, how much of your limits you use, how long you have had credit, new applications, and the mix of loans and cards. Payment history is the largest piece in the well-known FICO weighting. The score is not your salary and it is not your net worth. A missed payment can stay on a report for years, so one late bill can raise the rate a lender offers even if your income is fine. Checking your own score is not the same as a lender pulling it for a new loan.",
            "Treat the score as a function s(H) of the credit file H, not of wages. In the classic FICO public weighting, payment history is about 35%, amounts owed about 30%, length of history about 15%, new credit about 10%, and mix about 10%. Those weights are a published summary of one family of models, not a formula you can invert. A 30-day delinquency is a binary event in H that later models still see. APR offers are then a second map from tier(s) and product term to a rate sheet. Income enters the lender's separate ability-to-pay check, often through a debt-to-income ratio.",
        ),
        "example": {"title": "Utilization is one input, not the whole score", "kind": "utilization", "balance": 1500, "limit": 5000},
        "quiz": [
            _quiz(
                "q1",
                "Which change helps a typical score the most over time?",
                ["Paying every account on time", "Closing your oldest card for tidiness", "Applying for five cards in a week", "Raising your income while payments stay late"],
                0,
                "On-time payments are the biggest habit the score rewards.",
                "Income is not the score. Closing an old card can shorten history, and many new applications add inquiries.",
                "Payment history has the largest published FICO weight. Income never enters s(H). Several hard inquiries land in the new-credit slice at once.",
            ),
            _quiz(
                "q2",
                "A missed auto payment matters because:",
                ["It can be reported and can raise the rate you are offered later", "It erases the principal you already paid", "It changes the car's residual by itself", "It increases your savings APY"],
                0,
                "A missed payment can show up on the credit file and make future borrowing more expensive.",
                "The dollars you already paid still reduced the balance. The new damage is the reported late status and any late fees in the contract.",
                "The event updates H and therefore s(H) and the tier on the rate sheet. It does not reverse prior principal credits, and it does not rewrite a lease residual.",
            ),
        ],
    },
    {
        "id": "credit-utilization",
        "topic_id": "credit",
        "title": "Utilization is how full the cards are",
        "minutes": 4,
        "summary": "Utilization = reported card balances divided by credit limits.",
        "prerequisites": ["credit-score"],
        "explanation": _levels(
            "Utilization is the share of your credit limits that you are using. Lower is usually better for a score.",
            "Add up the balances that will be reported, often the statement balances, and divide by the sum of the limits. A person with a $4,000 balance and a $5,000 limit is at 80%, which is high, even if they pay in full after the statement. Paying the card down before the statement can lower the number the score sees. Around 30% is a common guideline. It is not a cliff, and it is only one part of the score.",
            "Utilization U = Σ balances / Σ limits, using the balances the issuer reports. Overall U and per-card U can both matter depending on the model. U is dimensionless and usually falls when either the balance falls or a limit rises. A limit increase cuts U only if spending does not rise with it. Because amounts owed are roughly 30% of the classic FICO weighting, a jump in U can move s(H) even when every payment is on time. Interest is a separate equation: if you revolve a balance, interest ≈ average daily balance × APR/365.",
        ),
        "example": {"title": "A $1,800 balance on a $6,000 limit", "kind": "utilization", "balance": 1800, "limit": 6000},
        "quiz": [
            _quiz(
                "q1",
                "Balances are $3,000 and limits are $10,000. Utilization is:",
                ["30%", "70%", "3%", "$7,000"],
                0,
                "3,000 / 10,000 = 30%.",
                "Divide the balance by the limit. The unused amount is not the utilization.",
                "U = 3000/10000 = 0.30. Unused credit is 1 − U = 0.70, which is a different number.",
            ),
            _quiz(
                "q2",
                "You pay the statement in full every month but the statement balance is almost the whole limit. What can still happen?",
                ["The reported utilization can be high", "You are charged interest on a paid-in-full grace period", "Your APY falls", "The loan residual changes"],
                0,
                "The score may see the high statement balance even when you pay it off after.",
                "Utilization uses the reported balance. Interest can still be zero if you are inside the grace period. Those are different systems.",
                "Issuers typically report the statement balance, so U can be high for a transactor who later pays in full. Interest posts when a revolving balance breaks the grace period; that is the APR path, not the U path.",
            ),
        ],
    },
    {
        "id": "amort-payment",
        "topic_id": "loan_amortization",
        "title": "A fixed payment slowly retires the balance",
        "minutes": 6,
        "summary": "Each payment covers that month's interest first. Whatever is left reduces principal.",
        "prerequisites": ["credit-score"],
        "explanation": _levels(
            "The payment stays the same, but early on most of it is interest. Later, more of it pays down what you owe.",
            "Interest this month is the balance you still owe times the monthly rate. The monthly rate is the APR divided by 12. Your payment minus that interest is the principal you retire. Because the balance is largest at the start, the interest slice is largest at the start. The scheduled payment is sized so the balance hits zero at the last month if every payment is made on time and the rate stays fixed.",
            "Let P be the starting principal, annual APR the contract rate, r = APR/12, and n the number of months. The fully amortizing payment is M = P · r · (1+r)^n / ((1+r)^n − 1). For month t with balance B_{t−1}, interest I_t = B_{t−1} · r and principal Π_t = M − I_t, with B_t = B_{t−1} − Π_t. Total interest = nM − P. If r = 0, M = P/n and interest is zero. This curriculum compounds auto and mortgage loans monthly using r = APR/12, which matches a standard fixed installment contract.",
        ),
        "example": {"title": "$18,000 at 6% for 48 months", "kind": "loan", "principal": 18000, "apr": 6.0, "months": 48},
        "quiz": [
            _quiz(
                "q1",
                f"An $18,000 loan at 6% APR for 48 months has a scheduled payment closest to which amount?",
                [money(_PMT_18K), money(_PMT_18K + 80), money(_PMT_18K - 70), "$18,000"],
                0,
                f"The amortizing payment is {money(_PMT_18K)}.",
                f"M = P r (1+r)^n / ((1+r)^n − 1) with P = 18000, r = 0.06/12, n = 48, which equals {money(_PMT_18K)}.",
                f"r = 0.005, (1.005)^48 ≈ {((1.005) ** 48):.5f}, M = { _PMT_18K :.2f}. The other choices are not the annuity payment.",
            ),
            _quiz(
                "q2",
                "Why is the interest slice of the payment larger in month 1 than in a later month?",
                ["The balance it is charged on is larger at the start", "The APR rises every month on a fixed loan", "Principal is optional at the start", "Banks always take half"],
                0,
                "Interest is a percent of what you still owe, and you owe the most at the beginning.",
                "I_t = B_{t−1} × r. B falls as you pay principal, so I falls. On a fixed-rate loan r does not change.",
                "∂I/∂B = r > 0, so a higher opening balance produces a higher interest charge. Π_t = M − I_t therefore rises as B falls.",
            ),
        ],
    },
    {
        "id": "amort-extra",
        "topic_id": "loan_amortization",
        "title": "Extra principal shortens the loan",
        "minutes": 5,
        "summary": "Money above the scheduled payment, applied to principal, cuts interest and the number of months.",
        "prerequisites": ["amort-payment"],
        "explanation": _levels(
            "Paying extra principal means you owe less, so every later month charges less interest.",
            "The scheduled payment already covers this month's interest. Anything extra reduces principal immediately. You then pay the loan off in fewer months, and you never pay the interest those months would have charged. Direct the extra amount to principal. If the servicer uses it to 'pay ahead' a future bill instead, the balance may not fall the way you expect. A lower payment from stretching the term is a different choice and can raise total interest.",
            "Keep M fixed and add extra X applied entirely to principal. Then Π_t = M + X − I_t and the horizon becomes the smallest T such that B_T = 0, with T < n when X > 0 and the original loan was fully amortizing. Interest saved is (nM − P) − Σ I_t under the faster path. There is no closed form as tidy as M once X is constant, so the curriculum simulates month by month. Prepayment penalties, if the contract has them, are an extra cash cost and can offset the savings.",
        ),
        "example": {"title": "$50 extra on the $18,000 example", "kind": "loan", "principal": 18000, "apr": 6.0, "months": 48, "extra": 50},
        "quiz": [
            _quiz(
                "q1",
                "Extra principal does which of these, on a fixed-rate loan with no prepayment penalty?",
                ["Reduces total interest and the number of payments", "Increases the APR", "Increases residual value", "Moves the due date without touching the balance"],
                0,
                "You pay the balance off sooner and pay less interest.",
                "The rate stays the same. The balance falls faster, so later interest charges shrink. That is different from skipping a due date.",
                "X increases Π_t, which lowers B_t and therefore every later I = B r. The contractual APR is unchanged. Residual value is a lease input, not a result of a loan prepayment.",
            ),
            _quiz(
                "q2",
                "A servicer offers to 'pay your next bill early' with the extra money instead of posting it to principal. What should you check?",
                ["That the extra actually reduced today's principal balance", "Only that the APR fell", "That the residual rose", "Nothing; those are the same posting"],
                0,
                "You want the balance itself to drop, not only the next due date to move.",
                "A paid-ahead due date can leave the principal unchanged. Interest is computed on principal, so the posting rules matter.",
                "If the cash is held as a future installment rather than credited to B_t, then I_{t+1} = B_t r does not fall. Confirm the principal balance on the next statement.",
            ),
        ],
    },
    {
        "id": "inv-return",
        "topic_id": "investments",
        "title": "Return is profit divided by what you put in",
        "minutes": 5,
        "summary": "A return measures the gain relative to the money invested, not the dollar gain alone.",
        "prerequisites": ["bank-apy"],
        "explanation": _levels(
            "Return answers 'how much did this grow compared with what I invested?' A $10 gain on $100 is a much bigger return than a $10 gain on $10,000.",
            "Simple return = (ending value + cash you received − money you put in) / money you put in. A savings APY is a kind of return the bank promised. An investment return is usually not promised. Inflation matters: if prices rise 3% and the investment gained 3%, buying power did not increase. That real result is the one that pays for future spending.",
            "Simple return R = (V_1 − V_0 + D) / V_0 where D is distributions such as dividends or interest. Real return is approximately R − inflation, or more precisely (1 + R)/(1 + π) − 1. Multi-period simple returns compound: wealth relative = Π (1 + R_t). They do not add. Log returns r_t = ln(V_t / V_{t−1}) do add across time, which is why later quantitative work prefers them. Past R is a sample, not the next R.",
        ),
        "example": {"title": "A share plus a dividend", "kind": "stock", "start": 100, "end": 108, "dividend": 2},
        "quiz": [
            _quiz(
                "q1",
                "You invest $2,000 and later have $2,200 with no extra deposits. The simple return is:",
                ["10%", "200%", "$200", "2%"],
                0,
                "You gained $200 on $2,000, which is 10%.",
                "R = (2200 − 2000) / 2000 = 0.10. The dollar gain and the percent return are different units.",
                "R = ΔV / V_0 = 200/2000 = 0.10. Quoting only ΔV hides the capital base.",
            ),
            _quiz(
                "q2",
                "An investment gained 4% while inflation was 4%. Buying power:",
                ["Stayed about the same", "Doubled", "Fell by 4%", "Is measured by the APY formula only"],
                0,
                "The gain and the rise in prices canceled.",
                "Real change ≈ 4% − 4% = 0. You can buy about the same basket as before.",
                "Exact real return = (1.04/1.04) − 1 = 0. The subtraction shortcut matches here because the two rates are equal.",
            ),
        ],
    },
    {
        "id": "inv-risk",
        "topic_id": "investments",
        "title": "Risk is how wide the outcomes are",
        "minutes": 5,
        "summary": "A higher average return usually comes with a wider range of results, including losses.",
        "prerequisites": ["inv-return"],
        "explanation": _levels(
            "Risk means you might not get the result you expect. Safer places to hold cash have a narrower range. Stocks have a wider one.",
            "Expected return is the probability-weighted average outcome. It is not a promise that the average will show up this year. Standard deviation measures how far outcomes typically sit from that average. A bank deposit's range is very tight if you stay under the insurance limit. A single stock can go to zero. People get paid, on average and over long histories, for taking risks that they cannot diversify away. They are not paid for risks they could have canceled by holding a mix.",
            "For outcomes (p_i, x_i), E[X] = Σ p_i x_i and variance σ² = Σ p_i (x_i − E[X])². σ is the standard deviation. A mean-preserving spread increases σ and leaves E[X] unchanged; a risk-averse utility function u with u'' < 0 then has lower expected utility by Jensen's inequality. In a simple one-factor picture, total variance = systematic variance + idiosyncratic variance. Diversification drives the idiosyncratic term toward zero as independent risks are combined. It does not remove the systematic term.",
        ),
        "example": {
            "title": "A coin-flip investment",
            "kind": "expectation",
            "outcomes": [[0.5, 1000], [0.5, -200]],
        },
        "quiz": [
            _quiz(
                "q1",
                "A 50% chance of gaining $1,000 and a 50% chance of losing $200 has expected value:",
                ["$400", "$800", "$0", "$1,000"],
                0,
                "Half of 1000 plus half of −200 is 400.",
                "E[X] = 0.5×1000 + 0.5×(−200) = 500 − 100 = 400. You might still lose $200 this time.",
                "The expectation is the average over the probability distribution, not the better outcome and not the outcome you will observe in one draw.",
            ),
            _quiz(
                "q2",
                "Which risk can a broad mix of stocks reduce?",
                ["The risk that one company fails", "The risk that the whole market falls", "Inflation of the currency", "A change in the tax law that hits every account"],
                0,
                "One company's failure hurts less if you own many companies.",
                "That company-specific risk is idiosyncratic. A drop in the whole market is systematic and the mix still feels it.",
                "Idiosyncratic variance averages down across imperfectly correlated names. Market-factor variance remains. Inflation and a universal tax change are economy-wide too.",
            ),
        ],
    },
    {
        "id": "stock-price",
        "topic_id": "stock_markets",
        "title": "A stock price is today's trade",
        "minutes": 4,
        "summary": "The price is what buyers and sellers agreed at the last trade. Your return also includes dividends.",
        "prerequisites": ["inv-return"],
        "explanation": _levels(
            "A stock is a slice of a company. The price moves when people change what they will pay for that slice.",
            "You make money two ways: the price rises, or the company pays a dividend (cash sent to owners). A price drop is a loss only if you sell or if you are marking the account to today's price; the share is still a claim on the company. Prices can change fast because new information changes what buyers will pay. Nobody in this curriculum knows the next move, and a lesson should not pretend to.",
            "Holding-period return R = (P_1 − P_0 + D) / P_0. The dividend yield is D / P_0 and the capital gain is (P_1 − P_0) / P_0. Log price return ln(P_1/P_0) adds across periods: ln(P_T/P_0) = Σ ln(P_t/P_{t−1}). A quoted price is the marginal trade, not a promise of fundamental value. Discounting expected future dividends gives one model of value, P_0 = Σ E[D_t] / (1 + k)^t, where k is a required return. That model is sensitive to both the cash-flow guess and k.",
        ),
        "example": {"title": "Price up $8 and a $2 dividend on a $100 share", "kind": "stock", "start": 100, "end": 108, "dividend": 2},
        "quiz": [
            _quiz(
                "q1",
                "A share goes from $50 to $47 and pays a $1 dividend. The simple return is:",
                ["−4%", "−6%", "+2%", "−$2"],
                0,
                "You are down $3 on price and up $1 from the dividend, so down $2 on a $50 share, which is −4%.",
                "R = (47 + 1 − 50) / 50 = −2/50 = −0.04.",
                "Capital gain = −3/50 = −6%. Dividend yield = 1/50 = 2%. Sum = −4%. Dollar P&L and percent return are different objects.",
            ),
            _quiz(
                "q2",
                "Which claim is something this lesson will not do?",
                ["Predict next month's stock price", "Define holding-period return", "Separate the dividend from the price change", "Show a log return"],
                0,
                "The lesson explains how return is measured. It does not know the next price.",
                "A definition is not a forecast. Anyone selling a certain next price is going beyond the math.",
                "P_1 is random from today's information set. The identities for R and ln(P_1/P_0) hold after P_1 is observed; they do not identify P_1 in advance.",
            ),
        ],
    },
    {
        "id": "stock-diversify",
        "topic_id": "stock_markets",
        "title": "A mix beats a single bet",
        "minutes": 4,
        "summary": "Owning many companies reduces the damage if one of them fails. It does not remove market-wide declines.",
        "prerequisites": ["stock-price", "inv-risk"],
        "explanation": _levels(
            "If you own one company and it fails, you can lose that investment. If you own many, one failure is a smaller piece.",
            "An index fund holds a large list of companies in one purchase, which is an easy way to diversify. Diversification does not mean the account cannot fall. In a recession, most stocks can fall together. The point of the mix is to avoid having your result depend on one headquarters, one product, or one scandal. Concentration can win big and can also go to zero.",
            "Portfolio variance for two assets is w_1² σ_1² + w_2² σ_2² + 2 w_1 w_2 Cov_12. Covariance can be written ρ σ_1 σ_2. When ρ < 1, the portfolio standard deviation is below the weighted average of the two standard deviations, which is the diversification effect. As N independent, identical idiosyncratic risks are equal-weighted, idiosyncratic variance scales like 1/N. A common market factor with weight β_i remains: systematic variance does not scale like 1/N. Indexing is a low-cost way to hold a large N; the expense ratio is a certain drag on return.",
        ),
        "example": {
            "title": "One stock can dominate the outcome",
            "kind": "expectation",
            "outcomes": [[0.9, 500], [0.1, -5000]],
        },
        "quiz": [
            _quiz(
                "q1",
                "Diversification is most effective against:",
                ["One company doing badly for its own reasons", "A crash that hits almost every stock", "A fee that every fund charges", "Inflation"],
                0,
                "It spreads out company-specific trouble.",
                "A market-wide crash is the risk that is left after you diversify. Fees and inflation are not solved by owning more stocks.",
                "Idiosyncratic shocks average down with N. A common factor shock hits the β terms together, so portfolio variance stays positive as N grows.",
            ),
            _quiz(
                "q2",
                "Two stocks move perfectly together (correlation 1). Mixing them:",
                ["Does not reduce risk below a weighted average of their risks", "Eliminates the chance of loss", "Doubles the expected return for free", "Sets the price of both to the residual value"],
                0,
                "If they always move together, mixing does not cancel anything.",
                "Diversification needs imperfect correlation. Correlation of 1 means the mix behaves like one bet of a blended size.",
                "When ρ = 1, σ_p = w_1 σ_1 + w_2 σ_2. The variance identity then has no interior reduction. Expected return is still the weighted average, not double.",
            ),
        ],
    },
    {
        "id": "cd-ladder",
        "topic_id": "cds_iras",
        "title": "A CD locks a yield for a term",
        "minutes": 5,
        "summary": "A certificate of deposit pays a set yield if you leave the money until maturity. A ladder staggers those dates.",
        "prerequisites": ["bank-apy"],
        "explanation": _levels(
            "A CD is a bank deposit you agree not to touch until a date. In return, the rate is fixed. Taking it out early can cost a penalty.",
            "Because the rate is fixed, a CD protects you if new savings rates fall, and it frustrates you if new rates rise — you are stuck unless you pay the penalty. A ladder splits cash across CDs that mature at different times, for example 1, 2, and 3 years. Each time one matures you can spend it or buy a new CD at whatever rate is then offered. CDs at banks are deposits, so FDIC insurance applies up to the legal limit, unlike a stock.",
            "Value at maturity, with no deposits or withdrawals, is P × (1 + APY)^T where T is the term in years and APY is the effective annual yield in the contract. An early-withdrawal penalty of k months of interest changes the result to roughly P × (1 + APY)^{t} − penalty, and can even produce a loss of principal if you exit very quickly. Laddering with maturities T, 2T, … is a way to shorten the average time until cash is free (duration of the cash-flow schedule) while keeping some money in longer, higher quotes. Reinvestment rate risk remains on the rung that matures.",
        ),
        "example": {"title": "A 2-year CD at 4.5% APY", "kind": "cd", "principal": 5000, "apy": 4.5, "years": 2},
        "quiz": [
            _quiz(
                "q1",
                "What is the main trade for a higher CD rate?",
                ["You give up easy access until maturity", "You take stock-market losses", "The bank can change the rate every day", "You must lease a car"],
                0,
                "The money stays until the maturity date unless you pay a penalty.",
                "The rate is fixed, which is the point. This is still a deposit, not a stock. The cost of the fixed rate is illiquidity.",
                "The contract exchanges a locked yield for a restriction on withdrawal. Early exit is priced by the penalty schedule, not by a market price the way a bond is.",
            ),
            _quiz(
                "q2",
                "Why build a ladder instead of one long CD?",
                ["Some cash matures sooner, so you are not waiting on a single date", "It removes the early-withdrawal penalty on every rung", "It guarantees rates will rise", "It is the same as a Roth IRA"],
                0,
                "Pieces come due at different times.",
                "Each rung can still have a penalty if you break it early. The ladder only schedules the maturity dates. It does not predict rates, and it is not a retirement-account type.",
                "The ladder's maturity profile is a set of dates rather than one date, which lowers the waiting time for the first dollar of principal. Each instrument still has its own penalty if broken.",
            ),
        ],
    },
    {
        "id": "ira-types",
        "topic_id": "cds_iras",
        "title": "IRAs change when the tax is paid",
        "minutes": 5,
        "summary": "Traditional and Roth IRAs are account types. The investments inside them can be cash, funds, or other allowed holdings.",
        "prerequisites": ["cd-ladder", "inv-return"],
        "explanation": _levels(
            "An IRA is a retirement account with tax rules. Traditional often gives a tax break now and taxes withdrawals later. Roth taxes the money now and qualified withdrawals later are tax-free.",
            "The account is a wrapper. You still choose what it holds: a CD, a fund, a stock. The wrapper does not make a risky investment safe. Contribution limits exist and change; this lesson uses an example amount and does not quote a legal cap, because the IRS figure is year-specific and income can phase it out. Taking money out early can trigger tax and a penalty. The curriculum will not guess whether Traditional or Roth is better for you — that depends on your tax rate now versus later.",
            "Let c be the annual contribution, r the annual return, T the years, and t0, tT the tax rates now and in retirement. Ignoring limits and penalties, a deductible Traditional contribution grows as a pre-tax annuity FV = c ((1+r)^T − 1) / r and is then taxed, leaving (1 − tT) FV. A Roth contribution is made from after-tax income, so the invested amount is c(1 − t0) if c was the pre-tax equivalent, and the qualified ending balance is not taxed again. The two match when t0 = tT and the same r applies. If you expect tT > t0, Roth's tax-free exit is more valuable, and the reverse favors the deduction. Early-withdrawal penalties are an additional haircut not in this identity.",
        ),
        "example": {"title": "$6,000 a year for 20 years at 6%", "kind": "ira", "annual_contribution": 6000, "annual_return": 6, "years": 20},
        "quiz": [
            _quiz(
                "q1",
                "What does the IRA wrapper itself do?",
                ["Changes the tax timing of allowed contributions and withdrawals", "Guarantees a 6% return", "Insures stocks the way the FDIC insures deposits", "Sets the residual on a lease"],
                0,
                "It changes the tax rules. It does not pick the investment's return.",
                "A stock inside a Roth can still fall. FDIC insurance applies only if the holding is an insured deposit, not because the account is an IRA.",
                "The wrapper applies t0 and tT. The path of r is a property of the assets held inside, and deposit insurance is a property of a bank deposit, not of the IRA statute.",
            ),
            _quiz(
                "q2",
                "Traditional and Roth ending wealth match in the simple model when:",
                ["The tax rate now equals the tax rate at withdrawal, and the return is the same", "You hold only CDs", "You are under 30", "Inflation is zero"],
                0,
                "If the tax rate does not change, the simple math ties.",
                "You either pay tax before the money goes in or when it comes out. The same rate on both ends ties the results. Age and inflation are separate.",
                "With equal rates t, (1 − t) times a Roth-style after-tax contribution path equals taxing a Traditional FV by (1 − t) at the end, given identical r and timing. The identity breaks when t0 ≠ tT.",
            ),
        ],
    },
    {
        "id": "mtg-payment",
        "topic_id": "mortgages",
        "title": "A mortgage is a long amortizing loan",
        "minutes": 5,
        "summary": "The same payment formula used on an auto loan runs for many more months and is secured by the house.",
        "prerequisites": ["amort-payment"],
        "explanation": _levels(
            "A mortgage payment covers interest and principal on a home loan. The house is the collateral.",
            "Most fixed mortgages in the U.S. use the same amortizing payment as a car loan, just with a bigger balance and a longer term, often 15 or 30 years. The monthly rate is still APR/12. A quoted housing payment may also collect taxes and insurance into escrow. Those escrow dollars are not interest and do not reduce the loan balance. Missing payments can put the home at risk because the lender has a lien.",
            "M = P r (1+r)^n / ((1+r)^n − 1) with r = APR/12 and n = 180 or 360 for 15- and 30-year fixed loans. Interest and principal split exactly as in the auto lesson: I_t = B_{t−1} r, Π_t = M − I_t. Escrow E is added to the cash payment but is not part of M; the contractual amortization uses M only. On a 30-year loan, I_1 is close to M because n is large and B is large, so principal builds slowly at first. Total interest nM − P is therefore much larger than on a short auto term.",
        ),
        "example": {"title": "$320,000 at 6.5% for 30 years", "kind": "loan", "principal": 320000, "apr": 6.5, "months": 360},
        "quiz": [
            _quiz(
                "q1",
                "Escrow for taxes and insurance inside the monthly draft:",
                ["Does not reduce the loan principal", "Is the same thing as interest", "Is the residual", "Raises the home's market value one-for-one"],
                0,
                "Escrow pays bills. It is not principal.",
                "Only the principal slice of the loan payment reduces the balance. Tax and insurance are costs of owning the home.",
                "The amortizing identity uses M, not M + E. E is a pass-through for third-party bills. B_t = B_{t−1} − (M − I_t).",
            ),
            _quiz(
                "q2",
                "Compared with a 5-year auto loan, a 30-year mortgage of similar rate usually:",
                ["Pays much more total interest because the balance stays outstanding longer", "Has no interest in the early months", "Uses a different monthly-rate definition, APR/365", "Cannot be amortized"],
                0,
                "The balance is large for a long time, so interest adds up.",
                "The monthly rate is still APR/12. Early mortgage payments are mostly interest, which is the same mechanism as a car loan stretched out.",
                "Total interest = nM − P grows with n even after M is recalculated, because the average outstanding balance stays high. r = APR/12 in both products in this curriculum.",
            ),
        ],
    },
    {
        "id": "mtg-equity",
        "topic_id": "mortgages",
        "title": "Home equity is value minus the loan",
        "minutes": 4,
        "summary": "Equity is the part of the home's value you would have left after paying off the mortgage. It is not cash in the checking account.",
        "prerequisites": ["mtg-payment"],
        "explanation": _levels(
            "Equity = what the home is worth minus what you still owe. You can spend it only by selling or by borrowing against it.",
            "If a home is worth $400,000 and the mortgage balance is $250,000, equity is $150,000. If prices fall, equity falls even if you paid every bill. A refinance or a home-equity loan turns equity into cash only by taking a new loan, which has its own rate, fees, and payment. Selling turns equity into cash after costs such as commissions, but then you no longer own the home.",
            "Equity E = V − B, where V is a market estimate and B is the payoff used to clear the lien. A price move ΔV changes E one-for-one. Principal paydown ΔB changes E by −ΔB (paying the balance down raises equity). A new cash-out loan increases B and decreases E by the amount cashed out, before fees. Loan-to-value LTV = B / V = 1 − E/V. Lenders often cap LTV, so the equity you can borrow is less than E. Transaction costs mean cash at sale ≈ E − costs, not E.",
        ),
        "example": {"title": "How slow principal is early on a long mortgage", "kind": "loan", "principal": 320000, "apr": 6.5, "months": 360},
        "quiz": [
            _quiz(
                "q1",
                "Home value $400,000, mortgage balance $250,000. Equity is:",
                ["$150,000", "$650,000", "$250,000", "$400,000"],
                0,
                "400,000 minus 250,000 is 150,000.",
                "Equity is value minus debt. Adding them would double-count the house.",
                "E = V − B = 150000. LTV = 250/400 = 62.5%.",
            ),
            _quiz(
                "q2",
                "Home prices in your area fall 10% and you made every payment. Equity:",
                ["Falls, because value fell", "Rises automatically", "Is unchanged because payments were on time", "Becomes the residual value"],
                0,
                "The house is worth less, so your slice is worth less.",
                "On-time payments still reduced the balance a little, but a 10% price drop on the whole house is usually much larger than one month of principal.",
                "ΔE ≈ ΔV − ΔB. ΔV = −0.10 V is an immediate mark. ΔB over one month is only Π_t, which is small early in a 30-year loan.",
            ),
        ],
    },
    {
        "id": "auto-loan",
        "topic_id": "automotive_finance",
        "title": "An auto loan finances a depreciating asset",
        "minutes": 6,
        "summary": "You borrow the amount financed and pay it down with an amortizing payment. The car's value follows its own path.",
        "prerequisites": ["amort-payment"],
        "explanation": _levels(
            "An auto loan is a fixed set of payments on the amount you financed. The car is collateral. The APR is the yearly rate used to compute each month's interest.",
            "Amount financed is not always the sticker price. It can include taxes, fees, and any negative equity rolled in from a previous car, minus your down payment and rebates. Interest this month is the unpaid balance times APR/12. A payoff quote is what the lender will accept to close the loan today. It can be a bit higher than the balance on the statement because interest has accrued since the last payment.",
            "Amount financed P = vehicle price + tax + fees + rolled negative equity − down payment − rebates. Then M and the split (I_t, Π_t) follow the amortization lesson with the contract APR. Payoff at a date between due dates is approximately B plus accrued interest B · r · (days/30), plus any contractual fee. The formula explains why the payoff can exceed the current balance shown on a statement.",
        ),
        "example": {"title": "A $24,000 balance at 7.9% with 48 months left", "kind": "loan", "principal": 24000, "apr": 7.9, "months": 48},
        "quiz": [
            _quiz(
                "q1",
                "Which inputs can make amount financed larger than the car's price?",
                ["Taxes, fees, and negative equity from a prior car, if they were rolled in", "A bigger down payment", "A lower APR", "A higher residual"],
                0,
                "Rolled-in costs and a prior balance you still owe can be added to the loan.",
                "A down payment reduces the amount financed. APR changes the payment, not the starting principal. Residual belongs to leases.",
                "P increases with add-ons and rolled B_prior, and decreases with cash down. APR enters M, not P. Residual is a lease contract term.",
            ),
            _quiz(
                "q2",
                "A payoff quote is slightly above the balance on the app. Why can that happen?",
                ["Interest has built up since the last payment, and a fee may apply", "The residual increased", "Depreciation reversed", "APY was applied to the loan"],
                0,
                "You owe the balance plus interest for the days since the last payment.",
                "The statement balance is often as of the last posting. Closing the loan today settles interest through the payoff date.",
                "Accrued interest ≈ B · (APR/12) · (days since payment / 30), plus any contractual payoff fee. That sum is the payoff, not a new APR.",
            ),
        ],
    },
    {
        "id": "auto-equity",
        "topic_id": "automotive_finance",
        "title": "Vehicle equity compares value with what you owe",
        "minutes": 5,
        "summary": "Equity is the car's market value minus the loan balance. If that number is negative, you are upside down.",
        "prerequisites": ["auto-loan"],
        "explanation": _levels(
            "If the car is worth more than you owe, you have equity. If you owe more than it is worth, you have negative equity.",
            "Cars usually depreciate: the market value falls as they age and gain miles, fastest in the early years. A small down payment and a long term can leave the balance above the value for a while. That gap matters if you want to trade in or if the car is totaled. Insurance that only covers market value would not cover a bigger loan payoff unless you bought extra coverage for that gap. Vehicle equity for a loan is market value minus current balance. A dealer trade uses the payoff, which can be a little higher.",
            "Equity versus the statement balance is E_bal = V − B. Equity versus getting out today is E_pay = V − payoff. The pack reports est_equity = E_bal. Negative equity E < 0 rolled into the next contract raises the next amount financed, so the new loan starts underwater by that amount before any new depreciation. Depreciation over a holding period is V_0 − V_t (using the purchase price as V_0). It is a change in the asset, while principal paydown is a change in the liability. Equity rises when paydown outruns depreciation.",
        ),
        "example": {"title": "A $31,500 vehicle now worth $22,700", "kind": "depreciation", "price": 31500, "market": 22700, "months_owned": 29},
        "quiz": [
            _quiz(
                "q1",
                "Market value is $18,000 and the loan balance is $20,000. Equity is:",
                ["−$2,000", "$2,000", "$38,000", "$20,000"],
                0,
                "The car is worth $2,000 less than the balance. That is negative equity.",
                "E = 18000 − 20000 = −2000. You would need about $2,000 more than the car brings in order to clear the balance.",
                "E_bal = V − B = −2000. Clearing the loan from a sale at V requires a cash contribution of −E, before fees.",
            ),
            _quiz(
                "q2",
                "Equity on a car rises during a month when:",
                ["Principal you paid exceeds the drop in market value", "The APR is quoted as an APY", "You miss a payment", "The term is extended and no extra cash is paid"],
                0,
                "You need the debt to fall faster than the car's value.",
                "Depreciation lowers value. Principal payments lower the balance. Equity is the race between those two. Extending the term usually slows principal.",
                "ΔE ≈ −ΔV_depreciation − ΔB. Principal paydown makes ΔB negative, so −ΔB is positive. Equity rises when −ΔB > depreciation.",
            ),
        ],
    },
    {
        "id": "lvb-structures",
        "topic_id": "lease_vs_buy",
        "title": "A lease pays for use. A loan pays for ownership.",
        "minutes": 6,
        "summary": "Lease payments cover depreciation plus a rent charge. The residual is the preset end value. A loan leaves you the car.",
        "prerequisites": ["auto-loan"],
        "explanation": _levels(
            "Leasing means you pay to use the car and give it back, or buy it at a price that was set at the start. That preset price is the residual value. Buying with a loan means the car is yours once the loan is gone.",
            "A lease payment has two teaching pieces. The depreciation piece is (capitalized cost − residual) / number of months. The rent charge is (capitalized cost + residual) × money factor. Add them for the base payment, before taxes. Money factor × 2400 is a rough APR. At the end you can return the car, and mileage or damage above the contract can cost extra, or you can buy it for the residual plus a fee. A loan has no residual. You already own the car subject to the lien, and you keep whatever it is worth after the loan.",
            "Let C be capitalized cost, R the residual, n the term, and f the money factor. Depreciation portion d = (C − R) / n. Rent charge ρ = (C + R) · f. Base payment ≈ d + ρ. The approximation APR ≈ 2400 f is an industry conversion, not a federally identical APR. Lease-end buyout ≈ R + purchase-option fee. Equity versus that buyout is V − (R + fee); the pack uses a $350 fee in its lease equity note. A loan has R undefined. Setting R = 0 inside the lease formula is not how installment loans are priced; loans use the amortizing M on the unpaid balance.",
        ),
        "example": {
            "title": "Cap cost $26,384, residual $16,320, 36 months, factor 0.00205",
            "kind": "lease",
            "cap": 26384,
            "residual": 16320,
            "term": 36,
            "money_factor": 0.00205,
        },
        "quiz": [
            _quiz(
                "q1",
                "Residual value is:",
                ["The contract's preset value of the car at lease end, used in the payment and as the buyout starting point", "The APR", "The down payment", "This month's interest"],
                0,
                "It is the end value written into the lease.",
                "The payment uses it to decide how much depreciation you prepay. The buyout uses it as the price to keep the car.",
                "R enters both d = (C − R)/n and ρ = (C + R) f, and the purchase option is priced from R. It is not a rate.",
            ),
            _quiz(
                "q2",
                "Money factor 0.00200 is approximately what APR?",
                ["4.80%", "2.00%", "0.20%", "24.00%"],
                0,
                "Multiply by 2400. 0.002 × 2400 = 4.8.",
                "The conversion people use in auto leasing is APR ≈ money factor × 2400. 0.00200 × 2400 = 4.80%.",
                "2400 × 0.002 = 4.8. The factor 2400 = 24 × 100, combining a monthly-to-annual scale with percent units. It is an approximation.",
            ),
        ],
    },
    {
        "id": "lvb-compare",
        "topic_id": "lease_vs_buy",
        "title": "Compare what you pay and what you own",
        "minutes": 6,
        "summary": "The cheaper monthly payment is not the cheaper choice if one path ends with a car and the other ends with nothing.",
        "prerequisites": ["lvb-structures", "auto-equity"],
        "explanation": _levels(
            "Put the two paths side by side: total money paid, and what you own at the end. A lease often has the lower payment because you are not paying the whole car down.",
            "On a lease, payments plus fees plus any excess-mileage charges are the cost of using the car, and at the end you own nothing unless you buy it. On a loan, payments are higher when the term matches, but the car is yours and any leftover value is equity. A fair comparison uses the same number of months, subtracts equity you could actually receive, and includes fees, taxes, and mileage. Sometimes the lease wins for someone who always wants a new car and stays inside the mileage cap. Sometimes the loan wins because equity is large. There is no universal winner.",
            "Over horizon n, lease net cost ≈ n · P_lease + disposition + excess miles + capitalized fees − any equity if you buy and the car is worth more than the buyout. Loan net cost ≈ n · M + down payment − E_n, where E_n = V_n − B_n (B_n is 0 if the loan is paid off). Choose the loan when its net cost is lower for the same miles and the same V_n, and you are willing to hold the asset. Mileage enters the lease path as max(0, miles − allowance) × cents per mile, and enters the loan path only through a lower V_n. Because V_n is an estimate, show it as a sensitivity, not a single truth.",
        ),
        "example": {"title": "Same-term rate drop is a different question than lease versus buy", "kind": "refi", "balance": 20000, "old_apr": 9.0, "new_apr": 6.0, "months": 36},
        "quiz": [
            _quiz(
                "q1",
                "A lease payment is lower than the loan payment. What else do you need before calling it cheaper?",
                ["What you own at the end, plus fees and mileage charges", "Only the first month's payment", "The savings APY", "The credit-score weight for payment history"],
                0,
                "The car you keep, or do not keep, is part of the cost.",
                "Subtract ending equity from the loan's total payments, and add lease turn-in costs. Then compare.",
                "The objective is net cost over the horizon, nP_lease + fees − owned value versus nM + down − E_n. Payment size alone omits E_n.",
            ),
            _quiz(
                "q2",
                "Driving far more miles than a lease allows usually:",
                ["Adds an excess-mileage charge and would also lower the car's value if you owned it", "Increases the residual in the contract", "Removes the rent charge", "Raises the savings APY"],
                0,
                "Extra miles can cost money at lease turn-in. They also make a car you own worth less.",
                "The lease charges the excess directly. On a loan nobody sends that bill, but the market value used for equity is lower.",
                "Lease cash cost includes max(0, m − allowance) × rate. Loan equity uses a lower V_n(m). Residual R is contractual and does not rise because you drove more.",
            ),
        ],
    },
    {
        "id": "rate-fixed",
        "topic_id": "interest_rate_risk",
        "title": "Fixed rates lock the deal. Variable rates reprice.",
        "minutes": 5,
        "summary": "If your rate can reset, a rise in market rates can raise your payment. If you hold a bond, a rise in rates can lower its price.",
        "prerequisites": ["amort-payment", "inv-return"],
        "explanation": _levels(
            "A fixed APR means the rate in your payment stays the same. A variable rate can change, so the payment can change. When market rates go up, existing fixed-rate bonds become less attractive and their prices tend to fall.",
            "Borrowers with a fixed auto loan or mortgage are protected if new rates rise, and they look stuck if new rates fall — unless they refinance, which is a new contract. Savers with a variable savings rate benefit when rates rise. Someone who locked a CD does not. For bonds, price and yield move in opposite directions: you locked an old coupon, and buyers now demand a higher yield, so they will only buy your bond at a discount.",
            "A variable-rate loan sets r_{t} = index_t + margin, so M is recomputed when the index resets, using the remaining balance and remaining term. A fixed loan holds r constant. For a bond, modified duration D satisfies ΔP/P ≈ −D · Δy for a small yield change Δy. The minus sign is the rate risk of a lender or bondholder. A borrower's exposure has the opposite sign on a variable contract: higher y raises the payment. Convexity adds a ½ C (Δy)² term; this lesson uses the duration line only, and says so when the yield move is large.",
        ),
        "example": {"title": "A bond with duration 6 when yields rise 1 point", "kind": "duration", "price": 1000, "duration": 6, "yield_change": 1.0},
        "quiz": [
            _quiz(
                "q1",
                "Market rates rise. Who is hurt first?",
                ["A borrower with a variable rate, and a bondholder who wants to sell", "A borrower with a fixed rate they can keep", "A saver in a variable-rate savings account", "Nobody, because APR and price are unrelated"],
                0,
                "The variable loan can reprice higher, and the bond's price tends to drop.",
                "The fixed-rate borrower keeps the old payment. The variable-rate saver starts earning more. Those are the other side of the same move.",
                "Variable M is increasing in r. Bond ΔP/P ≈ −D Δy < 0 when Δy > 0. A fixed contractual r does not change. A variable deposit yield moves with the index.",
            ),
            _quiz(
                "q2",
                "Modified duration of 5 and a yield increase of 0.50 percentage points implies an approximate price change of:",
                ["−2.5%", "+2.5%", "−5%", "0%"],
                0,
                "Price moves about −5 × 0.50% = −2.5%.",
                "The formula is minus duration times the yield change. 5 × 0.50% = 2.5%, and the sign is negative when yields rise.",
                "ΔP/P ≈ −D Δy = −5 × 0.005 = −0.025. The sign is the definition of long-bond rate risk.",
            ),
        ],
    },
    {
        "id": "rate-refi",
        "topic_id": "interest_rate_risk",
        "title": "Refinancing replaces the rate and the term",
        "minutes": 6,
        "summary": "A refinance pays off the old contract with a new one. Interest changes because both the rate and the number of months can change.",
        "prerequisites": ["rate-fixed", "auto-loan"],
        "explanation": _levels(
            "Refinancing means a new loan pays off the old loan. If the new rate is lower and you keep the same number of months, you pay less interest. If you stretch the months to get a smaller payment, you can pay more interest even with a lower rate.",
            "Compare interest, not just the payment. Take today's payoff, the remaining months, and the old payment. Then price a new loan on that same payoff. Same months and a lower rate: payment falls and total interest falls. Longer months: payment falls more, but you may pay interest for extra years. Fees to originate the new loan are a cash cost. Subtract them from the interest savings, or think of how many months of savings it takes to earn the fees back. A rate sheet can say what APR a tier maps to. It is not proof the lender will approve it. A recent missed payment is a common reason a refinance is declined or priced higher.",
            "Let payoff be Q, remaining term n, old payment M_old (which may not exactly match a fresh amortization of Q), new rate r_new, and new term n_new. New payment M_new = Q r_new (1+r_new)^{n_new} / ((1+r_new)^{n_new} − 1). Interest on a freshly amortizing path is n M − Q. Savings versus keeping the old contract ≈ (interest of simulating M_old on Q) − (n_new M_new − Q) − fees. Stretching n_new increases the interest term even when r_new < r_old. Break-even months ≈ fees / (M_old − M_new) when the payment actually falls and you ignore the difference in principal speed. This curriculum labels rate-sheet numbers as synthetic.",
        ),
        "example": {"title": "$23,000 payoff, 43 months, 12.9% versus 7.7%", "kind": "refi", "balance": 23000, "old_apr": 12.9, "new_apr": 7.7, "months": 43},
        "quiz": [
            _quiz(
                "q1",
                "A lower APR with the same balance and the same months left will:",
                ["Lower the payment and lower total interest", "Lower the payment and raise total interest", "Leave interest unchanged", "Increase the residual"],
                0,
                "Same term, lower rate, less interest.",
                "The payment formula is increasing in the rate. Total interest nM − P falls when M falls and n and P stay put.",
                "∂M/∂r > 0 on an amortizing loan, so a lower r lowers M. With n fixed, interest = nM − P falls. Residual is not a term in a loan refinance.",
            ),
            _quiz(
                "q2",
                "You cut the payment by adding two extra years. What else must you check?",
                ["Whether total interest rose because the balance is outstanding longer", "Whether APY on savings fell by the same amount", "Whether utilization became the residual", "Nothing; a lower payment always saves money"],
                0,
                "A smaller payment can still cost more interest if you pay for more months.",
                "Interest is charged on the balance every month the balance exists. Extra months are extra chances to charge it.",
                "Interest = Σ B_{t−1} r. Extending T adds terms to the sum. If the drop in r is small and the added months are many, the sum can increase. Compare both paths, then subtract fees.",
            ),
        ],
    },
    {
        "id": "quant-tvm",
        "topic_id": "quant_fundamentals",
        "title": "A dollar later is worth less today",
        "minutes": 5,
        "summary": "If money can earn a return, cash in the future must be discounted to compare it with cash now.",
        "prerequisites": ["bank-apy", "inv-return"],
        "explanation": _levels(
            "Money you will get later is worth less than the same amount today, because today's money can earn something in the meantime.",
            "Future value grows a present amount forward: multiply by (1 + rate) once per year. Present value does the reverse: divide. This is why a residual received at lease end, a CD that matures in two years, and a paycheck today are not compared by adding the raw dollars. Use the same rate and the same dates, or the comparison is noise. The rate you pick should match the risk. A bank CD and a stock do not deserve the same discount rate.",
            "FV = PV × (1 + r)^T and PV = FV / (1 + r)^T for an effective annual rate r and whole years T. With m compounds per year, the growth factor is (1 + r_nom/m)^{mT}. Discounting a stream is PV = Σ_t CF_t / (1 + r)^t. The amortization payment is the annuity whose present value equals P: P = Σ_{t=1}^{n} M / (1 + r_month)^t, which solves to the M formula used throughout this curriculum. Choosing r is the modeling decision: risk-free cash uses a low r; uncertain stock cash flows use a higher r, which lowers PV.",
        ),
        "example": {"title": "$1,000 for 3 years at 5%", "kind": "tvm", "present": 1000, "annual_rate": 5, "years": 3},
        "quiz": [
            _quiz(
                "q1",
                "At 5% a year, the present value of $105 received in one year is about:",
                ["$100", "$105", "$110.25", "$5"],
                0,
                "You would need about $100 today, because 100 × 1.05 = 105.",
                "PV = 105 / 1.05 = 100. Discounting undoes one year of growth at 5%.",
                "PV = FV / (1 + r) = 105 / 1.05 = 100. The one-year factor is the definition of that rate.",
            ),
            _quiz(
                "q2",
                "Why is a lease residual not added one-for-one to today's costs?",
                ["It is a future amount, so timing matters, and you only pay it if you buy the car", "Because residuals are APYs", "Because money factor is a dollar balance", "It is always zero"],
                0,
                "It happens at the end, and only if you choose to buy.",
                "A future optional price is not cash today. If you return the car you never pay it. If you compare it with today's value, discount or at least do not pretend it is a current bill.",
                "The buyout is an option at date n with strike near R, not a present liability of size R. A present-value comparison uses R / (1 + r)^T only in scenarios where the option is exercised.",
            ),
        ],
    },
    {
        "id": "quant-ev",
        "topic_id": "quant_fundamentals",
        "title": "Expected value is a weighted average",
        "minutes": 5,
        "summary": "Multiply each outcome by its probability and add them. The spread around that average is risk.",
        "prerequisites": ["quant-tvm", "inv-risk"],
        "explanation": _levels(
            "Expected value is the average result if the same situation happened many times. It is not a promise about the one time that is happening to you.",
            "List the outcomes you think are possible, put a probability on each, and make the probabilities add to 100%. Multiply and add. Also look at the worst outcome you can live with, because a good average can hide a bad left tail. Standard deviation summarizes the typical distance from the average. In personal finance this shows up as: the 'expected' repair cost is not the bill you will get; it is the long-run average of bills like it.",
            "E[X] = Σ p_i x_i with Σ p_i = 1. Variance σ² = E[(X − E[X])²] = Σ p_i (x_i − E[X])². For independent risks, variances add and the standard deviation of the sum grows like the square root of the number of risks, which is why pooling idiosyncratic risks is powerful. A decision rule that looks only at E[X] is risk-neutral. A rule that also penalizes σ, or that rejects plans whose worst case breaks the emergency fund, is closer to how a household should use the number. Probabilities you write down are a model. If they are wrong, E[X] is wrong with them.",
        ),
        "example": {
            "title": "Repair risk",
            "kind": "expectation",
            "outcomes": [[0.8, 0], [0.15, 400], [0.05, 2500]],
        },
        "quiz": [
            _quiz(
                "q1",
                "80% chance of $0, 15% chance of $400, 5% chance of $2,500. Expected cost is:",
                ["$185", "$400", "$2,500", "$966"],
                0,
                "Most of the time you pay nothing, but the rare big bill pulls the average up to $185.",
                "0.80×0 + 0.15×400 + 0.05×2500 = 60 + 125 = 185.",
                "E[X] = 185. The median outcome is $0, which shows why the average alone is a poor description of a skewed bill.",
            ),
            _quiz(
                "q2",
                "A plan has a pleasant expected value and a 5% chance of wiping out the emergency fund. A careful reading:",
                ["Looks at that bad case, not only the average", "Ignores anything under 50% probability", "Treats expected value as the amount that will occur", "Converts the probability into an APR"],
                0,
                "The average hides a bad tail. Check whether you can survive the bad case.",
                "Expected value is the long-run average. One household lives through one draw. If that draw breaks the budget, the average does not pay the bill.",
                "A risk-neutral rule maxes E[X]. A household with a liquidity constraint also needs the loss in the tail to stay inside cash B plus insurance. Probability is not an interest rate.",
            ),
        ],
    },
]


SCENARIOS: list[dict] = [
    {
        "id": "sc-budget",
        "topic_id": "personal_finance",
        "title": "Assign a first paycheck",
        "lesson_id": "pf-budget",
        "situation": "Alex takes home $3,600 this month. Rent and other needs are $2,100. A credit card balance carries 22% APR. There is $400 in savings, which is less than one month of needs.",
        "questions": [
            _quiz(
                "q1",
                "What is a defensible order for the $1,500 that is not rent?",
                [
                    "Keep building a small cash starter, pay the card next, then wants",
                    "Spend the $1,500 on wants because the card can wait forever",
                    "Move the $400 starter into one stock",
                    "Ignore needs because a budget is optional",
                ],
                0,
                "A little cash first, then the expensive card, then wants.",
                "The starter fund is below one month of needs, and the card rate is far above any savings yield. Wants come after those.",
                "Starter B0 is below essential spending E = 2100. The card spread versus savings is about 22% minus a small APY, so dollars after the starter reduce interest fastest.",
            ),
            _quiz(
                "q2",
                "Cash flow if Alex spends the entire $1,500 on wants and pays no card principal is:",
                ["$0 surplus", "$1,500 surplus", "$3,600 surplus", "Negative, because rent is a need"],
                0,
                "3,600 − 2,100 − 1,500 = 0. Nothing is left.",
                "All take-home pay is assigned to needs and wants. The card balance does not fall.",
                "C = 3600 − 2100 − 1500 = 0. Interest will still accrue on the revolving balance, so net worth can fall while cash flow is zero.",
            ),
        ],
    },
    {
        "id": "sc-utilization",
        "topic_id": "credit",
        "title": "The statement balance",
        "lesson_id": "credit-utilization",
        "situation": "Riley has one card with a $2,000 limit. The statement will cut tomorrow with a $1,700 balance. Riley can pay in full on the due date three weeks later and has the cash today. No other cards.",
        "questions": [
            _quiz(
                "q1",
                "If the $1,700 balance is what gets reported, utilization is:",
                ["85%", "15%", "41%", "170%"],
                0,
                "1,700 / 2,000 = 85%.",
                "Utilization uses the reported balance, which is high even though Riley intends to pay in full later.",
                "U = 1700/2000 = 0.85. The later payment does not rewrite the balance that was already reported.",
            ),
            _quiz(
                "q2",
                "Paying the balance down before the statement, while still paying any remainder by the due date, mainly changes:",
                ["The utilization that gets reported", "The car's residual", "The CD penalty", "The mortgage escrow"],
                0,
                "A lower statement balance is a lower reported utilization.",
                "The score sees what is reported. Paying before the statement changes that number. The due-date payment is what avoids interest.",
                "Reported U falls if the statement balance falls. Interest depends on whether a revolving balance breaks the grace period. Those are separate mechanisms.",
            ),
        ],
    },
    {
        "id": "sc-extra",
        "topic_id": "loan_amortization",
        "title": "An extra $50",
        "lesson_id": "amort-extra",
        "situation": (
            f"A loan of $18,000 at 6% for 48 months has a scheduled payment of {money(_PMT_18K)}. "
            "The contract has no prepayment penalty. Jordan can add $50 and wants it applied to principal."
        ),
        "questions": [
            _quiz(
                "q1",
                "What should Jordan confirm on the next statement?",
                [
                    "The principal balance fell by the scheduled principal plus about $50",
                    "The APR changed to 0%",
                    "The residual was rewritten",
                    "The extra $50 was only a donation",
                ],
                0,
                "The extra dollars should show up as a lower balance.",
                "Interest is fixed this month by the starting balance. Extra principal comes off the balance on top of the scheduled principal slice.",
                f"I_1 is about {money(_LOAN_18K.first_interest)} on this loan. Principal from the scheduled payment is about {money(_LOAN_18K.first_principal)}. Posting X = 50 should reduce B by about that principal plus 50.",
            ),
            _quiz(
                "q2",
                "Compared with paying only the scheduled amount, the extra $50 path:",
                ["Pays the loan off sooner and with less total interest", "Raises total interest", "Extends the term", "Changes a fixed APR into a variable APR"],
                0,
                "Less balance later means less interest and fewer months.",
                "The rate does not change. The horizon does. That is the point of principal prepayment.",
                "Simulating X = 50 shortens T and reduces Σ I_t. Contractual r is unchanged.",
            ),
        ],
    },
    {
        "id": "sc-lease-buy",
        "topic_id": "lease_vs_buy",
        "title": "Lower payment, nothing owned",
        "lesson_id": "lvb-compare",
        "situation": "Sam can lease a car for $310 a month for 36 months and return it, with an estimated $400 of turn-in fees and no excess miles. Or Sam can finance the same car for $540 a month for 36 months and own a car worth about $16,000 at the end, with the loan paid off. Ignore taxes.",
        "questions": [
            _quiz(
                "q1",
                "Approximate net cost of the lease path is:",
                ["$11,560", "$310", "$16,000", "$540"],
                0,
                "36 × 310 plus the $400 fee is $11,560, and Sam owns nothing.",
                "36 × 310 = 11,160. Add the $400 disposition fee. There is no car to subtract at the end if Sam returns it.",
                "Net = n P_lease + fees − owned value = 11160 + 400 − 0 = 11560.",
            ),
            _quiz(
                "q2",
                "Approximate net cost of the loan path, after subtracting the car Sam owns, is:",
                ["$3,440", "$19,440", "$16,000", "$540"],
                0,
                "36 × 540 is $19,440, minus a $16,000 car, is $3,440.",
                "The payments are higher, but the car is an asset at the end. Subtract its value before comparing with the lease.",
                "Net = 36 × 540 − 16000 = 19440 − 16000 = 3440, which is lower than the lease net in this particular set of assumptions. A lower ending value could reverse the result.",
            ),
        ],
    },
    {
        "id": "sc-refi",
        "topic_id": "interest_rate_risk",
        "title": "Same term or a longer term",
        "lesson_id": "rate-refi",
        "situation": "Priya owes $12,000. At 10% APR for the 36 months remaining, the amortizing payment is about $387.21 and total interest is about $1,939. A 6% refinance for the same 36 months has a payment near $365 and less interest. A 6% refinance stretched to 60 months has a payment near $232.",
        "questions": [
            _quiz(
                "q1",
                "Which statement about the 6% / 36-month refinance is right?",
                [
                    "Payment and total interest both fall versus keeping 10% for 36 months",
                    "Interest rises because the rate fell",
                    "The residual must increase",
                    "It is identical to a lease",
                ],
                0,
                "Same months, lower rate, less interest.",
                "Nothing about the term got worse. The only change is a lower rate on the same balance and months, so interest falls.",
                "M(6%, 36) < M(10%, 36) and n is unchanged, so nM − P falls. This scenario is an installment loan, so there is no residual.",
            ),
            _quiz(
                "q2",
                "Why is the $232 payment not automatically the best deal?",
                [
                    "Sixty months of interest can cost more overall even though each payment is smaller",
                    "Because a lower payment always means a higher APR",
                    "Because APY forbids terms over 48 months",
                    "Because equity in a home changed",
                ],
                0,
                "You might pay interest for two extra years.",
                "Always compare total interest and fees, not the monthly draft alone. Stretching the term is what makes the payment so small.",
                "Interest = Σ B_{t−1} r over the life of the contract. Adding 24 months adds positive terms. Compute both sums before preferring the smaller M.",
            ),
        ],
    },
    {
        "id": "sc-rate-risk",
        "topic_id": "interest_rate_risk",
        "title": "Rates move after you lock",
        "lesson_id": "rate-fixed",
        "situation": "Noor locked a 2-year CD at 4% APY. A month later, new CDs pay 5%. Noor also has a fixed-rate car loan at 6% and a bond fund. Market yields jumped.",
        "questions": [
            _quiz(
                "q1",
                "The CD at 4% when new CDs pay 5% means:",
                [
                    "Noor is stuck at 4% unless they pay the early-withdrawal penalty",
                    "The bank must raise Noor's CD to 5%",
                    "The car loan APR automatically becomes 5%",
                    "The residual on a lease changes",
                ],
                0,
                "A CD rate stays put until maturity. Getting out early can cost a penalty.",
                "That is the lock. The car loan is a separate fixed contract and also does not reprice by itself.",
                "The CD's yield is contractual until T. Repricing requires breaking it and paying the penalty, then reinvesting at the new rate. The auto APR does not reference the CD index.",
            ),
            _quiz(
                "q2",
                "Yields jumped. The bond fund price, approximately:",
                ["Falls", "Rises one-for-one with the car payment", "Is the money factor", "Cannot move"],
                0,
                "Higher yields, lower bond prices.",
                "Duration says the price change is about minus duration times the yield change. The sign is negative when yields rise.",
                "ΔP/P ≈ −D Δy < 0 when Δy > 0. The car payment is fixed, so it does not absorb this move.",
            ),
        ],
    },
]


def _index() -> dict[str, dict]:
    return {lesson["id"]: lesson for lesson in LESSONS}


LESSON_INDEX = _index()
SCENARIO_INDEX = {item["id"]: item for item in SCENARIOS}


def knowledge_map() -> dict:
    topic_x = {topic["id"]: index for index, topic in enumerate(TOPICS)}
    seen_in_topic: dict[str, int] = {}
    nodes = []
    edges = []
    for lesson in LESSONS:
        y = seen_in_topic.get(lesson["topic_id"], 0)
        seen_in_topic[lesson["topic_id"]] = y + 1
        nodes.append(
            {
                "id": lesson["id"],
                "title": lesson["title"],
                "topic_id": lesson["topic_id"],
                "minutes": lesson["minutes"],
                "x": topic_x[lesson["topic_id"]],
                "y": y,
                "prerequisites": list(lesson["prerequisites"]),
            }
        )
        for source in lesson["prerequisites"]:
            edges.append({"source": source, "target": lesson["id"], "kind": "prerequisite"})
    return {"topics": TOPICS, "nodes": nodes, "edges": edges}


def validate_curriculum() -> None:
    ids = [lesson["id"] for lesson in LESSONS]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate lesson id")
    topic_ids = {topic["id"] for topic in TOPICS}
    for lesson in LESSONS:
        if lesson["topic_id"] not in topic_ids:
            raise RuntimeError(f"Unknown topic on {lesson['id']}")
        for level in ("simple", "learner", "detailed"):
            if not lesson["explanation"][level].strip():
                raise RuntimeError(f"Missing {level} on {lesson['id']}")
        if not lesson["quiz"]:
            raise RuntimeError(f"Missing quiz on {lesson['id']}")
        for item in lesson["quiz"]:
            if not 0 <= item["answer_index"] < len(item["choices"]):
                raise RuntimeError(f"Bad answer on {lesson['id']} {item['id']}")
            for level in ("simple", "learner", "detailed"):
                if not item["explanation"][level].strip():
                    raise RuntimeError(f"Missing quiz explanation on {item['id']}")
        for prereq in lesson["prerequisites"]:
            if prereq not in LESSON_INDEX:
                raise RuntimeError(f"Missing prereq {prereq}")
    # Cycle check.
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise RuntimeError(f"Cycle at {node}")
        visiting.add(node)
        for nxt in LESSON_INDEX[node]["prerequisites"]:
            walk(nxt)
        visiting.remove(node)
        visited.add(node)

    for lesson_id in LESSON_INDEX:
        walk(lesson_id)
    for scenario in SCENARIOS:
        if scenario["lesson_id"] not in LESSON_INDEX:
            raise RuntimeError(f"Scenario {scenario['id']} points at a missing lesson")


validate_curriculum()
