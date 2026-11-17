# Design Document - `opspilot investigate`

## Overview

```text
alert 14:07 ──► first_message() ──► messages
                                        │
            ┌───────────────────────────▼───────────────────────────┐
            │ investigate() - the agent loop                        │
            │   Claude on Bedrock (effort high, strict tools)       │
            │      │ text → log_thought()      tool_use ▼           │
            │      │                    limit reached? → LIMIT_MESSAGE
            │      │                    run_tool() → log_step() ──► out/investigation_steps.jsonl
            │      ◄──────── tool results (one user message) ◄──────┤
            │   until submit_report · no tool call · limit + 1 call │
            └───────────────────────────┬───────────────────────────┘
                                        ▼
                         print_report() ──► out/investigation_report.md

Tools (read-only, data up to 14:12):
  query_metrics      Lab 1 clean_metrics()         search_runbooks     Lab 4
  search_logs        Lab 4 (log templates)         similar_incidents   Lab 4
  recent_changes     Task 1 (change calendar)      submit_report       ends the investigation
```

## Components and Interfaces

| Module / file | Function | Status |
|---|---|---|
| `agent.py` | `query_metrics()`, `search_logs()`, `search_runbooks()`, `similar_incidents()` - wrappers of Labs 1 and 4 | ✅ ready |
| `agent.py` | `TOOLS`, `SUBMIT_REPORT`, `tool_definitions()`, `run_tool()`, `accept_report()`, `log_step()`, `log_thought()`, `first_message()` | ✅ ready |
| `agent.py` | `alert_at()`, `at()`, `client()`, `prompt()`, `guess()`, `print_report()` | ✅ ready |
| `agent.py` | `recent_changes(service, hours, now)` and `RECENT_CHANGES_TOOL` | 🛠️ Task 1 |
| `agent.py` | `investigate(client, system, alert, now, max_steps, max_seconds) -> dict` | 🛠️ Task 2 |
| `prompts/investigate/v2.md` | The system prompt of the agent | 🛠️ Task 3 |
| `agent.py` | `is_repeat(name, args, history) -> bool` | 🛠️ Task 4 (stretch) |
| `prompts/investigate/` | `no_tools.md` (Step 1), `v1.md` (naive agent) | ✅ ready |
| `__main__.py` | `investigate [--prompt v1] [--at 14:12] [--max-steps 8] [--max-seconds 120] [--no-tools] [--tool NAME key=value ...]` | ✅ ready |

## Data Models

**Tool definition:** `{"name", "description", "input_schema", "strict": true}` - the description is what the model
reads to choose a tool; the strict schema guarantees valid input.

**Tool results** (JSON text, at most 4,000 characters):

- `query_metrics`: `service`, `from`, `to`, `slo_p95_ms`, `first_minute_above_slo`, `per_5_min` (time, p95_ms,
  error_rate_pct, requests_per_min);
- `search_logs`: per message `level`, `message`, `lines`, `first`, `last`, `versions`, `similarity`;
- `recent_changes`: per change `change_id`, `service`, `type`, `version`, `status`, `started_at`, `finished_at`,
  `description`;
- `search_runbooks` / `similar_incidents`: `source` or `incident`, `similarity`, `text`.

**Report** (`submit_report` input): `summary`, `hypotheses` (cause, confidence, evidence: tool and fact),
`ruled_out`, `next_step`.

## Approach and Rationale per Requirement

### Requirement 1 - The tool `recent_changes`

| Rule | How | Why |
|---|---|---|
| Time window | `now - hours < started_at <= now`. | An agent that sees tomorrow's change calendar would explain the past with the future. |
| Plain JSON | Times as text, `None` for empty values. | The result goes to the model as JSON text. |
| Description | What it returns + when to use it. | The model chooses tools by their description - a vague description means wrong or missing calls. |
| Strict schema | `enum` for the service, `additionalProperties: false`. | The model cannot invent a service or a parameter. |

### Requirement 2 - The agent loop

| Rule | How | Why |
|---|---|---|
| Loop | Call the model; run its tool calls; send the results back; repeat. | That is all an agent is: an LLM in a loop with tools (sense → plan → act → reflect). |
| Content unchanged | Append `response.content` as it is. | The model's thinking must stay in the conversation, or the next call loses its reasoning. |
| One user message | All tool results of one answer together, each with its `tool_use_id`. | The API pairs every result with its call. |
| Step and time limit | Count tool calls and seconds; block calls beyond the limit. | Agents can loop. A limit bounds cost and time - Google SRE calls this a circuit breaker. |
| One more call | After a limit, the model may still hand in its report. | A partial result with evidence is better than nothing - and a human takes over. |
| Check the report | `accept_report()` rejects a report without hypotheses or with tags inside a field; the model gets the problem and tries again. | LLM output is untrusted (Lab 2). In tests, Claude sometimes packed the whole report into `summary` - so the schema lists the structured fields first and `summary` last. A rejected report counts as a step, so the step limit still holds. |
| Log every step | `log_step()` writes `out/investigation_steps.jsonl`. | Transparency: every conclusion can be traced back to a tool result. |
| Effort high | `output_config={"effort": "high"}`. | Planning several steps needs more thinking than a one-shot answer. |

### Requirement 3 - The system prompt v2

| Rule | How | Why |
|---|---|---|
| Read-only role | The agent recommends, it does not act. | Autonomy level L1. Acting comes later, with guardrails and approval (Lab 7). |
| Time order | A cause starts before the symptom. | The settlement export error fires at 14:07 - like the alert - but it has done so every 15 minutes since 12:07, in both versions. |
| Two tools | Stop when two independent tools agree. | One source can mislead; two independent ones make a credible hypothesis. |
| Data, not instructions | Tool results are untrusted. | A runbook contains a hidden instruction (Lab 4). |

### Requirement 4 - Repeat guard

| Rule | How | Why |
|---|---|---|
| Same tool, same input | Compare names and normalised inputs. | The same question gives the same answer - repeating it only costs steps. |
| Still a step | The blocked call counts. | A looping agent ends at the step limit instead of running forever. |

### Ready: read-only tools and guardrails

- Every tool only reads; there is no tool that changes anything (no ambient access).
- Tools see data only up to `--at` (default 14:12).
- Tool errors go back to the model as results (`is_error`), never as crashes.
- Tool results are cut at 4,000 characters, so one tool cannot flood the context.

## Verification

| Task | Command | Expected result |
|---|---|---|
| 0 | `python -m opspilot investigate --tool query_metrics service=payment-api minutes=60` | `first_minute_above_slo`: `14:05` |
| 1 | `python -m opspilot investigate --tool recent_changes service=all hours=6` | CHG-20448 and CHG-20446, newest first |
| 2 | `python -m opspilot investigate --max-steps 2` | At most 2 tool calls; `report submitted` or `step limit` |
| 3 | `python -m opspilot investigate --prompt v2` | First hypothesis release 2.3.1 with evidence from at least two tools; the settlement export error is not a hypothesis |
| 4 | `python -m opspilot investigate --prompt v2` | A repeated call shows ⚠️ and "You already called" in the step log |

LLM answers vary, so the order of the tool calls and the wording differ from run to run.
