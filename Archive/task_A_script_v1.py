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
# ? run the TEMPLATE cell, then a rule section. Totals come from GROUP BY ROLLUP, so
# ?   adsets are distinct across the week and overlaps are a union — not sums.

# %% TEMPLATE — shared queries (run this cell first; nothing executes here)
# ? usage: in a rule's section set RULE, then qr(BLOCK_A), qr(BLOCK_B), qr(K_...).
# ? qr reads RULE at call time, so one set of queries serves every rule.
qr = lambda sql: q(sql.replace("@RULE", RULE))

# ? Block A — activity by action_date. Every day with any firing, incl. fail-only days.
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

# ? Block B — money by action_date. Successful decisions only; blank on fail-only days.
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

# ? K4 evidence size — what the rule knew when it acted (first SUCCESS firing per adset-day).
# ?   0 conversions = today_cpa_at_action NULL or 0. Budget = live Meta budget at the firing.
K_EVIDENCE = """
WITH d AS (
  SELECT * FROM $.rule_executions_scoped WHERE rule_id = '@RULE' AND response = 'SUCCESS'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY adset_id, action_date ORDER BY action_time) = 1
)
SELECT COUNT(*)                                                             decisions,
  COUNTIF(IFNULL(today_cpa_at_action, 0) = 0)                               zero_conv_at_action,
  COUNTIF(today_roi_at_action = -1)                                         roi_minus_100,
  ROUND(APPROX_QUANTILES(spend_at_action, 2)[SAFE_OFFSET(1)], 2)            median_spend_at_action,
  ROUND(MAX(spend_at_action), 2)                                            max_spend_at_action,
  ROUND(APPROX_QUANTILES(current_budget_from_fb, 2)[SAFE_OFFSET(1)], 2)     median_budget,
  APPROX_TOP_COUNT(current_budget_from_fb, 1)[SAFE_OFFSET(0)].value         most_common_budget,
  APPROX_TOP_COUNT(current_budget_from_fb, 1)[SAFE_OFFSET(0)].count         most_common_budget_n
FROM d
"""

# ? revenue lag + same-day spend after the action.
# ?   compares the ROI the rule saw with the adset's final ROI for that day.
K_LAG = """
WITH p AS (SELECT adset_id, CAST(date AS DATE) dt, SUM(spend) spend, SUM(IFNULL(revenue, 0)) rev
           FROM $.performance_scoped GROUP BY 1, 2),
d AS (
  SELECT * FROM $.rule_executions_scoped WHERE rule_id = '@RULE' AND response = 'SUCCESS'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY adset_id, action_date ORDER BY action_time) = 1
),
x AS (
  SELECT d.today_roi_at_action roi0, d.spend_at_action s0, p.spend ds, p.rev dr,
         SAFE_DIVIDE(p.rev, p.spend) - 1 - d.today_roi_at_action roi_gap
  FROM d JOIN p ON p.adset_id = d.adset_id AND p.dt = CAST(d.action_date AS DATE)
)
SELECT COUNT(*)                                                    decisions,
  ROUND(SAFE_DIVIDE(SUM(s0 * (1 + roi0)), SUM(s0)) - 1, 3)         roi_at_action,
  ROUND(SAFE_DIVIDE(SUM(dr), SUM(ds)) - 1, 3)                      roi_end_of_day,
  COUNTIF(roi_gap > 0.10)                                          improved_over_10pt,
  COUNTIF(ABS(roi_gap) <= 0.10)                                    within_10pt,
  COUNTIF(roi_gap < -0.10)                                         worsened_over_10pt,
  COUNTIF(dr > ds)                                                 profitable_end_of_day,
  COUNTIF(ds - s0 > 0.01)                                          spent_after_action,
  ROUND(SUM(ds - s0), 2)                                           spend_after_action,
  ROUND(MAX(ds - s0), 2)                                           max_spend_after_action
FROM x
"""

