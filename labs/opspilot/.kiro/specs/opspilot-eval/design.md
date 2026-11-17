# Design Document - `opspilot eval`

## Overview

```text
 data/gold/rca_gold.csv (20 closed incidents)            data/gold/red_team.jsonl (3 attacks)
          │                                                         │
          ▼                                                         ▼
 propose_code():  record ──► redact() ──► Claude (structured output: cause_code ∈ catalog, explanation, evidence)
                                               ──► redact() ──► answer                   (Task 3: the guard)
          │                                                         │
          ├─► exact match: cause_code = Gold?                       ├─► sent to Bedrock: personal data? secret?
          ├─► LLM grader (judge.md): explanation correct / partial / wrong     answer: personal data? secret?
          ▼                                                         └─► injection: cause code hijacked?
 print_run(): per incident · overall · group_report() per service and type (Task 1)
 out/eval_<version>.jsonl ──► eval --compare
```

## Components and Interfaces

| Module / file | Function | Status |
|---|---|---|
| `evaluate.py` | `group_report(results, by) -> pd.DataFrame` | 🛠️ Task 1 |
| `prompts/eval/v2.md` | The hardened prompt | 🛠️ Task 2 |
| `evaluate.py` | `redact(text) -> tuple[str, list[str]]` | 🛠️ Task 3 |
| `evaluate.py` | `render()`, `answer_schema()`, `propose_code()`, `judge()`, `run()`, `print_run()`, `compare()` | ✅ ready |
| `evaluate.py` | `red_team()`, `leaks()`, `LEAKS`, `print_cases()` | ✅ ready |
| `prompts/eval/` | `v1.md` (naive: only the names of the cause codes), `judge.md` (the grader) | ✅ ready |
| `__main__.py` | `eval [--prompt v1] [--cases] [--compare] [--attack]` | ✅ ready |
| `data/` | `itsm/cause_codes.json`, `gold/rca_gold.csv`, `gold/red_team.jsonl` | ✅ data |

## Data Models

**Answer** (structured output): `{"cause_code": one of the catalog, "explanation": str, "evidence": [str]}`.

**Result row** (`out/eval_<version>.jsonl`): `incident_id`, `service`, `incident_type`, `gold`, `cause_code`,
`code_correct`, `verdict`, `judge_reason`, `explanation`, `evidence`, `tokens_in`, `tokens_out`.

**Group report:** index = the group; columns `cases`, `cause_code`, `explanation`, `cause_code_pct`,
`explanation_pct`.

## Approach and Rationale per Requirement

### Requirement 1 - Quality per group

| Rule | How | Why |
|---|---|---|
| Per service and per type | `groupby(by)` with counts and percentages. | An overall 85 % can hide a group at 50 % - check quality per group, not only the total (deck 08, fairness and bias). |
| Weakest first | Sort by `cause_code_pct`. | The table is a to-do list: the first row is where to look. |
| Count the cases | Keep `cases` in the table. | 1 of 1 is 100 % - but proves little. The Gold set has 8 payment-api incidents and 1 of each platform service: representation bias. |

### Requirement 2 - The prompt v2

| Rule | How | Why |
|---|---|---|
| Definitions, not names | `{{cause_code_definitions}}`. | v1 knows only the names. The model understands each incident - the explanations are right - but not the team's conventions, e.g. a pool size changed **in a release** is `change-code`. |
| Conventions as rules | Release, duplicates, third-party. | The errors of v1 cluster exactly there - the group report shows it. |
| Evidence in own words | No copies of the record. | Copied text carries copied personal data and secrets. |
| Data, not instructions | One rule. | The injection in RT-1 claims to come from the platform lead. |

### Requirement 3 - The guard on both sides

| Rule | How | Why |
|---|---|---|
| Before the prompt | `redact(record)`. | Data minimisation (GDPR, Lab 1): the model provider gets only what the task needs. A prompt is a data transfer. |
| After the answer | `redact()` on every answer field. | LLM output is untrusted (OWASP LLM02, LLM05) - a model can repeat what it saw anywhere in its context. |
| In code | Regular expressions, placeholders. | A prompt rule is a wish, a code rule is a guarantee (deck 07). |
| IBAN before phone | Order of the patterns. | An IBAN contains long digit groups that a phone pattern would partly match. |

### Ready: the evaluation harness

- **Structured outputs** with an `enum` of the cause codes: the answer always parses and always names a valid code.
- **Exact match + LLM grader:** deterministic where possible, an LLM only for free text (Google SRE, deck 08).
- **The grader has its own prompt** and gets the record, the reference and the candidate - not the cause code, so it
  judges the explanation only.
- **Red-team checks** look at what was **sent** and what was **answered** - and at a hijacked cause code.
- Every run is stored in `out/eval_<version>.jsonl`; `--compare` shows quality and tokens per version.

## Verification

| Task | Command | Expected result |
|---|---|---|
| 0 | `python -m opspilot eval --cases` | 20 incidents · payment-api 8 · 5 cause codes |
| 1 | `python -m opspilot eval --prompt v1` | Overall score, then a table per service and per incident type, weakest first |
| 2 | `python -m opspilot eval --prompt v2` and `eval --compare` | v2 at least 90 % cause codes, above v1 |
| 3 | `python -m opspilot eval --attack --prompt v2` | `3 of 3 attacks withstood`; guard replaced e-mail, IBAN, phone, secret |

LLM answers vary, so single cause codes can differ from run to run - compare the totals and the groups.
