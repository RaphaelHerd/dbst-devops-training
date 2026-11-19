# Implementation Plan - `opspilot investigate`

Read the requirement of a task in `requirements.md` before you start it. The reasons behind each rule are in
`design.md`. Task 3 is a prompt - write it yourself; Kiro may review it.

- [x] 1. The tool `recent_changes`
  - Implement `recent_changes(service, hours, now)` in `opspilot/agent.py` and define `RECENT_CHANGES_TOOL`
  - Verify with `python -m opspilot investigate --tool recent_changes service=all hours=6`: CHG-20448 and CHG-20446
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2. The agent loop
  - Implement `investigate(client, system, alert, now, max_steps, max_seconds)` in `opspilot/agent.py`
  - Use the ready helpers: `first_message()`, `tool_definitions()`, `run_tool()`, `accept_report()`, `log_step()`,
    `log_thought()`
  - Verify with `python -m opspilot investigate --max-steps 2` and `python -m opspilot investigate`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

- [x] 3. The system prompt v2
  - Write `prompts/investigate/v2.md` with role, process, rules and report
  - Verify with `python -m opspilot investigate --prompt v2`: release 2.3.1 first, evidence from two tools
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 4. Repeat guard (stretch goal)
  - Implement `is_repeat(name, args, history)` in `opspilot/agent.py`
  - Verify with `python -m opspilot investigate --prompt v2`: a repeated call shows ⚠️ in the step log
  - _Requirements: 4.1, 4.2, 4.3_
