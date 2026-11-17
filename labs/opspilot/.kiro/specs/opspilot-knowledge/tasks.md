# Implementation Plan - `opspilot ask` and `opspilot similar`

Read the requirement of a task in `requirements.md` before you start it. The reasons behind each rule are in
`design.md`. Task 3 is a prompt - write it yourself; Kiro may review it.

- [ ] 1. Chunk the runbooks
  - Implement `chunk_runbook(text, source)` in `opspilot/knowledge.py`
  - Verify with `python -m opspilot ask --chunks`: 6 runbooks · 1 archived, skipped · 14 chunks
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [ ] 2. Find by meaning
  - Implement `top_k(query, matrix, k)` in `opspilot/knowledge.py` with NumPy - cosine similarity, no loop over rows
  - Verify with `python -m opspilot ask "checkout is slow" --search` and `python -m opspilot ask --eval`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 3. The answer prompt
  - Write `prompts/ask/answer.md` with role, input, task and rules
  - Verify with `python -m opspilot ask "What do I check first when payments take long?"`: citations and sources
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 4. Group alerts by meaning
  - Implement `cluster(vectors, threshold)` in `opspilot/knowledge.py` - leader rule, no LLM
  - Verify with `python -m opspilot similar --alerts --threshold 1.0` (8 groups) and `--threshold -1` (1 group)
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
