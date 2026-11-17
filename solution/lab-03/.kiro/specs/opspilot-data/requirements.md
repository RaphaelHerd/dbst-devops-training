# Requirements Document - `opspilot data`

## Introduction

`opspilot data` turns the raw ops exports in `data/` into trustworthy, AI-ready data. It cleans the Grafana metric
exports, documents the data quality, adds features, detects anomalies with a classic statistical method, protects
personal data and finally asks Claude on Amazon Bedrock for a one-sentence summary for the on-call channel.

All times are local time **Europe/Berlin**. The incident day is Monday, 9 November 2026.

## Requirements

### Requirement 1 - Clean the metrics

**User Story:** As an on-call engineer, I want one clean time series per service and minute, so that alarms point to
real events and not to export problems.

#### Rules and Acceptance Criteria

1. WHEN a timestamp ends with `Z` THEN OpsPilot SHALL treat it as UTC and convert it to Europe/Berlin time. It SHALL
   NOT simply remove the `Z`.
2. WHEN a timestamp has no offset THEN OpsPilot SHALL interpret it as Europe/Berlin local time.
3. WHEN cleaning is done THEN every timestamp SHALL be timezone-aware (Europe/Berlin).
4. WHEN two or more rows have the same `service` and the same `timestamp` THEN OpsPilot SHALL keep the first row and
   remove the others.
5. WHEN `p95_latency_ms` is `0` THEN OpsPilot SHALL set it to missing (NaN), because a latency of 0 ms is a scrape
   gap, not a measurement.
6. WHEN `error_rate_pct` or `requests_per_min` is `0` THEN OpsPilot SHALL keep the value, because 0 % errors and
   0 requests are real measurements.
7. WHEN a value is missing THEN OpsPilot SHALL leave it missing. It SHALL NOT fill, interpolate or drop it.
8. WHEN cleaning is done THEN OpsPilot SHALL remove the column `source`, sort by `service` and `timestamp` and write
   the result to `out/metrics_clean.csv`.
9. WHEN cleaning is done THEN `clean_metrics()` SHALL return the clean table and a cleaning log with the keys
   `rows_in`, `utc_converted`, `duplicates_removed`, `zero_latency_set_missing` and `rows_out`.

### Requirement 2 - Quality report and features

**User Story:** As an on-call engineer, I want to see what was fixed in the data and get context for every minute, so
that I can judge whether an anomaly is real and what happened around it.

#### Rules and Acceptance Criteria

1. WHEN `opspilot data` runs THEN OpsPilot SHALL write `out/data_quality.md` with:
   - per export: rows, first and last raw timestamp, time format (UTC or local);
   - the cleaning log: rows in, timestamps converted from UTC, duplicates removed, latency zeros set to missing,
     rows out, time range;
   - missing values per metric column;
   - the masked personal data per type (Requirement 4), or a note that masking has not run yet.
2. WHEN features are added THEN OpsPilot SHALL add `hour` (0 to 23) and `weekday` (0 = Monday).
3. WHEN features are added THEN OpsPilot SHALL add `minutes_since_deployment` and `last_deployment_version`, based on
   the most recent change in `data/itsm/changes.csv` of the same service with `type` = `deployment` and a
   `finished_at` at or before the minute.
4. WHEN a change is a `config` change or has no `finished_at` THEN it SHALL NOT count as a deployment.
5. WHEN features are added THEN OpsPilot SHALL add `load_level`: the ratio of `requests_per_min` to
   `avg_requests_per_min` of the same service, weekday and hour in `data/grafana/load_baseline_last_week.csv`.
   Below 0.7 is `low`, above 1.3 is `high`, otherwise `normal`. Without a ratio the level is `unknown`.
6. WHEN features are added THEN the input table SHALL NOT be changed; `add_features()` returns a new table.

### Requirement 3 - Robust anomaly detection

**User Story:** As an on-call engineer, I want one alarm per real latency anomaly, so that I chase incidents, not
ghosts.

#### Rules and Acceptance Criteria

1. WHEN detecting anomalies THEN OpsPilot SHALL use the clean data of Requirement 1, the metric `p95_latency_ms` and
   every service separately.
2. WHEN calculating the baseline of a minute THEN OpsPilot SHALL use the values of the **previous 30 minutes**. The
   current minute SHALL NOT be part of its own baseline.
3. WHEN the previous 30 minutes contain fewer than 20 values THEN OpsPilot SHALL NOT calculate a z-score for that
   minute.
4. WHEN calculating the z-score THEN OpsPilot SHALL use z = (value - mean of the baseline) / standard deviation of
   the baseline. Missing values SHALL be ignored.
