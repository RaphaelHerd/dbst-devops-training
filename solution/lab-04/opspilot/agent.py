"""Lab 5 - the investigation agent (rules: .kiro/specs/opspilot-agent/requirements.md).

Ready: the read-only tools from Labs 1-4, the report tool, the tool dispatcher, the step log and the report.
To build: recent_changes() and its tool definition (Task 1), investigate() - the agent loop (Task 2),
is_repeat() (Task 4, stretch goal). Task 3 is the prompt prompts/investigate/v2.md.
"""
from __future__ import annotations

import json
import time

import pandas as pd

from . import config, loaders
from .config import DATA_DIR, OUT_DIR, ROOT

PROMPTS = ROOT / "prompts" / "investigate"
STEPS_LOG = OUT_DIR / "investigation_steps.jsonl"
REPORT = OUT_DIR / "investigation_report.md"
DAY = "2026-11-09"
MAX_RESULT_CHARS = 4000
LIMIT_MESSAGE = ("Limit reached ({}). This tool call was not run. Do not call more tools - call submit_report now "
                 "with what you know.")
LIMIT_NOTICE = "Limit reached ({}). Do not call more tools - call submit_report now with what you know."


# ---------- Task 1: a new tool ----------

def recent_changes(service: str, hours: int, now: pd.Timestamp) -> list[dict]:
    """Changes and deployments of one service - or of all services - in the `hours` before `now`, newest first."""
    raise NotImplementedError("Task 1 - see .kiro/specs/opspilot-agent/requirements.md, Requirement 1")


RECENT_CHANGES_TOOL: dict | None = None           # Task 1: the tool definition (name, description, input_schema)


# ---------- Task 2: the agent loop ----------

def investigate(client, system: str, alert: str, now: pd.Timestamp, max_steps: int = 8,
                max_seconds: int = 120) -> dict:
    """Let the model investigate the alert with the tools until it submits a report or a limit stops it."""
    raise NotImplementedError("Task 2 - see .kiro/specs/opspilot-agent/requirements.md, Requirement 2")


# ---------- Task 4 (stretch goal): repeat guard ----------

def is_repeat(name: str, args: dict, history: list[tuple[str, dict]]) -> bool:
    """True when the same tool was already called with the same input."""
    raise NotImplementedError("Task 4 - see .kiro/specs/opspilot-agent/requirements.md, Requirement 4")


# ---------- ready: the read-only tools from Labs 1-4 ----------

def query_metrics(service: str, minutes: int, now: pd.Timestamp) -> dict:
    """Lab 1: the clean metrics of a service in the last `minutes` before `now`, per 5 minutes."""
    from .cleaning import clean_metrics

    clean, _ = clean_metrics(loaders.load_metrics_raw())
    minutes = max(15, min(int(minutes), 240))
    df = clean[(clean["service"] == service) & (clean["timestamp"] <= now)
               & (clean["timestamp"] > now - pd.Timedelta(minutes=minutes))]
    if df.empty:
        return {"error": f"no metrics for '{service}'. Known services: {', '.join(sorted(clean['service'].unique()))}"}
    slo = loaders.load_slo()
    limit = slo.loc[slo["service"] == service, "slo_p95_ms"]
    limit = int(limit.iloc[0]) if len(limit) else None
    per5 = (df.set_index("timestamp")[["p95_latency_ms", "error_rate_pct", "requests_per_min"]]
              .resample("5min").agg({"p95_latency_ms": "median", "error_rate_pct": "mean", "requests_per_min": "mean"}))
    above = df[df["p95_latency_ms"] > limit] if limit else df.iloc[0:0]
    num = lambda v, d=0: None if pd.isna(v) else round(float(v), d or None)   # noqa: E731 - JSON has no NaN
    return {"service": service, "from": f"{df['timestamp'].min():%H:%M}", "to": f"{df['timestamp'].max():%H:%M}",
            "slo_p95_ms": limit,
            "first_minute_above_slo": f"{above['timestamp'].min():%H:%M}" if len(above) else None,
            "per_5_min": [{"time": f"{t:%H:%M}", "p95_ms": num(r.p95_latency_ms),
                           "error_rate_pct": num(r.error_rate_pct, 2), "requests_per_min": num(r.requests_per_min)}
                          for t, r in per5.iterrows()]}


def search_logs(query: str, now: pd.Timestamp) -> list[dict]:
    """Lab 4: the 3 distinct log messages of payment-api closest in meaning to the query - up to `now`."""
    from .knowledge import search_logs as search

    return [{"level": t["level"], "message": t["template"], "lines": int(t["count"]),
             "first": f"{t['first']:%H:%M}", "last": f"{t['last']:%H:%M}", "versions": t["versions"],
             "similarity": round(score, 2)} for t, score in search(query, until=now)]