# ? timing — UTC hour of each decision (first SUCCESS firing).
K_TIMING = """
SELECT EXTRACT(HOUR FROM CAST(action_time AS TIMESTAMP)) hour_utc, COUNT(*) decisions
FROM (SELECT * FROM $.rule_executions_scoped WHERE rule_id = '@RULE' AND response = 'SUCCESS'
      QUALIFY ROW_NUMBER() OVER (PARTITION BY adset_id, action_date ORDER BY action_time) = 1)
GROUP BY 1 ORDER BY 1
"""

# ? budget units — metadata daily_budget vs the live Meta budget the engine read.
K_BUDGET_UNITS = """
SELECT COUNT(*) decisions,
  COUNTIF(ABS(m.daily_budget / 100 - r.current_budget_from_fb) < 0.011) metadata_div_100_matches,
  COUNTIF(ABS(m.daily_budget - r.current_budget_from_fb) < 0.011)       metadata_raw_matches
FROM (SELECT * FROM $.rule_executions_scoped WHERE rule_id = '@RULE' AND response = 'SUCCESS'
        AND current_budget_from_fb IS NOT NULL
      QUALIFY ROW_NUMBER() OVER (PARTITION BY adset_id, action_date ORDER BY action_time) = 1) r
JOIN $.metadata_scoped m USING (adset_id)
"""

# ? segment 1 — day-1 traffic quality: adsets the rule killed vs every other day-1 adset.
K_DAY1_QUALITY = """
WITH p AS (SELECT DISTINCT adset_id, account_name, CAST(date AS DATE) dt, spend,
                  IFNULL(revenue, 0) rev, IFNULL(estimated_conversions, 0) ec, spend_day_no
           FROM $.performance_scoped),
k AS (SELECT DISTINCT adset_id FROM $.rule_executions_scoped WHERE rule_id = '@RULE' AND response = 'SUCCESS')
SELECT CASE WHEN p.adset_id IN (SELECT adset_id FROM k) THEN '1 killed by rule'
            WHEN account_name = 'ACC-04' THEN '2 ACC-04 other day-1' ELSE '3 other accounts day-1' END grp,
  COUNT(*) adsets, ROUND(AVG(spend), 2) avg_spend, ROUND(SUM(ec), 1) conv, COUNTIF(ec = 0) zero_conv,
  ROUND(SAFE_DIVIDE(SUM(spend), SUM(ec)), 2) cpa, ROUND(SAFE_DIVIDE(SUM(rev), SUM(ec)), 2) rpc,
  ROUND(SUM(rev) / SUM(spend) - 1, 3) roi
FROM p WHERE spend_day_no = 1 AND spend > 0 GROUP BY 1 ORDER BY 1
"""

