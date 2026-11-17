# Design Document - `opspilot change-review`

## Overview

```text
data/cicd/pipeline_runs.csv ──► release_runs() ──► runs of 2.3.1 · deployed run · previous release run
data/cicd/logs/*.log ─────────► extract_failures() ──► a few lines per run ─────────────────────┐
data/cicd/release-2.3.1.diff ─► scan_diff() ──► findings ──► redact() ──► diff without secrets ─┤
                                     │                                                          ▼
                                     └──► policy_gate() ──► PASS / FAIL        prompt chain on Claude:
                                                │                              1 failures → 2 cause → 3 fix
                                                │                                           │
                                                └──────────────► 4 summary ◄────────────────┘
                                                                    │
                                                                 5 critic ── issues ──► 4 summary, revised once
                                                                    │
                                                         out/change_review_2.3.1.md
```

## Components and Interfaces

| Module / file | Function | Status |
|---|---|---|
| `review.py` | `load_runs()`, `release_runs()`, `read_log()`, `load_diff()`, `load_advisories()`, `change_ticket()`, `redact()` | ✅ ready |
| `review.py` | `ask()` (one link, structured outputs), `naive()`, `review()`, `chain()` | ✅ ready |
| `review.py` | `extract_failures(log) -> list[str]` | 🛠️ Task 1 |
| `review.py` | `scan_diff(diff, advisories) -> list[dict]` | 🛠️ Task 2 |
| `prompts/change-review/` | `naive.md`, `1_failures.md`, `3_fix.md`, `4_summary.md`, `5_critic.md` | ✅ ready |
| `prompts/change-review/2_cause.md` | Link 2 of the chain | 🛠️ Task 3 |
| `review.py` | `policy_gate(release, previous, findings) -> dict` | 🛠️ Task 4 |
| `__main__.py` | `python -m opspilot change-review [--naive] [--checks]` | ✅ ready |

## Data Models

**Pipeline runs** (`pipeline_runs.csv`): `run_id`, `service`, `version`, `commit`, `trigger`, `status`
(`success` / `failed`), `started_at`, `finished_at`, `tests_passed`, `tests_failed`, `tests_skipped`,
`coverage_pct`, `log_file`. Release 2.3.1 has two runs: 4711 (failed) and 4712 (manual re-run, deployed).

**Log line:** `2026-11-09T13:16:14.507+01:00 ERROR [integration-test] E   AssertionError: ...` - timestamp, level
(`DEBUG`, `INFO`, `WARN`, `ERROR`), stage, message.

**Advisories** (`advisories.csv`): `package`, `fixed_in`, `advisory` (CVE), `severity`, `summary`.

**Finding:** `{"kind": "secret" | "dependency", "severity": "critical", "file": "payment_client.py",
"diff_line": 26, "evidence": "psk_test… (provider key)"}`.

**Gate:** `{"decision": "PASS" | "FAIL", "reasons": ["..."]}`.

## Approach and Rationale per Requirement

### Requirement 1 - Shrink the pipeline log

| Rule | How | Why |
|---|---|---|
| Parse | One regular expression per line: timestamp, level, stage, message. | A log is semi-structured text. Parsing it once makes every rule simple. |
| Drop `DEBUG` | Filter by level. | Debug output is most of the volume and almost never the answer. |
| Keep signals | `ERROR`, `WARN`, stage `pipeline`, `FAILED`, `SKIPPED`, `quarantine`. | Failures and skipped tests are what a reviewer must see. The pipeline lines give the frame: which run, which commit, which result. |
| Collapse | A dict from (level, stage, message) to the first position and a counter. | 312 identical deprecation warnings are one fact, not 312. |
| No LLM | Pure Python. | Exact and repeatable - and the LLM gets 22 lines instead of 4,721. Long prompts cost more, take longer and hide the important line in the middle. |

### Requirement 2 - Scan the diff

