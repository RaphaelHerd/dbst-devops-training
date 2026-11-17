# Implementation Plan - `opspilot triage`

Read the requirement of a task in `requirements.md` before you start it. The reasons behind each rule are in
`design.md`. Tasks 1, 3, 4 and 5 are prompts - write them yourself; Kiro may review them.

- [ ] 1. Prompt v2: role and structure
  - Write `prompts/triage/v2.md` with role, context, task, rules and output format
  - Verify with `python -m opspilot triage --prompt v2 --show 3`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 2. Parse and validate the answer
  - Implement `parse_triage(raw, schema)` in `opspilot/triage.py` with `json` and `jsonschema`
  - Find the JSON object, parse it, validate it, raise `ValueError` with a clear message
  - Verify with `python -m opspilot triage --prompt v2`: parser robust, 100 % parsed or needs human, retries > 0
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 3. Prompt v3: allowed values
  - Write `prompts/triage/v3.md`: v2 plus `{{categories}}` and `{{priorities}}`
  - Verify with `python -m opspilot triage --prompt v3`: fewer retries, higher category accuracy
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 4. Prompt v4: few-shot examples
  - Write `prompts/triage/v4.md`: v3 plus `{{examples}}`
  - Verify with `python -m opspilot triage --prompt v4` and `python -m opspilot triage --compare`
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 5. Tone guard
  - Write `prompts/triage/v5.md`: v4 plus the rules for `customer_reply`
  - Implement `check_reply(reply)` in `opspilot/triage.py`
  - Verify with `python -m opspilot triage --prompt v5`: tone line shows the replies without a rule break
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 6. Structured outputs (stretch goal)
  - Implement `triage_structured(client, system, ticket, schema)` in `opspilot/triage.py`
  - Verify with `python -m opspilot triage --prompt v5 --structured` and `--compare`
  - _Requirements: 6.1, 6.2, 6.3, 6.4_
