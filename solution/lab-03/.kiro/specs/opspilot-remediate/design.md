# Design Document - `opspilot remediate`

## Overview

```text
  Claude proposes ──► check_action() ──► dry_run() ──► decide() ──┬─ block     nothing happens
  (one tool call)      safe action set    plan + risk   Task 3    ├─ escalate  a human leads
  or --action "..."    Task 1             Task 2                  ├─ auto      execute
                                                                   └─ approve   approval card ──► human: approve?
                                                                                                      │
  stop switch (out/STOP) · circuit breaker (2 changes / 30 min) ──► before any execution              ▼
                                                    execute(): canary → verify → the rest → verify ──► audit log

  grey = LLM (probabilistic)   white = Python code (deterministic)   orange = human        (deck 07, slide 6)
```

## Components and Interfaces

| Module / file | Function | Status |
|---|---|---|
| `remediate.py` | `check_action(action, state, releases) -> list[str]` | 🛠️ Task 1 |
| `remediate.py` | `dry_run(action, state, releases, now) -> dict` | 🛠️ Task 2 |
| `remediate.py` | `decide(action, violations, plan) -> str` | 🛠️ Task 3 |
| `prompts/remediate/postmortem.md` | Prompt for the post-mortem draft | 🛠️ Task 4 (stretch) |
| `remediate.py` | `propose()` with `PROPOSAL_TOOLS` and `incident_context()`; `parse_action()` | ✅ ready |
| `remediate.py` | `load_state()`, `save_state()`, `load_releases()`, `previous_version()`, `p95_ms()` | ✅ ready |
| `remediate.py` | `run()`, `approval_card()`, `execute()`, `execute_naive()`, `breaker_open()`, `audit()` | ✅ ready |
| `remediate.py` | `print_status()`, `reset()`, `stop_switch()`, `postmortem()` | ✅ ready |
| `prompts/remediate/propose.md` | System prompt of the planner | ✅ ready |
| `__main__.py` | `remediate [--action "..."] [--naive] [--status] [--reset] [--stop] [--resume] [--postmortem]` | ✅ ready |
| `data/cicd/` | `platform.json` (services, versions, instances, limits), `releases.csv` (history, DB migrations) | ✅ data |

## Data Models

**Action** (from Claude's tool call or from `parse_action()`):
`{"action": "rollback", "service": "payment-api", "version": "2.3.0", "replicas": None, "team": None,
"reason": "...", "evidence": [...], "source": "llm" | "manual"}`

**State** (`out/platform_state.json`): per service `kind` (`service` or `database`), `team`, `version`,
`instances` (one version per instance) and `max_instances`; plus `deployment_running`.

**Plan** (from `dry_run`): `steps`, `instances_affected`, `minutes`, `migrations_to_undo`, `risk_factors`, `risk`.

**Audit line** (`out/remediation_audit.jsonl`): `time`, `event` (`proposal`, `decision`, `approval`, `executed`,
`refused`, `stop switch`) and its fields.

## Approach and Rationale per Requirement

### Requirement 1 - The safe action set

| Rule | How | Why |
|---|---|---|
| Allow-list of actions | `SAFE_ACTIONS`; everything else is one violation. | The strongest limit is the missing tool - what is not in the set cannot run (deck 07, slide 4). |
| Never a database | Only `kind == "service"`. | The hidden runbook instruction of Lab 4 says *"scale payment-db --replicas 0"*. An LLM may follow it - the code never does. |
| One step back | `previous_version()`. | 2.2.4 is the version of INC-3920; older versions may need DB migrations undone. |
| Up, at most +50 % | `current < replicas <= floor(current × 1.5)`. | Bounded change; a scale to 0 is an outage. |
| Every source | The same check for Claude and for `--action`. | An action can come from a model, a chat, a ticket or a tired human - check the call, not the source. |

### Requirement 2 - The dry run

| Rule | How | Why |
|---|---|---|
| No side effects | Compute only; never touch `state`. | Google SRE: every action API supports `dry_run=true` - a preview must be safe to run any time. |
| Canary first | 1 instance, verify, then the rest. | If the target version is bad, only one instance is hurt - and the canary is restored. |
| Migrations | List the DB migrations to undo. | A rollback across a schema change is a different, risky operation. |
| Real-time risk | Active incident, running deployment, migration, peak hours. | The same action is fine at 03:00 and dangerous at 18:00 (Safety Trifecta, deck 07). |

### Requirement 3 - Automate or escalate

| Rule | How | Why |
|---|---|---|
| Order of the rules | block → page auto → high risk escalate → small scale auto → approve. | The first matching rule wins; the safe answers come first. |
| Rollback = approve | Always a human. | L2 for critical actions; L3 only for bounded actions that proved themselves (deck 07, slide 7). |
| Escalate on high risk | Nothing executes, a human leads. | Google's control plane downgrades risky requests to a human. |

### Ready: brakes and transparency

- **Stop switch** (`--stop`, file `out/STOP`): the red button - no execution until `--resume`.
- **Circuit breaker:** at most 2 executed changes per service in 30 minutes; then `escalate`. It stops loops such as
  roll back, redeploy, roll back.
- **Fail closed:** if Task 1, 2 or 3 is not built, nothing is executed (except `--naive` in Step 1).
- **Verify:** after the canary and after the rest; an unhealthy canary is restored at once.
- **Audit log:** every proposal, decision, approval and execution.

### Requirement 4 - Post-mortem draft

| Rule | How | Why |
|---|---|---|
| Facts only | Missing facts are marked *"to be confirmed"*. | A post-mortem with invented details does more harm than none. |
| Blameless | Systems and decisions, not people. | People only report honestly when nobody is blamed. |

## Verification

| Task | Command | Expected result |
|---|---|---|
| 0 | `python -m opspilot remediate --status` | payment-api 6× 2.3.1, p95 2,400 ms 🔴 |
| 1 | `python -m opspilot remediate --action "scale payment-db 0"` (and the other three) | `⛔ Decision: block`, the violation, no change |
| 2 | `python -m opspilot remediate --action "rollback payment-api 2.3.0"` | Card with the canary steps, `~13 min`, `Risk: medium - active incident on payment-api` |
| 3 | `python -m opspilot remediate --action "page_team team-payments"` | `🤖 Decision: auto` |
| 3 | `python -m opspilot remediate`, then `approve` | Claude proposes rollback 2.3.1 → 2.3.0; canary 250 ms; p95 250 ms 🟢 |
| 4 | `python -m opspilot remediate --postmortem` | `out/postmortem.md` with timeline, root cause and the approved rollback |
