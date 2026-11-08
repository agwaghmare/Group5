-- Gold views use security_invoker so the caller's RLS applies (customers see only their own rows).
SET search_path = finpilot, public;

CREATE VIEW gold_monthly_cashflow WITH (security_invoker = true, security_barrier = true) AS
SELECT customer_id,
       date_trunc('month', posted_date)::date AS month,
       coalesce(sum(amount) FILTER (WHERE flow_class = 'income'), 0)::numeric(14,2) AS income,
       coalesce(sum(amount) FILTER (WHERE flow_class = 'expense' AND category NOT LIKE 'debt_payment%'), 0)::numeric(14,2)
           AS consumption_spending,
       coalesce(sum(amount) FILTER (WHERE flow_class = 'expense' AND category IN
           ('rent','utilities','insurance','telecom','groceries','healthcare','fuel')), 0)::numeric(14,2) AS essential_spending,
       coalesce(sum(amount) FILTER (WHERE flow_class = 'expense' AND category NOT LIKE 'debt_payment%'
           AND category NOT IN ('rent','utilities','insurance','telecom','groceries','healthcare','fuel')), 0)::numeric(14,2)
           AS discretionary_spending,
       coalesce(sum(amount) FILTER (WHERE flow_class = 'expense' AND category LIKE 'debt_payment%'
           AND category <> 'debt_payment_credit_card'), 0)::numeric(14,2) AS debt_payments,
       -- card payments settle spending already counted as consumption at purchase time: never added to outflow
       coalesce(sum(amount) FILTER (WHERE category = 'debt_payment_credit_card'), 0)::numeric(14,2) AS card_settlements,
       coalesce(sum(amount) FILTER (WHERE flow_class = 'internal_transfer' AND transaction_type = 'transfer_out'
           AND account_type = 'checking' AND category IN ('savings_transfer','retirement_contribution')), 0)::numeric(14,2)
           AS savings_transfers_out,
       coalesce(sum(balance_change) FILTER (WHERE flow_class = 'external_transfer'), 0)::numeric(14,2) AS external_net,
       count(*) AS transaction_count
  FROM pnc_transactions
 GROUP BY customer_id, date_trunc('month', posted_date)::date;

GRANT SELECT ON gold_monthly_cashflow TO app_customer;
