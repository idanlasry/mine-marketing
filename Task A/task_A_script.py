# %%
"""Task A / Step 1 — pull the working columns.

Three views on the scoped base from `task_a_recon.py` (CH.2), narrowed to the
columns the analysis uses. Views, not tables: fix the scope upstream and these
follow.
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


# %% rule_executions
# ! no `action` column exists here. `action_name` ("Turn OFF", "Increase Budget")
# ! is the one that matches auto_rules.action, so it is aliased to `action`.
q("""
CREATE OR REPLACE VIEW $.rx_sel AS
SELECT DISTINCT
       adset_id, action_date, action_time, rule_id,
       action_name AS action,
       old_budget, new_budget, set_budget, current_budget_from_fb,
       response, budget_level,
       -- what the engine saw at evaluation time (same-day, cumulative up to action_time)
       spend_at_action, today_roi_at_action, last_3_days_roi_at_action
FROM $.rule_executions_scoped
""")

# %% daily_adset_performance
q("""
-- * DEDUP: the 72 identical ACC-03 / 06-09 copies. Lossless, no tie-break.
CREATE OR REPLACE VIEW $.perf_sel AS
SELECT DISTINCT
       adset_id, date, spend, revenue, fb_conversions,
       estimated_conversions, spend_day_no, fb_ad_account_id
FROM $.performance_scoped
""")

# %% auto_rules
# * no adset_id in this table, so no _scoped view to sit on — 12-row lookup.
q("""
CREATE OR REPLACE VIEW $.rules_sel AS
SELECT rule_id, rule_name, action
FROM $.auto_rules
""")


# =============================================================================
#  EXEC SUMMARY — the week in one row
# =============================================================================

# %% week totals: spend, conversions, revenue, profit, roi, rule executions
# ? profit and roi recomputed from spend/revenue, not read from the file's columns
q("""
WITH perf AS (
  SELECT ROUND(SUM(spend), 2)                                   AS spend,
         SUM(fb_conversions)                                    AS fb_conv,
         ROUND(SUM(estimated_conversions), 1)                   AS est_conv,
         ROUND(SUM(revenue), 2)                                 AS revenue,
         ROUND(SUM(revenue) - SUM(spend), 2)                    AS profit,
         ROUND(SAFE_DIVIDE(SUM(revenue) - SUM(spend), SUM(spend)), 4) AS roi
  FROM $.perf_sel
),
rx AS (
  SELECT COUNT(*)                         AS rules_executed,
         COUNTIF(response = 'SUCCESS')    AS rules_succeeded,
         COUNTIF(response != 'SUCCESS')   AS rules_failed
  FROM $.rx_sel
)
SELECT * FROM perf CROSS JOIN rx
""")
# * spend $8,912 -> revenue $9,790 -> profit $878, ROI +9.9%. Thin but positive.
# * recomputed profit == file's profit column to the cent (0 row mismatches).
# * est_conv / fb_conv = 1.053: internal model credits 5% more than Meta.
# ! 214 executed but only 164 SUCCESS — 50 (23%) never happened. Quote 164.
# ! all 214 are ACC-04; the other 5 accounts ran with zero rules.
# ! daily spend peaks 06-07 ($1,739) and ends 06-12 at $843 (-52%). Mandate is grow.
# ? 06-12 is the freshest day — revenue may not be fully settled yet.

# %% same totals per day, with rule successes/failures
# ! rules keyed on action_date, not DATE(action_time): action_time is UTC and
# ! late-evening firings roll to the next action_date (06-07T22:30Z -> 06-08).
q("""
WITH perf AS (
  SELECT date,
         ROUND(SUM(spend), 2)                                   AS spend,
         SUM(fb_conversions)                                    AS fb_conv,
         ROUND(SUM(estimated_conversions), 1)                   AS est_conv,
         ROUND(SUM(revenue), 2)                                 AS revenue,
         ROUND(SUM(revenue) - SUM(spend), 2)                    AS profit,
         ROUND(SAFE_DIVIDE(SUM(revenue) - SUM(spend), SUM(spend)), 4) AS roi
  FROM $.perf_sel
  GROUP BY date
),
rx AS (
  SELECT action_date                      AS date,
         COUNTIF(response = 'SUCCESS')    AS rules_succeeded,
         COUNTIF(response != 'SUCCESS')   AS rules_failed
  FROM $.rx_sel
  GROUP BY action_date
)
SELECT perf.*,
       IFNULL(rules_succeeded, 0) AS rules_succeeded,
       IFNULL(rules_failed, 0)    AS rules_failed
