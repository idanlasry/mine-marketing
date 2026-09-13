# %%
"""Task A — rule template.

Shared queries for the rule-by-rule pass (INVESTIGATION.md "Rule impact — method").
Template only: no rule sections, no results. Set RULE, then run the cells below —
or from the repo root: uv run python .claude/skills/rule-analysis/run_rule.py R04

Previous version (exploration cells, R04 method-v1 cells): Archive/task_A_script_v1.py.
"""

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)

PROJECT, DATASET = "first-proj001", "mine_marketing"
client = bigquery.Client(project=PROJECT)

# ? token is "$." not "$" so a regex anchor ($) inside a query survives
q = lambda sql: client.query(
    sql.replace("$.", f"`{PROJECT}.{DATASET}`.")
).to_dataframe()


# =============================================================================
#  RULE TEMPLATE
# =============================================================================
# ? dedup: reads *_scoped only. performance_scoped = SELECT DISTINCT (4947 -> 4875, one row per
# ?   adset x date); rule_executions / metadata have no duplicates; buyer_actions duplicates
# ?   all fall outside scope (buyer_actions_scoped 715 rows, all distinct).
# ? totals come from GROUP BY ROLLUP, so adsets are distinct across the week and overlaps are a
# ?   union — not sums. Rule totals can't be added across rules (overlaps count for both).

# %% TEMPLATE — shared queries (run this cell first; nothing executes here)
RULE = "R__"  # set before running, e.g. "R04"
qr = lambda sql: q(sql.replace("@RULE", RULE))

# ? Block A — what the rule did, by action_date. Every day with any firing, incl. fail-only days.
BLOCK_A = """
WITH rx AS (SELECT *, CAST(action_date AS DATE) ad FROM $.rule_executions_scoped),
r AS (SELECT * FROM rx WHERE rule_id = '@RULE'),
-- B1: decision = rule x adset x action_date with at least one SUCCESS
dec AS (
  SELECT adset_id, ad, MIN(CAST(action_time AS TIMESTAMP)) first_t
  FROM r WHERE response = 'SUCCESS' GROUP BY 1, 2
),
-- B5: other rules that succeeded on the same adset-day; B6: rollover of the first SUCCESS firing
dec_x AS (
  SELECT dec.adset_id, dec.ad, dec.ad != DATE(dec.first_t) rollover,
         STRING_AGG(DISTINCT CONCAT(o.rule_id, '@', o.adset_id), ',') overlap_tags
  FROM dec
  LEFT JOIN (SELECT DISTINCT rule_id, adset_id, ad FROM rx
             WHERE response = 'SUCCESS' AND rule_id != '@RULE') o
    ON o.adset_id = dec.adset_id AND o.ad = dec.ad
  GROUP BY 1, 2, 3
),
agg AS (
  SELECT r.ad,
    COUNT(DISTINCT IF(x.adset_id IS NOT NULL, CONCAT(r.adset_id, CAST(r.ad AS STRING)), NULL))        decisions,
    COUNT(*) - COUNT(DISTINCT CONCAT(r.adset_id, CAST(r.ad AS STRING)))                                repeat_firings,
    COUNTIF(r.response = 'SUCCESS')                                                                    success_runs,
    COUNTIF(r.response != 'SUCCESS')                                                                   failed_runs,
    COUNT(DISTINCT x.adset_id)                                                                         adsets,
    COUNT(DISTINCT IF(x.overlap_tags IS NOT NULL, CONCAT(r.adset_id, CAST(r.ad AS STRING)), NULL))     overlaps_n,
    STRING_AGG(DISTINCT x.overlap_tags, ',')                                                           overlapping_rules,
    COUNT(DISTINCT IF(x.rollover, CONCAT(r.adset_id, CAST(r.ad AS STRING)), NULL))                     rollover
  FROM r LEFT JOIN dec_x x ON x.adset_id = r.adset_id AND x.ad = r.ad
  GROUP BY ROLLUP (r.ad)
)
SELECT IFNULL(CAST(DATE_DIFF(ad, DATE '2026-06-06', DAY) + 1 AS STRING), 'total') day,
       CAST(ad AS STRING) date, * EXCEPT (ad)
FROM agg ORDER BY ad IS NULL, ad
"""

