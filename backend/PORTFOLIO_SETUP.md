# Portfolio / Risk Manager workspace

The Portfolio tab now shows a client queue, assignment, holdings, risk/return charts,
investment assumptions, proposal comparisons and change history. Credit research
and marketing's aggregate-only view are preserved. Bessie uses the existing NVIDIA
adapter and only the selected assigned client's authorized evidence.

## Start and use

Restart the backend, then refresh the frontend. Sign in using a provisioned
`portfolio_manager` account. No new employee accounts or passwords are created.
If needed, provision one using the existing operator CLI (password prompted privately):

```sh
cd backend
source .venv/bin/activate
python manage_database.py create-employee \
  --email your-manager@company.com --name "Portfolio Manager" \
  --role portfolio_manager --hire-date 2024-01-01
```

1. Open Portfolio and choose **Assign client**. Search the unassigned directory and
   select **Assign to me**. Only client IDs/names are available before assignment.
2. Select the client and run an assessment. Review Overview and Risk & returns.
3. Confirm/update the modeled investment profile: goal, horizon, tolerance,
   liquidity need and return target. Saving automatically recalculates the assessment
   and shows confirmation beside Save. Old proposals become stale; earlier assessments
   remain in history. Risk limits and goal flags update, while historical performance
   remains tied to actual modeled allocations and market history.
4. Enter a rationale on Rebalance and generate a suitable mix, or preview your own
   percentages. They must total exactly 100%; risk/concentration constraints still apply.
5. Review the before/after comparison, cost estimate and goal-feasibility message.
   Explicitly confirm the simulation before approval. History records the change,
   and the current assessment automatically refreshes for the new allocation.

## Schema and initialization

SQLAlchemy adds eight tables without resetting existing records:
`portfolio_assignments`, `investment_profiles`, `portfolio_accounts`,
`portfolio_holdings`, `portfolio_market_history`, `portfolio_assessments`,
`portfolio_rebalance_proposals`, `portfolio_history`.

Allocation columns store domestic stocks, domestic bonds and foreign equities as
integer millionths. Database CHECK constraints enforce nonnegative weights totaling
1,000,000; API Decimal validation accepts fractions totaling one with six decimal
places. Foreign holdings are equities in this initial three-bucket universe, so they
are not also counted in domestic stocks. Cash is outside the modeled investment
basket and remains in the existing finance tracker. Holdings conserve the account
value exactly in cents. Unsupported real instruments require a future import flow.

The initialized local database contains 500 modeled portfolios and 183 market
observations (61 month ends for three buckets). Generation is deterministic and
idempotent. Newly imported funded synthetic tracker clients initialize when the
portfolio directory is read. Accounts and price observations are not overwritten.
New real customers or clients without funded tracker data are not fabricated.
Existing users, customer records, finance snapshots, credit runs and decisions
were fingerprinted before/after initialization and were unchanged.

## Calculations and data limits

Market history is **synthetic**, using correlated monthly return factors and a
seeded downturn. Holdings start with tracker portfolio value/equity allocation;
a modeled portion of equities is foreign. Questionnaire answers are synthetic,
not inferred client preferences. Manager edits remain prototype assumptions.
No Lab Package files are read, no real market-data provider is connected and no
actual client returns are claimed.

Python computes monthly constant-mix total/annualized returns, annualized sample
covariance risk, drawdown including initial capital, and a same-window benchmark
(45% domestic stocks / 40% bonds / 15% foreign equities). Index paths start at 100.
These are gross historical modeled results, not realized performance or forecasts.
Actual contribution/withdrawal-adjusted returns cannot be calculated without an
account cash-flow feed. Tracker savings contributions are not portfolio deposits.
The history tab labels these distinctions and does not infer actual trading behavior.

Capacity uses emergency funds, income stability, debt-service burden and surplus.
The applicable volatility budget is the minimum of capacity, stated tolerance,
horizon and liquidity constraints. Prototype budgets and concentration limits are
versioned in `portfolio-risk-v1`; they are not a validated suitability assessment.
Automatic proposals search 5% allocation increments, prefer low turnover when the
historical return goal is feasible, otherwise maximize modeled historical return
within the risk budget. No future-return promise or performance optimization
claim is made; no risk is added beyond the budget to chase a return goal.
Estimated costs are a disclosed synthetic 0.10% of one-way turnover, deducted on
approval. Taxes, tax lots and actual brokerage fees are unavailable.

## Authorization and integrity

Only `portfolio_manager` with the database's `staff.portfolio` grant may use
individual-client routes. Self-assignment cannot take another manager's client;
the assignment primary key and SQLite write transaction serialize competing claims.
There is no public reassignment endpoint. Marketing/customer/other staff sessions
cannot read or change individual portfolios. Existing aggregate suppression stays
at five. Every read/assignment/assessment/proposal/approval is audited.

Approval checks ownership, portfolio revision and a fingerprint of financial,
profile and market context. Stale proposals return 409. Already approved proposals
are idempotent. Portfolio histories, assessments and assignments are append-only
at database level. The AI has no assignment/approval/trading tool and evidence is
rechecked after its network call. Bessie receives a summary and pending proposal,
not client identities, passwords or every chart point.