FROM perf LEFT JOIN rx USING (date)
ORDER BY date
""")
# * rows sum back to week totals: spend $8,912, 214 executions. No day lost in the join.
# * 06-06 -> 06-07: 110 executions, 106 SUCCESS. Spend +43%, profit -$246.
# ! 06-08: 27 of 46 failed (token outage). 06-09: 13/13 failed (R02 retry loop).

# %% same totals per account, with rule executions
# ? perf_sel has no account_name -> adset->account map from performance_scoped
q("""
WITH acct AS (SELECT DISTINCT adset_id, account_name FROM $.performance_scoped),
perf AS (
  SELECT account_name,
         ROUND(SUM(spend), 2)                                   AS spend,
         SUM(fb_conversions)                                    AS fb_conv,
         ROUND(SUM(estimated_conversions), 1)                   AS est_conv,
         ROUND(SUM(revenue), 2)                                 AS revenue,
         ROUND(SUM(revenue) - SUM(spend), 2)                    AS profit,
         ROUND(SAFE_DIVIDE(SUM(revenue) - SUM(spend), SUM(spend)), 4) AS roi
  FROM $.perf_sel JOIN acct USING (adset_id)
  GROUP BY account_name
),
rx AS (
  SELECT account_name,
         COUNT(*)                         AS rules_executed,
         COUNTIF(response = 'SUCCESS')    AS rules_succeeded,
         COUNTIF(response != 'SUCCESS')   AS rules_failed
  FROM $.rx_sel JOIN acct USING (adset_id)
  GROUP BY account_name
)
SELECT perf.*,
       IFNULL(rules_executed, 0)  AS rules_executed,
       IFNULL(rules_succeeded, 0) AS rules_succeeded,
       IFNULL(rules_failed, 0)    AS rules_failed
FROM perf LEFT JOIN rx USING (account_name)
ORDER BY account_name
""")
# * spend sums back to week totals ($8,911.85). ACC-04 = 29% of spend, 56% of profit.
# ! all 214 executions are ACC-04; ACC-05 (-21% ROI, -$147) ran with zero rules.


# =============================================================================
#  RULE EXECUTIONS — which budget column is real, and ROI before / after
# =============================================================================
# TODO failed executions (50): counted only in the per-rule template, not calculated —
#      analyse their effect (incl. as a control group) in a separate session.

# %% budget columns: which base does set_budget apply the rule's % to?
q("""
SELECT action, COUNT(*) n,
  COUNTIF(ABS(set_budget / current_budget_from_fb - pct) < 0.002) set_over_fb_ok,
  COUNTIF(ABS(set_budget / new_budget - pct)             < 0.002) set_over_new_ok,
  COUNTIF(ABS(set_budget / old_budget - pct)             < 0.002) set_over_old_ok
FROM (SELECT *, 1 - CAST(REGEXP_EXTRACT(action, r'-(\\d+)%') AS INT64) / 100 AS pct
      FROM $.rx_sel WHERE set_budget IS NOT NULL)
GROUP BY action
""")
# * set_budget / current_budget_from_fb == the rule's % on 17/17 rows (new: 12/17, old: 0/17).
# * the change a rule makes = current_budget_from_fb -> set_budget. buyer_actions confirms it:
# *   update_ad_set_budget at the same timestamp, e.g. 06-07 02:30 128.93 -> 103.14.
# ! old_budget / new_budget are NOT this action. They echo the adset's previous budget change
# !   (often a buyer's): 06-10 19:30 R02 shows 103.14 -> 82.51 = buyer ui_adjust on 06-07 14:16.
# ! decreases show new_budget > old_budget (avg x1.33) — only makes sense as a lagged echo.
# ? set_budget is blank on Turn OFF/ON (no budget change) and on OAuth failures.
# ? current_budget_from_fb is NULL on OAuth failures (Meta never read) — failed, nothing changed.

# %% ROI before / after the action, same day
# ? before = what the engine saw: spend_at_action, today_roi_at_action (ROI up to the action).
# ? after  = rest of the day: day spend/revenue (perf_sel) minus what had accrued at action_time.
# ? revenue at action rebuilt as spend_at_action * (1 + roi); roi is 2dp -> <=0.5% of spend error.
# ? first firing per adset-day-action-outcome only, so repeated firings don't double-count "before".
# ? failed executions = same trigger, no change applied -> a natural comparison group.
q("""
WITH p AS (SELECT adset_id, date, SUM(spend) spend, SUM(revenue) revenue
           FROM $.perf_sel GROUP BY 1, 2),
