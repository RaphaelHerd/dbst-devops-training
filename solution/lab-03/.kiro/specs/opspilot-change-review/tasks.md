# Implementation Plan - `opspilot change-review`

Read the requirement of a task in `requirements.md` before you start it. The reasons behind each rule are in
`design.md`. Task 3 is a prompt - write it yourself; Kiro may review it.

- [x] 1. Shrink the pipeline log
  - Implement `extract_failures(log)` in `opspilot/review.py` - pure Python, no LLM
  - Verify with `python -m opspilot change-review --checks`: run 4711 2,254 → 13 lines, run 4712 2,467 → 9 lines
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 2. Scan the diff
  - Implement `scan_diff(diff, advisories)` in `opspilot/review.py`: secrets and vulnerable dependencies
  - Verify with `python -m opspilot change-review --checks`: exactly 2 findings, no full secret value
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 3. Link 2 of the chain: the cause
  - Write `prompts/change-review/2_cause.md` with role, input, task and rules
  - Verify with `python -m opspilot change-review`: the cause names `PaymentClient.charge()`, flaky: no
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 4. Policy gate
  - Implement `policy_gate(release, previous, findings)` in `opspilot/review.py` - rules only, no LLM
  - Verify with `python -m opspilot change-review --checks`: Gate FAIL with 4 reasons, exit code 1
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_