## API

All routes use the existing Bearer session under `/staff/portfolio`:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /clients | Assigned client queue |
| GET | /unassigned?search= | Minimal unassigned directory, up to 200 matches |
| POST | /assignments | Self-assign `{client_id}` |
| GET | /clients/{id} | Assigned client's holdings, profile and history |
| PUT | /clients/{id}/profile | Update prototype investment assumptions |
| POST | /clients/{id}/assessments | Persist a calculated assessment |
| POST | /clients/{id}/proposals | Generate/preview with rationale and optional allocations |
| POST | /clients/{id}/proposals/{proposal}/approve | Explicit simulated approval and rationale |

`POST /staff/assistant` uses `feature_id: staff.portfolio`, `agent: bessie` and
`resource_id` equal to the selected client ID. No resource means permitted aggregates.

## Checks

Backend tests cover client isolation, forbidden roles, assignment collisions,
allocation API/database constraints, covariance/drawdown math, unit formatting,
proposal approval/staleness/idempotency, immutability and scoped Bessie evidence.
UI tests exercise assignment, selected-client assistant context, failure reporting
and explicit approval confirmation. All tests use isolated databases and mocked AI.

Verification: the broader backend run passed 113 tests (195 archived tests skipped).
The final portfolio run passed all 19 tests, including the additional zero-equity
regression. All 20 frontend tests, TypeScript, production build, backend lint and
new UI/test lint passed. A live NVIDIA request with entirely synthetic portfolio
metrics passed evidence validation using bessie-v4. No real client data was sent
in that probe. UI flows were tested with React Testing Library; no manual browser
visual review was performed.

Profile-save correction: profile changes and their recalculated assessment are
atomic; a calculation failure rolls the profile change back. The profile endpoint
returns the profile plus `saved`, `revision` and `assessment`. The UI shows pending,
inline success/error states and updated risk budget, return goal and review flags.
Changing preferences does not invent a new historical return.

Profile-aligned preview: assessments include separate financial-capacity,
stated-tolerance, horizon and liquidity limits, plus binding limit(s). Horizon
bands remain under 36 months = 6%, 36–83 months = 12%, and 84+ months = 20% before
other constraints. A short horizon can keep the effective risk budget unchanged
when tolerance rises. The UI explains this explicitly and shows a read-only
profile-aligned allocation, metrics and a third chart series, using the same
feasible-mix search as automatic proposals. This is a synthetic historical replay,
not an automatic change of holdings or a future forecast. If current weights
already match the preview, the UI explains overlapping curves. Save the profile
or run assessment to refresh older records. Tests cover changed previews/curves
when a binding budget changes, and unchanged previews under the same horizon cap.

Rebalance editor correction: custom percentage edits invalidate the displayed
comparison and clear approval confirmation. Preview my allocation sends exactly
those weights; the automatic generator intentionally uses the investment profile.
The editor selects the proposal returned by that request instead of falling back
to an older entry from history. Rejections are shown inline with the draft retained.
Unchanged allocations are labeled no-change, zero-value trade rows are hidden and
approval is unavailable; the backend rejects no-change approval with 409.
Verification: all 25 portfolio tests and all 24 frontend tests passed, as did
TypeScript, backend/new-UI lint and production build.

Custom preview versus approval: any structurally valid allocation totaling one can
now be previewed, even if volatility or concentration exceeds policy. The response
retains the requested weights and includes `approval_allowed` and structured
`constraint_violations` with actual/limit values. Such previews are visibly labeled
preview-only; confirmation and approval are disabled. The approval API independently
recalculates proposed risk/concentration using current context and returns 422 if
limits are exceeded, even if stored display metadata incorrectly permits approval.
Invalid totals/weights and incomplete required financial data remain errors.
Custom input percentages are preserved; only automatic generation replaces them
with its generated allocation. This supersedes the earlier preview-time policy
rejection; the risk limits remain enforced at approval.

Portfolio manager navigation now uses Home, Portfolio, Benefits and Activity.
Learn/Wilbur is removed for this role at both database-grant and API levels;
Bessie remains the employee assistant. Existing roles migrate on the next backend
request without restoring any explicitly revoked permission. Other staff roles
retain their existing workspaces.

`GET /staff/portfolio/activity` returns only the signed-in manager's portfolio
assignment, assessment, profile-edit, preview, simulated approval and blocked
approval events for clients still assigned to that manager. Optional `action`
filters the supported event type; `limit` is 1–500 (default 100). The frontend
shows newest entries with filter controls and expandable evidence. Preview events
are distinguished from applied simulated changes. Credit analyst Activity is
unchanged. Bessie can explain the manager's recent authorized activity.

Activity verification: 123 backend tests passed (195 archived tests skipped),
all 28 frontend tests passed, and TypeScript, backend/new-component lint and
production build passed. Tests cover another manager's event isolation, event
filtering, removal of Wilbur access and preserving revoked DB grants during migration.
