"""Rule-by-rule check for one auto-rule — the R01 process, stages 1-7 (7 = value). Prints only; writes nothing.

usage (from anywhere in the repo):
    PYTHONIOENCODING=utf-8 uv run python .claude/skills/rule-analysis/run_rule.py R01
    PYTHONIOENCODING=utf-8 uv run python .claude/skills/rule-analysis/run_rule.py R07 --condition "roi >= -0.50 AND budget > 65"

Condition columns (end-of-day, per ACC-04 adset-day): age (spend_day_no), budget (metadata daily_budget / 100,
end-of-week snapshot), usage (spend / budget), roi, profit, total_profit and positive_days (this week, up to the day).
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery

_root = next(p for p in Path(__file__).resolve().parents if (p / "Task A").is_dir())
os.chdir(_root)
load_dotenv(_root / ".env")
sys.stdout.reconfigure(encoding="utf-8")

pd.set_option("display.width", 400)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", 500)
pd.set_option("display.max_colwidth", 90)

PROJECT, DATASET = "first-proj001", "mine_marketing"
client = bigquery.Client(project=PROJECT)
q = lambda sql: client.query(sql.replace("$.", f"`{PROJECT}.{DATASET}`.")).to_dataframe()

# conditions as the engine ran them (rule_executions.condition_name), inclusive thresholds
CONDITIONS = {
    "R01": "age >= 5",
    "R02": "roi > -0.30 AND roi <= -0.10",
    "R03": "positive_days = 0 AND age > 2",
    "R04": "age = 1 AND usage >= 0.35 AND roi <= -0.50",
    "R05": "profit <= -1 AND usage >= 0.15",
    "R06": "profit <= -1.25 AND age <= 3 AND total_profit <= -3",
    "R07": "roi >= -0.50 AND budget > 65",
    "R08": "age = 4",
    "R09": None,  # Turn ON "automation mistake" — not a performance condition
    "R10": "roi > -0.10 AND roi <= 0.05 AND budget >= 100",
    "R11": "positive_days = 0 AND age > 3",
    "R12": "roi <= -0.50 AND budget <= 65",
}

parser = argparse.ArgumentParser()
parser.add_argument("rule", help="rule id, e.g. R01")
parser.add_argument("--condition", help="override the replayed condition (SQL on the columns above)")
args = parser.parse_args()
RULE = args.rule.upper()
if RULE not in CONDITIONS:
    sys.exit(f"unknown rule '{RULE}' — use R01 to R12")
CONDITION = args.condition or CONDITIONS[RULE]


def show(title, sql):
    print(f"\n===== {RULE} — {title}")
    try:
        df = q(sql)
        print(df.to_string(index=False) if len(df) else "(no rows)")
        return df
    except Exception as e:  # keep going: one failing query shouldn't hide the rest
        print("ERROR:", str(e)[:400])


# first SUCCESS firing per decision (rule x adset x action_date) — reused by steps 3, 4, 6
DECISIONS = f"""
  SELECT adset_id, CAST(action_date AS DATE) AS dt, ANY_VALUE(action_name) AS action,
         ARRAY_AGG(STRUCT(action_time, last_3_days_roi_at_action AS roi_3d, today_roi_at_action AS roi,
                          spend_at_action AS spent, current_budget_from_fb AS live,
                          total_days_at_action AS engine_days) ORDER BY action_time LIMIT 1)[OFFSET(0)].*,
         ARRAY_AGG(set_budget IGNORE NULLS ORDER BY action_time DESC LIMIT 1)[SAFE_OFFSET(0)] AS last_set
  FROM $.rule_executions_scoped WHERE rule_id = '{RULE}' AND response = 'SUCCESS'
  GROUP BY 1, 2