# ? segment 1 (R05/R06) — killed-winner check: lifetime profit at the kill (prior days + today) > 0.
# ?   engine: last_3_days_* excludes today, so it is the whole prior life when total_days_at_action <= 3.
# ?   perf: prior days in performance_scoped — missing when the adset started before 06-06.
# ?   mismatch columns compare the two where both exist (td <= 3 and perf history present).
K_KILLED_WINNER = """
WITH p AS (SELECT adset_id, CAST(date AS DATE) dt, SUM(spend) spend, SUM(IFNULL(revenue, 0)) rev
           FROM $.performance_scoped GROUP BY 1, 2),
d AS (
  SELECT * FROM $.rule_executions_scoped WHERE rule_id = '@RULE' AND response = 'SUCCESS'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY adset_id, action_date ORDER BY action_time) = 1
),
h AS (
  SELECT d.adset_id, d.action_date, SUM(p.spend) ps, SUM(p.rev) pr, COUNTIF(p.spend > 0) pdays
  FROM d LEFT JOIN p ON p.adset_id = d.adset_id AND p.dt < CAST(d.action_date AS DATE)
  GROUP BY 1, 2
),
x AS (
  SELECT d.*, h.ps, h.pr, IFNULL(h.pdays, 0) pdays,
    d.spend_at_action * d.today_roi_at_action                                                    today_profit,
    IFNULL(d.last_3_days_revenue_at_action - d.last_3_days_spend_at_action, 0)
      + d.spend_at_action * d.today_roi_at_action                                                life_engine,
    IFNULL(h.pr - h.ps, 0) + d.spend_at_action * d.today_roi_at_action                           life_perf
  FROM d JOIN h USING (adset_id, action_date)
)
SELECT COUNT(*)                                                           decisions,
  COUNTIF(total_days_at_action <= 3)                                      engine_history_complete,
  COUNTIF(total_days_at_action > 1 AND pdays = 0)                         perf_history_missing,
  COUNTIF(life_engine > 0)                                                winner_engine,
  COUNTIF(life_perf > 0)                                                  winner_perf,
  ROUND(SUM(today_profit), 2)                                             today_profit,
  ROUND(SUM(life_engine), 2)                                              lifetime_profit_engine,
  ROUND(SUM(life_perf), 2)                                                lifetime_profit_perf,
  COUNTIF(pdays > 0 AND total_days_at_action <= 3
          AND ABS(last_3_days_spend_at_action - ps) > 0.02)               prior_spend_mismatch,
  COUNTIF(pdays > 0 AND total_days_at_action <= 3
          AND ABS(last_3_days_revenue_at_action - pr) > 0.02)             prior_revenue_mismatch
FROM x
"""


# =============================================================================
#  SEGMENT 1 — DAY 1-2 KILL  /  R04
#  "Turn Off - OWN RSOC | Total Days = 1 | budget > 35%| ROI < -50%"   (Turn OFF)
# =============================================================================

# %% R04 — set rule
RULE = "R04"

# %% R04 — Block A: activity
qr(BLOCK_A)
# * active on 4 days: 06-06 15 decisions, 06-07 17, 06-10 5, 06-11 2. Total 39 decisions = 39 adsets.
# * 109 SUCCESS, 0 failed. No overlaps with other rules, no rollover.
# ! 70 of 109 firings are repeats on adsets already turned off -> count decisions, not firings.

# %% R04 — Block B: money
qr(BLOCK_B)
# * exposure $40.44 | before: spend $31.95, conv 40.61, rev $6.80, ROI -78.7%.
# * after (day): spend $4.64, conv 30.39, rev $1.36, ROI -70.7%.
# * accumulated after == after (day): no killed adset spent again that week.
# ! conversions keep landing after the kill (+30.39) but revenue doesn't (+$1.36).

# %% R04 — K4 evidence size
qr(K_EVIDENCE)
# * 39 decisions: 25 with 0 conversions at the kill, 23 at ROI exactly -100%.
# * median spend at the kill $0.55 (max $2.02). Most common budget $1.27/day (33 of 39).

# %% R04 — revenue lag + spend after the kill
qr(K_LAG)
# * ROI at kill -78.7% -> end of day -77.7%. 36/39 within 10pt, 3 improved >10pt, 0 worsened.
# * 0 of 39 were profitable by end of day -> no late revenue rescued a killed adset.
# ! 38/39 kept spending after a SUCCESS Turn OFF: $4.64 total, max $0.46 (Meta delivery lag).

# %% R04 — timing
qr(K_TIMING)
# * 28 of 39 kills between 12:00 and 17:00 UTC; earliest 06:00, none after 17:00.

# %% R04 — budget units
qr(K_BUDGET_UNITS)
# ! metadata daily_budget / 100 == live Meta budget on 39/39, raw on 0 -> metadata budgets are in cents.

# %% R04 — day-1 traffic quality
qr(K_DAY1_QUALITY)
# * killed (39): CPA $0.52, revenue/conv $0.11, ROI -77.7%.
# * ACC-04 other day-1 (55): CPA $0.35, revenue/conv $0.47, ROI +35.3%.
# * other accounts day-1 (729): CPA $0.52, revenue/conv $0.44, ROI -15.3%.
# ! killed traffic converts, but each conversion is worth ~4x less than its peers'.