def search_runbooks(query: str, now: pd.Timestamp) -> list[dict]:
    """Lab 4: the 3 runbook sections closest in meaning to the query."""
    from .knowledge import search_runbooks as search

    return [{"source": c["id"], "updated": c["updated"], "similarity": round(score, 2), "text": c["text"]}
            for c, score in search(query)]


def similar_incidents(description: str, now: pd.Timestamp) -> list[dict]:
    """Lab 4: the 3 past incidents closest in meaning to the description."""
    from .knowledge import similar_incidents as search

    return [{"incident": e["id"], "date": e["updated"], "similarity": round(score, 2), "text": e["text"]}
            for e, score in search(description)]


def _schema(**props) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


SERVICES = {"type": "string", "enum": ["payment-api", "checkout-web", "booking-search"]}
TOOLS = [
    {"name": "query_metrics",
     "description": "Grafana metrics of one service for the last N minutes before now, per 5 minutes: p95 latency "
                    "(ms), error rate (%) and requests per minute, plus the first minute above the latency SLO. "
                    "Use it to see WHEN a problem started and how big it is.",
     "input_schema": _schema(service=SERVICES,
                             minutes={"type": "integer", "description": "How far back from now: 15 to 240."})},
    {"name": "search_logs",
     "description": "Search the payment-api application logs by meaning, up to now. Returns the 3 closest distinct "
                    "messages (IDs and numbers replaced by placeholders) with the number of lines, the first and "
                    "last time and the versions that wrote them. Use it to find errors and when they started.",
     "input_schema": _schema(query={"type": "string", "description": "What you look for, e.g. 'timeouts'."})},
    {"name": "search_runbooks",
     "description": "Search the team's runbooks (Agora) by meaning. Returns the 3 closest runbook sections with "
                    "their text. Use it for diagnosis steps and the approved mitigation.",
     "input_schema": _schema(query={"type": "string", "description": "The symptom or the question."})},
    {"name": "similar_incidents",
     "description": "Find past incidents similar to a problem description, with root cause and resolution. Use it "
                    "to learn what helped before.",
     "input_schema": _schema(description={"type": "string", "description": "The problem in one or two sentences."})},
]
SUBMIT_REPORT = {
    "name": "submit_report",
    "description": "Finish the investigation and hand the result to the on-call engineer. Call it exactly once - "
                   "when the evidence is enough, or when the tools give nothing new.",
    "input_schema": _schema(                          # structured fields first, the free text last
        hypotheses={"type": "array", "description": "Root-cause hypotheses, the most likely first.",
                    "items": _schema(cause={"type": "string"},
                                     confidence={"type": "string", "enum": ["high", "medium", "low"]},
                                     evidence={"type": "array",
                                               "items": _schema(tool={"type": "string"}, fact={"type": "string"})})},
        ruled_out={"type": "array", "items": {"type": "string"},
                   "description": "What you checked and excluded, and why."},
        next_step={"type": "string", "description": "The recommended next step for a human - you only read."},
        summary={"type": "string", "description": "What happened, in at most three sentences."}),
}
FUNCTIONS = {"query_metrics": query_metrics, "search_logs": search_logs, "recent_changes": recent_changes,
             "search_runbooks": search_runbooks, "similar_incidents": similar_incidents}


def tool_definitions() -> list[dict]:
    """All tools the model may call - strict schemas, so the tool inputs always match."""
    tools = TOOLS + ([RECENT_CHANGES_TOOL] if RECENT_CHANGES_TOOL else []) + [SUBMIT_REPORT]
    return [{**t, "strict": True} for t in tools]


# ---------- ready: run a tool, log a step, the first message ----------

def run_tool(name: str, args: dict, now: pd.Timestamp, history: list[tuple[str, dict]]) -> tuple[str, bool]:
    """Run one read-only tool. Returns (result as text, is_error). Never raises - errors go back to the model."""
    if name not in FUNCTIONS or (name == "recent_changes" and not RECENT_CHANGES_TOOL):
        return f"Unknown tool '{name}'. Use one of the tools you were given.", True
    try:
        if is_repeat(name, args, history):
            return f"You already called {name} with this input - use the result above or try something else.", True
    except NotImplementedError:
        pass                                            # Task 4 not built: no repeat guard
    history.append((name, dict(args)))
    try:
        result = FUNCTIONS[name](**args, now=now)
    except NotImplementedError as error:
        return f"This tool is not available: {error}", True
    except Exception as error:                          # wrong input, missing data, network
        return f"The tool failed - {type(error).__name__}: {error}", True
    text = json.dumps(result, ensure_ascii=False, default=str)
    return (text[:MAX_RESULT_CHARS] + " ... (cut)") if len(text) > MAX_RESULT_CHARS else text, False