"""

# ---------------------------------------------------------------- 1. definition and activity
show("1a definition: auto_rules vs what the engine logged", f"""
SELECT a.rule_name AS auto_rules_name, a.action, a.schedule, a.scope,
       (SELECT STRING_AGG(DISTINCT rule_name, ' || ') FROM $.rule_executions_scoped WHERE rule_id = '{RULE}') AS executions_rule_name,
       (SELECT STRING_AGG(DISTINCT TRIM(condition_name), ' || ') FROM $.rule_executions_scoped WHERE rule_id = '{RULE}') AS condition_ran
FROM $.auto_rules a WHERE a.rule_id = '{RULE}'
""")
print(f"replayed condition (end-of-day): {CONDITION}")

show("1b activity", f"""
SELECT COUNT(*) AS firings, COUNTIF(response = 'SUCCESS') AS successes, COUNTIF(response != 'SUCCESS') AS fails,
       COUNT(*) - COUNT(DISTINCT CONCAT(adset_id, action_date)) AS repeats,
       COUNT(DISTINCT adset_id) AS adsets, COUNT(DISTINCT IF(response = 'SUCCESS', CONCAT(adset_id, action_date), NULL)) AS decisions,
       MIN(action_time) AS first_firing, MAX(action_time) AS last_firing, COUNT(DISTINCT action_date) AS days_active
FROM $.rule_executions_scoped WHERE rule_id = '{RULE}'
""")

show("1c failures by response", f"""
SELECT LEFT(response, 60) AS response, COUNT(*) AS n, STRING_AGG(DISTINCT action_date) AS dates
FROM $.rule_executions_scoped WHERE rule_id = '{RULE}' AND response != 'SUCCESS' GROUP BY 1
""")

# ---------------------------------------------------------------- 2. day by day
show("2 day by day — acted adsets, whole week (rules = all rules that succeeded that day)", f"""
WITH a AS (SELECT DISTINCT adset_id FROM $.rule_executions_scoped WHERE rule_id = '{RULE}'),
fired AS (SELECT adset_id, CAST(action_date AS DATE) AS dt, STRING_AGG(DISTINCT rule_id ORDER BY rule_id) AS rules
          FROM $.rule_executions_scoped WHERE response = 'SUCCESS' GROUP BY 1, 2)
SELECT p.adset_id, CAST(p.date AS DATE) AS dt, p.spend_day_no AS age, ROUND(p.spend, 2) AS spend,
       ROUND(IFNULL(p.revenue, 0) - p.spend, 2) AS profit, ROUND(SAFE_DIVIDE(IFNULL(p.revenue, 0) - p.spend, p.spend), 2) AS roi,
       f.rules
FROM $.performance_scoped p JOIN a USING (adset_id)
LEFT JOIN fired f ON f.adset_id = p.adset_id AND f.dt = CAST(p.date AS DATE)
ORDER BY p.adset_id, dt
""")

# ---------------------------------------------------------------- 3. decisions: fire time vs close
show("3 decisions — engine view at fire vs the day's close (revenue at fire = spent x (1 + roi))", f"""
WITH d AS ({DECISIONS})
SELECT d.adset_id, d.dt, d.action_time AS fired_utc, d.action,
       d.roi_3d AS roi_3d_at_fire, d.roi AS roi_at_fire,
       ROUND(SAFE_DIVIDE(p.revenue - p.spend, p.spend), 3) AS roi_at_close,
       ROUND(d.spent, 2) AS spent_at_fire, ROUND(p.spend, 2) AS spent_at_close,
       ROUND(d.spent * (1 + d.roi), 2) AS revenue_at_fire, ROUND(p.revenue, 2) AS revenue_at_close,
       CASE WHEN d.roi < 0 AND p.revenue - p.spend >= 0 THEN 'flipper'
            WHEN d.roi < 0 THEN 'loser' ELSE 'winner at fire' END AS kind
