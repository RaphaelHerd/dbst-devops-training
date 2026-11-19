# Implementation Plan - `opspilot remediate`

Read the requirement of a task in `requirements.md` before you start it. The reasons behind each rule are in
`design.md`. Task 4 is a prompt - write it yourself; Kiro may review it.

- [x] 1. The safe action set
  - Implement `check_action(action, state, releases)` in `opspilot/remediate.py`
  - Verify with `python -m opspilot remediate --action "scale payment-db 0"`: decision `block`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 2. The dry run
  - Implement `dry_run(action, state, releases, now)` in `opspilot/remediate.py`
  - Verify with `python -m opspilot remediate --action "rollback payment-api 2.3.0"`: the approval card shows the plan
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 3. Automate or escalate
  - Implement `decide(action, violations, plan)` in `opspilot/remediate.py`
  - Verify with `python -m opspilot remediate --action "page_team team-payments"`: decision `auto`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 4. Post-mortem draft (stretch goal)
  - Write `prompts/remediate/postmortem.md` with role, task and rules
  - Verify with `python -m opspilot remediate --postmortem`: `out/postmortem.md`
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
