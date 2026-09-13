how much money did rule-driven actions save or burn?

## Rule impact — method

Each rule is judged on its own, by hand, inside its segment: a fixed activity/money table, then the KPIs that fit how the segment acts. There is no single bulk table — per-rule numbers are checked one rule at a time before any verdict.

### Rule segmentation

Rule names as logged in `rule_executions.rule_name`.

| segment | question it must answer | rule | action | rule name |
|---|---|---|---|---|
| 1. Day 1-2 kill | Did it stop losers before they burned money? | R04 | Turn OFF | Turn Off - OWN RSOC \| Total Days = 1 \| budget > 35%\| ROI < -50% |
| | | R05 | Turn OFF | Turn Off \| OWN RSOC \| Total Profit <= -2.5$ \| budget_usage_today >= 15% |
| | | R06 | Turn OFF | Turn Off \| today_profit <= -1.25 $\| total_days <= 3 \| total profit <=-4$ \| OWN RSOC |
| 2. Never profitable | Were the adsets really never profitable? | R03 | Turn OFF | Turn Off \| positive_days = 0 \| total_days > 2 \| OWN RSOC |
| | | R11 | Turn OFF | Turn Off \| positive_days = 0 \| total_days > 3 \| OWN RSOC |
| 3. Age kill | No performance condition — did it kill winners? | R01 | Turn OFF | Turn OFF \| Total Days >= 5 \| OWN RSOC |
| | | R08 | Turn OFF | Turn OFF \| Total Days = 4 \| OWN RSOC |
| 4. Budget cut | The adset keeps running — did the cut improve profit or just shrink spend? | R02 | Decrease -20% (min 9) | Budget Decrease \| OWN RSOC \| -30 < ROI <= -10 |
| | | R07 | Decrease -40% (min 9) | Budget Decrease \| OWN RSOC \| -50 <= ROI \| Budget > 65$ |
| | | R10 | Decrease -15% (min 9) | Budget Decrease \| OWN RSOC \| -10 < ROI <= 5 \| Budget >= 100$ |
| | | R12 | Decrease -40% (min 9) | Budget Decrease \| OWN RSOC \| ROI <= -50 \| Budget <= 65$ |
| 5. Undo | Did it try to undo the right thing? | R09 | Turn ON | Turn On \| Automation Mistake - Today \| OWN RSOC |

### Base definitions

| # | definition |
|---|---|
| B1 | **Decision** = rule x adset x `action_date`. Repeated firings on the same adset-day collapse into one decision. |
| B2 | **Before** = the first SUCCESS firing of the adset-day — the last numbers the rule saw before it changed anything. |
| B3 | **Exposure** = what the action removed. Turn OFF: `current_budget_from_fb − spend_at_action`. Decrease: `current_budget_from_fb − set_budget`. Turn ON: `−current_budget_from_fb`. |
| B4 | **Accumulated after** runs from the action to the end of the week, or until the same rule acts on that adset again. |
| B5 | **Overlaps**: when two rules succeed on the same adset-day, both get full credit (both acted). Same-segment overlaps are flagged as redundant rules. |
| B6 | **Dates** are keyed on `action_date` (the reporting date), not the UTC date of `action_time`. Rollover decisions (fired before midnight UTC, logged against the next date) are flagged. |
| B7 | **Conversions** = `estimated_conversions`. Before = `spend_at_action / today_cpa_at_action`; 0 when CPA is null (nothing had converted yet). |
| B8 | **Revenue before** = `spend_at_action × (1 + today_roi_at_action)`. ROI is rounded to 2 decimals, so up to ~0.5% of spend in error. |

### Per-rule table

One table per rule, one row per `action_date` (day 1 = 06-06 … day 7 = 06-12), plus a total row.

**Block A — activity.** Every day with any firing, including days where every run failed.

| column | formula | total row |
|---|---|---|
| decisions | distinct adset-days with at least one SUCCESS | Σ |
| repeat firings | all firings (any response) − distinct adset-days | Σ |
| success runs / failed runs | `COUNTIF(response = 'SUCCESS')` / the rest | Σ |
| adsets | distinct adsets with a successful decision | distinct, not Σ |
| overlaps (n) | decisions where another rule also succeeded on that adset-day | Σ |
| overlapping rules | `rule@adset`, e.g. `R06@31818629447720` | union |
| rollover | decisions flagged under B6 | Σ |

**Block B — money.** Successful decisions only; blank on days with no successful decision.

| column | formula |
|---|---|
| exposure | B3 |
| spend / conv / rev before | `spend_at_action` · B7 · B8 |
| spend / conv / rev after (day) | the day's performance total − the "before" value |
| spend / conv / rev after (accumulated) | the rest of that day + following days, within the B4 window |
| ROI before / after (day) / after (accumulated) | `Σ rev / Σ spend − 1` in every row, including the total row — never an average of row ROIs |

### KPIs

**All segments**

| KPI | formula |
|---|---|
| K1 Activity | Block A |
| K2 Stakes | exposure, spend / conv / ROI before |
| K3 Condition adherence | share of decisions whose logged metrics satisfy `condition_name`, and separately the rule name |
| K4 Evidence size | share of decisions with 0 conversions at action; median `spend_at_action` |

**Per segment**

| segment | KPI | formula / source |
|---|---|---|
| 1. Day 1-2 kill | Revenue-lag check | end-of-day ROI − ROI at action |
| | Leak | spend after the kill, same day |
| | Traffic quality | revenue per conversion on the day vs other day-1 adsets |
| | Killed-winner check | lifetime profit at action (prior days + today) > 0. R05/R06 only — R04 adsets have no history |
| 2. Never profitable | Premise check | prior days with profit > 0 in performance data; any > 0 means the premise was false |
| | Redundancy | share of R11 decisions R03 also made |
| | Rollover share | share of decisions flagged under B6 |
| 3. Age kill | Winner-kill rate | share of decisions with prior-day ROI > 0 (performance data; engine `last_3_days_roi_at_action` where history is missing) |
| | Profit forgone (estimate) | average daily profit over the prior days, where positive |
| | Leak and late revenue | spend after the kill; revenue on zero-spend days after |
| 4. Budget cut | ROI and profit before vs after | Block B |
| | Shrink | spend after vs spend before |
| | Profit forgone or avoided | exposure × ROI after |
| | Noise cut | `last_3_days_roi_at_action` > 0 while ROI at action < 0 |
| | Human override | later buyer budget increases on the adset (`ui_*` events only; `update_ad_set_budget` is the rule's own logged change) |
| | Direction check | logged ROI against the rule name (R07 "-50 <= ROI" may be inverted) |
| 5. Undo | Failure rate and type | Block A, `response` |
| | Target check | was the adset it tried to revive wrongly killed? Depends on the segment 3 verdict for that kill |

### Decisions and limits

- **Failed runs are counted, not calculated.** The question is what the rules did. Failed runs as a control group are left for a later session.
- **The replay on the five accounts with no rules** is run inside the rule-by-rule pass, where it applies.
- **Rows for different rules can't be summed** into a week total, because overlapping decisions count for both rules.
- **Negative "after (day)" values are shown as-is**, not clamped to zero. They occur on rollover decisions, where the "before" snapshot may belong to the previous day.
