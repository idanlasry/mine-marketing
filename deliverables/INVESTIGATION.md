how much money did rule-driven actions save or burn?

## Rule impact — method
first it will be a brief overview on the rules, rule segmantation, and rule preformence view, then each rule will be evaluated alone, with a skill that been built. the file will consist only takeaways, important tables, and bottom lines, but the skill and script are available in the repo.

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

### Rule view

Successful decisions per rule (rule × adset × `action_date`), action-day totals.

| rule | action | successful firings | failed firings | decisions | losers / winners at action | losers / winners end of day | loser → winner same day | spend $ | profit $ | ROI |
|---|---|---|---|---|---|---|---|---|---|---|
| R01 | OFF, age ≥5 | 4 | 0 | 3 | 3 / 0 | 2 / 1 | 1 | 31 | −1 | −3.7% |
| R03 | OFF, never positive, age >2 | 17 | 19 | 10 | 10 / 0 | 10 / 0 | 0 | 1 | −1 | −94.6% |
| R04 | OFF, day 1 | 109 | 0 | 39 | 39 / 0 | 39 / 0 | 0 | 37 | −28 | −77.7% |
| R05 | OFF, profit | 6 | 1 | 5 | 5 / 0 | 5 / 0 | 0 | 8 | −6 | −70.7% |
| R06 | OFF, profit, age ≤3 | 1 | 0 | 1 | 1 / 0 | 1 / 0 | 0 | 3 | −1 | −34.3% |
| R08 | OFF, age = 4 | 13 | 2 | 9 | 9 / 0 | 6 / 3 | 3 | 24 | −7 | −30.2% |
| R11 | OFF, never positive, age >3 | 2 | 0 | 1 | 1 / 0 | 1 / 0 | 0 | 0 | 0 | −100% |
| **Turn-offs** | | **152** | **22** | **68** | **68 / 0** | **64 / 4** | **4** | **104** | **−44** | |
| R02 | cut −20% | 6 | 17 | 6 | 6 / 0 | 3 / 3 | 3 | 300 | +22 | +7.3% |
| R07 | cut −40% | 1 | 0 | 1 | 1 / 0 | 0 / 1 | 1 | 54 | +8 | +15.3% |
| R10 | cut −15% | 2 | 0 | 2 | 1 / 1 | 1 / 1 | 1 | 584 | +57 | +9.8% |
| R12 | cut −40% | 3 | 3 | 3 | 3 / 0 | 2 / 1 | 1 | 36 | −5 | −13.7% |
| **Budget cuts** | | **12** | **20** | **12** | **11 / 1** | **6 / 6** | **6** | **974** | **+82** | |
| R09 | ON | 0 | 8 | 0 | – | – | – | – | – | – |
| **All rules** | | **164** | **50** | **80** | | | | | | |

Source: `task_A_script.py` RULE.1. At action = `today_roi_at_action` of the first successful firing; end of day = that adset-day's final profit in performance.

**Caveats.**
- If two rules acted on the same adset-day, its spend counts under both rules, so the totals may be slightly high.
- The end-of-day check covers only the action day. Whether a killed adset would have recovered later in the week is the $ impact step.
- "At action" ROI reads too low early in the day (data issue 11), so some "flippers" were never real losers.

# 1- computing the rules outcome

