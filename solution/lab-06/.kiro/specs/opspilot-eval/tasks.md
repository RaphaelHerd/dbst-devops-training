# Implementation Plan - `opspilot eval`

Read the requirement of a task in `requirements.md` before you start it. The reasons behind each rule are in
`design.md`. Task 2 is a prompt - write it yourself; Kiro may review it.

- [ ] 1. Quality per group
  - Implement `group_report(results, by)` in `opspilot/evaluate.py`
  - Verify with `python -m opspilot eval --prompt v1`: a table per service and per incident type, weakest first
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 2. The prompt v2
  - Write `prompts/eval/v2.md` with role, cause codes (`{{cause_code_definitions}}`) and rules
  - Verify with `python -m opspilot eval --prompt v2` and `python -m opspilot eval --compare`
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [ ] 3. The guard on both sides
  - Implement `redact(text)` in `opspilot/evaluate.py`
  - Verify with `python -m opspilot eval --attack --prompt v2`: 3 of 3 attacks withstood
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
