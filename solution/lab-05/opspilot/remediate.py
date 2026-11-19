"""Lab 7 - safe remediation (rules: .kiro/specs/opspilot-remediate/requirements.md).

Ready: the proposal by Claude, the action parser, the approval card, the simulated deployment platform (canary,
rollback, scaling, verification), the stop switch, the circuit breaker and the audit log.
To build: check_action() (Task 1), dry_run() (Task 2), decide() (Task 3). Task 4 (stretch) is the prompt
prompts/remediate/postmortem.md.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd

from . import agent, config, loaders
from .config import DATA_DIR, OUT_DIR, ROOT

STATE = OUT_DIR / "platform_state.json"
AUDIT = OUT_DIR / "remediation_audit.jsonl"
STOP = OUT_DIR / "STOP"
PROMPTS = ROOT / "prompts" / "remediate"
NOW = "14:20"
SAFE_ACTIONS = ("rollback", "scale", "page_team")
SLO_MS = 300
BREAKER = (2, 30)                                   # at most 2 executed changes per service in 30 minutes


# ---------- Task 1: the safe action set ----------

def check_action(action: dict, state: dict, releases: pd.DataFrame) -> list[str]:
    """The rules of the safe action set this action breaks - an empty list means the action is allowed."""
    raise NotImplementedError("Task 1 - see .kiro/specs/opspilot-remediate/requirements.md, Requirement 1")


# ---------- Task 2: the dry run ----------

def dry_run(action: dict, state: dict, releases: pd.DataFrame, now: pd.Timestamp) -> dict:
    """What the action would change and how risky it is right now - without changing anything."""
    raise NotImplementedError("Task 2 - see .kiro/specs/opspilot-remediate/requirements.md, Requirement 2")


# ---------- Task 3: automate or escalate ----------

def decide(action: dict, violations: list[str], plan: dict) -> str:
    """The decision tree: block, escalate, approve or auto."""
    raise NotImplementedError("Task 3 - see .kiro/specs/opspilot-remediate/requirements.md, Requirement 3")


# ---------- ready: platform state and release history ----------

def load_releases() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "cicd" / "releases.csv", dtype=str, keep_default_na=False)
    df["released_at"] = pd.to_datetime(df["released_at"], utc=True).dt.tz_convert(config.TIMEZONE)
    return df.sort_values(["service", "released_at"], ignore_index=True)


def previous_version(service: str, releases: pd.DataFrame, current: str) -> str | None:
    """The release of `service` right before `current` - the only target of a rollback."""
    versions = list(releases.loc[releases["service"] == service, "version"])
    return versions[versions.index(current) - 1] if current in versions and versions.index(current) > 0 else None


def load_state() -> dict:
    """The simulated platform: out/platform_state.json, or a fresh copy of data/cicd/platform.json."""
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    state = json.loads((DATA_DIR / "cicd" / "platform.json").read_text(encoding="utf-8"))
    for s in state["services"].values():
        s["instances"] = [s["version"]] * s["instances"]       # one entry per instance: its version
    return state


def save_state(state: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def p95_ms(service: str, version: str) -> int:
    """Simulated p95 latency of one instance: 2.3.1 has the timeout problem, 2.2.4 the pool problem (INC-3920)."""
    return {("payment-api", "2.3.1"): 2400, ("payment-api", "2.2.4"): 1900}.get((service, version), 250)


def audit(event: str, **fields) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), "event": event, **fields}
    with AUDIT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _audit_entries() -> list[dict]:
    return [json.loads(x) for x in AUDIT.read_text(encoding="utf-8").splitlines()] if AUDIT.exists() else []


def breaker_open(service: str | None) -> bool:
    """Circuit breaker: too many executed changes to this service in the last minutes - a human takes over."""
    limit, minutes = BREAKER
    since = datetime.now().astimezone() - timedelta(minutes=minutes)
    done = [e for e in _audit_entries() if e["event"] == "executed" and e.get("service") == service
            and datetime.fromisoformat(e["time"]) >= since]
    return len(done) >= limit


# ---------- ready: where an action comes from ----------

def parse_action(text: str) -> dict:
    """An action typed by a person - or pasted from a chat, a ticket, a runbook: 'rollback payment-api 2.3.0'."""
    words = text.split()
    action = {"action": words[0].lower() if words else "", "service": None, "version": None, "replicas": None,
              "team": None, "reason": "typed by hand", "evidence": [], "source": "manual"}
    rest = words[1:]
    if action["action"] == "page_team":
        action["team"] = rest[0] if rest else None
        return action
    action["service"] = rest[0] if rest else None
    if len(rest) > 1:
        if action["action"] == "scale":
            action["replicas"] = int(rest[1]) if rest[1].lstrip("-").isdigit() else None
        else:
            action["version"] = rest[1]
    return action


def _tool(name: str, description: str, **props) -> dict:
    props.update(reason={"type": "string", "description": "Why - in one or two sentences."},
                 evidence={"type": "array", "items": {"type": "string"}, "description": "Facts that support it."})
    return {"name": name, "description": description, "strict": True,
            "input_schema": {"type": "object", "properties": props, "required": list(props),
                             "additionalProperties": False}}


PROPOSAL_TOOLS = [
    _tool("rollback", "Propose to roll a service back to an earlier version.",
          service={"type": "string"}, version={"type": "string"}),
    _tool("scale", "Propose to change the number of instances of a service.",
          service={"type": "string"}, replicas={"type": "integer"}),
    _tool("page_team", "Propose to page the on-call engineer of a team.", team={"type": "string"}),
]


def incident_context(now: pd.Timestamp, state: dict | None = None) -> str:
    """What the planner knows: the alert, the latest change, the platform, the investigation report (Lab 5),
    two runbooks."""
    alert, _ = agent.alert_at()
    changes = loaders.load_changes()
    latest = changes[changes["started_at"] <= now].sort_values("started_at").iloc[-1]
    state, releases = state or load_state(), load_releases()
    platform = []
    for name, s in state["services"].items():
        history = releases[releases["service"] == name].tail(3)
        shown = ", ".join(f"{r.version} ({r.released_at:%Y-%m-%d}{', DB migration ' + r.db_migration if r.db_migration else ''})"
                          for r in history.itertuples())
        platform.append(f"{name} ({s['kind']}): {len(s['instances'])} instances on {s['version']}"
                        + (f" · last releases: {shown}" if shown else ""))
    parts = [f"<alert>\n{alert}\n</alert>",
             f"<latest_change>\n{latest['change_id']} {latest['service']} {latest['type']} {latest['version']} - "
             f"{latest['description']} - finished {latest['finished_at']:%H:%M}\n</latest_change>",
             "<platform>\n" + "\n".join(platform) + "\n</platform>"]
    report = agent.REPORT
    if report.exists():
        parts.append(f"<investigation_report>\n{report.read_text(encoding='utf-8')}\n</investigation_report>")
    for name in ("payment-api-latency.md", "payment-db.md"):
        text = (DATA_DIR / "agora" / "runbooks" / name).read_text(encoding="utf-8")
        parts.append(f'<runbook source="{name}">\n{text}\n</runbook>')
    return "\n\n".join(parts) + f"\n\nCurrent time: {now:%H:%M}. Propose one action."


def propose(now: pd.Timestamp, state: dict) -> dict | None:
    """Claude proposes exactly one action as a tool call - a proposal, never an execution."""
    response = agent.client().messages.create(
        model=config.model_id(), max_tokens=4000, output_config={"effort": "medium"},
        system=(PROMPTS / "propose.md").read_text(encoding="utf-8"), tools=PROPOSAL_TOOLS,
        messages=[{"role": "user", "content": incident_context(now, state)}])
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined the request.")
    call = next((b for b in response.content if b.type == "tool_use"), None)
    if call is None:
        return None
    action = {"action": call.name, "service": None, "version": None, "replicas": None, "team": None,
              "source": "llm"}
    action.update(call.input)
    return action


# ---------- ready: the simulated platform executes ----------

def describe(action: dict, state: dict) -> str:
    a, service = action.get("action"), action.get("service")
    current = state["services"].get(service, {}).get("version", "?") if service else "?"
    if a == "rollback":
        return f"rollback {service} {current} → {action.get('version')}"
    if a == "scale":
        now_n = len(state["services"].get(service, {}).get("instances", [])) if service else 0
        return f"scale {service} {now_n} → {action.get('replicas')} instances"
    if a == "page_team":
        return f"page the on-call engineer of {action.get('team')}"
    return " ".join(str(v) for v in (a, service, action.get("version") or action.get("replicas")) if v)


def execute_naive(action: dict, state: dict) -> None:
    """Step 1 only: do exactly what the text says - everywhere at once, no checks, no dry run, no approval."""
    a, service = action["action"], action.get("service")
    target = state["services"].get(service)
    if a == "page_team":
        print(f"   📟 paged {action.get('team')}")
    elif target is None:
        print(f"   🤷 '{service}' does not exist - nothing happened, by luck")
    elif a == "rollback":
        target["instances"] = [action["version"]] * len(target["instances"])
        target["version"] = action["version"]
        print(f"   ⏪ all {len(target['instances'])} instances of {service} restarted at once on {action['version']}")
        print(f"   📈 p95 now {p95_ms(service, action['version']):,} ms (SLO {SLO_MS} ms)")
    elif a == "scale":
        n = action.get("replicas") or 0
        target["instances"] = [target["version"]] * max(n, 0)
        print(f"   ⚖️ {service} now has {len(target['instances'])} instances")
        if not target["instances"]:
            print(f"   💥 {service} has no instance left - every request that needs it fails")
    else:
        print(f"   💥 '{a}' was executed on {service}")
    save_state(state)


def execute(action: dict, state: dict) -> bool:
    """Run an approved action on the simulated platform: canary first, verify, then the rest. True = healthy."""
    a, service = action["action"], action.get("service")
    if a == "page_team":
        print(f"   📟 paged the on-call engineer of {action['team']}")
        return True
    target = state["services"][service]
    if a == "scale":
        target["instances"] += [target["version"]] * (action["replicas"] - len(target["instances"]))
        save_state(state)
        p95 = p95_ms(service, target["version"])
        print(f"   ⚖️ {service} scaled to {len(target['instances'])} instances (simulated: 2 min)")
        print(f"   {'✅' if p95 <= SLO_MS else '❌'} verify: p95 {p95:,} ms (SLO {SLO_MS} ms)"
              + ("" if p95 <= SLO_MS else " - more instances do not help: the cause is not load"))
        return p95 <= SLO_MS
    old, new = target["version"], action["version"]
    target["instances"][0] = new
    canary = p95_ms(service, new)
    print(f"   🐤 canary: 1 of {len(target['instances'])} instances on {new} (simulated: 3 min)")
    print(f"   {'✅' if canary <= SLO_MS else '❌'} verify canary: p95 {canary:,} ms · other instances on {old}: "
          f"{p95_ms(service, old):,} ms")
    if canary > SLO_MS:
        target["instances"][0] = old
        save_state(state)
        print("   ↩️ canary unhealthy - canary restored, nothing else touched. A human takes over.")
        return False
    target["instances"] = [new] * len(target["instances"])
    target["version"] = new
    save_state(state)
    print(f"   ⏪ the other {len(target['instances']) - 1} instances on {new} (simulated: 10 min)")
    print(f"   ✅ verify: p95 {p95_ms(service, new):,} ms - below the SLO of {SLO_MS} ms. The alert clears.")
    return True


# ---------- ready: one remediation run ----------

def approval_card(action: dict, state: dict, plan: dict) -> None:
    why = action.get("reason") or "-"
    evidence = "; ".join(action.get("evidence") or [])
    migrations = ", ".join(plan.get("migrations_to_undo") or []) or "no DB migration to undo"
    factors = ", ".join(plan.get("risk_factors") or []) or "no risk factor"
    print("   ┌ 🙋 Approval needed - OpsPilot")
    print(f"   │ Action:  {describe(action, state)}{', canary first' if action['action'] == 'rollback' else ''}")
    print(f"   │ Why:     {why}")
    if evidence:
        print(f"   │          evidence: {evidence[:300]}")
    print(f"   │ Dry run: {' → '.join(plan.get('steps', []))} · ~{plan.get('minutes', '?')} min · {migrations}")
    print(f"   │ Risk:    {plan.get('risk', '?')} - {factors}")
    print("   └")


def run(text: str | None = None, naive: bool = False, answer: str | None = None) -> int:
    now = agent.at(NOW)
    state, releases = load_state(), load_releases()
    if STOP.exists() and not naive:
        audit("refused", reason="stop switch")
        print("🛑 The stop switch is on (out/STOP) - OpsPilot executes nothing. "
              "python -m opspilot remediate --resume turns it off.")
        return 1
    action = parse_action(text) if text else propose(now, state)
    if action is None:
        print("🤷 No proposal - the model answered without a tool call. A human takes over.")
        return 1
    print(f"💡 Proposal ({action['source']}): {describe(action, state)}")
    audit("proposal", **{k: v for k, v in action.items() if v not in (None, [])})
    if naive:
        print("⚡ Naive mode: executed as proposed - no checks, no dry run, no approval")
        execute_naive(action, state)
        return 0

    try:
        violations = check_action(action, state, releases)
    except NotImplementedError as error:
        print(f"⏳ {error}\n🛑 Nothing is executed before the safe action set is built.")
        return 1
    for v in violations:
        print(f"   ⛔ {v}")
    plan: dict = {}
    if not violations:
        try:
            plan = dry_run(action, state, releases, now)
        except NotImplementedError as error:
            print(f"⏳ {error}\n🛑 Nothing is executed without a dry run.")
            return 1
    try:
        decision = decide(action, violations, plan)
    except NotImplementedError as error:
        print(f"⏳ {error}\n🛑 Nothing is executed without a decision.")
        return 1
    if decision in ("auto", "approve") and breaker_open(action.get("service")):
        print(f"🧯 Circuit breaker: {BREAKER[0]} changes to {action.get('service')} in the last {BREAKER[1]} min - "
              "a human takes over.")
        decision = "escalate"
    audit("decision", decision=decision, violations=violations, plan=plan)
    icon = {"block": "⛔", "escalate": "📟", "approve": "🙋", "auto": "🤖"}.get(decision, "❓")
    print(f"{icon} Decision: {decision}")

    if decision == "block":
        print("   Not in the safe action set - nothing is executed.")
        return 1
    if decision == "escalate":
        team = state["services"].get(action.get("service") or "", {}).get("team", "the incident commander")
        print(f"   Too risky for OpsPilot - page {team}. Nothing is executed.")
        return 1
    if decision == "approve":
        approval_card(action, state, plan)
        reply = (answer or input("   Type approve or reject: ")).strip().lower()
        audit("approval", answer=reply)
        if reply != "approve":
            print("   ❎ Rejected - nothing is executed.")
            return 1
        print("   ✅ Approved")
    healthy = execute(action, state)
    audit("executed", action=action["action"], service=action.get("service"), healthy=healthy,
          version=action.get("version"), replicas=action.get("replicas"))
    print("📒 out/remediation_audit.jsonl - every proposal, decision, approval and step")
    return 0 if healthy else 1


# ---------- ready: status, reset, stop switch, post-mortem ----------

def print_status() -> None:
    state = load_state()
    print(f"🖥️ Simulated platform{' · 🛑 STOP SWITCH ON' if STOP.exists() else ''}")
    for name, s in state["services"].items():
        versions = pd.Series(s["instances"]).value_counts() if s["instances"] else pd.Series(dtype=int)
        shown = " + ".join(f"{n}× {v}" for v, n in versions.items()) or "0 instances"
        worst = max((p95_ms(name, v) for v in s["instances"]), default=0)
        flag = (" · 💥 down" if not s["instances"] else
                "" if s["kind"] == "database" else f" · p95 {worst:,} ms {'🔴' if worst > SLO_MS else '🟢'}")
        print(f"   {name:<15} {s['kind']:<8} {shown}{flag}")


def reset() -> None:
    for path in (STATE, AUDIT, STOP):
        path.unlink(missing_ok=True)
    print("🔄 Platform reset to 14:20: payment-api 2.3.1 on 6 instances · audit log and stop switch cleared")


def stop_switch(on: bool) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if on:
        STOP.write_text("Red button pressed - no OpsPilot action until removed.\n", encoding="utf-8")
        audit("stop switch", on=True)
        print("🛑 Stop switch ON - OpsPilot executes nothing until: python -m opspilot remediate --resume")
    else:
        STOP.unlink(missing_ok=True)
        audit("stop switch", on=False)
        print("▶️ Stop switch off")


def postmortem() -> None:
    """Task 4 (stretch): Claude drafts a blameless post-mortem from the facts and the audit log."""
    prompt = PROMPTS / "postmortem.md"
    if not prompt.exists():
        raise FileNotFoundError(f"{prompt.relative_to(ROOT).as_posix()} does not exist yet - write it first.")
    entries = _audit_entries()
    facts = incident_context(agent.at(NOW)).rsplit("\n\nCurrent time", 1)[0]
    trail = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries[-30:]) or "(no remediation recorded)"
    note = (f"The times in the audit are the times of the lab run. In the incident, the remediation started at {NOW} "
            "on the day of the alert.")
    response = agent.client().messages.create(
        model=config.model_id(), max_tokens=6000, output_config={"effort": "medium"},
        system=prompt.read_text(encoding="utf-8"),
        messages=[{"role": "user", "content": f"{facts}\n\n<remediation_audit>\n{note}\n{trail}\n"
                                              "</remediation_audit>"}])
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined the request.")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    (OUT_DIR / "postmortem.md").write_text(text + "\n", encoding="utf-8")
    print(text[:1500] + ("\n..." if len(text) > 1500 else ""))
    print("\n📄 out/postmortem.md - a draft: a human reviews and completes it")
