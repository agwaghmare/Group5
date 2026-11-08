"""Fast, role-scoped welcome messages without financial-data retrieval or AI calls."""
import re

HELP = {
    "credit_analyst": "credit research, in-progress decisions, policy evidence and your employee benefits",
    "service_specialist": "your assigned cases, consented case briefs and employee benefits",
    "portfolio_manager": "assigned client portfolios, risk assessments, simulated rebalance proposals and employee benefits",
    "marketing_analyst": "permitted campaign information and employee benefits",
    "compliance_analyst": "compliance reviews, audit evidence and employee benefits",
    "auditor": "read-only audit evidence and your employee benefits",
    "benefits_admin": "the benefits catalog, benefit rules and usage",
}


def welcome(question, role, agent):
    text = re.sub(r"[!.?,]+", "", question.strip().lower())
    text = re.sub(r"\s+", " ", text)
    greetings = {"hi", "hello", "hey", "hi there", "hello there", "good morning", "good afternoon", "good evening"}
    for name in ("bessie", "wilbur"):
        greetings.update({"hi "+name, "hello "+name, "hey "+name})
    if text not in greetings | {"help", "who are you", "what can you do", "how can you help", "how can you help me"}:
        return None
    name = "Wilbur" if agent == "wilbur" else "Bessie"
    scope = "terms, formulas and the evidence your role can access" if agent == "wilbur" else HELP[role]
    return f"Hi, I'm {name}. I can help with {scope}. What would you like to work on?"


def question_feature(question, current):
    # Only route to read-only benefit context on an explicit benefits question.
    if current == "staff.access" and re.search(r"\b(benefits?|discounts?|tenure|vouchers?|redemptions?|annual cap)\b", question, re.I):
        return "staff.benefits"
    return current