| Rule | How | Why |
|---|---|---|
| Added lines only | `+` but not `+++`; track the file from `+++ b/`. | A review judges what the change adds. Removed lines are gone. |
| Secret rules | Four regular expressions. | Secrets have known formats. Rules find them every time - an LLM may or may not notice. |
| Masked evidence | First 8 characters + `…`. | A scanner that prints the secret leaks it into logs, tickets and prompts. |
| Dependencies | Parse `name==version`; look up `advisories.csv`. | Known vulnerabilities are facts in a list - a lookup, not an opinion. |
| Numeric versions | `tuple(int(p) for p in version.split("."))`. | As text, `"1.26.18" < "1.26.5"` - a false alarm for `urllib3`. |
| Redact before the LLM | Ready code `redact()` replaces each secret line in the diff. | The LLM needs the code change, not the key. Same idea as masking the tickets in Lab 1. |

### Requirement 3 - Link 2: the cause

| Rule | How | Why |
|---|---|---|
| Chain | Link 1 lists the failures; link 2 explains them with the diff; link 3 proposes an action. | One prompt per decision is easier to write, test and check than one prompt that does everything. |
| Structured outputs | `output_config.format` with the JSON schema `CAUSE`. | The API guarantees valid JSON, so the next link can rely on it (Lab 2, stretch goal). The content still needs checking. |
| Evidence | Exact lines from the input. | A claim with a line can be checked in seconds; a claim without one cannot. |
| Flaky or not | A failure explained by a code change is deterministic. | "Flaky" is how a real defect gets quarantined. |
| "unknown" | Allowed with confidence `low`. | An LLM that may say "I don't know" invents less. |

### Requirement 4 - Policy gate

| Rule | How | Why |
|---|---|---|
| Findings | Every `critical` or `high` finding is a reason. | A hard-coded key or a critical CVE must never reach production. |
| Skipped tests | Compare with the previous release run. | A new skipped test is a test that stopped protecting you. |
| Coverage | Drop of more than 5 points. | New code without tests lowers the coverage - a cheap signal for missing tests. |
| No LLM | Only numbers from `pipeline_runs.csv` and the findings. | The gate must decide the same way every time and must not be talked into a pass. |
| Exit code | `--checks` ends with exit code 1 on FAIL (ready). | That is how a pipeline stops: OpsPilot can run as a pipeline step. |

### Ready: self-healing rule, summary and critic

- **Self-healing rule (code):** a proposal of link 3 may run automatically only when it is a `rerun` of a failure
  that link 2 marked as `flaky`. Every other action needs a human.
- **Link 4 - summary:** Markdown with Verdict, What changed, Pipeline, Risks, Likely cause and Next step, at most 180
  words. The gate decision is copied unchanged.
- **Link 5 - critic:** runs five named checks on the summary against the same facts - claims, gate, cause, secrets,
  sections - each with a finding first and then `passed` true or false. The **code** counts the failed checks; with failures, link 4 runs once
  more with the draft and the problems (self-refine) - only once, to keep cost and time bounded.
- **Outputs:** `out/change_review_extract.txt`, `out/change_review_2.3.1.md` (for change ticket CHG-20448) and
  `out/change_review_2.3.1.json` (all links and the tokens).

## Verification

| Task | Command | Expected result |
|---|---|---|
| 1 | `python -m opspilot change-review --checks` | `run 4711 2,254 → 13 lines · run 4712 2,467 → 9 lines`; the extract shows the FAILED test in 4711 and the SKIPPED (quarantined) test in 4712 |
| 2 | `python -m opspilot change-review --checks` | 2 findings: `psk_test… (provider key)` in `payment_client.py`, `pyyaml==5.3.1 - CVE-2020-14343` |
| 3 | `python -m opspilot change-review` | Link 2 names the timeout and retry loop in `PaymentClient.charge()`, `flaky: no`; link 3 does not propose `rerun` or `quarantine-test` |
| 4 | `python -m opspilot change-review --checks` | `Gate: FAIL` with 4 reasons (2 findings, 1 skipped test, coverage 78.4 % → 69.8 %); exit code 1 |

LLM answers vary, so the wording of links 1-5 varies from run to run.
