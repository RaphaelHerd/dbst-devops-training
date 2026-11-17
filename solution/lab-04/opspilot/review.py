"""Lab 3 - change and pipeline review (rules: .kiro/specs/opspilot-change-review/requirements.md).

Ready: loading the CI/CD exports, the prompt chain with structured outputs, the critic pass and the report.
Built in this solution: extract_failures() (Task 1), scan_diff() (Task 2), policy_gate() (Task 4).
"""
from __future__ import annotations

import json
import re

import pandas as pd

from . import config
from .config import DATA_DIR, OUT_DIR, ROOT

SERVICE, VERSION = "payment-api", "2.3.1"
CICD = DATA_DIR / "cicd"
PROMPTS = ROOT / "prompts" / "change-review"
TAIL_LINES = 200


# ---------- Task 1: shrink the pipeline log ----------

LOG_LINE = re.compile(r"^(\S+) (\w+)\s+\[([\w-]+)\] (.*)$")


def extract_failures(log: str) -> list[str]:
    """The lines of a pipeline log that matter for a review, in log order, repeated lines collapsed."""
    kept, seen = [], {}                                 # seen: (level, stage, message) -> [position, count]
    for raw in log.splitlines():
        match = LOG_LINE.match(raw)
        if not match:
            continue
        stamp, level, stage, message = match.groups()
        if level == "DEBUG":
            continue
        signal = (level in ("ERROR", "WARN") or stage == "pipeline" or "FAILED" in message or "SKIPPED" in message
                  or "quarantine" in message.lower())
        if not signal:
            continue
        key = (level, stage, message)
        if key in seen:
            seen[key][1] += 1
            continue
        seen[key] = [len(kept), 1]
        kept.append(f"{stamp[11:19]} {level} [{stage}] {message}")
    for position, count in seen.values():
        if count > 1:
            kept[position] += f" (× {count})"
    return kept


# ---------- Task 2: scan the diff ----------

SECRET_RULES = {
    "provider key": re.compile(r"\b(?:psk|sk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "secret assignment": re.compile(r"(?i)\b\w*(?:password|secret|token|api_key)\w*\s*[:=]\s*[\"']([^\"']{12,})[\"']"),
}
PINNED = re.compile(r"^([A-Za-z0-9_.\-]+)==([0-9][0-9.]*)")
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _version(text: str) -> tuple[int, ...]:
    """'1.26.18' -> (1, 26, 18): versions compare as numbers, part by part."""
    return tuple(int(part) for part in text.split(".") if part.isdigit())


def scan_diff(diff: str, advisories: pd.DataFrame) -> list[dict]:
    """Hard-coded secrets and vulnerable dependencies in the ADDED lines of a unified diff."""
    known = {row["package"].lower().replace("_", "-"): row for _, row in advisories.iterrows()}
    findings, current = [], None
    for number, line in enumerate(diff.splitlines(), 1):
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
            continue
        if not line.startswith("+"):
            continue
        added = line[1:]
        for rule, pattern in SECRET_RULES.items():
            match = pattern.search(added)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                findings.append({"kind": "secret", "severity": "critical", "file": current, "diff_line": number,
                                 "evidence": f"{value[:8]}… ({rule})"})      # never the full value
                break
        name = (current or "").split("/")[-1]
        if name.startswith("requirements") and name.endswith(".txt"):
            pin = PINNED.match(added.strip())
            if pin:
                package, version = pin.group(1).lower().replace("_", "-"), pin.group(2)
                advisory = known.get(package)
                if advisory is not None and _version(version) < _version(advisory["fixed_in"]):
                    findings.append({"kind": "dependency", "severity": advisory["severity"], "file": current,
                                     "diff_line": number,
                                     "evidence": f"{package}=={version} - {advisory['advisory']}, "
                                                 f"fixed in {advisory['fixed_in']}"})
    return sorted(findings, key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))


# ---------- Task 4: policy gate ----------

