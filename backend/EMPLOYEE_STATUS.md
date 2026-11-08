# Employee implementation status

**Current verification:** account-based workspaces and Mistral Bessie are implemented;
72 backend tests and 13 frontend tests pass, with frontend type/build checks and
backend/changed-file lint passing. The live Mistral probe returned HTTP 429;
successful live completion remains externally blocked by quota/rate limiting.
Old sample logins are disabled, their data/history is preserved, and an operator
must adopt/provision the intended email account. See BESSIE_SETUP.md. SQLite
permissions are application-enforced, not database-user RLS. Finance workshop/Lab
coverage was not changed or revalidated in this account-and-agent task.

**Current account/AI setup:** see [BESSIE_SETUP.md](BESSIE_SETUP.md). Normal sign-in now requires a provisioned email/password account. Demo login and auto-seeding are disabled; old sample logins below are historical. Bessie uses MISTRAL_API_KEY directly, without AGENT_PROVIDER. Existing financial data remains synthetic.

**Storage update:** the active backend now uses SQLAlchemy + local SQLite with
email-based users and a shared role directory. Tiger and Lab Package integrations
are retired for the active app. See SQLALCHEMY_SETUP.md for current verification;
the earlier cloud-specific notes below describe the superseded implementation.

Backend-only implementation against the current PNC scope in Skill.md. Frontend
implementation remains with the teammate. This is not a completed production system.

## Implemented

| Registry feature | Result |
| --- | --- |
| staff.access | Eight seeded employees across seven roles; opaque expiring demo sessions; role-derived tabs/features; API guards; denial audit; grant expiry/conflicts/break-glass. PostgreSQL policies provided, not cloud-verified. |
| staff.prospect | Thirty reproducible synthetic prospects; assigned metadata queue; blind credit file gated by purpose. |
| staff.creditresearch | pnc-demo-v1 personal-loan/card engine; threshold evidence, outcomes, missing inputs, indicative pricing, replay-validated numerical counterfactuals, immutable runs. |
| staff.decision | Human rationale required; override reason and compliance flag; no external notice. |
| staff.cases | Assigned synthetic handoffs, consented-context briefs, status transitions and immutable case events. Live Amelia handoff creation pending. |
| staff.portfolio | Latest snapshots from the 500-user local CSV, aggregate-only role response, research outcomes and override rate; groups under five suppressed. |
| staff.benefits | Tenure tiers, cap, quarterly item limit, cents arithmetic, idempotent simulated vouchers/ledger, versioned admin catalog/rules. |
| staff.audit | Searchable immutable event history for compliance/auditors; explicit denial and break-glass events. |
| staff.fairness | Recorded-run rates by synthetic groups and offline seed mirror-pair invariance; illustrative ratios only. |
| staff.campaigns | Fail-closed empty audience because consent/protection/channel data is missing; creation blocked. |
| staff.anomaly | Explicit unavailable state until fin.fraud provides detections. |
| learn.explain | Mock Wilbur benefit formulas and role-authorized recorded credit evidence. |

Bessie is a deterministic placeholder, with no model calls. It reports mock status
and returns authorized evidence. Agent keys exist only as placeholders in the
ignored backend/.env; backend/.env.example is the shareable configuration template.

## Staff coverage and verification

API tests exercise every role against each employee domain endpoint. Analysts
cannot use compliance/cases; specialists cannot read credit files; marketing gets
campaign aggregates only; managers get aggregates; auditors cannot mutate credit
decisions; Benefits Admin has no customer/credit domain access. Each employee sees
only their own benefit ledger, except the admin's explicit benefits-only usage view.

Verified locally: **15 employee API/policy tests and 9 existing Learn checks passed**.
The pnc-demo-v1 excluded-input mirror test passes. Numerical boundary, missing-data,
counterfactual, corrupt-evidence, consent-source, immutable-storage, session-expiry,
override, benefit-cap/idempotency and seeded reproducibility checks pass.

Three direct PostgreSQL isolation tests are **skipped**, awaiting a dedicated
STAFF_TEST_DATABASE_URL. Therefore database-level isolation is not yet verified.
The default SQLite adapter provides API-level isolation only so development can
continue without cloud credentials. Regular PostgreSQL RLS tables are supplied;
Timescale hypertables/compression and the cloud connection pooler are unverified.

## Workshop, integrations, registry and self-check

Finance workshop checklist §5.1 and sponsor Lab_Package assets were not changed
or revalidated in this employee-only task. No Lab_Package assets were reused.
No Toyota feature implementation was added. Skill.md registry text is unchanged;
backend staff registry mirrors its role/feature permissions, tested against seeds.

All employee data is generated and synthetic. Portfolio reads local CSV data,
not a claimed live Tiger query. Shared Tiger data has not been changed.
No external identity, LLM, messaging or transaction integration is claimed.

Provisional engineering self-score (0–5, not a judge score): value 3 (functional
staff API journeys); innovation 3 (evidence/counterfactual research); function 3
(API tests pass, live cloud checks pending); orchestration 2 (mock code pipeline,
no model/LangGraph execution); trust 3 (tested API boundaries, SQL verification
pending); presentation 1 (backend handoff only; frontend intentionally untouched).

## Remaining and demo

The complete Staff definition of done remains open for verified Tiger isolation,
frontend role journeys, live agent adapters, live consented handoff creation,
marketing-consent sources, and fraud detections. The current cohort differs from
Skill.md's 30-customer Portfolio wording; no arbitrary cohort was fabricated.

Use EMPLOYEE_API.md for commands and payloads. Shortest demo: start backend on
8010; open /docs; sign in as E001; grant P001/APP-001; run research; ask mock Bessie;
record a human decision; switch to E006/E007 for reviews/audit; use E003 for cases
and E008 for benefits administration. Bearer tokens go in the Authorization header.