FROM d JOIN $.performance_scoped p ON p.adset_id = d.adset_id AND CAST(p.date AS DATE) = d.dt
ORDER BY d.action_time
""")

show("3b decisions total — spend-weighted ROI", f"""
WITH d AS ({DECISIONS})
SELECT COUNT(*) AS decisions,
       ROUND(SAFE_DIVIDE(SUM(d.spent * (1 + d.roi)), SUM(d.spent)) - 1, 3) AS roi_at_fire,
       ROUND(SAFE_DIVIDE(SUM(p.revenue), SUM(p.spend)) - 1, 3) AS roi_at_close,
       ROUND(SUM(d.spent), 2) AS spent_at_fire, ROUND(SUM(p.spend), 2) AS spent_at_close
FROM d JOIN $.performance_scoped p ON p.adset_id = d.adset_id AND CAST(p.date AS DATE) = d.dt
""")

# ---------------------------------------------------------------- 4. did it take effect?
show("4 took effect? — spend/revenue after the fire, later days, human budget changes after", f"""
WITH d AS ({DECISIONS}),
last_day AS (SELECT MAX(CAST(date AS DATE)) AS last_dt FROM $.performance_scoped),
later AS (
  SELECT d.adset_id, d.dt, SUM(p.spend) AS later_spend, COUNTIF(p.spend > 0) AS later_days_with_spend,
         SUM(IFNULL(p.revenue, 0) - p.spend) AS later_profit
  FROM d JOIN $.performance_scoped p ON p.adset_id = d.adset_id AND CAST(p.date AS DATE) > d.dt
  GROUP BY 1, 2),
buyer AS (
  SELECT d.adset_id, d.dt, COUNT(*) AS human_changes_after,
         STRING_AGG(CONCAT(LEFT(b.action_time, 16), ' ', CAST(b.old_budget AS STRING), '->', CAST(b.new_budget AS STRING)), ' | '
                    ORDER BY b.action_time LIMIT 3) AS first_changes
  FROM d JOIN $.buyer_actions_scoped b
    ON b.adset_id = d.adset_id AND b.event_type LIKE 'ui_%' AND TIMESTAMP(b.action_time) > TIMESTAMP(d.action_time)
  GROUP BY 1, 2)
SELECT d.adset_id, d.dt, d.action, ROUND(d.live, 2) AS live_budget, ROUND(d.last_set, 2) AS set_budget,
       ROUND(p.spend - d.spent, 2) AS spend_after_fire_same_day,
       ROUND(p.revenue - d.spent * (1 + d.roi), 2) AS revenue_after_fire_same_day,
       DATE_DIFF(ld.last_dt, d.dt, DAY) AS days_left_in_data,
       IFNULL(l.later_days_with_spend, 0) AS later_days_with_spend, ROUND(IFNULL(l.later_spend, 0), 2) AS later_spend,
       ROUND(IFNULL(l.later_profit, 0), 2) AS later_profit,
       IFNULL(bu.human_changes_after, 0) AS human_changes_after, bu.first_changes
