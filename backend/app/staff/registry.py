"""Backend source for staff tabs, features and endpoint permissions (Skill.md §3)."""
ROLES = {
    "credit_analyst": ("Credit Analyst", "research"),
    "service_specialist": ("Customer Service Specialist", "cases"),
    "marketing_analyst": ("Retention / Marketing Analyst", "portfolio"),
    "portfolio_manager": ("Portfolio / Risk Manager", "portfolio"),
    "compliance_analyst": ("Compliance Analyst", "compliance"),
    "auditor": ("Auditor", "compliance"),
    "benefits_admin": ("Benefits Admin", "benefits"),
}
ALL = list(ROLES)
FEATURES = {
    "staff.access": ALL,
    "staff.prospect": ["credit_analyst"],
    "staff.creditresearch": ["credit_analyst"],
    "staff.decision": ["credit_analyst", "compliance_analyst"],
    "staff.cases": ["service_specialist"],
    "staff.portfolio": ["portfolio_manager", "marketing_analyst"],
    "staff.benefits": ALL,
    "staff.audit": ["auditor", "compliance_analyst"],
    "staff.fairness": ["compliance_analyst"],
    "staff.campaigns": ["marketing_analyst"],
    "staff.anomaly": ["compliance_analyst"],
    "learn.explain": [role for role in ALL if role != "credit_analyst"],
}
BANNER = "Synthetic data. Prototype policy rules, not PNC policy."


def visible(role):
    workspace = ROLES[role][1]
    # Credit analysts review decisions on Activity. They do not get Learn or Wilbur.
    tail = "activity" if role == "credit_analyst" else "learn"
    return list(dict.fromkeys(["home", workspace, "benefits", tail]))


def capabilities(role):
    return [key for key, roles in FEATURES.items() if role in roles]
