# Design Document - `opspilot serve`

## Overview

```text
 MCP host (Kiro, or serve --test)                     opspilot_server.py → opspilot/serve.py
 ┌───────────────────────────┐   JSON-RPC over stdio   ┌─────────────────────────────────────────────────┐
 │ LLM decides: which tool,  │ ──── tools/call ──────► │ MCPServer("OpsPilot")                           │
 │ which arguments           │                         │   input schema check (type hints, Task 3)       │
 │                           │ ◄─── result / error ─── │   guarded(): stdout → stderr, audit log (Task 2) │
 └───────────────────────────┘                         │   tool → Labs 1-5 functions on the 14:20 clock  │
                                                       │   read_export / runbook → safe_path() (Task 1)  │
                                                       └───────────────┬─────────────────────────────────┘
                                                                       ▼
                                          data/ (itsm, grafana, logs, cicd, agora) · out/mcp_audit.jsonl

 Tools (read-only): query_metrics · search_logs · recent_changes · search_runbooks · similar_incidents · read_export
 Resource: runbook://{service}            Prompt: triage_ticket(ticket_id)
```

## Components and Interfaces

| Module / file | Function | Status |
|---|---|---|
| `opspilot_server.py` | The file the host starts: `python opspilot_server.py` | ✅ ready |
| `serve.py` | `mcp = MCPServer("OpsPilot")`, the tool registration with `guarded()`, `READ_TOOLS`, `NOW` | ✅ ready |
| `serve.py` | `runbook(service)` - resource `runbook://{service}`; `triage_ticket(ticket_id)` - prompt | ✅ ready |
| `serve.py` | `run_test()`, `write_kiro_config()`, `print_audit()`, `main()` | ✅ ready |
| `serve.py` | `safe_path(path) -> Path` | 🛠️ Task 1 |
| `serve.py` | `guarded(func)` - decorator | 🛠️ Task 2 |
| `serve.py` | Docstrings and type hints of the 6 tool functions | 🛠️ Task 3 |
| `.kiro/settings/mcp.json` | Kiro's server list with `autoApprove` | 🛠️ Task 4 (configuration) |
| `__main__.py` | `serve [--test] [--kiro-config] [--audit]` | ✅ ready |

## Data Models

**What the model sees per tool:** name (function name), description (docstring) and input schema (type hints). The
SDK builds all three from the function.

**Audit line** (`out/mcp_audit.jsonl`, one JSON object per call):

```json
{"time": "2026-11-17T10:42:07+01:00", "tool": "read_export", "arguments": {"path": "../.env"},
 "outcome": "error", "error": "ToolError: '../.env' leaves the data folder - ...", "seconds": 0.0}
```

**Kiro configuration** (`.kiro/settings/mcp.json`):

```json
{"mcpServers": {"opspilot": {"command": "<this python>", "args": ["<project>/opspilot_server.py"],
                             "disabled": false, "autoApprove": ["query_metrics", "..."]}}}
```

## Approach and Rationale per Requirement

### Requirement 1 - The data boundary

| Rule | How | Why |
|---|---|---|
| Relative to `data/` only | Refuse absolute paths, drive letters, leading `/` or `\`. | A tool argument comes from an LLM - and through it from any text the LLM read. Treat it as untrusted input. |
| Resolve, then check | `(DATA_DIR / path).resolve()` must be inside `DATA_DIR.resolve()`. | `../` and links are resolved first, so they cannot slip through a text check. |
| Allow-list of folders | `ALLOWED_FOLDERS`; `gold/` is out. | Least privilege: the server needs the exports, not the exam answers - and never `.env`. |
| `ToolError` with the rule | The message names the allowed folders, not the machine's path. | The model can correct its call; the client learns nothing about your disk. |

### Requirement 2 - The guard

| Rule | How | Why |
|---|---|---|
| Keep the signature | `functools.wraps(func)`. | The SDK reads name, docstring and type hints - without them the schema is gone. |
| Clean stdout | `contextlib.redirect_stdout(sys.stderr)` around the call. | On stdio, stdout **is** the protocol. A `print()` either corrupts the message stream or - on Windows with an emoji - crashes the tool. Lab 4's `embed()` prints too, so the guard must sit around every tool. |
| Audit every call | One JSON line per call, also on error. | Transparency: who asked what, when, with which result - the base for every review and for Lab 8. |
| Raise again | Write the line in `finally`, then let the exception go on. | The SDK knows how to report errors: `ToolError` text to the model, other details hidden. |

### Requirement 3 - Tool descriptions and input schemas

| Rule | How | Why |
|---|---|---|
| Docstring = description | What, when, read-only. | The model never sees your code - only name, description and schema (deck 06: "write the docstring like a prompt"). |
| `Literal` for services | `Literal["payment-api", ...]` becomes an `enum`. | The model cannot invent a service such as `payment`. |
| Limits on numbers and text | `Field(ge=, le=)`, `Field(min_length=, max_length=)`. | A wrong call is refused by the SDK before your code runs - with a message the model can act on. |
| Bodies unchanged | Only signature and docstring change. | The tools are the tested functions of Labs 1-5. |

### Requirement 4 - Connect Kiro

| Rule | How | Why |
|---|---|---|
| Generated config | `serve --kiro-config` writes this Python and this server path. | Absolute paths differ on every machine; a wrong path is the most common reason a server does not start. |
| `autoApprove` = trusted read-only tools | Edit the list yourself. | Approval for every call leads to approval fatigue; auto-approval for a write tool removes the human. |
| No key in the file | The server reads `.env`. | Config files get shared and committed - keys do not belong there. |

### Ready: read-only by design

- The server registers `READ_TOOLS` only. Write tools (rollback, scale) never go to this server - they get their own
  path with a dry run and approval (Lab 7).
- The tools see data only up to the replay clock (14:20).
- `log_level="WARNING"`: the server log on stderr shows only problems.

## Verification

| Task | Command | Expected result |
|---|---|---|
| 0 | `python -m opspilot serve --test` | 6 tools, 1 resource template, 1 prompt; `0 of 4 bad requests refused`, a crashed `search_logs`, no audit lines |
| 1 | `python -m opspilot serve --test` | `../.env` and `gold/triage_gold.csv` refused (🛡️) |
| 2 | `python -m opspilot serve --test` and `serve --audit` | `0 tool(s) crashed`; one audit line per call that reached the code |
| 3 | `python -m opspilot serve --test` | Services and limits in *"What the model sees"*; `4 of 4 bad requests refused` |
| 4 | Kiro chat: *"Why is payment-api slow since 14:05?"*, then `serve --audit` | Kiro calls OpsPilot's tools; the calls are in the audit log |
