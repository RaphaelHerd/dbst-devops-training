# Implementation Plan - `opspilot serve`

Read the requirement of a task in `requirements.md` before you start it. The reasons behind each rule are in
`design.md`. Task 4 is configuration - do it yourself.

- [ ] 1. The data boundary
  - Implement `safe_path(path)` in `opspilot/serve.py`
  - Verify with `python -m opspilot serve --test`: `../.env` and `gold/triage_gold.csv` are refused
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

- [ ] 2. The guard around every tool
  - Implement `guarded(func)` in `opspilot/serve.py`
  - Verify with `python -m opspilot serve --test` (no tool crashed, audit lines) and `python -m opspilot serve --audit`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 3. Tool descriptions and input schemas
  - Rewrite the docstrings and type hints of the 6 tool functions in `opspilot/serve.py` - not their bodies
  - Verify with `python -m opspilot serve --test`: 4 of 4 bad requests refused
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 4. Connect Kiro
  - Run `python -m opspilot serve --kiro-config`, then set `autoApprove` in `.kiro/settings/mcp.json`
  - Verify in Kiro chat with *"Why is payment-api slow since 14:05?"*, then `python -m opspilot serve --audit`
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
