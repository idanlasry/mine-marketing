# RESULTS

## Task C — Decision agent replay

**Run:** [Task C/agent.py](../Task%20C/agent.py)

 - One 02:00 call per adset a day
 - Haiku 4.5 as a test model (production: Sonnet 5)
 - 837 active adset-days checked
 - 107 passed the bar or were re-called and went to the LLM
 - LLM cost: 0.34 USD for 107 calls (0.0032 USD per call).

- **Every active adset gets a decision:** adsets under the bar get `keep` from code, logged in `bar_check_log.jsonl`. LLM decisions are in [Task C/agent_log.csv] one row per call.
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
- Confidence is the model's own number and isn't calibrated.
- Every escalation came from the model itself.
- A low confidence level and an 'escalate' decision is an easy decision that gives nothing, but it's the start of what we can improve and adjust.



### 4. Feedback loop 

The Refactor agent from ARCHITECTURE.md ("the reporter") improves the Decision agent without retraining a model. 

- **Signal it learns from:** each decision's outcome at day + 2, once revenue is final and the datasets have a clear view of how the intervention worked, whether the buyer also changed the budget, and whether the agent's own `self_assessment` was right.
- **Where it is stored:**
  - verdicts (right / wrong / unclear, and why) are git logged and findings sent to a developer to review and approve
  - one `daily_report` per day, with stats, 3 cases (worst, best, random), up to 3 lessons and suggested changes
  - reports accumulate, and the reporter reads its last 7, so a lesson is only proposed when a pattern repeats

**Example from this replay:** after days 1–2 I reviewed the log by hand, the way the reporter would, and changed the prompt to better distinguish between a losing hiccup and a losing trend before day 3. Result: diminish went from 0 on day 1 and 5 on day 2 to 15 on day 3.

Caveat: this demands full prompt eval checks on the edge cases it finds, and also a basic eval for the starter cases right at shipping.

### How to measure success

- **Primary metric: A/B testing**
Design an A/B test to determine if the agent-touched adsets did better in profit and ROI. The key part is designing the control group. I think of segmenting each account's adsets into two groups, checking some A/A testing (adset characteristics, goal, spend etc.) and randomly allocating one group to the agent, with full exposure to this group. With a controlled overview on the metrics (so the drop won't fall sharply), observe the difference online, with peeking as in a Bayesian A/B test.
Moreover, keep overall tracks on all the adsets that the agent touched.

- Use the reporter: check if revenue caught up, explore log breaks, resumes, and scale_up decisions in the aftermath.

- Another very efficient tool is to keep a log of FB engine samples that are sampled every 30 min midday, and to simulate the agent's "online" decisions and outcome. Without training it, but with tests evaluating the prompts.

### Where the agent is weak

1.**there is no Kill switch or reversemethod.** just the tracking, and its a bit dagngourus
2.**It still lacks some important indicators.** Its self-assessments say "my wait worked" when the buyer changed the budget; it needs an indication of whether the outcome resulted from its own decision.
3. **No edge-case handling** and no tests done.
4. **One LLM call handles all the decisions:** it might be all over the place, and chaining different LLM calls might resolve a better outcome.
5. **Tested on Haiku, not Sonnet 5,** and on daily sums, not intraday data.
6. **Escalations are never resolved:** it can't handle escalation, and it resolves easily to human handling.

What is the real step I would take?
Define two actions it could take, pause and kill, and optimise for that in specific cases (young, small and losing).
Optimise, verify, and eval.
Then escalate and grow.

