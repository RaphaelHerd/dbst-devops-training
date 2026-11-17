# 🛟 Solutions - OpsPilot After Every Lab

📁 one complete project per lab · ✅ tested against Claude Haiku 5.5 and Titan Text Embeddings V2 (`us-west-2`)<br>
🎯 Fell behind? Take the missing part from here and continue with the next lab.

> [!NOTE]
> 🧠 Try it yourself first - the review of your own (or Kiro's) code is where you learn. Use a solution to catch up,
> or to compare after you finished.

## 📦 What Each Folder Contains

Every folder is the complete `opspilot` project after that lab - with all tasks of this lab **and all labs before**:

| Folder | Built in this lab | Prompts written in this lab |
|---|---|---|
| `lab-01/` | `cleaning.py`, `quality.py`, `anomaly.py`, `masking.py`, `llm.py`, `forecast.py` | - |
| `lab-02/` | `triage.py`: `parse_triage()`, `check_reply()`, `triage_structured()` | `prompts/triage/v2.md` … `v5.md` |
| `lab-03/` | `review.py`: `extract_failures()`, `scan_diff()`, `policy_gate()` | `prompts/change-review/2_cause.md` |
| `lab-04/` | `knowledge.py`: `chunk_runbook()`, `top_k()`, `cluster()` | `prompts/ask/answer.md` |
| `lab-05/` | `agent.py`: `recent_changes()` + tool definition, `investigate()`, `is_repeat()` | `prompts/investigate/v2.md` |

The task lists in `.kiro/specs/*/tasks.md` are ticked up to that lab.

## 🔁 Catch Up

Copy only what you missed into **your** project. In PowerShell, from `labs/opspilot`:

```powershell
Copy-Item ..\..\solution\lab-02\opspilot\triage.py opspilot\
Copy-Item ..\..\solution\lab-02\prompts\triage\v3.md prompts\triage\
```

> [!WARNING]
> ⚠️ Copying a module replaces **your** version of that file. Copy the module of the lab you missed - not the whole
> folder: later labs' modules in a solution still contain their stubs.

## ▶️ Run a Solution Directly

Each folder runs on its own. Inside the folder: copy `.env.example` to `.env`, paste the key from your trainer, and
run the commands of the lab README, e.g. `python -m opspilot change-review`.

> [!CAUTION]
> 🔐 `.env` holds the key. It is listed in `.gitignore` - never commit it, never share a solution folder with a
> `.env` inside.

## ✅ Tested

Every folder was run against Bedrock (`us-west-2`, `us.anthropic.claude-haiku-5-5`, `amazon.titan-embed-text-v2:0`):

| Lab | Result |
|---|---|
| 1 | 1,086 → 993 rows · 1 event at 14:05 · no personal data in the prompt · one-sentence summary · 32 of 216 bad minutes left |
| 2 | v5: 100 % parsed, 98 % category, all replies without a tone break · problem proposal for `team-payments`, P1 since 14:33 · structured outputs |
| 3 | 22 log lines · 2 findings · gate FAIL · chain finds the retry loop, critic passes |
| 4 | "checkout is slow" → latency runbook · 8 of 8 test questions · INC-3920 · hidden instruction ignored and reported · 31 payment alerts in one group |
| 5 | agent finds release 2.3.1 in 5-6 steps, rules out the old SFTP error, recommends the rollback · step limit, repeat guard and report check work |

LLM answers vary from run to run - the wording and single numbers can differ a little.