def policy_gate(release: pd.Series, previous: pd.Series, findings: list[dict]) -> dict:
    """PASS or FAIL for a release, with one reason per broken rule - rules in code, no LLM."""
    reasons = [f"{f['severity']} {f['kind']} in {f['file']}: {f['evidence']}"
               for f in findings if f["severity"] in ("critical", "high")]
    skipped, skipped_before = int(release["tests_skipped"]), int(previous["tests_skipped"])
    if skipped > skipped_before:
        reasons.append(f"{skipped} skipped test{'s' if skipped != 1 else ''} - {previous['version']} had "
                       f"{skipped_before}")
    drop = float(previous["coverage_pct"]) - float(release["coverage_pct"])
    if drop > 5:
        reasons.append(f"coverage {release['coverage_pct']} % - {previous['version']} had "
                       f"{previous['coverage_pct']} % (-{drop:.1f} points, limit 5)")
    return {"decision": "FAIL" if reasons else "PASS", "reasons": reasons}


# ---------- ready: CI/CD exports ----------

def load_runs() -> pd.DataFrame:
    df = pd.read_csv(CICD / "pipeline_runs.csv", dtype={"run_id": str, "commit": str, "version": str},
                     keep_default_na=False)
    for col in ("started_at", "finished_at"):
        df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert(config.TIMEZONE)
    return df


def release_runs(runs: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """The runs of the release under review, its deployed run and the deployed run of the previous release."""
    mine = runs[runs["service"] == SERVICE].sort_values("started_at")
    this = mine[mine["version"] == VERSION]
    deployed = this[this["status"] == "success"].iloc[-1]
    before = mine[(mine["version"] != VERSION) & (mine["status"] == "success")
                  & (mine["started_at"] < this["started_at"].min())]
    return this, deployed, before.iloc[-1]


def read_log(run: pd.Series) -> str:
    return (CICD / run["log_file"]).read_text(encoding="utf-8")


def load_diff() -> str:
    return (CICD / f"release-{VERSION}.diff").read_text(encoding="utf-8")


def load_advisories() -> pd.DataFrame:
    return pd.read_csv(CICD / "advisories.csv", dtype=str)


def change_ticket() -> str:
    changes = pd.read_csv(DATA_DIR / "itsm" / "changes.csv", dtype=str)
    row = changes[(changes["service"] == SERVICE) & (changes["version"] == VERSION)]
    return row["change_id"].iloc[0] if len(row) else "no change ticket"


def redact(diff: str, findings: list[dict]) -> str:
    """Replace every diff line with a secret by a placeholder - the LLM never sees the value."""
    lines = diff.splitlines()
    for f in findings:
        if f["kind"] == "secret":
            lines[f["diff_line"] - 1] = "+[REDACTED: hard-coded secret]"
    return "\n".join(lines)


def tag(name: str, body: str, **attrs) -> str:
    extra = "".join(f' {k}="{v}"' for k, v in attrs.items())
    return f"<{name}{extra}>\n{body}\n</{name}>"


# ---------- ready: the LLM calls ----------

def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


TEXT, TEXTS = {"type": "string"}, {"type": "array", "items": {"type": "string"}}
FAILURES = _obj({"failures": {"type": "array", "items": _obj({"run_id": TEXT, "what": TEXT, "error": TEXT,
                                                              "evidence": TEXT})},
                 "skipped": {"type": "array", "items": _obj({"run_id": TEXT, "test": TEXT, "reason": TEXT})},
                 "summary": TEXT})
CAUSE = _obj({"cause": TEXT, "changed_code": TEXT, "flaky": {"type": "boolean"}, "evidence": TEXTS,
              "confidence": {"type": "string", "enum": ["low", "medium", "high"]}})
FIX = _obj({"action": {"type": "string", "enum": ["rerun", "quarantine-test", "revert-change", "fix-forward"]},
            "why": TEXT, "steps": TEXTS})
CRITIC = _obj({"checks": {"type": "array", "items": _obj({"check": TEXT, "finding": TEXT,      # finding first,
                                                          "passed": {"type": "boolean"}})}})   # then the decision


def _client():
    from anthropic import AnthropicBedrock             # key: AWS_BEARER_TOKEN_BEDROCK from the environment
    return AnthropicBedrock(aws_region=config.aws_region())


def _prompt(name: str) -> str:
    path = PROMPTS / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"{path.relative_to(ROOT).as_posix()} does not exist yet - write it first.")
    return path.read_text(encoding="utf-8")