# %% R04 — condition adherence (R04 thresholds)
# ? usage = spend_at_action / current_budget_from_fb. Strict = the name (> 35%, < -50%);
# ?   inclusive = >= 35%, <= -50%.
q("""
WITH f AS (
  SELECT *, spend_at_action / current_budget_from_fb usage,
         ROW_NUMBER() OVER (PARTITION BY adset_id, action_date ORDER BY action_time) = 1
           AND response = 'SUCCESS' is_decision
  FROM $.rule_executions_scoped WHERE rule_id = 'R04'
),
pd AS (SELECT DISTINCT adset_id, CAST(date AS DATE) dt, spend_day_no,
              SAFE_DIVIDE(revenue, spend) - 1 eod_roi FROM $.performance_scoped)
SELECT COUNT(*) firings, COUNTIF(is_decision) decisions,
  COUNTIF(total_days_at_action = 1) day1_engine, COUNTIF(pd.spend_day_no = 1) day1_perf,
  COUNTIF(total_days_at_action = 1 AND usage > 0.35 AND today_roi_at_action < -0.5)             strict_all,
  COUNTIF(total_days_at_action = 1 AND ROUND(usage, 4) >= 0.35 AND today_roi_at_action <= -0.5) inclusive_all,
  COUNTIF(is_decision AND NOT (usage > 0.35 AND today_roi_at_action < -0.5))                    decisions_fail_strict,
  COUNTIF(is_decision AND pd.eod_roi <= -0.5)                                                   decisions_still_true_end_of_day,
  COUNT(DISTINCT TRIM(condition_name)) n_condition_names
FROM f LEFT JOIN pd ON pd.adset_id = f.adset_id AND pd.dt = CAST(f.action_date AS DATE)
""")
# * 109/109 firings on day 1 (engine and performance agree); one condition_name.
# ! engine fires on >= 35% / <= -50%, the name says > 35% / < -50%: strict passes 99/109 firings,
# !   inclusive 109/109. 8 decisions fired at usage exactly 35%.
# * all 39 decisions still meet ROI <= -50% at end of day.

# %% R04 — replay on end-of-day values (all accounts, day-1 adsets with a following day)
# ? flagged = day 1, spend / (daily_budget / 100) > 35%, ROI < -50%, on the day's final numbers.
# ? follows each adset's later days. Validation: must flag all 39 real R04 kills.
q("""
WITH p AS (SELECT DISTINCT adset_id, account_name, CAST(date AS DATE) dt, spend,
                  IFNULL(revenue, 0) rev, IFNULL(estimated_conversions, 0) ec, spend_day_no
           FROM $.performance_scoped),
m AS (SELECT adset_id, daily_budget / 100 b FROM $.metadata_scoped),
k AS (SELECT DISTINCT adset_id FROM $.rule_executions_scoped WHERE rule_id = 'R04' AND response = 'SUCCESS'),
c AS (
  SELECT p.adset_id, p.account_name, p.dt d1,
         SAFE_DIVIDE(p.spend, m.b) > 0.35 AND SAFE_DIVIDE(p.rev - p.spend, p.spend) < -0.5 flagged,
         p.adset_id IN (SELECT adset_id FROM k) killed
  FROM p JOIN m USING (adset_id)
  WHERE p.spend_day_no = 1 AND p.spend > 0 AND p.dt < DATE '2026-06-12'
),
n AS (SELECT c.adset_id, SUM(x.spend) s, SUM(x.rev) r, COUNTIF(x.spend > 0) days
      FROM c JOIN p x ON x.adset_id = c.adset_id AND x.dt > c.d1 GROUP BY 1)
SELECT c.account_name = 'ACC-04' acc04, c.flagged, c.killed, COUNT(*) adsets,
  COUNTIF(IFNULL(n.days, 0) > 0) kept_spending,
  ROUND(SUM(IFNULL(n.s, 0)), 2) spend_after, ROUND(SUM(IFNULL(n.r, 0) - IFNULL(n.s, 0)), 2) profit_after,
  ROUND(SAFE_DIVIDE(SUM(n.r), SUM(n.s)) - 1, 3) roi_after, COUNTIF(n.r > n.s) profitable_after
FROM c LEFT JOIN n USING (adset_id) GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
""")
# * validation: all 39 R04 kills are flagged by the replay.
# * other accounts, flagged (243): 35 kept spending, $44.23 at ROI -31.7% (-$14.02), 8 profitable.
# * other accounts, not flagged (341): 241 kept spending, $1,502.55 at -0.4%.
# * ACC-04 flagged but not killed (9): 4 kept spending, -$3.53 at -100%.
# * saving estimate: a flagged adset that keeps spending loses ~$0.40 over the following days.
# *   14% keep spending (35/243) -> 39 x 14% x $0.40 ~ $2. If all 39 had kept spending -> ~$16.