def accept_report(report: dict) -> tuple[dict | None, str]:
    """Check the input of submit_report - LLM output is untrusted. Returns (report, tool result) or (None, the fix)."""
    problems = []
    if not report.get("hypotheses"):
        problems.append("hypotheses is empty - add at least one hypothesis with its evidence")
    for key, value in report.items():
        if "<parameter" in json.dumps(value) or "</" in json.dumps(value):
            problems.append(f"{key} contains tags - put every part of the report into its own field")
    if problems:
        print(f"      ⚠️ report rejected - {'; '.join(problems)}")
        return None, "The report was not accepted: " + "; ".join(problems) + ". Call submit_report again."
    return report, "Report received."


def log_step(step: int, name: str, args: dict, result: str, is_error: bool, seconds: float) -> None:
    """Print one tool call and append it to out/investigation_steps.jsonl - every step is traceable."""
    shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
    print(f"  {step:>2}. {'⚠️' if is_error else '🔧'} {name}({shown}) → {len(result):,} chars · {seconds:.1f} s")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with STEPS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"step": step, "tool": name, "input": args, "error": is_error, "seconds": round(seconds, 2),
                            "result": result}, ensure_ascii=False) + "\n")


def log_thought(text: str) -> None:
    """Print what the model writes between its tool calls."""
    if text.strip():
        print(f"      💭 {' '.join(text.split())[:220]}")


def first_message(alert: str, now: pd.Timestamp) -> str:
    return (f"<alert>\n{alert}\n</alert>\n\nCurrent time: {now:%H:%M} on {now:%A}, {now:%d %B %Y}. "
            "Investigate this alert.")


def alert_at(rule: str = "PaymentApiLatencyHigh") -> tuple[str, pd.Timestamp]:
    """The first alert of a rule from data/grafana/alerts.csv, as text and time."""
    from .knowledge import load_alerts

    first = load_alerts().query("rule == @rule").sort_values("fired_at").iloc[0]
    return f"{first['fired_at']:%H:%M} {first['severity'].upper()} {rule} - {first['summary']}", first["fired_at"]


def at(hhmm: str) -> pd.Timestamp:
    return pd.Timestamp(f"{DAY} {hhmm}", tz=config.TIMEZONE)


# ---------- ready: client, prompts, report ----------

def client():
    from anthropic import AnthropicBedrock             # key: AWS_BEARER_TOKEN_BEDROCK from the environment
    return AnthropicBedrock(aws_region=config.aws_region())


def prompt(version: str) -> str:
    path = PROMPTS / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"{path.relative_to(ROOT).as_posix()} does not exist yet - write it first.")
    return path.read_text(encoding="utf-8")


def guess(alert: str) -> str:
    """Step 1: one prompt, no tools - the model can only guess."""
    response = client().messages.create(model=config.model_id(), max_tokens=2048, output_config={"effort": "low"},
                                        system=prompt("no_tools"),
                                        messages=[{"role": "user", "content": f"<alert>\n{alert}\n</alert>"}])
    return "".join(b.text for b in response.content if b.type == "text").strip()


def print_report(result: dict, alert: str, now: pd.Timestamp, version: str) -> None:
    tokens = result.get("tokens", {})
    print(f"\n📋 Report · prompt {version} · stop: {result['stop']} · {result['steps']} steps · "
          f"{result['seconds']:.0f} s · tokens {tokens.get('in', 0):,} in / {tokens.get('out', 0):,} out")
    report = result.get("report")
    if not report:
        print("   No report - the agent stopped without submit_report. A human takes over.")
        return
    lines = [f"# Investigation - {alert}", "", f"Agent time: {now:%H:%M} · prompt {version} · stop: {result['stop']} · "
             f"{result['steps']} steps · {result['seconds']:.0f} s", "", "## Summary", report["summary"], "",
             "## Hypotheses"]
    print(f"   {report['summary']}")
    for n, h in enumerate(report["hypotheses"], 1):
        print(f"   {n}. [{h['confidence']}] {h['cause']}")
        lines.append(f"{n}. **[{h['confidence']}] {h['cause']}**")
        for e in h["evidence"]:
            print(f"        - {e['tool']}: {e['fact']}")
            lines.append(f"   - {e['tool']}: {e['fact']}")
    if report["ruled_out"]:
        print("   Ruled out:")
        lines += ["", "## Ruled out"]
        for r in report["ruled_out"]:
            print(f"        - {r}")
            lines.append(f"- {r}")
    print(f"   ➡️ Next step (for a human): {report['next_step']}")
    lines += ["", "## Next step (for a human)", report["next_step"]]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("📄 out/investigation_report.md · every step: out/investigation_steps.jsonl")