def ask(client, prompt: str, message: str, usage: dict, schema: dict | None = None):
    """One link of the chain. With a schema, structured outputs guarantee valid JSON."""
    output = {"effort": "low"}
    if schema:
        output["format"] = {"type": "json_schema", "schema": schema}
    response = client.messages.create(model=config.model_id(), max_tokens=2048, output_config=output,
                                      system=_prompt(prompt), messages=[{"role": "user", "content": message}])
    usage["in"] += response.usage.input_tokens
    usage["out"] += response.usage.output_tokens
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"Link {prompt}: the answer stopped early ({response.stop_reason}).")
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return json.loads(text) if schema else text


# ---------- ready: naive review, checks, the chain ----------

def naive() -> None:
    """Step 1: send only the end of the deployed run's log - as most CI tools show it."""
    _, deployed, _ = release_runs(load_runs())
    lines = read_log(deployed).splitlines()
    usage = {"in": 0, "out": 0}
    answer = ask(_client(), "naive", tag("log", "\n".join(lines[-TAIL_LINES:]), run=deployed["run_id"]), usage)
    print(f"Naive review - sent the last {TAIL_LINES} of {len(lines):,} lines of run {deployed['run_id']} "
          f"· {usage['in']:,} tokens in\n\n📣 {answer}")


def _print_findings(findings: list[dict]) -> None:
    for f in findings:
        icon = "🔴" if f["severity"] in ("critical", "high") else "🟡"
        print(f"   {icon} {f['severity']:<9} {f['kind']:<11} {f['file']:<20} {f['evidence']}")


def review(use_llm: bool) -> int:
    """Run every built task; with use_llm also the prompt chain. Returns 1 when the gate says FAIL."""
    runs = load_runs()
    this, deployed, previous = release_runs(runs)
    ticket = change_ticket()
    print(f"Change review - {SERVICE} {VERSION} ({ticket}) · runs {', '.join(this['run_id'])} · "
          f"deployed by run {deployed['run_id']}")

    extracts, findings, gate = None, None, None
    try:
        shrunk = {}
        for _, run in this.iterrows():
            log = read_log(run)
            shrunk[run["run_id"]] = (len(log.splitlines()), extract_failures(log))
        extracts = shrunk
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "change_review_extract.txt").write_text(
            "\n\n".join(tag("extract", "\n".join(lines), run=run) for run, (_, lines) in extracts.items()),
            encoding="utf-8")
        print("✅ Task 1 - logs shrunk: " + " · ".join(f"run {run} {n:,} → {len(lines)} lines"
                                                      for run, (n, lines) in extracts.items())
              + " · out/change_review_extract.txt")
    except NotImplementedError as error:
        print(f"⏳ {error}")

    diff = load_diff()
    try:
        findings = scan_diff(diff, load_advisories())
        print(f"✅ Task 2 - diff scanned: {len(findings)} finding{'s' if len(findings) != 1 else ''}")
        _print_findings(findings)
    except NotImplementedError as error:
        print(f"⏳ {error}")

    if findings is not None:
        try:
            gate = policy_gate(deployed, previous, findings)
            print(f"🚦 Gate: {gate['decision']}")
            for reason in gate["reasons"]:
                print(f"   - {reason}")
        except NotImplementedError as error:
            print(f"⏳ {error}")

    if use_llm:
        if extracts is None:
            print("🛑 The chain needs the shrunk logs - build Task 1 first.")
            return 1
        if findings is None:
            print("🛑 Nothing from the diff is sent to the LLM before Task 2 (scan) is built - it may contain "
                  "secrets.")
            return 1
        try:
            chain(this, extracts, redact(diff, findings), findings, gate, ticket)
        except FileNotFoundError as error:
            print(f"⏳ Task 3 - {error}")
            return 1
    if gate and gate["decision"] == "FAIL":
        print("exit code 1 - a pipeline would stop here")
        return 1
    return 0


