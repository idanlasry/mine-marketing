# %%
# Task C: agent input. Queries (loaded once) + the JSON for one LLM call.
# Imported by agent.py (step 2 of the flow).
import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

PROJECT, DATASET = "first-proj001", "mine_marketing"
bq = bigquery.Client(project=PROJECT)

# ? token is "$." not "$" so a regex anchor ($) inside a query survives
q = lambda sql: bq.query(
    sql.replace("$.", f"`{PROJECT}.{DATASET}`.")
).to_dataframe()

REPLAY_DAYS = ("2026-06-10", "2026-06-12")
SHARK_SPEND = 50.0


# %% Load data once (end-of-day values; the 2:00 call sees the finished day)
perf = q("""
SELECT adset_id, account_name, date, spend, revenue, profit, roi,
  estimated_conversions AS conversions, spend_day_no
FROM $.performance_scoped
WHERE date <= '2026-06-12'
""")

# ! daily_budget is in cents: median metadata/buyer budget ratio = 100 (185 adsets), so /100
# ! metadata is one end-of-week snapshot, so early days can see a budget set later
meta = q("""
SELECT adset_id, bid_strategy, roas_target, daily_budget / 100 AS daily_budget,
  ARRAY_LENGTH(JSON_VALUE_ARRAY(geo_countries)) AS geo_count, effective_status
FROM $.metadata_scoped
""")

buyer = q("""
SELECT adset_id, CAST(DATE(TIMESTAMP(action_time)) AS STRING) AS date, action_time,
  event_type, old_budget, new_budget, note
FROM $.buyer_actions_scoped
WHERE adset_id != ''
ORDER BY action_time
""")

hist_by = {k: g for k, g in perf.groupby("adset_id")}
buyer_by_adset = {k: g for k, g in buyer.groupby("adset_id")}
meta_by = meta.set_index("adset_id").to_dict("index")
replay = perf[perf["date"].between(*REPLAY_DAYS) & (perf["spend"] > 0)].sort_values(["date", "account_name"])
print(f"{len(replay)} adset-days with spend in the replay window")


def clean(v):
    """numpy/NaN → plain JSON values (NaN is not valid JSON)."""
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [clean(x) for x in v]
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, "item") else v


# %% Budgets and the agent's own history on an adset
def buyer_actions_on(adset_id, date):
    b = buyer_by_adset.get(adset_id)
    return b[b["date"] == date] if b is not None else pd.DataFrame()


def buyer_budget(adset_id, date):
    """The cap: the buyer's last set budget up to that day, else the metadata budget."""
    b = buyer_by_adset.get(adset_id)
    if b is not None:
        set_so_far = b.loc[b["date"] <= date, "new_budget"].dropna()
        if len(set_so_far):
            return float(set_so_far.iloc[-1])
    budget = (meta_by.get(adset_id) or {}).get("daily_budget")
    return None if budget is None or pd.isna(budget) else float(budget)


def past_decisions(adset_id, date, agent_log):
    """The agent's own decisions on this adset in the 2 days before `date` (LLM calls only)."""
    since = str(pd.Timestamp(date) - pd.Timedelta(days=2))[:10]
    return [e for e in agent_log
            if e["adset_id"] == adset_id and since <= e["decision_date"] < date and e["source"] != "code"]


def is_tracked(adset_id, date, agent_log):
    past = past_decisions(adset_id, date, agent_log)
    return bool(past) and past[-1]["final"]["action"] != "untrack"


def current_budget(adset_id, date, agent_log):
    """Budget now: the buyer's change today stands; else the agent's last budget change; else the buyer budget."""
    if len(buyer_actions_on(adset_id, date)):
        return buyer_budget(adset_id, date)
    changed = [e["amount"] for e in past_decisions(adset_id, date, agent_log) if e["amount"] is not None]
    return changed[-1] if changed else buyer_budget(adset_id, date)


def allowed_actions(is_shark, buyer_today, cap, now):
    """Added by code so the agent can't propose what the gate will block."""
    actions = ["wait", "diminish", "pause", "unpause", "untrack", "escalate"]
    if is_shark:  # sharks: diminish and wait only (+ untrack / escalate)
        actions = [a for a in actions if a not in ("pause", "unpause")]
    if buyer_today:  # the buyer's change today stands
        actions = [a for a in actions if a not in ("pause", "unpause")]
    if cap is None or now is None or now >= cap:  # nothing to restore
        actions = [a for a in actions if a != "unpause"]
    if now is None:
        actions = [a for a in actions if a != "diminish"]
    return actions


# %% Build the JSON for the LLM call (3 blocks + fields added by code)
def build_input(r, agent_log):
    h = hist_by[r.adset_id]
    h = h[(h["date"] < r.date) & (h["date"] >= str(pd.Timestamp(r.date) - pd.Timedelta(days=7))[:10])]
    b = buyer_actions_on(r.adset_id, r.date)
    m = meta_by.get(r.adset_id)
    cap = buyer_budget(r.adset_id, r.date)
    now = current_budget(r.adset_id, r.date, agent_log)
    is_shark = bool(r.spend_day_no >= 3 and r.spend >= SHARK_SPEND)

    flags = []
    if m is None:
        flags.append("missing_metadata")
    if h.empty:
        flags.append("no_spend_history")
    if cap is None:
        flags.append("no_buyer_budget")

    past = [e["final"] | {"decision_date": e["decision_date"], "new_budget": e["amount"]}
            for e in past_decisions(r.adset_id, r.date, agent_log)]

    return clean({
        "engine_now": {
            "spend_now": r.spend, "revenue_now": r.revenue, "profit_now": r.profit, "roi_now": r.roi,
            "current_budget": now, "buyer_budget": cap, "hours_into_day": 24, "spend_day_no": r.spend_day_no,
            "last_7_days": h[["date", "spend", "revenue", "profit", "roi", "conversions"]].to_dict("records"),
        },
        "metadata": m,
        "history": {
            "buyer_actions_24h": b.drop(columns=["adset_id", "date"]).to_dict("records") if len(b) else [],
            "agent_log_48h": past,
        },
        "data_quality_flags": flags,
        "is_shark": is_shark,
        "allowed_actions": allowed_actions(is_shark, bool(len(b)), cap, now),
        "self_assessment_required": bool(past),
    })
