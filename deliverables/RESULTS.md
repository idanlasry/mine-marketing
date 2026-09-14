# RESULTS

## Task C — Decision agent replay

**Run:** [Task C/agent.py](../Task%20C/agent.py)

 - one 02:00 call per adset a day 
 - Haiku 4.5 as a test model (production: Sonnet 5)
 - 837 active adset-days checked
 - 107 passed the bar or were re-called and went to the LLM
 - LLM cost: 0.34 USD for 107 calls (0.0032 USD per call).

- **Every active adset gets a decision:** adsets under the bar get `keep` from code, logged in `bar_check_log.jsonl`. LLM decisions are in [Task C/agent_log.csv](../Task%20C/agent_log.csv), one row per call.
- **Data caveat:** the snapshot has full-day sums only, no 30-minute engine runs, so the replay has one 02:00 check per day and no intraday re-calls.

### Output: the brief's schema + extra fields

| Field | Why |
|---|---|
| `brief_action` + `action` | Brief names (scale_down, keep…) plus the architecture's (diminish, wait, untrack…), so wait and untrack stay distinguishable |
| `amount_pct`, `hours` | The size of a cut and how long a wait or pause lasts; `amount` alone hides it |
| `trigger` | `sent` (new bar hit) or `re_call` (tracked adset): why the agent was called |
| `self_assessment` | On re-calls the agent grades its own earlier decision; input for the feedback loop |
| `gate_notes` | What the code gate overrode and why |
| `execution_status` | Whether the decision was actually applied (below) |
| `input_json` | The exact context the decision relied on, for audit |
| `input_tokens`, `output_tokens`, `cost_usd`, `model` | Cost per decision, for the 30 USD/day stop |

### Execution outcome: was the decision updated?

Every LLM call logs an `execution_status`. In the replay the executor is simulated; in production it is the Meta API response.

| Status | Calls | Actions |
|---|---|---|
| applied | 35 | 17 diminish, 18 pause |
| no_change | 54 | 38 wait, 16 untrack |
| pending_human | 15 | escalate |
| failed_below_min_budget | 3 | diminish to 0.95 USD, under Meta's minimum daily budget |

The 3 failures led to a prompt change: a cut must keep the budget at 1 USD or more, otherwise pause or escalate.

### 2. Context per decision (no raw tables)

Code builds one JSON per adset, about 2,600 input tokens including the prompt:
- **Engine now:** today's spend, revenue, profit, ROI, current budget, buyer budget (the cap), age
- **Last 7 days:** one row per day (spend, revenue, profit, ROI, conversions)
- **Metadata:** bid strategy, ROAS target, budget, geo count, status
- **History:** buyer actions that day; the agent's own decisions on this adset in the last 48 h
- **Added by code:** `data_quality_flags`, `is_shark`, `allowed_actions`, `self_assessment_required`

Query and JSON building: [Task C/agent_input.py](../Task%20C/agent_input.py).

### 3. The uncertainty mechanism

The agent is told not to guess, and code enforces it in layers:

