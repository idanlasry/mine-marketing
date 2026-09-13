# Rule outputs — review tracker

One rule at a time, reviewed together. A rule is marked scanned only after its review; insight and data issues are filled in from that review.

Run a rule (asks for the rule number):
```
uv run python .claude/skills/rule-analysis/run_rule.py
```

## Segments

| segment | question it must answer | rules | scanned |
|---|---|---|---|
| 1. Day 1-2 kill | Did it stop losers before they burned money? | R04, R05, R06 | ⬜ 0 of 3 |
| 2. Never profitable | Were the adsets really never profitable? | R03, R11 | ⬜ 0 of 2 |
| 3. Age kill | No performance condition — did it kill winners? | R01, R08 | ⬜ 0 of 2 |
| 4. Budget cut | The adset keeps running — did the cut improve profit or just shrink spend? | R02, R07, R10, R12 | ⬜ 0 of 4 |
| 5. Undo | Did it try to undo the right thing? | R09 | ⬜ 0 of 1 |

## Rules

| segment | rule | action | rule name | scanned | insight | data issues |
|---|---|---|---|---|---|---|
| 1. Day 1-2 kill | R04 | Turn OFF | Turn Off - OWN RSOC \| Total Days = 1 \| budget > 35%\| ROI < -50% | ⬜ | | |
| 1. Day 1-2 kill | R05 | Turn OFF | Turn Off \| OWN RSOC \| Total Profit <= -2.5$ \| budget_usage_today >= 15% | ⬜ | | |
| 1. Day 1-2 kill | R06 | Turn OFF | Turn Off \| today_profit <= -1.25 $\| total_days <= 3 \| total profit <=-4$ \| OWN RSOC | ⬜ | | |
| 2. Never profitable | R03 | Turn OFF | Turn Off \| positive_days = 0 \| total_days > 2 \| OWN RSOC | ⬜ | | |
| 2. Never profitable | R11 | Turn OFF | Turn Off \| positive_days = 0 \| total_days > 3 \| OWN RSOC | ⬜ | | |
| 3. Age kill | R01 | Turn OFF | Turn OFF \| Total Days >= 5 \| OWN RSOC | ⬜ | | |
| 3. Age kill | R08 | Turn OFF | Turn OFF \| Total Days = 4 \| OWN RSOC | ⬜ | | |
| 4. Budget cut | R02 | Decrease −20% (min 9) | Budget Decrease \| OWN RSOC \| -30 < ROI <= -10 | ⬜ | | |
| 4. Budget cut | R07 | Decrease −40% (min 9) | Budget Decrease \| OWN RSOC \| -50 <= ROI \| Budget > 65$ | ⬜ | | |
| 4. Budget cut | R10 | Decrease −15% (min 9) | Budget Decrease \| OWN RSOC \| -10 < ROI <= 5 \| Budget >= 100$ | ⬜ | | |
| 4. Budget cut | R12 | Decrease −40% (min 9) | Budget Decrease \| OWN RSOC \| ROI <= -50 \| Budget <= 65$ | ⬜ | | |
| 5. Undo | R09 | Turn ON | Turn On \| Automation Mistake - Today \| OWN RSOC | ⬜ | | |

⬜ not scanned · ✅ scanned