# ? Block B — money around the action, by action_date. Successful decisions only; blank on fail-only days.
BLOCK_B = """
WITH p AS (
  SELECT adset_id, CAST(date AS DATE) dt,
         SUM(spend) spend, SUM(IFNULL(revenue, 0)) rev, SUM(IFNULL(estimated_conversions, 0)) ec
  FROM $.performance_scoped GROUP BY 1, 2
),
days AS (SELECT DISTINCT CAST(action_date AS DATE) ad FROM $.rule_executions_scoped WHERE rule_id = '@RULE'),
-- B2: before = first SUCCESS firing of the adset-day
first_ok AS (
  SELECT *, CAST(action_date AS DATE) ad FROM $.rule_executions_scoped
  WHERE rule_id = '@RULE' AND response = 'SUCCESS'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY adset_id, action_date ORDER BY action_time) = 1
),
dec AS (
  SELECT adset_id, ad,
    LEAD(ad) OVER (PARTITION BY adset_id ORDER BY ad)                               next_ad,  -- B4
    CASE WHEN UPPER(action_name) LIKE 'TURN OFF%' THEN current_budget_from_fb - spend_at_action
         WHEN UPPER(action_name) LIKE 'DECREASE%' THEN current_budget_from_fb - set_budget
         WHEN UPPER(action_name) LIKE 'TURN ON%'  THEN -current_budget_from_fb END exposure, -- B3
    spend_at_action                                                                 s0,
    IFNULL(SAFE_DIVIDE(spend_at_action, today_cpa_at_action), 0)                    c0,       -- B7
    spend_at_action * (1 + today_roi_at_action)                                     r0        -- B8
  FROM first_ok
),
-- following days, stopping at the same rule's next decision on the adset (B4)
nxt AS (
  SELECT dec.adset_id, dec.ad, SUM(n.spend) s, SUM(n.ec) c, SUM(n.rev) r
  FROM dec JOIN p n
    ON n.adset_id = dec.adset_id AND n.dt > dec.ad AND n.dt < IFNULL(dec.next_ad, DATE '9999-12-31')
  GROUP BY 1, 2
),
x AS (
  SELECT dec.ad, dec.exposure, dec.s0, dec.c0, dec.r0,
    IFNULL(day.spend, 0) - dec.s0 s_day, IFNULL(day.ec, 0) - dec.c0 c_day, IFNULL(day.rev, 0) - dec.r0 r_day,
    IFNULL(nxt.s, 0) s_nxt, IFNULL(nxt.c, 0) c_nxt, IFNULL(nxt.r, 0) r_nxt
  FROM dec
  LEFT JOIN p day ON day.adset_id = dec.adset_id AND day.dt = dec.ad
  LEFT JOIN nxt   ON nxt.adset_id = dec.adset_id AND nxt.ad = dec.ad
),
agg AS (
  SELECT ad,
    ROUND(SUM(exposure), 2)                                                exposure,
    ROUND(SUM(s0), 2) spend_before, ROUND(SUM(c0), 2) conv_before, ROUND(SUM(r0), 2) rev_before,
    ROUND(SAFE_DIVIDE(SUM(r0), SUM(s0)) - 1, 3)                            roi_before,
    ROUND(SUM(s_day), 2) spend_after_day, ROUND(SUM(c_day), 2) conv_after_day, ROUND(SUM(r_day), 2) rev_after_day,
    ROUND(SAFE_DIVIDE(SUM(r_day), SUM(s_day)) - 1, 3)                      roi_after_day,
    ROUND(SUM(s_day + s_nxt), 2) spend_after_acc, ROUND(SUM(c_day + c_nxt), 2) conv_after_acc,
    ROUND(SUM(r_day + r_nxt), 2) rev_after_acc,
    ROUND(SAFE_DIVIDE(SUM(r_day + r_nxt), SUM(s_day + s_nxt)) - 1, 3)      roi_after_acc
  FROM x GROUP BY ROLLUP (ad)
),
k AS (SELECT ad FROM days UNION ALL SELECT CAST(NULL AS DATE))
SELECT IFNULL(CAST(DATE_DIFF(k.ad, DATE '2026-06-06', DAY) + 1 AS STRING), 'total') day,
       CAST(k.ad AS STRING) date, agg.* EXCEPT (ad)
FROM k LEFT JOIN agg ON IFNULL(agg.ad, DATE '1900-01-01') = IFNULL(k.ad, DATE '1900-01-01')
ORDER BY k.ad IS NULL, k.ad
"""

