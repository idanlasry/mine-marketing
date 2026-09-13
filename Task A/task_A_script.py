# %%
"""Task A — rule template.

Shared queries for the rule-by-rule pass (INVESTIGATION.md "Rule impact — method").
Template only: no rule sections, no results. Set RULE, then run the cells below —
or from the repo root: uv run python .claude/skills/rule-analysis/run_rule.py R04

Five answers per rule:
  1. what it did          BLOCK_A
  2. stopped the bleeding K_BLEEDING
  3. vs peers + missed    K_PEERS
  4. impact $ + verdict   K_IMPACT, K_IMPACT_DECISIONS
  5. data issues          K_ISSUES

Previous versions: Archive/task_A_script_v1.py (exploration, R04 method v1),
Archive/task_A_script_v2.py (Block B, age x ROI-band peers).
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
# ?   adset x date); rule_executions / metadata have no duplicates.
# ? rule totals can't be added across rules (overlapping decisions count for both).

# %% TEMPLATE — shared queries (run this cell first; nothing executes here)
RULE = "R__"  # set before running, e.g. "R04"

# ? each rule's condition as the engine ran it (rule_executions.condition_name), checked on the
# ?   day's end-of-day numbers. R05 / R06 condition_name differs from rule_name — the engine's
# ?   numbers at the action fit condition_name, so that is used.
# ?   columns: age (spend_day_no), budget (metadata daily_budget / 100), usage (spend / budget),
# ?   roi (today), profit (today), total_profit and positive_days (this week only, up to the day).
# ?   thresholds are inclusive (>= / <=): the engine fires on the limits.
CONDITIONS = {
    "R01": "age >= 5",
    "R02": "roi > -0.30 AND roi <= -0.10",
    "R03": "positive_days = 0 AND age > 2",
    "R04": "age = 1 AND usage >= 0.35 AND roi <= -0.50",
    "R05": "profit <= -1 AND usage >= 0.15",                             # name: Total Profit <= -2.5$
    "R06": "profit <= -1.25 AND age <= 3 AND total_profit <= -3",        # name: total profit <= -4$
    "R07": "roi >= -0.50 AND budget > 65",
    "R08": "age = 4",
    "R09": "FALSE",  # Turn ON "automation mistake": not a performance condition, no replay
    "R10": "roi > -0.10 AND roi <= 0.05 AND budget >= 100",
    "R11": "positive_days = 0 AND age > 3",
    "R12": "roi <= -0.50 AND budget <= 65",
}
qr = lambda sql: q(sql.replace("@COND", CONDITIONS.get(RULE, "FALSE")).replace("@RULE", RULE))

# ? Answer 1 — what the rule did, by action_date. Every day with any firing, incl. fail-only days.
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

# ? shared CTEs.
# ?   p   = daily performance per adset
# ?   f   = p + the columns the rule conditions use
# ?   lat = what each adset-day was followed by: later days until 06-12
# ?   dec = this rule's decisions (B1, B2: first SUCCESS firing of the adset-day)
BASE_CTE = """
WITH p AS (
  SELECT adset_id, account_name, CAST(date AS DATE) dt,
         SUM(spend) spend, SUM(IFNULL(revenue, 0)) rev, MAX(spend_day_no) sdn,
         SUM(IFNULL(fb_conversions, 0)) fb, SUM(IFNULL(estimated_conversions, 0)) ec
  FROM $.performance_scoped GROUP BY 1, 2, 3
),
f AS (
  SELECT p.adset_id, p.account_name, p.dt, p.spend, p.rev, p.fb, p.ec,
    p.sdn age, b.budget, SAFE_DIVIDE(p.spend, b.budget) usage,
    SAFE_DIVIDE(p.rev, p.spend) - 1 roi, p.rev - p.spend profit,
    SUM(p.rev - p.spend) OVER w total_profit,
    SUM(IF(p.spend > 0 AND p.rev > p.spend, 1, 0)) OVER w positive_days
  FROM p LEFT JOIN (SELECT adset_id, daily_budget / 100 budget FROM $.metadata_scoped) b
    ON b.adset_id = p.adset_id
  WINDOW w AS (PARTITION BY p.adset_id ORDER BY p.dt ROWS UNBOUNDED PRECEDING)
),
lat AS (
  SELECT f.adset_id, f.dt, DATE_DIFF(DATE '2026-06-12', f.dt, DAY) days_left,
    IFNULL(SUM(n.spend), 0) later_spend, IFNULL(SUM(n.rev - n.spend), 0) later_profit,
    COUNTIF(n.spend > 0) later_spend_days,
    IFNULL(SUM(n.fb), 0) later_fb, IFNULL(SUM(n.ec), 0) later_ec,
    IFNULL(SUM(IF(n.spend = 0, n.fb, 0)), 0) later_fb_no_spend,
    IFNULL(SUM(IF(n.spend = 0, n.ec, 0)), 0) later_ec_no_spend
  FROM f LEFT JOIN p n ON n.adset_id = f.adset_id AND n.dt > f.dt
  GROUP BY 1, 2, 3
),
fo AS (
  SELECT *, CAST(action_date AS DATE) ad FROM $.rule_executions_scoped
  WHERE rule_id = '@RULE' AND response = 'SUCCESS'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY adset_id, action_date ORDER BY action_time) = 1
),
oth AS (
  SELECT DISTINCT adset_id, CAST(action_date AS DATE) ad FROM $.rule_executions_scoped
  WHERE rule_id != '@RULE' AND response = 'SUCCESS'
),
-- peers and missed: adsets this rule never acted on, on the first day they matched its condition
m AS (
  SELECT f.* FROM f
  WHERE f.spend > 0 AND IFNULL((@COND), FALSE)
    AND f.adset_id NOT IN (SELECT adset_id FROM fo)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY f.adset_id ORDER BY f.dt) = 1
),
grp AS (
  SELECT '1 acted by @RULE' grp, f.* FROM f JOIN fo ON fo.adset_id = f.adset_id AND fo.ad = f.dt
  UNION ALL
  SELECT CASE WHEN m.account_name != 'ACC-04' THEN '2 peers: 5 no-rule accounts'
              WHEN EXISTS (SELECT 1 FROM oth WHERE oth.adset_id = m.adset_id AND oth.ad = m.dt)
                THEN '4 ACC-04 missed, another rule acted'
              ELSE '3 ACC-04 missed, no rule acted' END, m.*
  FROM m
  WHERE m.account_name = 'ACC-04' OR m.dt < DATE '2026-06-12'  -- peers need later days to observe
),
g AS (SELECT grp.*, lat.* EXCEPT (adset_id, dt, later_fb, later_ec, later_fb_no_spend, later_ec_no_spend)
      FROM grp JOIN lat USING (adset_id, dt)),