def chain(this: pd.DataFrame, extracts: dict, diff: str, findings: list[dict], gate: dict | None,
          ticket: str) -> None:
    """failures → cause → fix → summary → critic (→ one revision). Each output is the next input."""
    client, usage = _client(), {"in": 0, "out": 0}
    columns = ["run_id", "commit", "trigger", "status", "tests_passed", "tests_failed", "tests_skipped",
               "coverage_pct"]
    runs_csv = this[columns].to_csv(index=False).strip()
    logs = "\n".join(tag("extract", "\n".join(lines), run=run) for run, (_, lines) in extracts.items())

    failures = ask(client, "1_failures", tag("runs", runs_csv) + "\n" + logs, usage, FAILURES)
    print(f"🔗 1 failures  {failures['summary']}")
    cause = ask(client, "2_cause", tag("failures", json.dumps(failures, indent=1)) + "\n" + tag("diff", diff),
                usage, CAUSE)
    print(f"🔗 2 cause     {cause['cause']} (flaky: {'yes' if cause['flaky'] else 'no'} · "
          f"confidence: {cause['confidence']})")
    fix = ask(client, "3_fix", tag("failures", json.dumps(failures)) + "\n" + tag("cause", json.dumps(cause)),
              usage, FIX)
    automatic = fix["action"] == "rerun" and cause["flaky"]     # self-healing rule, in code: only a flaky rerun
    print(f"🔗 3 fix       {fix['action']} - {fix['why']}\n              "
          f"{'🤖 may run automatically' if automatic else '🧑 needs a human decision'}")

    facts = "\n".join([tag("change", f"{ticket} · {SERVICE} {VERSION}"), tag("runs", runs_csv),
                       tag("failures", json.dumps(failures)), tag("cause", json.dumps(cause)),
                       tag("fix", json.dumps(fix)),
                       tag("findings", json.dumps([{k: f[k] for k in ("kind", "severity", "file", "evidence")}
                                                   for f in findings])),
                       tag("gate", json.dumps(gate) if gate else "not run - Task 4 is not built yet")])
    summary = ask(client, "4_summary", facts, usage)
    critic = ask(client, "5_critic", facts + "\n" + tag("summary", summary), usage, CRITIC)
    issues = [c["finding"] for c in critic["checks"] if not c["passed"]]      # the code counts, not the model
    if not issues:
        print(f"🧐 critic      ok - all {len(critic['checks'])} checks passed")
    else:
        print(f"🧐 critic      {len(issues)} of {len(critic['checks'])} checks failed → summary revised once")
        for issue in issues:
            print(f"              - {issue}")
        summary = ask(client, "4_summary", facts + "\n" + tag("draft", summary) + "\n"
                      + tag("critic", "\n".join(issues)), usage)

    path = OUT_DIR / f"change_review_{VERSION}.md"
    path.write_text(summary + "\n", encoding="utf-8")
    (OUT_DIR / f"change_review_{VERSION}.json").write_text(json.dumps(
        {"failures": failures, "cause": cause, "fix": fix, "findings": findings, "gate": gate, "critic": critic,
         "tokens": usage}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"📄 {path.relative_to(ROOT).as_posix()} · all links: out/change_review_{VERSION}.json · "
          f"tokens {usage['in']:,} in · {usage['out']:,} out")