# ? daily performance per adset (shared by the peer and impact queries).
P_CTE = """
p AS (
  SELECT adset_id, account_name, CAST(date AS DATE) dt,
         SUM(spend) spend, SUM(IFNULL(revenue, 0)) rev, MAX(spend_day_no) sdn
  FROM $.performance_scoped GROUP BY 1, 2, 3
)"""

# ? peers — what similar adsets did when no rule touched them (the 5 accounts with no rules).
# ?   every adset-day with spend before 06-12, grouped by age (spend day 1 / 2-3 / 4+) and by how
# ?   the day went (ROI < -50% / ROI -50% to 0 / profitable). For each of the 9 groups:
# ?   keep_rate            = share of the remaining days in the week on which the adset still spent
# ?   profit_per_spend_day = profit on those later spend days / number of those days
PEERS_CTE = """
peers AS (
  SELECT age, grp, COUNT(*) adset_days,
         SAFE_DIVIDE(SUM(spend_days_after), SUM(days_after)) keep_rate,
         SAFE_DIVIDE(SUM(profit_after), SUM(spend_days_after)) profit_per_spend_day
  FROM (
    SELECT l.adset_id, l.dt,
           CASE WHEN l.sdn <= 1 THEN '1' WHEN l.sdn <= 3 THEN '2-3' ELSE '4+' END age,
           CASE WHEN l.rev >= l.spend THEN 'profitable'
                WHEN SAFE_DIVIDE(l.rev, l.spend) - 1 < -0.5 THEN 'ROI < -50%'
                ELSE 'ROI -50% to 0' END grp,
           DATE_DIFF(DATE '2026-06-12', l.dt, DAY) days_after,
           COUNTIF(n.spend > 0) spend_days_after,
           IFNULL(SUM(IF(n.spend > 0, n.rev - n.spend, 0)), 0) profit_after
    FROM p l LEFT JOIN p n ON n.adset_id = l.adset_id AND n.dt > l.dt
    WHERE l.account_name != 'ACC-04' AND l.spend > 0 AND l.dt < DATE '2026-06-12'
    GROUP BY 1, 2, 3, 4, 5
  ) GROUP BY 1, 2
)"""

# ? peer table — same for every rule; shown for reference.
K_PEERS = "WITH " + P_CTE + "," + PEERS_CTE + """
SELECT age, grp peer_group, adset_days, ROUND(keep_rate, 3) keep_rate,
       ROUND(profit_per_spend_day, 3) profit_per_spend_day
FROM peers ORDER BY age, peer_group
"""