5. WHEN |z| > 3 THEN the minute SHALL be flagged as anomalous.
6. WHEN flagged minutes follow each other without a gap THEN OpsPilot SHALL group them into **one event**.
7. WHEN an event lasts less than 2 minutes THEN OpsPilot SHALL drop it.
8. WHEN an event is reported THEN it SHALL contain: `service`, `metric`, `start`, `end`, `baseline_ms` (median of
   the 30 minutes before `start`), `peak_ms` (maximum during the event) and, if the features of Requirement 2 are
   present, `minutes_since_deployment` and `deployment_version` at `start`.
9. WHEN `opspilot data` runs on the workshop data THEN exactly **one** event SHALL be found: `payment-api` at 14:05.

### Requirement 4 - Mask personal data

**User Story:** As a data protection officer, I want personal data removed before anything reaches an LLM, so that
no customer data leaves our control.

#### Rules and Acceptance Criteria

1. WHEN tickets are prepared for an LLM THEN OpsPilot SHALL keep only `ticket_id`, `created_at`, `service`,
   `subject` and `description` (data minimisation) and add the column `customer`.
2. WHEN a customer is pseudonymised THEN `customer` SHALL be `CUST-` followed by the first 6 hex characters of the
   SHA-256 hash of salt + e-mail address (lower case, trimmed). The salt comes from `OPSPILOT_PSEUDONYM_SALT`; the
   default is `opspilot-workshop`. The same e-mail address SHALL always give the same pseudonym.
3. WHEN `subject` or `description` contains an e-mail address THEN OpsPilot SHALL replace it with `<EMAIL>`.
4. WHEN `subject` or `description` contains an IPv4 address THEN OpsPilot SHALL replace it with `<IP>`.
5. WHEN `subject` or `description` contains a phone number (starting with `+` and a country code, or with `0`)
   THEN OpsPilot SHALL replace it with `<PHONE>`.
6. WHEN `subject` or `description` contains the ticket's own customer name THEN OpsPilot SHALL replace it with the
   pseudonym.
7. WHEN masking is done THEN `mask_tickets()` SHALL return the masked tickets and the counts of masked items with the
   keys `email`, `ip`, `phone`, `name` and `customers_pseudonymised`.
8. WHEN masking is done THEN the counts SHALL appear in `out/data_quality.md` (Requirement 2).
9. Known limit: names of other people in the free text (e.g. a family member) are not detected by these rules.
   Data minimisation and a check of the prompt preview SHALL be used to catch them.

### Requirement 5 - Bedrock summary

**User Story:** As an on-call engineer, I want a one-sentence summary of the anomaly and the latest customer
tickets, so that I can inform the on-call channel in seconds.

#### Rules and Acceptance Criteria

1. WHEN the tickets still contain `customer_name` or `customer_email` THEN `summarise_incident()` SHALL raise a
   `ValueError` and SHALL NOT send anything.
2. WHEN calling Claude THEN OpsPilot SHALL use the Anthropic Python SDK with `AnthropicBedrock` (the
   `bedrock-runtime` endpoint), the region from `AWS_REGION` and the model ID from `OPSPILOT_MODEL` - an inference
   profile ID such as `us.anthropic.claude-haiku-5-5`. The API key comes from `AWS_BEARER_TOKEN_BEDROCK` - the SDK
   reads it from the environment - and SHALL NOT appear in the code.
3. WHEN calling Claude THEN OpsPilot SHALL send the system prompt `SYSTEM_PROMPT` ("one sentence, facts only, no root
   cause"), the user message of `build_prompt()` with the 3 most recent masked tickets, `max_tokens` = 1024 and
   `output_config` = `{"effort": "low"}`.
4. WHEN calling Claude THEN OpsPilot SHALL NOT set `temperature`.
5. WHEN `stop_reason` is `refusal` THEN OpsPilot SHALL raise a `RuntimeError`.
6. WHEN reading the answer THEN OpsPilot SHALL join the content blocks with `type == "text"`, not take the first
   block, because the first block can be the model's thinking.

### Requirement 6 - SLO forecast (stretch goal)

**User Story:** As a service owner, I want to know when the error budget runs out, so that I can decide how urgent a
fix is.

#### Rules and Acceptance Criteria

1. WHEN forecasting THEN OpsPilot SHALL read the SLO from `data/grafana/slo_budget.csv`.
2. WHEN calculating the error budget THEN budget = (1 - `target_pct` / 100) × `window_days` × 1,440 bad minutes.
3. WHEN counting bad minutes THEN a minute is bad if its p95 latency is above `slo_p95_ms`. Missing values are not
   counted.
4. WHEN calculating the remaining budget THEN remaining = budget - `bad_minutes_before_today` - bad minutes today.
5. WHEN calculating the burn rate THEN OpsPilot SHALL use the share of bad minutes in the last 30 minutes of data.
6. WHEN the burn rate is above 0 THEN the budget is exhausted at: last timestamp + remaining / burn rate minutes.
7. WHEN `opspilot data --forecast` runs on the workshop data THEN `payment-api` SHALL have 32 of 216 bad minutes left,
   exhausted at about 17:02.
