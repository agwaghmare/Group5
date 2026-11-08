"""SQLAlchemy 2 models. Tracker columns preserve the source CSV's exact names."""
from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (CheckConstraint("key IN ('customer','credit_analyst','service_specialist','marketing_analyst','portfolio_manager','compliance_analyst','auditor','benefits_admin')", name="known_role"),)
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    tabs: Mapped[list] = mapped_column(JSON)
    features: Mapped[list] = mapped_column(JSON)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(trim(email)) AND instr(email, '@') > 1", name="normalized_email"),
        CheckConstraint("(role_key='customer' AND employee_id IS NULL) OR (role_key<>'customer' AND employee_id IS NOT NULL)", name="user_identity_kind"),
        UniqueConstraint("employee_id"),
    )
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    role_key: Mapped[str] = mapped_column(ForeignKey("roles.key"), index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    display_name: Mapped[str] = mapped_column(String(150))
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[Role] = relationship()
    customer: Mapped["Customer | None"] = relationship(back_populates="user", uselist=False)


class Customer(Base):
    __tablename__ = "customers"
    tracker_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    source_type: Mapped[str] = mapped_column(String(80), default="synthetic_finance_tracker")
    user: Mapped[User] = relationship(back_populates="customer")
    snapshots: Mapped[list["FinanceSnapshot"]] = relationship(back_populates="customer")


class FinanceSnapshot(Base):
    __tablename__ = "finance_snapshots"
    user_id: Mapped[int] = mapped_column(ForeignKey("customers.tracker_id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    income_volatility_3m: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    income_growth_6m: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    pay_frequency: Mapped[str | None] = mapped_column(String(40))
    months_employed: Mapped[int | None] = mapped_column(Integer)
    checking_balance: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    available_balance: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    overdraft_count_90d: Mapped[int | None] = mapped_column(Integer)
    recurring_bill_total: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    savings_balance: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    savings_apy: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    emergency_fund_months: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    monthly_savings_contribution: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    total_debt_balance: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    weighted_avg_apr: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    minimum_debt_payment: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    remaining_loan_term_months: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    credit_limit_total: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    credit_utilization: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    credit_card_apr: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    late_payments_12m: Mapped[int | None] = mapped_column(Integer)
    home_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    mortgage_balance: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    mortgage_interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    home_equity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    portfolio_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    equity_allocation_pct: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    retirement_contribution: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    investment_volatility: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    subscription_cost_monthly: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    spending_volatility_3m: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    budget_variance_pct: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    savings_streak_months: Mapped[int | None] = mapped_column(Integer)
    unusual_merchant_flag: Mapped[int | None] = mapped_column(Integer)
    transaction_amount_zscore: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    transaction_velocity_24h: Mapped[int | None] = mapped_column(Integer)
    merchant_category_change: Mapped[int | None] = mapped_column(Integer)
    liquidity_runway_months: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    projected_balance_30d: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    debt_service_coverage: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    bill_payment_delay_count: Mapped[int | None] = mapped_column(Integer)
    life_event_type: Mapped[str | None] = mapped_column(String(100))
    customer: Mapped[Customer] = relationship(back_populates="snapshots")


class DataImport(Base):
    __tablename__ = "data_imports"
    source: Mapped[str] = mapped_column(String(200), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)
    customer_count: Mapped[int] = mapped_column(Integer)
    columns: Mapped[list] = mapped_column(JSON)


class PortfolioAssignment(Base):
    __tablename__ = "portfolio_assignments"
    client_id: Mapped[int] = mapped_column(ForeignKey("customers.tracker_id"), primary_key=True)
    manager_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    assigned_at: Mapped[str] = mapped_column(String(40))


class InvestmentProfile(Base):
    __tablename__ = "investment_profiles"
    __table_args__ = (CheckConstraint("horizon_months > 0 AND tolerance BETWEEN 1 AND 5"),)
    client_id: Mapped[int] = mapped_column(ForeignKey("customers.tracker_id"), primary_key=True)
    goal: Mapped[str] = mapped_column(String(200))
    horizon_months: Mapped[int] = mapped_column(Integer)
    tolerance: Mapped[int] = mapped_column(Integer)
    liquidity_need_cents: Mapped[int] = mapped_column(Integer)
    target_return: Mapped[Decimal] = mapped_column(Numeric(12, 8))
    questionnaire: Mapped[dict] = mapped_column(JSON)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class PortfolioAccount(Base):
    __tablename__ = "portfolio_accounts"
    __table_args__ = (
        CheckConstraint("stocks_ppm BETWEEN 0 AND 1000000 AND bonds_ppm BETWEEN 0 AND 1000000 AND foreign_ppm BETWEEN 0 AND 1000000"),
        CheckConstraint("stocks_ppm + bonds_ppm + foreign_ppm = 1000000", name="portfolio_allocation_total"),
        CheckConstraint("value_cents >= 0 AND revision >= 1"),
    )
    client_id: Mapped[int] = mapped_column(ForeignKey("customers.tracker_id"), primary_key=True)
    stocks_ppm: Mapped[int] = mapped_column(Integer)
    bonds_ppm: Mapped[int] = mapped_column(Integer)
    foreign_ppm: Mapped[int] = mapped_column(Integer)
    value_cents: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    as_of: Mapped[str] = mapped_column(String(40))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (CheckConstraint("bucket IN ('stocks','bonds','foreign') AND value_cents >= 0"),)
    client_id: Mapped[int] = mapped_column(ForeignKey("portfolio_accounts.client_id"), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(20), primary_key=True)
    instrument: Mapped[str] = mapped_column(String(80))
    asset_class: Mapped[str] = mapped_column(String(30))
    geography: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    value_cents: Mapped[int] = mapped_column(Integer)
    units: Mapped[Decimal] = mapped_column(Numeric(24, 8))


class MarketObservation(Base):
    __tablename__ = "portfolio_market_history"
    __table_args__ = (CheckConstraint("total_return_index > 0"),)
    bucket: Mapped[str] = mapped_column(String(20), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    total_return_index: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    source: Mapped[str] = mapped_column(String(100))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class PortfolioAssessment(Base):
    __tablename__ = "portfolio_assessments"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("portfolio_accounts.client_id"), index=True)
    manager_id: Mapped[str] = mapped_column(ForeignKey("employees.id"))
    revision: Mapped[int] = mapped_column(Integer)
    assessed_at: Mapped[str] = mapped_column(String(40))
    evidence: Mapped[dict] = mapped_column(JSON)


class RebalanceProposal(Base):
    __tablename__ = "portfolio_rebalance_proposals"
    __table_args__ = (
        CheckConstraint("stocks_ppm BETWEEN 0 AND 1000000 AND bonds_ppm BETWEEN 0 AND 1000000 AND foreign_ppm BETWEEN 0 AND 1000000"),
        CheckConstraint("stocks_ppm + bonds_ppm + foreign_ppm = 1000000"),
        CheckConstraint("status IN ('proposed','approved')"),
    )
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("portfolio_accounts.client_id"), index=True)
    manager_id: Mapped[str] = mapped_column(ForeignKey("employees.id"))
    base_revision: Mapped[int] = mapped_column(Integer)
    stocks_ppm: Mapped[int] = mapped_column(Integer)
    bonds_ppm: Mapped[int] = mapped_column(Integer)
    foreign_ppm: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    evidence: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))
    approved_at: Mapped[str | None] = mapped_column(String(40))