# ? Impact — one $ figure per decision. + = saved (would have lost), - = missed income (would have earned).
# ?   Failed runs = $0 (not listed).
# ?   Budget cut: -(budget removed per day x ROI after the cut x days left)
# ?   Turn OFF:   -(peer profit per spend day x days left x peer keep rate)
# ?   days left   = whole days after the action until 06-12 or the same rule's next decision (B4)
# ?                 + the unspent share of the action day (1 - spend_at_action / budget).
# ?   peer group  = age at the action x ROI before (spend days before the action in the week;
# ?                 if none, the action day).
# ?   ROI after the cut = rest of the action day + following days in the window.
# ?   right call  = impact > 0.
IMPACT_BASE = "WITH " + P_CTE + "," + PEERS_CTE + """,
first_ok AS (
  SELECT *, CAST(action_date AS DATE) ad FROM $.rule_executions_scoped
  WHERE rule_id = '@RULE' AND response = 'SUCCESS'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY adset_id, action_date ORDER BY action_time) = 1
),
dec AS (
  SELECT adset_id, ad, action_name, total_days_at_action, current_budget_from_fb budget, set_budget,
         spend_at_action s0, spend_at_action * (1 + today_roi_at_action) r0,
         UPPER(action_name) LIKE 'TURN OFF%' is_off, UPPER(action_name) LIKE 'DECREASE%' is_cut,
         LEAD(ad) OVER (PARTITION BY adset_id ORDER BY ad) next_ad
  FROM first_ok
),
win AS (
  SELECT *, IFNULL(DATE_SUB(next_ad, INTERVAL 1 DAY), DATE '2026-06-12') end_d,
         GREATEST(0, 1 - IFNULL(SAFE_DIVIDE(s0, budget), 1)) rest_share
  FROM dec
),
hist AS (
  SELECT w.adset_id, w.ad, SUM(h.spend) spend_b, SUM(h.rev) rev_b, COUNT(*) hist_days
  FROM win w JOIN p h ON h.adset_id = w.adset_id AND h.dt < w.ad AND h.spend > 0
  GROUP BY 1, 2
),
aft AS (
  SELECT w.adset_id, w.ad, SUM(a.spend) - ANY_VALUE(w.s0) s_after, SUM(a.rev) - ANY_VALUE(w.r0) r_after
  FROM win w JOIN p a ON a.adset_id = w.adset_id AND a.dt BETWEEN w.ad AND w.end_d
  GROUP BY 1, 2
),
x AS (
  SELECT w.adset_id, w.ad, w.action_name, w.total_days_at_action, w.is_off, w.is_cut,
    CASE WHEN w.total_days_at_action <= 1 THEN '1' WHEN w.total_days_at_action <= 3 THEN '2-3' ELSE '4+' END age,
    DATE_DIFF(w.end_d, w.ad, DAY) + w.rest_share days_left,
    IFNULL(h.hist_days, 0) hist_days,
    IFNULL(h.spend_b, d0.spend) spend_b, IFNULL(h.rev_b, d0.rev) rev_b,
    IF(w.is_cut, w.budget - w.set_budget, NULL) budget_cut,
    IF(w.is_cut, SAFE_DIVIDE(a.r_after, a.s_after) - 1, NULL) roi_after_cut
  FROM win w
  LEFT JOIN hist h ON h.adset_id = w.adset_id AND h.ad = w.ad
  LEFT JOIN p d0   ON d0.adset_id = w.adset_id AND d0.dt = w.ad
  LEFT JOIN aft a  ON a.adset_id = w.adset_id AND a.ad = w.ad
),
y AS (
  SELECT x.*,
    IF(x.is_off, SAFE_DIVIDE(x.rev_b, x.spend_b) - 1, NULL) roi_before,
    IF(x.is_off, CASE WHEN x.rev_b >= x.spend_b THEN 'profitable'
                      WHEN SAFE_DIVIDE(x.rev_b, x.spend_b) - 1 < -0.5 THEN 'ROI < -50%'
                      ELSE 'ROI -50% to 0' END, NULL) peer_group
  FROM x
),
z AS (
  SELECT y.*, pr.profit_per_spend_day, pr.keep_rate,
    CASE WHEN y.is_off THEN -pr.profit_per_spend_day * y.days_left * pr.keep_rate
         WHEN y.is_cut THEN -y.budget_cut * y.roi_after_cut * y.days_left END impact
  FROM y LEFT JOIN peers pr ON pr.age = y.age AND pr.grp = y.peer_group
)
SELECT z.adset_id, CAST(z.ad AS STRING) action_date, z.action_name, z.total_days_at_action age_days, z.hist_days,
  ROUND(z.days_left, 2) days_left, ROUND(z.roi_before, 3) roi_before, z.peer_group,
  ROUND(z.profit_per_spend_day, 3) peer_profit_per_spend_day, ROUND(z.keep_rate, 3) peer_keep_rate,
  ROUND(z.budget_cut, 2) budget_cut, ROUND(z.roi_after_cut, 3) roi_after_cut,
  z.impact > 0 right_call, ROUND(z.impact, 2) impact
FROM z
"""

# ? Impact per decision, most missed income first. The top rows are candidate
# ?   "a competent human wouldn't do this" cases (Task A question 2).
K_IMPACT_DECISIONS = IMPACT_BASE + "ORDER BY impact"

# ? Impact — rule total.
K_IMPACT = """
SELECT COUNT(*) decisions, COUNTIF(right_call) right_calls, COUNTIF(NOT right_call) wrong_calls,
  COUNTIF(impact IS NULL) not_computable,
  ROUND(SUM(IF(impact > 0, impact, 0)), 2) saved,
  ROUND(SUM(IF(impact < 0, impact, 0)), 2) missed_income,
  ROUND(SUM(impact), 2) net_impact
FROM (""" + IMPACT_BASE + ")"

# %% Block A — what the rule did
qr(BLOCK_A)

# %% Block B — money around the action
qr(BLOCK_B)

# %% peers (same for every rule)
q(K_PEERS)

# %% Impact — rule total
qr(K_IMPACT)

# %% Impact — per decision, most missed income first
qr(K_IMPACT_DECISIONS)
