how much money did rule-driven actions save or burn?

## Rule impact — method

Each rule is judged on its own, one rule at a time, with five direct answers: what it did, did it stop the bleeding, how peers that met the same condition did (and what it missed in ACC-04), one $ impact with a verdict, and data issues. There is no single bulk table — per-rule numbers are checked before any verdict.

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
| B4 | **Window**: a budget cut's "after" runs to the end of the week, or until the same rule acts on that adset again. |
| B5 | **Overlaps**: when two rules succeed on the same adset-day, both get full credit (both acted). Same-segment overlaps are flagged as redundant rules. |
| B6 | **Dates** are keyed on `action_date` (the reporting date), not the UTC date of `action_time`. Rollover decisions (fired before midnight UTC, logged against the next date) are flagged. |
| B8 | **Profit before** = `spend_at_action × today_roi_at_action`. ROI is rounded to 2 decimals, so up to ~0.5% of spend in error. |

(B3 exposure and B7 conversions were used by the earlier Block B and are retired.)

### The five answers per rule

| # | answer | how |
|---|---|---|
| 1 | **What it did** | by `action_date`: decisions, repeat firings (all firings − distinct adset-days), success / failed runs, adsets, overlaps (`rule@adset`), rollover |
| 2 | **Did it stop the bleeding?** | the acted adsets: profit before the action (B8), profit on the rest of that day (day total − before), profit on the later days of the week. Also FB conversions (Meta) vs estimated conversions (internal model) on the action day and later days; conversions reported on later days with $0 spend are the delay |
| 3 | **Peers and missed** | **peers** = adsets in the 5 accounts with no rules that met the rule's condition, on their first matching day, before 06-12; what they made or lost on the later days. **Missed** = ACC-04 adsets that met the condition and the rule never acted on (split: no rule acted / another rule acted that day) |
| 4 | **Impact $ and verdict** | one $ figure per decision (below), summed per rule |
| 5 | **Data issues** | failed runs, repeat firings, rule name ≠ condition that ran, decisions that fail the condition on the engine's own numbers, engine age ≠ spend day, live budget ≠ metadata budget, rollover, spend after a turn-off |

**Rule conditions** are replayed as the engine ran them (`condition_name`), with inclusive thresholds, on each day's end-of-day numbers:

| rule | condition replayed |
|---|---|
| R01 | age ≥ 5 |
| R02 | −30% < ROI ≤ −10% |
| R03 | positive days = 0 and age > 2 |
| R04 | age = 1 and budget used ≥ 35% and ROI ≤ −50% |
| R05 | today's profit ≤ −$1 and budget used ≥ 15% (named "Total Profit <= -2.5$") |
| R06 | today's profit ≤ −$1.25 and age ≤ 3 and total profit ≤ −$3 (named "<= -4$") |
| R07 | ROI ≥ −50% and budget > $65 |
| R08 | age = 4 |
| R09 | not replayed (Turn ON "automation mistake" is not a performance condition) |
| R10 | −10% < ROI ≤ 5% and budget ≥ $100 |
| R11 | positive days = 0 and age > 3 |
| R12 | ROI ≤ −50% and budget ≤ $65 |

Age = `spend_day_no`; budget = metadata `daily_budget / 100`; budget used = day spend ÷ budget; total profit and positive days count this week only.

### Impact — how much each decision saved or missed

One $ figure per decision, and both directions count:
- **+ = saved:** the adset would have lost money.
- **− = missed income:** the adset would have made money.

Failed runs are $0: nothing changed.

| action | impact | why this way |
|---|---|---|
| Turn OFF | −(peer later profit per day left × days left) | the adset is off, so what it would have done is taken from peers that met the same condition and were left running |
| Budget cut | −(budget removed per day × ROI after the cut × days left) | the adset keeps running, so its ROI after the cut is observed |

| term | definition |
|---|---|
| peer later profit per day left | Σ peers' profit on the days after their matching day ÷ Σ the days left in the week after it. Peers that stopped on their own count as $0 days |
| days left (turn-off) | whole days after the action until 06-12 |
| days left (cut) | days after the action on which the adset still spent, within the B4 window, plus the unspent share of the action day (1 − `spend_at_action` / budget). $0 if another rule turned the adset off that day |
| ROI after the cut | revenue ÷ spend after the action, over the rest of the action day and the following days in the window, − 1 |
| verdict | **too small to matter** when \|net\| < 1% of ACC-04's week spend ($25.86); otherwise **right** (net > 0) or **wrong** |

**Assumptions.**
- A turned-off adset would have done what peers that met the same condition did.
- Peers are checked on end-of-day numbers; the engine checks during the day.
- The metadata budget is one end-of-week snapshot, so budget conditions on peers are approximate.
- The budget a cut removed would have been spent at the ROI the adset had after the cut.
- History is only what the week holds (06-06 → 06-12).