### Calculations rule by rule
#### Rule calculation formula:
##### Ive decided to calculate the roles preformence differantly for the two main types of rules. from after rule one, ive analysis ive built a skill analysing and building metadat tabales on each rule
- Cut budget rules: (ROI at close) × budget removed, counted only if the whole day's spend ≥ 95% of the new budget. Action day only.
- Turn-off rules: (the adset's average daily profit on its spend 3 days before the action). No history (day 1) → flagged and roi*0.8 of daily original budget. its might be missing future days but it suppoused to punish uncertainty

#### rule 1 (task_A_script.py:227): break even
- Break even, 3 adsets fired, two lost with a day before loses, one flipped and earned (it also earned the day before)
- 65 Misses adsets that could have been fire but dident, which is good but weird, otherwise 383$ of profit would been lost
#### rule 2- breaks even
#### rule 3- right on 10/10, saving + 12.68
#### rule 4 -+$20
- 70 repeat firings on adsets already turned off
- its harder to tell what is the real savings, but I've decided to go to budget saved * 0.5 (other small 1 day adsets in other account reached only 0.65 of their budget + I guess some revenue will add up)

#### rule 5 - + 4.80
- hidden age limits? it fired only on adset that ages 1–2 days and skipped 33 older losing adset-day

#### rule 6 and forth:
- I used the skill to get an assessment of all the next rules outcome:

Bottom line All rules

| | losers cut $ | winners cut $ | net $ |
|---|---|---|---|
| Turn-offs | +41.70 | −10.38 | +31.32 |
| Budget cuts | +4.61 | −14.78 | −10.17 |
| **ACC-04** | **+46.31** | **−25.16** | **+21.15** (+21.22 with the R05/R06 overlap counted once) |

#### Major take-aways are:
- budget cut rules was pure losses, just wasn't worth it. due to the revenue delay the engine cut winners more then loosers
- Turn-off rules was not smart enough on old adsets (blindly killing)
- R04 did the most of the savings. most of the new, small adsets losing money(over all acounts), the rule cut them properly, with more accurate, or smart agent, it can keep those who delayed while keeping the spends tight

# 2 - wrong rules
### R08 (and also R01)- Blind shut down, ignoring market winners
- It didn't always cut winners, it was mixed, big winners and big losers too
- It blindly ignores the past outcome, and even current revenue

31255165214890 case — the adset's week:

| date | age | spend $ | profit $ | ROI | rule |
|---|---|---|---|---|---|
| 06-06 | 2 | 23.70 | +26.44 | +112% | |
| 06-07 | 3 | 54.41 | +28.29 | +52% | |
| 06-08 | 4 | 9.60 | +2.88 | +30% | R08 |
| 06-09 → 12 | | 0 | 0 | | off for good |

The decision:

| adset | date | fired (UTC) | 3-day ROI (engine) | ROI at fire | ROI at close | spent at fire | spent at close |
|---|---|---|---|---|---|---|---|
| 31255165214890 | 06-08 | 06-07 22:30 | +5% | −87% | +30% | $8.23 | $9.60 |

### rule 10 - Budget Decrease | OWN RSOC | -10 < ROI <= 5 | Budget >= 100$
well. its just bad rule, if budget is more than 100, that probably means the ad set is a shark, it decided early on on low ROI (due to the revenue latency) and killed a strong adset.

| adset | date | fired (UTC) | 3-day ROI | ROI at fire | ROI at close | spent at fire | spent at close |
|---|---|---|---|---|---|---|---|
| 31302925337341 | 06-07 | 05:30 | +49% | +4% | 0% | $109 | $320 |
| 31302925337341 | 06-08 | 02:00 | +25% | −4% | +22% | $70 | $264 |

## Data issues

| # | issue | how I found it | how we handled it |
|---|---|---|---|
| 1 | Reporting day starts at 21:00 UTC — a firing at 22:30 UTC counts for the next day | noticed R01 and R08 fire at night (UTC) and checked it: `action_date` = next day on 21 of 21 firings at 21–23 UTC | noted; everything keyed on `action_date`, not `DATE(action_time)`. Late firings flagged: they see 1–2 hours of the new day, so ROI at fire reads far too low. Age rules fire exactly then, since total days ticks over at 21:00 UTC |
| 2 | old_budget new_budget are deceiving | checking the rules execution table, old budget didn't verify informative, while new budget and current_budget_from_fb are informative with the rule logic toward the set_budget; fusing set_budget as new adset real budget and new budget as previous | use set budget and current_budget_from_fb |
| 3 | Spend continues after a turn-off | related to the delay hinted in the brief | counted in "rest of day" |
| 4 | Many failed runs | 50 of 214 executions: R03 19, R02 17 (13 on one adset on 06-09), R09 8 of 8 | counted, $0 impact; separate analysis deferred |
| 5 | Duplicate performance rows | looked for dups in the performance table, deliberately | `performance_scoped` = `SELECT DISTINCT` (4,947 → 4,875) |
| 6 | Revenue delay within the day | deliberately looked for revenue gap in the data sets, found that between the recurring rules failed executions | using it.. it is a bad feature of the engine, it needs to take into account when planning automations and rules |
| 7 | Spend far above the adset budget | it popped up when I look at the characteristic of the rule one activated adsets (the table of the skill show spend and budget side by side). adset 31191755212537 for example has spent 41–72 every day on a $7.62–12.70 budget (Meta overspend allows up to 1.75×, according to Claude), with no matching buyer change. it might be a bug or an engine feature of shark adsets | rules diminish impact on these adsets was zeroed |
