# Implementation Plan - `opspilot data`

Read the requirement of a task in `requirements.md` before you start it. The reasons behind each rule are in
`design.md`.

- [x] 1. Clean the metrics
  - Implement `clean_metrics(raw, out_dir)` in `opspilot/cleaning.py`
  - Convert UTC timestamps (ending with `Z`) to Europe/Berlin; interpret timestamps without offset as local time
  - Remove duplicates per service and minute (after the time zone fix); set `p95_latency_ms == 0` to missing
  - Keep zeros in `error_rate_pct` and `requests_per_min`; do not fill missing values
  - Drop `source`, sort, write `out/metrics_clean.csv` and return the cleaning log
  - Verify with `python -m opspilot data`: 1,086 rows in, 993 rows out, 573 UTC timestamps converted,
    93 duplicates removed, 5 latency zeros set to missing
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

- [x] 2. Quality report and features
  - Implement `add_features(clean, changes, baseline)` in `opspilot/quality.py`: `hour`, `weekday`,
    `minutes_since_deployment`, `last_deployment_version`, `load_level`
  - Implement `write_quality_report(raw, clean, log, mask_counts, path)`: exports, cleaning log, missing values,
    masking counts
  - Verify with `python -m opspilot data` and open `out/data_quality.md`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 3. Robust anomaly detection
  - Implement `detect_events(df)` in `opspilot/anomaly.py`
  - Rolling baseline of the previous 30 minutes (current minute excluded, at least 20 values), z-score, threshold 3
  - Group consecutive flagged minutes into events, drop events shorter than 2 minutes, fill `AnomalyEvent`
  - Verify with `python -m opspilot data`: exactly one event - payment-api at 14:05, 2 min after deployment 2.3.1
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

- [x] 4. Mask personal data
  - Implement `pseudonym(email)` and `mask_tickets(tickets)` in `opspilot/masking.py`
  - Keep only the needed columns, add the pseudonym, mask e-mail addresses, IP addresses, phone numbers and the
    customer's own name in `subject` and `description`, count every masked item
  - Verify with `python -m opspilot data --preview-prompt`: no e-mail address, IP address or phone number
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

- [x] 5. Bedrock summary
  - Implement `summarise_incident(event, tickets)` in `opspilot/llm.py`
  - Refuse unmasked tickets; use `AnthropicBedrock`, `OPSPILOT_MODEL`, `SYSTEM_PROMPT`, `build_prompt()`,
    `max_tokens=1024`, `output_config={"effort": "low"}`, no `temperature`
  - Raise on refusal; join the text blocks instead of taking the first block
  - Verify with `python -m opspilot data --summary`: one factual sentence
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 6. SLO forecast (stretch goal)
  - Implement `forecast_error_budget(clean, slo, service)` in `opspilot/forecast.py`
  - Budget from `slo_budget.csv`, bad minutes today, burn rate of the last 30 minutes, linear projection
  - Verify with `python -m opspilot data --forecast`: 32 of 216 bad minutes left, exhausted at about 17:02
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