class PortfolioHistory(Base):
    __tablename__ = "portfolio_history"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("portfolio_accounts.client_id"), index=True)
    recorded_at: Mapped[str] = mapped_column(String(40))
    event: Mapped[str] = mapped_column(String(40))
    evidence: Mapped[dict] = mapped_column(JSON)


class Record:
    """Versioned/domain JSON documents; IDs and ownership remain relational."""
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    owner: Mapped[str] = mapped_column(String(50), default="", index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Employee(Record, Base):
    __tablename__ = "employees"


class Prospect(Record, Base):
    __tablename__ = "prospects"
    assigned_to: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    application_ref: Mapped[str] = mapped_column(String(100), unique=True)
    product: Mapped[str] = mapped_column(String(30))


class CreditProfile(Record, Base):
    __tablename__ = "credit_profiles"
    id: Mapped[str] = mapped_column(ForeignKey("prospects.id"), primary_key=True)
    annual_income: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    income_verified: Mapped[str | None] = mapped_column(String(10))
    credit_band: Mapped[str | None] = mapped_column(String(20))
    revolving_balance: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    revolving_limit: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    existing_monthly_debt: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    delinquencies_24m: Mapped[int | None] = mapped_column(Integer)
    delinquencies_12m: Mapped[int | None] = mapped_column(Integer)
    employment_months: Mapped[int | None] = mapped_column(Integer)
    bankruptcy_years_ago: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    history_months: Mapped[int | None] = mapped_column(Integer)
    inquiries_6m: Mapped[int | None] = mapped_column(Integer)
    requested_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    requested_limit: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    term_months: Mapped[int | None] = mapped_column(Integer)


class ProtectedProfile(Record, Base):
    __tablename__ = "protected"
    id: Mapped[str] = mapped_column(ForeignKey("prospects.id"), primary_key=True)


class EmployeeLink(Record, Base):
    __tablename__ = "links"


class CreditPolicy(Record, Base):
    __tablename__ = "policies"


class AccessGrant(Record, Base):
    __tablename__ = "grants"
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    prospect_id: Mapped[str] = mapped_column(ForeignKey("prospects.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    reference_id: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[str] = mapped_column(String(40))


class ResearchRun(Record, Base):
    __tablename__ = "runs"
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    prospect_id: Mapped[str] = mapped_column(ForeignKey("prospects.id"), index=True)
    grant_id: Mapped[str] = mapped_column(ForeignKey("grants.id"))
    policy_version: Mapped[str] = mapped_column(ForeignKey("policies.id"))
    outcome: Mapped[str] = mapped_column(String(30))


class CreditDecision(Record, Base):
    __tablename__ = "decisions"
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), unique=True)
    rationale: Mapped[str] = mapped_column(String(2000))
    override: Mapped[bool] = mapped_column(Boolean)


class DecisionDraft(Record, Base):
    """Editable in-progress decision. The recorded decision row stays append-only."""
    __tablename__ = "decision_drafts"
    employee_id: Mapped[str] = mapped_column(String(50), index=True)
    run_id: Mapped[str] = mapped_column(String(100), unique=True)


class HandoffCase(Record, Base):
    __tablename__ = "cases"


class CaseEvent(Record, Base):
    __tablename__ = "case_events"


class BenefitCatalog(Record, Base):
    __tablename__ = "catalog"


class BenefitRule(Record, Base):
    __tablename__ = "benefit_rules"


class Redemption(Record, Base):
    __tablename__ = "redemptions"


class AuditLog(Record, Base):
    __tablename__ = "audit"


class AuthSession(Record, Base):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    # Only a digest of an opaque token is stored in id.


class Campaign(Record, Base):
    __tablename__ = "campaigns"


class Anomaly(Record, Base):
    __tablename__ = "anomalies"


class Permission(Record, Base):
    __tablename__ = "permissions"


RECORD_MODELS = {model.__tablename__: model for model in (
    Employee, Prospect, CreditProfile, ProtectedProfile, EmployeeLink, CreditPolicy,
    AccessGrant, ResearchRun, CreditDecision, DecisionDraft, HandoffCase, CaseEvent, BenefitCatalog,
    BenefitRule, Redemption, AuditLog, AuthSession, Campaign, Anomaly, Permission,
)}
TRACKER_COLUMNS = [column.name for column in FinanceSnapshot.__table__.columns]
