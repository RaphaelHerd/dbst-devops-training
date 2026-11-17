# Design Document - `opspilot data`

## Overview

`opspilot data` is a small pipeline of pure functions. Each step takes a table and returns a new one, so every step
can be tested on its own and run in any order the command line needs.

```text
data/grafana/*.csv ──► load_metrics_raw() ──► clean_metrics() ──► add_features() ──► detect_events()
                                                    │                                     │
                                                    └──► write_quality_report() ◄──┐      ▼
data/itsm/tickets.csv ──► load_tickets() ──► mask_tickets() ───────────────────────┘   build_prompt()
                                                    │                                     │
                                                    └─────────────────────────────────────┴──► summarise_incident()
```

## Components and Interfaces

| Module | Function | Status at the start of Lab 1 |
|---|---|---|
| `loaders.py` | `load_metrics_raw()`, `load_tickets()`, `load_changes()`, `load_load_baseline()`, `load_slo()` | ✅ ready |
| `anomaly.py` | `naive_detect()`, `AnomalyEvent` | ✅ ready |
| `cleaning.py` | `clean_metrics(raw, out_dir) -> (clean, log)` | 🛠️ Task 1 |
| `quality.py` | `add_features(clean, changes, baseline) -> DataFrame`, `write_quality_report(raw, clean, log, mask_counts, path) -> Path` | 🛠️ Task 2 |
| `anomaly.py` | `detect_events(df) -> list[AnomalyEvent]` | 🛠️ Task 3 |
| `masking.py` | `pseudonym(email) -> str`, `mask_tickets(tickets) -> (masked, counts)` | 🛠️ Task 4 |
| `llm.py` | `select_recent_tickets()`, `build_prompt()`, `SYSTEM_PROMPT` | ✅ ready |
| `llm.py` | `summarise_incident(event, tickets) -> str` | 🛠️ Task 5 |
| `forecast.py` | `forecast_error_budget(clean, slo, service) -> dict` | 🛠️ Task 6 (stretch) |
| `__main__.py` | command line `python -m opspilot data [--naive] [--preview-prompt] [--summary] [--forecast]` | ✅ ready |

## Data Models

**Raw metrics** (`load_metrics_raw()`): `source`, `timestamp` (text, as exported), `service`, `p95_latency_ms`,
`error_rate_pct`, `requests_per_min`.

**Clean metrics** (`clean_metrics()`): `timestamp` (timezone-aware Europe/Berlin), `service`, `p95_latency_ms`,
`error_rate_pct`, `requests_per_min`. One row per service and minute.

**Features** (`add_features()`): clean metrics + `hour`, `weekday`, `minutes_since_deployment`,
`last_deployment_version`, `load_level`.

**Masked tickets** (`mask_tickets()`): `ticket_id`, `created_at`, `service`, `customer`, `subject`, `description`.

## Approach and Rationale per Requirement

### Requirement 1 - Clean the metrics

| Rule | How | Why |
|---|---|---|
| Time zones | Split the timestamps by "ends with `Z`". Parse the UTC part with `utc=True` and convert it with `tz_convert("Europe/Berlin")`; localise the rest with `tz_localize("Europe/Berlin")`. | Removing the `Z` keeps the clock time but changes the meaning: 13:05 UTC is 14:05 in Berlin. That is how the incident appeared twice. |
| Duplicates | `drop_duplicates(subset=["service", "timestamp"], keep="first")` **after** the time zone fix. | The exports overlap by 31 minutes. Before the fix the duplicates do not even look like duplicates. Both copies carry the same values, so keeping the first is safe. |
| Latency zeros | Set `p95_latency_ms == 0` to NaN. | The scraper writes 0 when it fails. A real request never takes 0 ms. |
| Other zeros | Keep `error_rate_pct == 0` and `requests_per_min == 0`. | 0 % errors is the normal, healthy case. Removing it would invent a problem. |
| No filling | Leave NaN as NaN. | An interpolated value is invented data. The detection must see that a value is missing. |
| Output | Sorted CSV in `out/`, cleaning log as a dict. | `out/` is the only place OpsPilot writes. The log feeds the quality report. |

### Requirement 2 - Quality report and features

| Rule | How | Why |
|---|---|---|
| Report | Markdown file built from the raw data, the cleaning log and the masking counts. | Data quality must be visible, not hidden in code. The report is the evidence that the data can be trusted. |
| `hour`, `weekday` | `dt.hour`, `dt.day_of_week`. | Load and latency follow the time of day and the day of the week (seasonality). |
| Deployment features | `pd.merge_asof(..., by="service", direction="backward")` on the finished deployments. | "2 minutes after a deployment" is the strongest hint an ops engineer can get. `merge_asof` finds the last deployment before each minute in one step. |
| `load_level` | Ratio to last week's average of the same weekday and hour; thresholds 0.7 and 1.3. | A latency jump at normal load points to a change, not to traffic. Comparing with the same hour last week removes the daily pattern. |