1. **Code flags known gaps before the call:** missing metadata, no spend history, no buyer budget.
   - Code: [agent_input.py:127-131](../Task%20C/agent_input.py#L127-L131)
2. **The agent can only choose from `allowed_actions`,** computed by code (no pause on sharks or after a buyer change today).
   - Code: [agent_input.py:101-111](../Task%20C/agent_input.py#L101-L111) builds the list
   - Prompt: [agent.py:107](../Task%20C/agent.py#L107) "Choose only from allowed_actions"
   - Gate: [agent.py:193-195](../Task%20C/agent.py#L193-L195) any other action becomes `escalate`
3. **The agent must give a confidence;** below 0.6 the gate turns any action into `escalate`.
   - Pydantic: [agent.py:69](../Task%20C/agent.py#L69) `confidence` is required (described as 0–1, not enforced)
   - Prompt: [agent.py:112](../Task%20C/agent.py#L112) "confidence < 0.6 means you don't know: choose escalate rather than guess"
   - Gate: [agent.py:190-192](../Task%20C/agent.py#L190-L192), threshold `MIN_CONFIDENCE` at [line 36](../Task%20C/agent.py#L36)
4. **The agent can escalate itself** and name the problem in `data_quality_flags`.
   - Pydantic: [agent.py:64](../Task%20C/agent.py#L64) `escalate` is an allowed action; [line 71](../Task%20C/agent.py#L71) `data_quality_flags` is required
   - Prompt: [agent.py:104](../Task%20C/agent.py#L104) "escalate: a human must decide"; [line 121](../Task%20C/agent.py#L121) "Conflicting signals or broken data (revenue 0 with conversions…): escalate and flag it"
   - Few-shot: [agent.py:130](../Task%20C/agent.py#L130) escalates at confidence 0.5 with a named flag
5. **Pydantic check:** an invalid answer becomes `escalate`, never a guess.
   - Gate: [agent.py:183-185](../Task%20C/agent.py#L183-L185)

**It worked on the unclear cases.** 15 of 107 calls escalated, all at confidence 0.35–0.50. The clearest case is an ACC-04 adset with conversions but zero revenue on 3 days in a row. The agent flagged a possible attribution break and escalated it on each call rather than cutting or keeping. Other escalations: a day-1 adset spending 41 USD against a 3.81 USD buyer budget, and a −90% ROI right after the buyer's own 50% cut.

**Weak spots:** 
- confidence is the model's own number and isn't calibrated.
-  every escalation came from the model itself.
-  low confidance level and 'escalate' decision is easy decision that give mothing, but its the start of what we can improve and adjust



### 4. Feedback loop 

The Refactor agent from ARCHITECTURE.md ("the reporter") improves the Decision agent without retraining a model. 

- **Signal it learns from:** each decision's outcome at day + 2, once revenue is final and the datasets have a clear view of how the intevantion worked whether the buyer also changed the budget, and whether the agent's own `self_assessment` was right.
- **Where it is stored:**
  - verdicts (right / wrong / unclear, and why) are git logged and findings sent to a developer to review and approve
  - one `daily_report` per day, with stats, 3 cases (worst, best, random), up to 3 lessons and suggested changes
  - reports accumulate, and the reporter reads its last 7, so a lesson is only proposed when a pattern repeats

**Example from this replay:** after days 1–2 I reviewed the log by hand, the way the reporter would, and changed the prompt before day 3 Results taht diminish went from 0 on day 1 and 5 on day 2 to 15 on day 3.

caveat- this demand a fulle prompt eval checks by edege cases it finde, and also a basic eval for the starter cases right at shipping

### How to measure success

- **Primary metric: A/B testing** 
design an a/b test to determine if the the agent touched adset did better. shdow agent, diffarent accounts, random selection or auto rules tht activated similar decisions, its probably the hardest thing to figure out, how to allocate the right controll group. i thnking on segmenting each account adsets into two groups,check some a/a testing (adsets cherecharistics, goal, spend etc) and randomly allocate to one the agent, full exposure to thisgroup. with a controlled overview on the metrics (so the drop wont fall sharply) observe (on line- with picking as in basyain a/b test) the diffarence. 
moreover keep overall traks on all the adsets that the agent touched

- explore log breaks,resumes, and scale up

- an other most efficiant tool  is to keep a log of fb engive samples that are sampeled every 30 min midday, andto simulate the agent "online" decisions, and outcome. without training it, but with test evaluating the prompts.  
### Where the agent is weak

1. **it still lacks the important indicators** Its self-assessments say "my wait worked" when the buyer changed the budget, it needs indication what the outcome resolved properly from its onw decision.
2. **no edge cases handalling** and no tests done
3. **one llm calls that handell all the decision** it might be all over the place, and cahin diffarent llm calls might reolve better outcome
4. **Tested on Haiku, not Sonnet 5,** and on daily sums, not intraday data.
5. **Escalations are never resolved** it cant handel escallation, and it resolved easly to human handeling

what is the real step i would take? 
define to action it could take, pause and kill, and optimise for that, in specific cases (young, small and losing)
optimise, varify, and eval, 
then escallate and grow.

