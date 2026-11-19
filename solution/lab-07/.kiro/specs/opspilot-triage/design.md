# Design Document - `opspilot triage`

## Overview

```text
data/itsm/tickets.csv ──► mask_tickets() (Lab 1) ──► one <ticket> message per ticket
prompts/triage/<version>.md ──► render_prompt() ──► system prompt
                                                        │
                       Claude on Bedrock ◄──────────────┘
                              │ raw answer
                              ▼
                       parse_triage()  ── invalid ──► 1 retry with the error ── invalid ──► needs_human
                              │ valid
                              ▼
                       route() → team · check_reply() → tone
                              │
                              ▼
                       evaluate() against data/gold/triage_gold.csv · propose_problem()
```

## Components and Interfaces

| Module / file | Function | Status |
|---|---|---|
| `prompts/triage/v1.md` | Naive prompt | ✅ ready |
| `prompts/triage/v2.md` … `v5.md` | Your prompt versions | 🛠️ Tasks 1, 3, 4, 5 |
| `triage.py` | `load_catalog()`, `load_examples()`, `build_schema()`, `render_prompt()`, `ticket_message()`, `route()` | ✅ ready |
| `triage.py` | `run()`, `triage_one()`, `evaluate()`, `propose_problem()`, `save()`, `report()`, `compare()` | ✅ ready |
| `triage.py` | `parse_triage(raw, schema) -> dict` | 🛠️ Task 2 |
| `triage.py` | `check_reply(reply) -> list[str]` | 🛠️ Task 5 |
| `triage.py` | `triage_structured(client, system, ticket, schema) -> (dict, usage)` | 🛠️ Task 6 (stretch) |
| `__main__.py` | `python -m opspilot triage --prompt <version> [--limit N] [--show N] [--structured] [--compare]` | ✅ ready |

## Data Models

**Catalog** (`data/itsm/triage_catalog.json`): `categories` (name, description, team), `priorities` (name, rule,
`assignable`, sla_hours), `problem_rule` (min_tickets, window_minutes, priority).

**Gold set** (`data/gold/triage_gold.csv`): `ticket_id`, `category`, `priority`, `team` for all 50 tickets.

**Examples** (`data/gold/triage_examples.jsonl`): six tickets with their ideal answer - not part of the Gold set.

**Triage answer** (validated by `build_schema()`): `category` (one of the catalog), `priority` (P2, P3 or P4),
`summary`, `customer_reply`; no other keys.

## Approach and Rationale per Requirement

### Requirement 1 - Prompt v2

| Rule | How | Why |
|---|---|---|
| Parts of the prompt | Role, context, task, rules, output format - as Markdown headings. | The 7 principles of good prompts from the slides: clear, structured, with context and a defined output. |
| `<ticket>` tags | The ticket arrives inside tags; the prompt says it is data. | Delimiters separate instructions from data - the first protection against prompt injection in tickets. |
| JSON only | Exact keys, no text around the object. | Code can only process what it can parse. |

### Requirement 2 - Parse and validate

| Rule | How | Why |
|---|---|---|
| Find the object | Slice from the first `{` to the last `}`. | Models like to add a sentence or a code fence around JSON. |
| Validate | `jsonschema.validate(data, schema)`. | Valid JSON is not yet a valid triage: the schema allows only known categories and priorities. |
| Clear errors | Raise `ValueError` with the messages of **all** validation errors (`iter_errors`). | The message goes back to the LLM in the retry - a precise error gets a precise correction. With only the first error, the retry fixes one field and fails on the next. |
| One retry, then a human | Ready code in `triage_one()`. | Unlimited retries cost money and time; after one failed correction a human decides. |

### Requirement 3 - Allowed values

| Rule | How | Why |
|---|---|---|
| Placeholders | `{{categories}}` and `{{priorities}}` are filled from the catalog. | One source of truth: the prompt and the validation use the same list. |
| No team from the LLM | `route()` maps the category to the team. | A lookup table is always right; an LLM can invent a team. Use the LLM for language, code for rules. |
| No P1 | P1 is not assignable; the schema rejects it. | A single ticket is never P1. P1 is a decision about many tickets (see the problem proposal). |

### Requirement 4 - Few-shot examples

| Rule | How | Why |
|---|---|---|
| Examples | `{{examples}}` is filled with six labelled examples. | Examples show the borderline cases better than any rule, e.g. "paid, but no confirmation" is a payment failure. |
| No leakage | The examples are separate tickets, not from the Gold set. | Examples from the test data would measure memory, not quality. |

### Requirement 5 - Tone guard

| Rule | How | Why |
|---|---|---|
| Rules in the prompt | v5 states the reply rules. | Prevention: the LLM knows the rules before it writes. |
| Check in code | `check_reply()` with simple text checks. | Control: a prompt is a wish, a check is a guarantee. Customer-facing text needs both. |

### Requirement 6 - Structured outputs

| Rule | How | Why |
|---|---|---|
| Format | `output_config` with `{"type": "json_schema", "schema": schema}`. | The API guarantees the structure - fewer retries, less parsing code. The content (is the category right?) still needs the Gold set. |

### Ready: problem proposal

`propose_problem()` groups the triaged tickets by team. WHEN at least 10 tickets of one team arrive within 60 minutes
THEN OpsPilot proposes one problem with priority P1 - from the minute the rule is reached - and shows the SLA due time
of P1. `triage_one()` adds `sla_due` to every ticket from the SLA hours of its priority. These are rules - pure
Python, no LLM.

## Verification

Run every version with `python -m opspilot triage --prompt <version>` and compare with
`python -m opspilot triage --compare`. LLM answers vary, so the numbers vary a little from run to run.

| Task | Typical result on the Gold set |
|---|---|
| v1 (ready) | 0 % parsed - free text cannot be measured |
| 1 - v2, naive parser | Valid JSON (Claude Haiku 5.5), but invented categories and priorities: 0 % correct. Other models may wrap the JSON in text and fail to parse |
| 2 - v2, with `parse_triage()` | 100 % parsed, but 50 retries: every answer is corrected only by the retry; about 60 % of the categories right, a wrong problem proposal |
| 3 - v3 | No retries; category accuracy 95 % or more |
| 4 - v4 | About the same accuracy as v3, about twice the input tokens - measured with `--compare` |
| 5 - v5 | Tone: all replies without a rule break |
| Every run from v3 | `📌 Problem proposal: 40 related tickets from 14:10 to 15:58 → team-payments · P1 since 14:33 … SLA due 15:33` - the count can vary by one or two |