peer AS (
  SELECT COUNT(*) peer_adsets, SAFE_DIVIDE(SUM(later_profit), SUM(days_left)) peer_profit_per_day
  FROM g WHERE grp LIKE '2%'
)"""

# ? Answer 2 — did it stop the bleeding? The acted adsets: profit before the action, the rest of
# ?   that day (spend that still came through), and the later days. Before = first SUCCESS firing (B2, B8).
K_BLEEDING = BASE_CTE + """
SELECT COUNT(*) decisions, COUNT(DISTINCT fo.adset_id) adsets,
  ROUND(SUM(fo.spend_at_action), 2) spend_before,
  ROUND(SUM(fo.spend_at_action * fo.today_roi_at_action), 2) profit_before,
  ROUND(SAFE_DIVIDE(SUM(fo.spend_at_action * fo.today_roi_at_action), SUM(fo.spend_at_action)), 3) roi_before,
  ROUND(SUM(f.spend - fo.spend_at_action), 2) spend_rest_of_day,
  ROUND(SUM(f.profit - fo.spend_at_action * fo.today_roi_at_action), 2) profit_rest_of_day,
  ROUND(SUM(l.later_spend), 2) spend_later_days,
  ROUND(SUM(l.later_profit), 2) profit_later_days,
  ROUND(SAFE_DIVIDE(SUM(l.later_profit), SUM(l.later_spend)), 3) roi_later_days,
  COUNTIF(l.later_spend_days > 0) adsets_spent_later,
  -- conversions: Meta (fb) vs the internal model (est). Action day = whole day (fb isn't logged at the action).
  -- "no spend" = later days with $0 spend: anything reported there arrived late (the delay).
  SUM(f.fb) fb_conv_action_day, ROUND(SUM(f.ec), 2) est_conv_action_day,
  SUM(l.later_fb) fb_conv_later_days, ROUND(SUM(l.later_ec), 2) est_conv_later_days,
  SUM(l.later_fb_no_spend) fb_conv_later_no_spend, ROUND(SUM(l.later_ec_no_spend), 2) est_conv_later_no_spend
FROM fo
LEFT JOIN f   ON f.adset_id = fo.adset_id AND f.dt = fo.ad
LEFT JOIN lat l ON l.adset_id = fo.adset_id AND l.dt = fo.ad
"""

# ? Answer 3 — peers and missed. One row per group:
# ?   1 acted by the rule (its decisions)
# ?   2 peers: adsets in the 5 accounts with no rules that matched the condition (first matching day)
# ?   3 ACC-04 adsets that matched but no rule acted that day  -> missed
# ?   4 ACC-04 adsets that matched, this rule didn't act, another rule did
# ?   "later" = the days after, until 06-12. profit_per_day_left = later profit / days left in the week.
K_PEERS = BASE_CTE + """
SELECT grp, COUNT(*) adsets, ROUND(SUM(spend), 2) day_spend, ROUND(SUM(profit), 2) day_profit,
  COUNTIF(later_spend_days > 0) spent_later, COUNTIF(later_profit > 0) profitable_later,
  ROUND(SUM(later_spend), 2) later_spend, ROUND(SUM(later_profit), 2) later_profit,
  ROUND(SAFE_DIVIDE(SUM(later_profit), SUM(later_spend)), 3) later_roi,
  ROUND(SAFE_DIVIDE(SUM(later_profit), SUM(days_left)), 3) profit_per_day_left
FROM g GROUP BY grp ORDER BY grp
"""

# ? Answer 4 — impact, one $ figure per decision. + = saved (would have lost), - = missed income.
# ?   Failed runs = $0 (not listed).
# ?   Turn OFF:   -(peer profit per day left x days left). Peers = group 2 above.
# ?               days left = whole days after the action until 06-12.
# ?   Budget cut: -(budget removed per day x ROI after the cut x days left).
# ?               days left = whole days until 06-12 or the same rule's next decision (B4)
# ?               + the unspent share of the action day (1 - spend_at_action / budget).
# ?               ROI after the cut = rest of the action day + following days in that window.
IMPACT_BASE = BASE_CTE + """,
dec AS (
  SELECT fo.adset_id, fo.ad, fo.action_name, fo.total_days_at_action,
         fo.current_budget_from_fb budget, fo.set_budget, fo.spend_at_action s0,
         fo.spend_at_action * (1 + fo.today_roi_at_action) r0,
         UPPER(fo.action_name) LIKE 'TURN OFF%' is_off, UPPER(fo.action_name) LIKE 'DECREASE%' is_cut,
         IFNULL(DATE_SUB(LEAD(fo.ad) OVER (PARTITION BY fo.adset_id ORDER BY fo.ad), INTERVAL 1 DAY),
                DATE '2026-06-12') end_d
  FROM fo
),
aft AS (
  SELECT d.adset_id, d.ad, SUM(a.spend) - ANY_VALUE(d.s0) s_after, SUM(a.rev) - ANY_VALUE(d.r0) r_after,
         COUNTIF(a.dt > d.ad AND a.spend > 0) spend_days_after
  FROM dec d JOIN p a ON a.adset_id = d.adset_id AND a.dt BETWEEN d.ad AND d.end_d
  GROUP BY 1, 2
),
-- another rule turned the adset off the same day: a cut then removes budget that won't be spent
off_oth AS (
  SELECT DISTINCT adset_id, CAST(action_date AS DATE) ad FROM $.rule_executions_scoped
  WHERE rule_id != '@RULE' AND response = 'SUCCESS' AND UPPER(action_name) LIKE 'TURN OFF%'
),
z AS (
  SELECT d.*, o.adset_id IS NOT NULL off_by_other_rule,
    IF(d.is_off, peer.peer_adsets, NULL) peer_adsets, IF(d.is_off, peer.peer_profit_per_day, NULL) peer_profit_per_day,
    IF(d.is_off, DATE_DIFF(DATE '2026-06-12', d.ad, DAY),
       IFNULL(a.spend_days_after, 0) + GREATEST(0, 1 - IFNULL(SAFE_DIVIDE(d.s0, d.budget), 1))) days_left,
    IF(d.is_cut, d.budget - d.set_budget, NULL) budget_cut,
    IF(d.is_cut, SAFE_DIVIDE(a.r_after, a.s_after) - 1, NULL) roi_after_cut
  FROM dec d CROSS JOIN peer
  LEFT JOIN aft a ON a.adset_id = d.adset_id AND a.ad = d.ad
  LEFT JOIN off_oth o ON o.adset_id = d.adset_id AND o.ad = d.ad
),
imp AS (
  SELECT z.*,
    CASE WHEN is_off THEN -peer_profit_per_day * days_left
         WHEN is_cut AND off_by_other_rule THEN 0
         WHEN is_cut THEN -budget_cut * roi_after_cut * days_left END impact
  FROM z
)"""

# ? Impact per decision, most missed income first. The top rows are candidate
# ?   "a competent human wouldn't do this" cases (Task A question 2).
K_IMPACT_DECISIONS = IMPACT_BASE + """
SELECT adset_id, CAST(ad AS STRING) action_date, action_name, total_days_at_action age_days,
  ROUND(days_left, 2) days_left, peer_adsets, ROUND(peer_profit_per_day, 3) peer_profit_per_day,
  ROUND(budget_cut, 2) budget_cut, ROUND(roi_after_cut, 3) roi_after_cut, ROUND(impact, 2) impact
FROM imp ORDER BY impact
"""

# ? Impact — rule total and verdict.
# ?   verdict: 'too small to matter' when |net| < 1% of ACC-04's week spend; else right (net > 0) / wrong.
K_IMPACT = IMPACT_BASE + """
SELECT COUNT(*) decisions, ANY_VALUE(peer_adsets) peer_adsets,
  COUNTIF(impact > 0) saved_calls, COUNTIF(impact < 0) missed_income_calls, COUNTIF(impact IS NULL) not_computable,
  ROUND(SUM(IF(impact > 0, impact, 0)), 2) saved,
  ROUND(SUM(IF(impact < 0, impact, 0)), 2) missed_income,
  ROUND(SUM(impact), 2) net_impact,
  ROUND((SELECT SUM(spend) FROM p WHERE account_name = 'ACC-04') * 0.01, 2) materiality_1pct,
  CASE WHEN COUNT(*) = 0 OR SUM(impact) IS NULL THEN 'no impact'
       WHEN ABS(SUM(impact)) < (SELECT SUM(spend) FROM p WHERE account_name = 'ACC-04') * 0.01 THEN 'too small to matter'
       WHEN SUM(impact) > 0 THEN 'right' ELSE 'wrong' END verdict
FROM imp
"""

# ? Answer 5 — data issues, the same checklist for every rule.
# ?   fails_condition_at_action: the engine's own numbers at the action (total_days_at_action,
# ?     current_budget_from_fb, today_roi_at_action, spend_at_action) don't meet the condition.
# ?   not_checkable_at_action: the condition needs total profit or positive days, which the engine doesn't log.
K_ISSUES = BASE_CTE + """,
rx AS (SELECT * FROM $.rule_executions_scoped WHERE rule_id = '@RULE'),
fx AS (
  SELECT f.*, fo.current_budget_from_fb, fo.spend_at_action, fo.action_name, fo.action_time,
         fo.total_days_at_action, fo.ad
  FROM fo LEFT JOIN f ON f.adset_id = fo.adset_id AND f.dt = fo.ad
),
eng AS (
  SELECT total_days_at_action age, current_budget_from_fb budget,
         SAFE_DIVIDE(spend_at_action, current_budget_from_fb) usage, today_roi_at_action roi,
         spend_at_action * today_roi_at_action profit,
         CAST(NULL AS FLOAT64) total_profit, CAST(NULL AS INT64) positive_days
  FROM fo
)
SELECT
  (SELECT COUNT(*) FROM rx)                                                         firings,
  (SELECT COUNTIF(response != 'SUCCESS') FROM rx)                                   failed_runs,
  (SELECT COUNT(*) - COUNT(DISTINCT CONCAT(adset_id, action_date)) FROM rx)         repeat_firings,
  (SELECT COUNTIF(REGEXP_REPLACE(condition_name, r'\\s', '') != REGEXP_REPLACE(rule_name, r'\\s', '')) FROM rx)
                                                                                    name_differs_from_condition,
  (SELECT COUNT(*) FROM fx)                                                         decisions,
  (SELECT COUNTIF((@COND) IS FALSE) FROM eng)                                       fails_condition_at_action,
  (SELECT COUNTIF((@COND) IS NULL) FROM eng)                                        not_checkable_at_action,
  (SELECT COUNTIF(total_days_at_action != age) FROM fx)                             engine_age_differs,
  (SELECT COUNTIF(ABS(budget - current_budget_from_fb) > 0.01) FROM fx)             budget_differs_from_metadata,
  (SELECT COUNTIF(ad != DATE(CAST(action_time AS TIMESTAMP))) FROM fx)              rollover,
  (SELECT ROUND(SUM(IF(UPPER(action_name) LIKE 'TURN OFF%', spend - spend_at_action, 0)), 2) FROM fx)
                                                                                    spend_after_turn_off
"""

# ? ACC-04 leftovers (not per rule) — every ACC-04 adset-day with spend that no rule acted on,
# ?   split into losers (profit < 0) and winners, and whether it matched any rule's condition.
# ?   R09 has no condition and is left out.
_match = ",\n    ".join(f"IF(IFNULL(({c}), FALSE), '{r}', NULL)" for r, c in CONDITIONS.items() if c != "FALSE")
LEFT_CTE = """
WITH p AS (
  SELECT adset_id, account_name, CAST(date AS DATE) dt,
         SUM(spend) spend, SUM(IFNULL(revenue, 0)) rev, MAX(spend_day_no) sdn
  FROM $.performance_scoped GROUP BY 1, 2, 3
),
f AS (
  SELECT p.adset_id, p.account_name, p.dt, p.spend, p.rev,
    p.sdn age, b.budget, SAFE_DIVIDE(p.spend, b.budget) usage,
    SAFE_DIVIDE(p.rev, p.spend) - 1 roi, p.rev - p.spend profit,
    SUM(p.rev - p.spend) OVER w total_profit,
    SUM(IF(p.spend > 0 AND p.rev > p.spend, 1, 0)) OVER w positive_days
  FROM p LEFT JOIN (SELECT adset_id, daily_budget / 100 budget FROM $.metadata_scoped) b
    ON b.adset_id = p.adset_id
  WINDOW w AS (PARTITION BY p.adset_id ORDER BY p.dt ROWS UNBOUNDED PRECEDING)
),
acted AS (
  SELECT DISTINCT adset_id, CAST(action_date AS DATE) dt FROM $.rule_executions_scoped WHERE response = 'SUCCESS'
),
left_ AS (
  SELECT f.*, ARRAY_TO_STRING([
    """ + _match + """
  ], ',') matched_rules
  FROM f LEFT JOIN acted a ON a.adset_id = f.adset_id AND a.dt = f.dt
  WHERE f.account_name = 'ACC-04' AND f.spend > 0 AND a.adset_id IS NULL
),
b AS (
  SELECT *, CASE
      WHEN profit < 0 AND matched_rules != '' THEN '1 loser, matched a rule: missed'
      WHEN profit < 0                        THEN '2 loser, no rule covers it'
      WHEN matched_rules = ''                THEN '3 winner, no rule matched: rightly spared'
      ELSE                                        '4 winner, matched a rule: lucky miss' END bucket
  FROM left_
)"""

K_LEFTOVER = LEFT_CTE + """
SELECT bucket, COUNT(*) adset_days, COUNT(DISTINCT adset_id) adsets,
  ROUND(SUM(spend), 2) spend, ROUND(SUM(profit), 2) profit, ROUND(SAFE_DIVIDE(SUM(profit), SUM(spend)), 3) roi
FROM b GROUP BY ROLLUP (bucket) ORDER BY bucket IS NULL, bucket
"""

# ? which rules the missed losers matched (an adset-day can match several rules)
K_LEFTOVER_BY_RULE = LEFT_CTE + """
SELECT r rule, COUNTIF(profit < 0) loser_days, ROUND(SUM(IF(profit < 0, profit, 0)), 2) loser_profit,
  COUNTIF(profit >= 0) winner_days, ROUND(SUM(IF(profit >= 0, profit, 0)), 2) winner_profit
FROM b, UNNEST(SPLIT(matched_rules, ',')) r WHERE matched_rules != ''
GROUP BY r ORDER BY r
"""

K_LEFTOVER_TOP = LEFT_CTE + """
SELECT bucket, adset_id, CAST(dt AS STRING) dt, age, ROUND(budget, 2) budget, ROUND(spend, 2) spend,
  ROUND(roi, 3) roi, ROUND(profit, 2) profit, matched_rules
FROM b WHERE bucket LIKE '1%' OR bucket LIKE '2%'
QUALIFY ROW_NUMBER() OVER (PARTITION BY bucket ORDER BY profit) <= 5
ORDER BY bucket, profit
"""

# %% 1 — what the rule did
qr(BLOCK_A)

# %% 2 — did it stop the bleeding?
qr(K_BLEEDING)

# %% 3 — peers and missed
qr(K_PEERS)

# %% 4 — impact: rule total and verdict
qr(K_IMPACT)

# %% 4 — impact per decision, most missed income first
qr(K_IMPACT_DECISIONS)

# %% 5 — data issues
qr(K_ISSUES)

# %% ACC-04 leftovers — losers and winners no rule acted on
q(K_LEFTOVER)

# %% ACC-04 leftovers — by matched rule
q(K_LEFTOVER_BY_RULE)

# %% ACC-04 leftovers — 5 biggest losers per bucket
q(K_LEFTOVER_TOP)