### Requirement 3 - Robust anomaly detection

| Rule | How | Why |
|---|---|---|
| Baseline | `series.rolling("30min", closed="left", min_periods=20)`. | `closed="left"` excludes the current minute. If a value is part of its own baseline, it pulls the mean towards itself and hides itself. |
| z-score | (value - mean) / std; std = 0 is treated as missing. | A simple, explainable, deterministic measure: "how many standard deviations away from normal". |
| Threshold | abs(z) > 3. | Common rule of thumb: in normal data, values beyond 3 standard deviations are rare. |
| Events | Group consecutive flagged minutes; drop groups shorter than 2 minutes. | The on-call engineer needs one alarm per incident. A single odd minute is noise, not an incident. |
| Baseline and peak | Median of the 30 minutes before the start; maximum during the event. | The median ignores single outliers; the peak shows the size of the problem. |

### Requirement 4 - Mask personal data

| Rule | How | Why |
|---|---|---|
| Minimisation | Keep only the needed columns. | What is not sent cannot leak. This is the strongest protection. |
| Pseudonym | `CUST-` + first 6 hex characters of SHA-256(salt + e-mail). | Stable: tickets of the same customer can still be grouped. Salted: the pseudonym cannot be reversed with a list of e-mail addresses. In production, keep the salt secret. |
| Patterns | Regular expressions for e-mail addresses, IPv4 addresses and phone numbers (`+` country code or leading `0`). | These formats are regular and can be found reliably. Dates and amounts do not match the phone pattern. |
| Own name | Replace the ticket's `customer_name` in the free text. | Customers often sign with their name. |
| Limit | Other names are not found. | Names have no fixed format. This is why minimisation comes first and the preview is checked. |

### Requirement 5 - Bedrock summary

| Rule | How | Why |
|---|---|---|
| Guard | Refuse tickets with personal columns. | A second line of defence: even a coding mistake cannot send raw tickets. |
| Client | `AnthropicBedrock(aws_region=...)` from `anthropic[bedrock]` - the `bedrock-runtime` endpoint; the SDK reads the key from `AWS_BEARER_TOKEN_BEDROCK`. | No secret in the code. The trainer controls region, key and model through `.env`. `bedrock-mantle` (`AnthropicBedrockMantle`) does not offer Claude Haiku 5.5 - it answers 404. |
| Model ID | An inference profile ID, e.g. `us.anthropic.claude-haiku-5-5`. | Claude runs on Bedrock only through inference profiles. The `us.` profile routes the requests within US Regions. |
| Parameters | `max_tokens=1024`, `output_config={"effort": "low"}`, no `temperature`. | The model thinks before it answers; thinking counts towards `max_tokens`. Low effort is enough for one sentence and keeps it fast and cheap. This model rejects `temperature`. |
| Answer | Join the blocks with `type == "text"`; check `stop_reason`. | The first block can be thinking. A refusal must be visible, not silently empty. |

### Requirement 6 - SLO forecast

| Rule | How | Why |
|---|---|---|
| Budget | (1 - 99.5 / 100) × 30 × 1,440 = 216 bad minutes. | The error budget is the number of bad minutes the SLO allows in the window. |
| Projection | Remaining budget / burn rate of the last 30 minutes. | A linear projection is simple and good enough to judge urgency. No LLM needed. |

## Error Handling

- A task that is not built yet raises `NotImplementedError`; the command line reports it and skips the task.
- Missing `.env` values raise a `RuntimeError` with a clear message (`config.py`).
- Nothing is sent to the LLM before masking works (command line and Requirement 5.1).

## Verification

Each task is verified with the command line. The expected results on the workshop data:

| Task | Command | Expected result |
|---|---|---|
| 1 | `python -m opspilot data` | 1,086 rows in, 993 rows out: 573 UTC timestamps converted, 93 duplicates removed, 5 latency zeros set to missing |
| 2 | `python -m opspilot data` | Features added; `out/data_quality.md` written |
| 3 | `python -m opspilot data` | Exactly one event: `payment-api` at 14:05, baseline ≈ 250 ms, peak ≈ 2.4 s, 2 min after deployment 2.3.1 |
| 4 | `python -m opspilot data --preview-prompt` | No e-mail address, IP address or phone number in the preview |
| 5 | `python -m opspilot data --summary` | One factual sentence from Claude |
| 6 | `python -m opspilot data --forecast` | 32 of 216 bad minutes left, exhausted at about 17:02 |
