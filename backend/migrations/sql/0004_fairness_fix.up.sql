-- 0004: fix ambiguous column reference (OUT parameter "n" vs column) in compliance.fairness_report.
CREATE OR REPLACE FUNCTION compliance.fairness_report(p_policy_version integer, p_min_group integer DEFAULT 5)
RETURNS TABLE (group_label text, n integer, meets integer, refer integer, does_not_meet integer,
               insufficient integer, meets_rate numeric, ratio_vs_highest numeric, flag text, suppressed boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = finpilot, compliance, public AS $$
#variable_conflict use_column
BEGIN
  IF cur_role() NOT IN ('compliance_analyst') THEN
    RAISE EXCEPTION 'fairness_report requires compliance_analyst' USING ERRCODE = 'insufficient_privilege';
  END IF;
  PERFORM _audit(cur_actor(), cur_role(), 'pnc', 'fairness.report', 'policy_v' || p_policy_version, NULL, NULL,
                 'allowed', false, cur_request(), '{}');
  RETURN QUERY
  WITH latest AS (
    SELECT DISTINCT ON (r.prospect_id) r.prospect_id, r.outcome FROM credit_research_runs r
     WHERE r.policy_version = p_policy_version ORDER BY r.prospect_id, r.run_at DESC),
  agg AS (
    SELECT p.group_label AS g, count(*)::integer AS n,
           count(*) FILTER (WHERE l.outcome = 'MEETS_POLICY')::integer AS meets,
           count(*) FILTER (WHERE l.outcome = 'REFER')::integer AS refer,
           count(*) FILTER (WHERE l.outcome = 'DOES_NOT_MEET')::integer AS dnm,
           count(*) FILTER (WHERE l.outcome = 'INSUFFICIENT_DATA')::integer AS insuf
      FROM latest l JOIN prospect_protected p USING (prospect_id) GROUP BY p.group_label),
  rated AS (SELECT a.*, a.meets::numeric / nullif(a.n, 0) AS rate FROM agg a),
  best AS (SELECT max(rate) AS top FROM rated WHERE n >= p_min_group)
  SELECT r.g, r.n,
         CASE WHEN r.n < p_min_group THEN NULL ELSE r.meets END, CASE WHEN r.n < p_min_group THEN NULL ELSE r.refer END,
         CASE WHEN r.n < p_min_group THEN NULL ELSE r.dnm END, CASE WHEN r.n < p_min_group THEN NULL ELSE r.insuf END,
         CASE WHEN r.n < p_min_group THEN NULL ELSE round(r.rate, 4) END,
         CASE WHEN r.n < p_min_group OR b.top IS NULL OR b.top = 0 THEN NULL ELSE round(r.rate / b.top, 4) END,
         CASE WHEN r.n < p_min_group THEN 'suppressed_small_group'
              WHEN b.top IS NULL OR b.top = 0 THEN 'not_computable'
              WHEN r.rate / b.top < 0.80 THEN 'review_ratio_below_0.80_illustrative'
              ELSE 'ok' END,
         r.n < p_min_group
    FROM rated r CROSS JOIN best b ORDER BY r.g;
END $$;
