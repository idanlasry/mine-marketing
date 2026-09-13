---
name: rule-analysis
description: Analyse one auto-rule (R01–R12) for Task A — run the shared template for that rule, give five direct answers (what it did, did it stop the bleeding, peers and missed, $ impact and verdict, data issues), and lock only what the user approves into Task A/RULE_OUTPUTS.md, deliverables/INVESTIGATION.md and deliverables/DECISIONS.md. Also runs the ACC-04 leftovers check. Use when the user names a rule or segment to analyse ("segment 2, R03", "run R05", "leftovers").
---

# Rule analysis — one rule at a time

Task A question 1: what did the auto-rules do over the week, and how much money did they save or miss. One rule per pass. **The verdict is the user's**: this skill runs, reports and recommends; it locks only what the user says to lock.

Keep it simple: five answers per rule, plain words, numbers from the run. No extra KPIs unless the user asks.

Read first:
- `deliverables/INVESTIGATION.md` → "Rule impact — method" (locked, don't redefine) and "Rule-by-rule results".
- `CLAUDE.md`: data gotchas.

## Segments

| segment | question it must answer | rules |
|---|---|---|
| 1. Day 1-2 kill | Did it stop losers before they burned money? | R04, R05, R06 |
| 2. Never profitable | Were the adsets really never profitable? | R03, R11 |
| 3. Age kill | No performance condition — did it kill winners? | R01, R08 |
| 4. Budget cut | The adset keeps running — did the cut improve profit or just shrink spend? | R02, R07, R10, R12 |
| 5. Undo | Did it try to undo the right thing? | R09 |

## Step 1 — run

```
PYTHONIOENCODING=utf-8 uv run python .claude/skills/rule-analysis/run_rule.py <RULE>
PYTHONIOENCODING=utf-8 uv run python .claude/skills/rule-analysis/run_rule.py leftover
```

A rule run prints the condition it replays, then:

| # | answer | query |
|---|---|---|
| 1 | What it did | `BLOCK_A` — decisions, repeats, successes / failures, adsets, overlaps, rollover, by day |
| 2 | Did it stop the bleeding? | `K_BLEEDING` — acted adsets: profit before the action, rest of that day, later days; FB vs estimated conversions on the action day and later days, and conversions reported on later $0-spend days (the delay) |
| 3 | Peers and missed | `K_PEERS` — acted / peers in the 5 no-rule accounts that met the same condition / ACC-04 adsets that met it and weren't acted on |
| 4 | Impact $ and verdict | `K_IMPACT` (total) and `K_IMPACT_DECISIONS` (per decision) |
| 5 | Data issues | `K_ISSUES` — the same checklist for every rule |

`leftover` prints the ACC-04 adset-days no rule acted on: losers vs winners, matched a rule or not.

Rule conditions live in `CONDITIONS` in `Task A/task_A_script.py`. Don't edit the script per rule — it is a template only. Investigate odd numbers with a throwaway query in the scratchpad.

## Step 2 — report (do not lock yet)

Short, plain words, one line each:
1. **What it did** — decisions, adsets, failed runs.
2. **Stopped the bleeding?** — yes / no, profit before vs after.
3. **Peers** — did matching peers lose or earn later ($). **Missed** — ACC-04 adsets it didn't act on ($).
4. **Impact** — net $ (+ saved / − missed income) and the verdict; the worst decision if it matters.
5. **Data issues** — only non-zero checks, each with its number.

Then the proposed locks.

## Step 3 — lock only what the user approves

| where | what |
|---|---|
| `Task A/RULE_OUTPUTS.md` | the rule's five answers as tables, with the run command |
| `deliverables/INVESTIGATION.md` | "Rule-by-rule results": the rule's row in the summary table; new data issues as rows in "Data issues" |
| `deliverables/DECISIONS.md` | only if a method decision was made: short `Finding:` / `Decision:` lines |

If the template changes, re-run R04 and check it still gives: peers later −$14.02, 9 missed, impact +$3.18.

## Guardrails

- **One rule per pass.** Rule totals can't be added across rules: overlapping decisions count for both.
- **No number that wasn't run.**
- **Failed runs** are counted in answer 1 and are $0 in impact.
- **Budgets from metadata are `daily_budget / 100`** and are a single end-of-week snapshot: budget conditions on peers are approximate.
- **Turn-off impact is an estimate from peers** that met the same condition. Say so when quoting it.
- **Conditions are checked on end-of-day numbers** for peers and missed; the engine checks during the day.

## BigQuery and tooling gotchas

- `at` is a reserved word — don't use it as an alias.
- A CTE alias can be shadowed by a same-named column → name date columns `dt`.
- Correlated subqueries that reference another table inside an aggregate are rejected → rewrite as a JOIN.
- `QUALIFY` cannot sit in the same SELECT as a `GROUP BY` aggregate → filter in a subquery first.
- Write multi-line Python/SQL helpers with the Write tool, not `python -c` in Bash — quoting breaks.
- Set `PYTHONIOENCODING=utf-8` when printing; campaign names contain non-Latin text.
