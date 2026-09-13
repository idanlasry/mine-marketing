---
name: rule-analysis
description: Rule-by-rule check of one ACC-04 auto-rule (R01–R12) for Task A, following the process worked out on R01 — definition and activity, day-by-day view, decisions at fire time vs day close, did it take effect, adsets that met the condition but weren't hit (accumulated ROI), odd behaviour, then a short bottom line. Runs `run_rule.py <RULE>`, reports, and locks only what the user approves. Use when the user names a rule to check ("rule 2", "do R08", "next rule").
---

# Rule analysis — one rule at a time

Task A: did each auto-rule save or burn money? One rule per pass. **The verdict is the user's**: run, report, push back, and lock only what the user approves.

House style: short replies, plain words, one question per turn. Only what was asked — offer extras in one line. Numbers only from runs.

## Run

```
PYTHONIOENCODING=utf-8 uv run python .claude/skills/rule-analysis/run_rule.py R02
PYTHONIOENCODING=utf-8 uv run python .claude/skills/rule-analysis/run_rule.py R07 --condition "roi >= -0.50 AND budget > 65"
```

The runner prints steps 1–6. Conditions live in `CONDITIONS` in `run_rule.py` (as the engine ran them, `condition_name`). Chase odd numbers with a throwaway query in the scratchpad, not in the runner.

## The process (worked out on R01)

| step | output block | what to look for |
|---|---|---|
| 1. Definition & activity | 1a, 1b, 1c | Name = `condition_name`? (R04/R05/R06 differ.) Firings, successes, fails, repeats, adsets, decisions, first/last firing, days active, failure reasons. |
| 2. Day by day | 2 | Each acted adset's week: already dying? flipping win/lose every day? other rules cutting it the same days? |
| 3. Decisions | 3, 3b | Per decision: 3-day ROI at fire, ROI at fire vs close, spend and revenue at fire vs close. `flipper` = loser at fire, winner at close — usually an early reading before revenue arrived. Verdict per adset: right / wrong / reasonable. |
| 4. Took effect? | 4 | Turn-off: did spend stop (later days with no spend)? Cut: did spend actually drop? Revenue that came after the fire. Human (`ui_*`) budget changes after the rule — a reversal? |
| 5. Met condition, not hit | 5 | ACC-04 adset-days meeting the condition, fired vs not, winning/losing at close, accumulated ROI. What would the rule hit if it ran as named — and was not firing a loss or luck? |
| 6. Odd behaviour | 6a, 6b | Fires far less than eligible (switched on late? only on losing-at-the-moment?). Rollover firings, decisions on the last data day (no after-window), engine age ≠ spend_day_no, overspending adsets. |
| 7. Value | 7 | One $ per decision (+ saved / − missed), summed; too small to matter if \|total\| < $25.86. Rules below. |
| 8. Bottom line | — | Right on X of Y · value $ · what is out of reach · data issues. |

### Value rules (stage 7) — decided with the user

| action | value | counts when |
|---|---|---|
| Budget cut | −(ROI at close) × budget removed (live budget − last set budget) | the **whole day's** spend reached ≥ 95% of the new budget; else zero. Action day only. No 0.9 discount. |
| Turn-off | −(adset's average daily profit over the **last 3 days** before the action day) × days left in the data | zero-spend days in the window count as zero profit. No spend in the window (new, or paused before) → no value (blank, not zero), flag it. Last data day (06-12) → zero. Window before 06-06 (data start) → no value, flag it; partly before → average over the days present, flag it. Why last 3 days, not all history: a dying adset's early wins made a right turn-off look like a loss (R01, 31167350331032). |

## Report format

**Show every stage, in order (1 → 8), each as its own heading with a small table and 1–2 plain lines.** Never skip to the bottom line — the user reviews each stage the way R01 was done. Stage 2 (day by day) as an adset × date grid: `profit (spend)` with the rules that fired that day.

Stage 3 example (R01):

| adset | fired (UTC) | 3-day ROI at fire | ROI at fire | ROI at close | spent at fire | spent at close |
|---|---|---|---|---|---|---|
| 31167350331032 | 06-11 02:00 | −58% | −100% | −100% | 0.71 USD | 0.93 USD |
| 31191755212537 | 06-11 23:30 | +5% | −47% | +30% | $8.38 | $9.45 |
| 31626016833981 | 06-12 16:30 | −11% | −15% | −15% | $20.28 | $20.22 |

- Right on 2 of 3 (already losing over 3 days); 1 wrong — a winner judged on an early reading ($7.84 revenue arrived after the turn-off).
- Break-even on the action day (−4% on $31). Real cost = days after, beyond the data.
- As named it would have hit 65 adset-days earning +18.9%; it fired on 3, all on 06-11/12.

## Lock only what the user approves

| where | what |
|---|---|
| `Task A/task_A_script.py` | set `RULE` / `CONDITION` in the RBR and RBR.2 cells; results as `# *` / `# !` comments under the cells |
| `deliverables/INVESTIGATION.md` | the user writes the bottom line; add tables or data-issue rows only when asked |
| `deliverables/DECISIONS.md` | only if a method decision was made |

## Lessons already learned — don't repeat the mistakes

- **Action-day $ is not the value.** A turn-off costs or saves mostly on the days AFTER (31255165214890: ~$100 missed over 4 days, nothing on the action day). Value turn-offs with history on the adset's own daily profit × days left; day-1 adsets (R04) need peers or budget use (0.65 for day-1, budget ≤ $5).
- **Budget ≠ spend.** Two adsets spend 6–9× their budget (data issue #12) — budget-based $ breaks there, and a cut can "succeed" and change nothing.
- **Revenue delay.** ROI at fire reads too low at 00–12 UTC and on rollover firings (21–23 UTC) — data issue #11. Check fire time before calling a loser.
- **06-12 is the last data day** — no after-window; say so.
- **`buyer_actions`: only `ui_*` rows are humans**; `update_*` rows are often the rules' own changes.
- **Accumulated ROI = SUM(revenue) / SUM(spend) − 1**, never an average of daily ROIs.
- **Rule totals can't be added across rules** — overlapping decisions count for both.
- **Failed runs changed nothing** — count them, no value.
- Metadata budget = `daily_budget / 100`, one end-of-week snapshot.

## BigQuery gotchas

- `action_date` is STRING → `CAST(... AS DATE)` before date math; compare `CAST(p.date AS DATE)`.
- Reserved words: `at`, `nulls`, `over`. Avoid select aliases that equal a grouped column name (ROLLUP labels come back NULL).
- 0/0 raises → always `SAFE_DIVIDE`.
- Run scripts from a file, not stdin (`load_dotenv` asserts); set `PYTHONIOENCODING=utf-8`.