# =============================================================================
#  SEGMENT 1 — DAY 1-2 KILL  /  R05
#  "Turn Off | OWN RSOC | Total Profit <= -2.5$ | budget_usage_today >= 15%"   (Turn OFF)
# =============================================================================

# %% R05 — set rule
RULE = "R05"

# %% R05 — Block A: activity
qr(BLOCK_A)

# %% R05 — Block B: money
qr(BLOCK_B)

# %% R05 — K4 evidence size
qr(K_EVIDENCE)

# %% R05 — revenue lag + spend after the kill
qr(K_LAG)

# %% R05 — timing
qr(K_TIMING)

# %% R05 — budget units
qr(K_BUDGET_UNITS)

# %% R05 — day-1 traffic quality
qr(K_DAY1_QUALITY)

# %% R05 — killed-winner check
qr(K_KILLED_WINNER)

# %% R05 — condition adherence (name vs engine thresholds), every firing
# ? name:   Total Profit <= -2.5$ AND usage >= 15%.  engine condition_name: Today_profit <= -1$ AND usage >= 15%.
# ? today profit = spend_at_action * today_roi_at_action. total profit = engine prior days
# ?   (last_3_days_revenue - last_3_days_spend, excludes today; whole life while total_days <= 3) + today.
# ? usage = spend_at_action / current_budget_from_fb. strict = <, >; inclusive = <=, >=.
q("""
WITH f AS (
  SELECT *,
    spend_at_action * today_roi_at_action                                                   today_profit,
    IFNULL(last_3_days_revenue_at_action - last_3_days_spend_at_action, 0)
      + spend_at_action * today_roi_at_action                                               total_profit,
    SAFE_DIVIDE(spend_at_action, current_budget_from_fb)                                    usage,
    response = 'SUCCESS' AND ROW_NUMBER() OVER (PARTITION BY adset_id, action_date, response = 'SUCCESS'
                                                ORDER BY action_time) = 1                   is_decision
  FROM $.rule_executions_scoped WHERE rule_id = 'R05'
)
SELECT CAST(action_date AS STRING) action_date, action_time, adset_id, response = 'SUCCESS' ok, is_decision,
  CAST(action_date AS DATE) != DATE(CAST(action_time AS TIMESTAMP)) rollover,
  total_days_at_action td, ROUND(spend_at_action, 2) spend0, ROUND(current_budget_from_fb, 2) budget,
  ROUND(usage, 3) usage, today_roi_at_action roi0,
  ROUND(today_profit, 2) today_profit, ROUND(total_profit, 2) total_profit,
  ROUND(usage, 4) >= 0.15 AND ROUND(today_profit, 2) <= -1    engine_inclusive,
  usage > 0.15 AND today_profit < -1                          engine_strict,
  ROUND(usage, 4) >= 0.15 AND ROUND(total_profit, 2) <= -2.5  name_inclusive,
  COUNT(DISTINCT TRIM(condition_name)) OVER ()                n_condition_names
FROM f ORDER BY action_time
""")