r AS (
  SELECT r.*, p.spend AS day_spend, p.revenue AS day_rev,
         r.spend_at_action * (1 + r.today_roi_at_action)            AS rev_at_action,
         p.spend   - r.spend_at_action                               AS spend_after,
         p.revenue - r.spend_at_action * (1 + r.today_roi_at_action) AS rev_after,
         ROW_NUMBER() OVER (PARTITION BY r.adset_id, r.action_date, r.action, r.response = 'SUCCESS'
                            ORDER BY r.action_time) AS k
  FROM $.rx_sel r JOIN p ON p.adset_id = r.adset_id AND p.date = r.action_date
)
SELECT IF(action LIKE 'Decrease%', 'Decrease', action)                      AS action,
       response = 'SUCCESS'                                                 AS applied,
       COUNT(*)                                                             AS n,
       ROUND(SUM(spend_at_action), 2)                                       AS spend_before,
       ROUND(SAFE_DIVIDE(SUM(rev_at_action), SUM(spend_at_action)) - 1, 3)  AS roi_before,
       ROUND(SUM(spend_after), 2)                                           AS spend_after,
       ROUND(SAFE_DIVIDE(SUM(rev_after), SUM(spend_after)) - 1, 3)          AS roi_after,
       ROUND(SAFE_DIVIDE(SUM(day_rev), SUM(day_spend)) - 1, 3)              AS roi_day,
       ROUND(SAFE_DIVIDE(SUM(spend_after), SUM(day_spend)), 3)              AS share_spend_after,
       ROUND(AVG(last_3_days_roi_at_action), 3)                             AS avg_l3d_roi,
       COUNTIF(rev_after < 0)                                               AS neg_rev_after
FROM r WHERE k = 1
GROUP BY 1, 2 ORDER BY 1, 2
""")
# * spend_at_action is cumulative intraday: never decreases across firings (0/132 pairs),
# *   <= the day's perf spend on 212/214 rows (max 103.7%). Safe to subtract.
# * Turn OFF applied (66): ROI -62% before on $91; only 9.4% of day spend came after the action.
# * Decrease applied (12): ROI -10% before ($358) -> +19% after ($616). Day ends +8.5%.
# * Decrease failed (8):  ROI -23% before ($170) -> +15% after ($225). Day ends -1.5%.
# !   the adsets recovered after a decrease whether or not it was applied -> regression to
# !   the mean, not proof the decrease worked. n is tiny (12 vs 8).
# ! Turn OFF "after" ROI +133% on $9 is late-attributed revenue from pre-OFF clicks, not a
# !   healthy tail. 6 rows have negative rev_after (revenue restated down after the action).
# ! roi_before (intraday) and last_3_days roi disagree: decreases fired on -10%/-23% today
# !   while the 3-day ROI was +22%/+24% — the rules act on intraday noise.

# %% Turn OFF: did spend actually stop?
q("""
WITH p AS (SELECT adset_id, CAST(date AS DATE) date, SUM(spend) spend FROM $.perf_sel GROUP BY 1, 2),
off AS (
  SELECT r.adset_id, CAST(r.action_date AS DATE) d, p.spend - r.spend_at_action AS spend_after,
         ROW_NUMBER() OVER (PARTITION BY r.adset_id, r.action_date ORDER BY r.action_time) k
  FROM $.rx_sel r JOIN p ON p.adset_id = r.adset_id AND p.date = CAST(r.action_date AS DATE)
  WHERE r.action = 'Turn OFF' AND r.response = 'SUCCESS'
)
SELECT COUNT(*)                          AS n_off,
       COUNTIF(spend_after > 0.01)       AS spent_after_off_same_day,
       ROUND(SUM(spend_after), 2)        AS same_day_spend_after_off,
       COUNTIF(nxt.adset_id IS NOT NULL) AS has_next_day_row,
       COUNTIF(nxt.spend > 0.01)         AS spent_next_day
FROM off LEFT JOIN p nxt ON nxt.adset_id = off.adset_id AND nxt.date = DATE_ADD(off.d, INTERVAL 1 DAY)
WHERE k = 1
""")
# * 0 of 63 adsets turned OFF spent anything the next day — Turn OFF works.
# ! 57/66 still spent $9.44 total the same day after a SUCCESS OFF (Meta delivery lag).
# !   Repeat OFF firings on the same adset show spend_at_action still climbing (06-12 R01
# !   16:30 -> 17:00: $20.28 -> $20.97).


# =============================================================================
#  RULE TEMPLATE — one rule at a time (definitions: INVESTIGATION.md "Rule impact — method")
# =============================================================================
# ? dedup: reads *_scoped only. performance_scoped = SELECT DISTINCT (4947 -> 4875, one row per
# ?   adset x date); rule_executions / metadata have no duplicates; buyer_actions duplicates
# ?   all fall outside scope (buyer_actions_scoped 715 rows, all distinct).
# ? set RULE, run Block A, then Block B. The total row comes from GROUP BY ROLLUP, so
# ?   adsets are distinct across the week and overlaps are a union — not sums.

# %% RULE — set the rule to analyse
RULE = "R02"
qr = lambda sql: q(sql.replace("@RULE", RULE))

# %% Block A — activity, by action_date
# ? every day with any firing, including fail-only days.
qr("""
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
""")

# %% Block B — money, by action_date (successful decisions only; blank on fail-only days)
qr("""
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
""")