**Concrete cases (question 2).** Decisions sorted by impact: the ones with the most missed income are the candidates for "a competent human wouldn't have done this".

### ACC-04 leftovers

Every ACC-04 adset-day with spend that no rule acted on, in four buckets: **loser, matched a rule** (missed) · **loser, no rule covers it** (a gap) · **winner, no rule matched** (rightly spared) · **winner, matched a rule** (a rule would have hit a winner). Loser = profit < 0 that day.

### Decisions made

| decision | why |
|---|---|
| Each rule gets the five answers only. | Extra KPIs made the method too complicated to follow and defend. |
| A decision is rule × adset × `action_date`; "before" is the first successful firing. | Repeat firings on an adset already acted on change nothing: R04 fired 109 times for 39 decisions. |
| Failed runs are counted in answer 1 and are $0 in impact. Failed runs as a control group are left for a later session. | The question is what the rules did. |
| When two rules act on the same adset-day, both get the impact. | Both acted. So rule totals can't be added into a week total. |
| Dates are keyed on `action_date`, with rollover flagged. | `action_time` is UTC; late firings belong to the next reporting date. |
| Metadata budgets are used as `daily_budget / 100`. | They are in cents: divided by 100 they match the live Meta budget on 39 of 39 R04 decisions, raw on 0. |
| Peers are adsets that met the rule's own condition. | Grouping peers by age × ROI band ignored R04's budget condition and flipped its result to "0 of 39 right, −$5.88". Peers that met R04's full condition lost −$14.02 later. |
| Conditions are replayed as `condition_name`, not `rule_name`. | That is what the engine ran: R05 and R06 ran different thresholds from their names, and the engine's numbers at the action fit `condition_name`. |
| A cut on an adset another rule turned off the same day is $0; cut days left count only days the adset still spent. | Otherwise R12 showed −$249 on an adset R08 turned off that morning. |
| Verdict "too small to matter" below 1% of ACC-04's week spend. | Separates rules that moved money from noise, with one fixed bar for every rule. |
| `task_A_script.py` is a template only; earlier versions are in `Archive/task_A_script_v1.py` and `_v2.py`. | Results live in `Task A/RULE_OUTPUTS.md`, not in code comments. |

## Rule-by-rule results

Filled in one rule at a time, after review.

## Data issues

| # | issue | how we found it | how we handled it |
|---|---|---|---|
| 1 | `metadata.daily_budget` is in cents, not dollars | divided by 100 it matches the live Meta budget in `rule_executions` on 39 of 39 R04 decisions; raw it matches 0 | every budget from metadata is used as `daily_budget / 100` |
| 2 | The engine ran a different condition than the rule's name | `condition_name` ≠ `rule_name`: R05 named "Total Profit <= -2.5$" ran "Today_profit <= -1$"; R06 named "<= -4$" ran "<= -3"; the engine's numbers at the action fit `condition_name` | conditions replayed as `condition_name` |
| 3 | Rules fired outside their own limits | engine numbers at the action: R11 fired at total days = 3 (condition > 3); R07 at ROI −51% (condition ≥ −50%); R05 once at today's profit −$0.25 (a rollover firing) | reported; impact still counted, since the action happened |
| 4 | Engine "total days" ≠ performance `spend_day_no` | R03: 5 of 10 decisions (engine 4–5 days vs spend day 1–2); no metadata date explains all cases | age for peers = `spend_day_no`; flagged per rule |
| 5 | Metadata budget is one end-of-week snapshot | live budget ≠ metadata on every budget-cut decision (e.g. 31626016833981: live $128.93 vs metadata $31.67) | budget conditions on peers are approximate; impact uses the live budget from `rule_executions` |
| 6 | Revenue on days with no spend | ACC-04: 3 adset-days, $9.75 (other accounts ≤ $1.04); shows up as R08 "+$6.55 later" with $0 spend | kept as-is |
| 7 | Spend continues after a turn-off | same-day spend after the action: R04 $4.64, R08 $3.07, R01 $1.22 | counted in "rest of day" |
| 8 | Many failed runs | 50 of 214 executions: R03 19, R02 17 (13 on one adset on 06-09), R09 8 of 8 | counted, $0 impact; separate analysis deferred |
| 9 | Rollover | action_time before midnight UTC logged on the next date: R03 7 of 10 decisions | keyed on `action_date`, flagged |
| 10 | Duplicate performance rows | 72 byte-identical rows, ACC-03 on 06-09 | `performance_scoped` = `SELECT DISTINCT` (4,947 → 4,875) |