# %% R05 — replay on end-of-day values (all accounts, spend days 1-2 with a following day)
# ? flagged = engine condition on the day's final numbers: profit <= -$1 and spend / (daily_budget / 100) >= 15%.
# ? restricted to spend_day_no 1-2: the condition has no day limit, but every R05 firing is on total_days 1-2.
# ? each adset is followed after its first flagged day (unflagged: after its last day-1/2 row).
# ? validation (second table): do the real R05 decisions meet the flag on their action_date?
q("""
WITH p AS (SELECT adset_id, account_name, CAST(date AS DATE) dt, SUM(spend) spend,
                  SUM(IFNULL(revenue, 0)) rev, MAX(spend_day_no) sdn
           FROM $.performance_scoped GROUP BY 1, 2, 3),
m AS (SELECT adset_id, daily_budget / 100 b FROM $.metadata_scoped),
k AS (SELECT DISTINCT adset_id FROM $.rule_executions_scoped WHERE rule_id = 'R05' AND response = 'SUCCESS'),
c AS (
  SELECT p.adset_id, p.account_name, p.dt,
         p.rev - p.spend <= -1 AND SAFE_DIVIDE(p.spend, m.b) >= 0.15 flagged
  FROM p JOIN m USING (adset_id)
  WHERE p.sdn IN (1, 2) AND p.spend > 0 AND p.dt < DATE '2026-06-12'
),
a AS (
  SELECT adset_id, account_name, LOGICAL_OR(flagged) flagged,
         IFNULL(MIN(IF(flagged, dt, NULL)), MAX(dt)) d0,
         adset_id IN (SELECT adset_id FROM k) killed
  FROM c GROUP BY 1, 2
),
n AS (SELECT a.adset_id, SUM(x.spend) s, SUM(x.rev) r, COUNTIF(x.spend > 0) days
      FROM a JOIN p x ON x.adset_id = a.adset_id AND x.dt > a.d0 GROUP BY 1)
SELECT a.account_name = 'ACC-04' acc04, a.flagged, a.killed, COUNT(*) adsets,
  COUNTIF(IFNULL(n.days, 0) > 0) kept_spending,
  ROUND(SUM(IFNULL(n.s, 0)), 2) spend_after, ROUND(SUM(IFNULL(n.r, 0) - IFNULL(n.s, 0)), 2) profit_after,
  ROUND(SAFE_DIVIDE(SUM(n.r), SUM(n.s)) - 1, 3) roi_after, COUNTIF(n.r > n.s) profitable_after
FROM a LEFT JOIN n USING (adset_id) GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
""")
q("""
WITH p AS (SELECT adset_id, CAST(date AS DATE) dt, SUM(spend) spend, SUM(IFNULL(revenue, 0)) rev,
                  MAX(spend_day_no) sdn FROM $.performance_scoped GROUP BY 1, 2),
m AS (SELECT adset_id, daily_budget / 100 b FROM $.metadata_scoped),
d AS (SELECT DISTINCT adset_id, CAST(action_date AS DATE) ad FROM $.rule_executions_scoped
      WHERE rule_id = 'R05' AND response = 'SUCCESS')
SELECT d.adset_id, CAST(d.ad AS STRING) action_date, p.sdn, ROUND(p.spend, 2) eod_spend, ROUND(m.b, 2) budget,
  ROUND(p.rev - p.spend, 2) eod_profit, ROUND(SAFE_DIVIDE(p.spend, m.b), 3) eod_usage,
  p.rev - p.spend <= -1 AND SAFE_DIVIDE(p.spend, m.b) >= 0.15 flagged_eod
FROM d LEFT JOIN p ON p.adset_id = d.adset_id AND p.dt = d.ad LEFT JOIN m ON m.adset_id = d.adset_id
ORDER BY d.ad
""")