FROM d CROSS JOIN last_day ld
JOIN $.performance_scoped p ON p.adset_id = d.adset_id AND CAST(p.date AS DATE) = d.dt
LEFT JOIN later l ON l.adset_id = d.adset_id AND l.dt = d.dt
LEFT JOIN buyer bu ON bu.adset_id = d.adset_id AND bu.dt = d.dt
ORDER BY d.action_time
""")

# ---------------------------------------------------------------- 5 & 6a. met the condition: fired vs not
DAYS = f"""
WITH base AS (
  SELECT p.adset_id, CAST(p.date AS DATE) AS dt, p.spend, IFNULL(p.revenue, 0) AS revenue,
         p.spend_day_no AS age, m.daily_budget / 100 AS budget,
         SAFE_DIVIDE(p.spend, m.daily_budget / 100) AS usage,
         SAFE_DIVIDE(IFNULL(p.revenue, 0) - p.spend, p.spend) AS roi,
         IFNULL(p.revenue, 0) - p.spend AS profit
  FROM $.performance_scoped p LEFT JOIN $.metadata_scoped m USING (adset_id)
  WHERE p.account_name = 'ACC-04'
),
cum AS (
  SELECT *, SUM(profit) OVER w AS total_profit, COUNTIF(profit > 0) OVER w AS positive_days
  FROM base WINDOW w AS (PARTITION BY adset_id ORDER BY dt ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
),
hit AS (SELECT DISTINCT adset_id, CAST(action_date AS DATE) AS dt
        FROM $.rule_executions_scoped WHERE rule_id = '{RULE}' AND response = 'SUCCESS'),
days AS (
  SELECT c.*, IF(h.adset_id IS NOT NULL, 'fired', 'did not fire') AS fired,
         IF(c.profit < 0, 'losing', 'winning') AS close_result
  FROM cum c LEFT JOIN hit h ON h.adset_id = c.adset_id AND h.dt = c.dt
  WHERE c.spend > 0 AND ({CONDITION})
)
"""
if CONDITION:
    show("5 met the condition (ACC-04, end-of-day, spend > 0): fired vs not — accumulated ROI = SUM(rev)/SUM(spend) - 1", DAYS + """
SELECT IFNULL(fired, 'ALL') AS rule_fired, IFNULL(close_result, 'all') AS day_close,
       COUNT(*) AS adset_days, COUNT(DISTINCT adset_id) AS adsets,
       ROUND(SUM(spend), 2) AS spend, ROUND(SUM(revenue), 2) AS revenue, ROUND(SUM(revenue) - SUM(spend), 2) AS profit,
       ROUND(SAFE_DIVIDE(SUM(revenue), SUM(spend)) - 1, 3) AS accumulated_roi
FROM days GROUP BY ROLLUP(fired, close_result) ORDER BY fired, close_result
""")
    show("6a eligible vs fired by day (does it fire as often as its condition allows?)", DAYS + """
SELECT dt, COUNT(*) AS eligible_adset_days, COUNTIF(fired = 'fired') AS fired,
       COUNTIF(fired != 'fired' AND close_result = 'losing') AS skipped_losing,
       COUNTIF(fired != 'fired' AND close_result = 'winning') AS skipped_winning
FROM days GROUP BY dt ORDER BY dt
""")
else:
    print(f"\n===== {RULE} — 5 / 6a skipped: no performance condition to replay")

# ---------------------------------------------------------------- 6b. flags per decision
show("6b flags — rollover, last data day, engine age vs spend_day_no, overspend (> 1.75x highest known budget)", f"""
WITH d AS ({DECISIONS}),
budgets AS (
  SELECT adset_id, daily_budget / 100 AS b FROM $.metadata_scoped
  UNION ALL SELECT adset_id, current_budget_from_fb FROM $.rule_executions_scoped
  UNION ALL SELECT adset_id, old_budget FROM $.buyer_actions_scoped
  UNION ALL SELECT adset_id, new_budget FROM $.buyer_actions_scoped),
max_b AS (SELECT adset_id, MAX(b) AS max_budget FROM budgets WHERE b > 0 GROUP BY 1),
overspend AS (
  SELECT p.adset_id, COUNTIF(p.spend > 1.75 * m.max_budget) AS overspend_days
  FROM $.performance_scoped p JOIN max_b m USING (adset_id) GROUP BY 1)
SELECT d.adset_id, d.dt, d.action_time,
       DATE(TIMESTAMP(d.action_time)) != d.dt AS rollover,
       d.dt = (SELECT MAX(CAST(date AS DATE)) FROM $.performance_scoped) AS on_last_data_day,
       d.engine_days, p.spend_day_no, d.engine_days != p.spend_day_no AS age_mismatch,
       IFNULL(o.overspend_days, 0) AS overspend_days
FROM d JOIN $.performance_scoped p ON p.adset_id = d.adset_id AND CAST(p.date AS DATE) = d.dt
LEFT JOIN overspend o ON o.adset_id = d.adset_id
ORDER BY d.action_time
""")

# ---------------------------------------------------------------- 7. value per decision
# Budget cut: -(ROI at close) x budget removed (live - last set budget); counts only if the WHOLE day's spend
#             reached >= 95% of the new budget, else $0. Action day only.
# Turn-off:   -(accumulated ROI over the 3 calendar days before the action day) x the action day's spend.
#             ROI = SUM(revenue) / SUM(spend) - 1 over the window. No spend in the window -> no value, flagged.
v = show("7 value per decision (+ saved / - missed)", f"""
WITH d AS ({DECISIONS}),
last_day AS (SELECT MAX(CAST(date AS DATE)) AS last_dt, MIN(CAST(date AS DATE)) AS first_dt FROM $.performance_scoped),
hist AS (
  SELECT d.adset_id, d.dt, NULLIF(COUNTIF(p.spend > 0), 0) AS history_days,
         SAFE_DIVIDE(SUM(IFNULL(p.revenue, 0)), SUM(p.spend)) - 1 AS roi_3d_before
  FROM d JOIN $.performance_scoped p
    ON p.adset_id = d.adset_id
   AND CAST(p.date AS DATE) BETWEEN DATE_SUB(d.dt, INTERVAL 3 DAY) AND DATE_SUB(d.dt, INTERVAL 1 DAY)
  GROUP BY 1, 2
),
j AS (
  SELECT d.adset_id, d.dt, d.action, d.live, d.last_set, p.spend AS day_spend,
         SAFE_DIVIDE(p.revenue - p.spend, p.spend) AS roi_close,
         h.history_days, h.roi_3d_before, DATE_DIFF(ld.last_dt, d.dt, DAY) AS days_left, ld.first_dt
  FROM d CROSS JOIN last_day ld
  JOIN $.performance_scoped p ON p.adset_id = d.adset_id AND CAST(p.date AS DATE) = d.dt
  LEFT JOIN hist h ON h.adset_id = d.adset_id AND h.dt = d.dt
)
SELECT adset_id, dt, action,
       ROUND(live, 2) AS budget, ROUND(last_set, 2) AS new_budget, ROUND(live - last_set, 2) AS budget_removed,
       ROUND(day_spend, 2) AS day_spend, ROUND(0.95 * last_set, 2) AS new_budget_95,
       ROUND(roi_close, 3) AS roi_close,
       IF(roi_close >= 0, 'winner at close', 'loser at close') AS close_result,
       history_days, ROUND(roi_3d_before, 3) AS roi_3d_before,
       ROUND(CASE
         WHEN action LIKE 'Decrease%' THEN IF(day_spend >= 0.95 * last_set, -roi_close * (live - last_set), 0)
         WHEN action = 'Turn OFF' AND history_days IS NULL THEN -roi_close * day_spend
         WHEN action = 'Turn OFF' THEN -roi_3d_before * day_spend
       END, 2) AS value,
       CASE
         WHEN action LIKE 'Decrease%' AND day_spend < 0.95 * last_set THEN 'cut: spend < 95% of new budget -> $0'
         WHEN action LIKE 'Decrease%' THEN 'cut: counted'
         WHEN action = 'Turn OFF' AND history_days IS NULL AND DATE_SUB(dt, INTERVAL 1 DAY) < first_dt
              THEN 'off: no history (before data start) -> action-day ROI x day spend'
         WHEN action = 'Turn OFF' AND history_days IS NULL THEN 'off: no spend in last 3 days -> action-day ROI x day spend'
         WHEN action = 'Turn OFF' AND DATE_SUB(dt, INTERVAL 3 DAY) < first_dt
              THEN 'off: 3-day ROI x day spend (window partly before data)'
         WHEN action = 'Turn OFF' THEN 'off: 3-day ROI x day spend'
         ELSE 'not valued'
       END AS how
FROM j ORDER BY dt, adset_id
""")
if v is not None and len(v):
    print()
    split = v.groupby("close_result").agg(decisions=("adset_id", "size"), valued=("value", "count"), value=("value", "sum"))
    print(split.round(2).to_string())
    print()
    print(f"NET value: {v['value'].sum():+.2f}  |  valued {v['value'].notna().sum()} of {len(v)} decisions"
          f"  (winner at close = cost of cutting winners, loser at close = saving from cutting losers)")
