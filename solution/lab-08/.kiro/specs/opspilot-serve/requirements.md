# Requirements Document - `opspilot serve`

## Introduction

`opspilot serve` turns OpsPilot's read-only tools of Labs 1-5 into an **MCP server** (Model Context Protocol, Python
SDK 2.x, `MCPServer`). Any MCP host - Kiro, or the ready test client - starts `opspilot_server.py` as a subprocess and
talks to it over stdin/stdout. The server offers 6 tools, the resource `runbook://{service}` and the prompt
`triage_ticket(ticket_id)`. It is a replay: the clock stands at 14:20 on Monday, 9 November 2026.

The server only reads (autonomy level L1). It must keep three boundaries: only the allowed data folders, only valid
inputs, and a record of every call. The ready parts are described in `design.md`.

## Requirements

### Requirement 1 - The data boundary `safe_path`

**User Story:** As a platform lead, I want the server to read only the ops exports, so that no client - and no prompt
injection - can make it hand out secrets or files it was never meant to share.

#### Rules and Acceptance Criteria

1. WHEN `safe_path(path)` is called THEN it SHALL treat `path` as relative to `data/` (`DATA_DIR`).
2. It SHALL refuse an empty path, an absolute path, a path with a drive letter (`:`) and a path that starts with `/`
   or `\`.
3. It SHALL resolve the path (`..`, links) and refuse it IF the result is outside `data/`.
4. It SHALL refuse a path whose first folder is not in `ALLOWED_FOLDERS` (`itsm`, `grafana`, `logs`, `cicd`,
   `agora`). `gold/` is not allowed: the Gold labels are the answers of every evaluation.
5. It SHALL refuse a file type that is not in `ALLOWED_SUFFIXES`, and a path that is not an existing file.
6. Every refusal SHALL raise `ToolError` (`mcp.server.mcpserver.exceptions`) with a message that says what is
   allowed. The message SHALL NOT contain the absolute path of the machine.
7. It SHALL return the resolved `Path`. `read_export()` and the runbook resource (ready) use it.
8. WHEN `python -m opspilot serve --test` runs THEN `read_export(path='../.env')` and
   `read_export(path='gold/triage_gold.csv')` SHALL be refused, and `read_export(path='itsm/changes.csv')` SHALL work.

### Requirement 2 - The guard `guarded`

**User Story:** As a platform lead, I want every tool call to be safe for the protocol and on record, so that a stray
`print()` cannot break the server and I can trace who asked for what.

#### Rules and Acceptance Criteria

1. WHEN `guarded(func)` is called THEN it SHALL return a wrapper with the same name, docstring and signature as
   `func` (`functools.wraps`) - the SDK builds the tool's name, description and input schema from them.
2. While the tool runs, everything it prints SHALL go to stderr, not to stdout (`contextlib.redirect_stdout`).
   Stdout carries only MCP messages.
3. Every call SHALL append one JSON line to `out/mcp_audit.jsonl` (`AUDIT_LOG`) with `time` (local ISO time with
   offset, in seconds), `tool`, `arguments`, `outcome` (`ok` or `error`), `seconds` (2 decimals), plus `result_chars`
   on success or `error` (type and message) on failure. It SHALL create `out/` IF it does not exist.
4. The audit line SHALL also be written WHEN the tool raises. The exception SHALL then be raised again unchanged: the
   SDK sends the message of a `ToolError` to the client and hides the details of any other exception.
5. WHEN `python -m opspilot serve --test` runs THEN no tool SHALL crash, and `out/mcp_audit.jsonl` SHALL get one new
   line per call that reached the code. `python -m opspilot serve --audit` (ready) SHALL show them.

### Requirement 3 - Tool descriptions and input schemas

**User Story:** As an on-call engineer, I want the model in my IDE to understand each tool and to send only valid
input, so that it calls the right tool the right way - and a wrong call is refused before any code runs.

#### Rules and Acceptance Criteria

1. Every tool function in `serve.py` SHALL have a docstring that says what the tool returns, when to use it, and that
   it is read-only. The descriptions of `agent.TOOLS` (Lab 5) MAY be reused.
2. A `service` parameter SHALL be a `Literal` of `payment-api`, `checkout-web` and `booking-search`;
   `recent_changes` SHALL also allow `all`.
3. Numbers SHALL have limits and a description with `Annotated[int, Field(...)]`: `minutes` 15 to 240, `hours` 1 to
   72.
4. Text SHALL have a length limit and a description with `Annotated[str, Field(...)]`: `query` 3 to 200 characters,
   `description` 10 to 500, `path` at most 200 - its description SHALL name the allowed folders.
5. The bodies of the tool functions SHALL NOT change.
6. WHEN `python -m opspilot serve --test` runs THEN *"What the model sees"* SHALL show the services and the limits, and
   `query_metrics(service='payment')` and `query_metrics(minutes=100000)` SHALL be refused by the schema before any
   code runs - **4 of 4 bad requests refused**.

### Requirement 4 - Connect Kiro

**User Story:** As an on-call engineer, I want to ask OpsPilot from Kiro chat, so that I get the evidence without
switching tools - and Kiro asks me before it runs a tool I have not approved.

#### Rules and Acceptance Criteria

1. `.kiro/settings/mcp.json` SHALL be written with `python -m opspilot serve --kiro-config` (ready): this Python, this
   server file.
2. `autoApprove` SHALL list only read-only tools the engineer trusts to run without a question. It SHALL NOT contain a
   tool that changes anything.
3. The file SHALL NOT contain a key: the server reads it from `.env` itself.
4. WHEN the engineer asks in Kiro chat *"Why is payment-api slow since 14:05?"* THEN Kiro SHALL call OpsPilot's tools,
   and `python -m opspilot serve --audit` SHALL show the calls.
