# 🔌 Lab 6 - OpsPilot as MCP Server

🏷️ **OpsPilot v0.6** · 💻 `opspilot serve` · ⏱️ **45 min** · 🧭 **LF7** AI functions via APIs and plugins · Least
privilege, input validation · Audit logging<br>
🎯 Make OpsPilot's tools usable from any AI client through one standard - with boundaries.

> [!CAUTION]
> ### 🔌 Monday, 17:30 - "Can I just ask from my IDE?"
>
> 🧑‍💻 The on-call engineer liked the investigation report: *"I work in Kiro all day. Can I ask there - why is
> payment-api slow since 14:05?"* 🧑‍💼 The platform lead agrees - with conditions: *"It reads our exports and nothing
> else. Nothing secret leaves. And I want to see every call."*
>
> 👉 **Your job: turn OpsPilot's read-only tools into an MCP server - with a data boundary, valid inputs only and an
> audit log.**

## 🎓 What You Will Learn

After this lab you can:

- ✅ explain how an MCP host, an MCP client and an MCP server work together over **stdio**;
- ✅ turn Python functions into **MCP tools** - and see what the model sees: name, description, input schema;
- ✅ test an MCP server with a small **Python client**, then use it from **Kiro chat**;
- ✅ enforce **boundaries** in code: allowed data folders, schema checks, read-only tools;
- ✅ keep stdout clean for the protocol and write an **audit log** of every call.

## 📁 What Is New in Your Project

You continue in your `labs/opspilot/` folder. Everything for this lab is already there:

```text
labs/opspilot/
├── .kiro/specs/opspilot-serve/   requirements.md · design.md · tasks.md
├── opspilot_server.py            ✅ ready - the file Kiro starts
└── opspilot/serve.py             ✅ server, resource, prompt, test client · 🛠️ safe_path(), guarded(), tool descriptions
```

No new data. The server offers what you built in Labs 1 to 5:

| Kind | Name | From |
|---|---|---|
| 🔧 Tools - the model decides | `query_metrics` · `search_logs` · `recent_changes` · `search_runbooks` · `similar_incidents` | Labs 1, 4, 5 |
| 🔧 Tool | `read_export` - one raw export file as text | ✅ ready |
| 📄 Resource - the app decides | `runbook://{service}` - the current runbooks of a service | Lab 4 data |
| 💬 Prompt - the user decides | `triage_ticket(ticket_id)` - your newest triage prompt with the masked ticket | Labs 1, 2 |

The server is a **replay**: its clock stands at **14:20** on the day of the incident.

## 📜 The Spec: Where the Rules Are

All rules of this lab are in `.kiro/specs/opspilot-serve/`: `requirements.md` (**what**, with acceptance criteria),
`design.md` (**how** and **why**) and `tasks.md` (the tasks).

## 🛠️ Step 0 - Start the Server Like Kiro Does (3 min)

```powershell
python -m opspilot serve --test
```

The ready test client starts `opspilot_server.py` as a subprocess - exactly as Kiro will - and talks MCP with it over
stdin and stdout. It lists what the server offers and calls every tool once.

✅ **Check:** the first line says `6 tools · 1 resource template · 1 prompt`.

> [!NOTE]
> 💤 `python -m opspilot serve` alone starts the server and waits silently for a host - that is normal for stdio.
> Stop it with `Ctrl+C`.

## 😱 Step 1 - See the Problem (5 min)

Look at the second half of the same output:

```text
Calls:
  ✅ query_metrics(service='payment-api', minutes=60) → 1,668 chars
  💥 search_logs(query='timeouts') → the tool crashed - the client only sees "Error executing tool search_logs".
  🔓 read_export(path='../.env') → 463 chars - YOUR BEDROCK KEY left the data folder (value not shown here)
  🔓 read_export(path='gold/triage_gold.csv') → 51 lines - the Gold labels, the answers of the Lab 2 exam
  ⚠️ query_metrics(service='payment', minutes=60) → accepted - the code had to cope with it
  ⚠️ query_metrics(service='payment-api', minutes=100000) → accepted - silently changed to a different request

Boundaries:
  🔓 0 of 4 bad requests refused
  💥 1 tool(s) crashed
  📒 audit log: 0 new line(s) in out/mcp_audit.jsonl for 8 calls that reached the code
```

🤔 **The test client is polite. The model in Kiro is not - it sends whatever it read. What could go wrong in a real
chat?**

<details>
<summary>💡 Hint</summary>

- 🔓 **`../.env`:** the tool hands out your Bedrock key. Any model connected to the server can ask for it - and so can
  a hidden instruction in a ticket or a runbook (Lab 4). The Gold labels are the answers of every evaluation.
- 💥 **`search_logs` crashed:** scroll up to the server log - `UnicodeEncodeError` in a `print()`. On stdio, **stdout
  is the protocol**. A stray print corrupts the message stream or, on Windows, crashes the tool. Lab 4's `embed()`
  prints too: in a real chat, every search with a new question crashes.
- ⚠️ **Wrong input accepted:** the model only knows `service: string` and `minutes: integer`. Your code had to guess
  what it meant.
- 📒 **No audit log:** nobody can say later which tool was called with what.

</details>

## 🛡️ Step 2 - The Data Boundary (8 min)

📜 **Rules:** `requirements.md` → **Requirement 1 - The data boundary `safe_path`.**

Start **Task 1** of the spec `opspilot-serve` in Kiro - the same way as in Lab 1. Kiro builds
`safe_path(path)`: a path relative to `data/` that must stay inside the allowed folders.

🔍 **Review before you accept:** is the path **resolved before** it is checked? A text check for `..` misses links and
other tricks. Does the error message tell the model what is allowed - without showing your disk?

✅ **Check:** `python -m opspilot serve --test` - both `read_export` attacks now show 🛡️ `refused`.

## 🧯 Step 3 - Guard Every Call (8 min)

📜 **Rules:** `requirements.md` → **Requirement 2 - The guard `guarded`.**

Start **Task 2**. Kiro builds the decorator `guarded(func)`. The ready code wraps every tool with it.

🔍 **Review before you accept:**

- Does it use `functools.wraps`? Without it the SDK loses the name, the description and the schema of the tool.
- Is stdout redirected **while the tool runs**?
- Is the audit line also written when the tool **fails** - and is the error raised again?

✅ **Check:**

```powershell
python -m opspilot serve --test
python -m opspilot serve --audit
```

`0 tool(s) crashed`, and one audit line per call that reached your code. The crashed print now shows up harmlessly in
the server log on stderr.

## 🏷️ Step 4 - Describe the Tools (8 min)

📜 **Rules:** `requirements.md` → **Requirement 3 - Tool descriptions and input schemas.**

Look at *"What the model sees"* in the test output: `"Metrics."`, `"Search."`, `service: string`. That is **all** the
model in Kiro knows about your tools.

Start **Task 3**. Kiro rewrites the docstrings and type hints of the 6 tool functions - not their bodies:

```python
def query_metrics(service: Literal["payment-api", "checkout-web", "booking-search"],
                  minutes: Annotated[int, Field(ge=15, le=240, description="How far back from now: 15 to 240.")]) -> dict:
    """Grafana metrics of one service ... Use it to see WHEN a problem started and how big it is. Read-only."""
```

🔍 **Review before you accept:** read every docstring like a prompt. Does it say **what** the tool returns and
**when** to use it?

✅ **Check:** `python -m opspilot serve --test` - *"What the model sees"* shows the services and the limits, and the
summary says **4 of 4 bad requests refused**. The two wrong `query_metrics` calls are now refused by the SDK **before**
your code runs.

## 🤝 Step 5 - Connect Kiro (10 min)

📜 **Rules:** `requirements.md` → **Requirement 4 - Connect Kiro.**

1. Write the Kiro configuration for your machine - this Python, this server file:

   ```powershell
   python -m opspilot serve --kiro-config
   ```

2. Open `.kiro/settings/mcp.json`. `autoApprove` is empty, so Kiro asks before **every** call. Add the read-only
   tools you trust to run without a question, e.g. `"autoApprove": ["query_metrics", "recent_changes"]`. Save -
   Kiro reloads the file on its own.
3. In the **Kiro panel**, open the **MCP servers** tab: `opspilot` shows its status and its tools. If it shows an error,
   right-click it → **Show MCP Logs**. If no server appears, open the settings, search for **MCP** and enable MCP
   support.
4. In Kiro chat, ask: *"Why is payment-api slow since 14:05? Use the OpsPilot tools."* For a tool that is not in
   `autoApprove`, Kiro shows the tool and its arguments - click **Approve** or **Deny**.
5. See what Kiro did:

   ```powershell
   python -m opspilot serve --audit
   ```

🤔 **Would you put `read_export` into `autoApprove`?**

<details>
<summary>💡 Hint</summary>

It reads raw files - only inside the allowed folders now, but still more than the other tools. Approval for every call
leads to approval fatigue; auto-approval removes the human. A good rule: auto-approve the narrow read-only tools, ask
for the broad ones - and never auto-approve a tool that changes something.

</details>

> [!IMPORTANT]
> 🔐 No key in `mcp.json`: the server reads it from `.env` itself. Config files get shared and committed - keys do
> not belong there.

🎯 **Kiro answers from OpsPilot's evidence - release 2.3.1 at 14:03, the provider timeouts, INC-3920 - without any glue
code. Every call is in the audit log, and nothing outside the exports leaves the server.**

## ➡️ Next

**Lab 7 - Safe Remediation** 🛡️ *(optional)*: the rollback of 2.3.1 is the next step - but an action needs a safe
action set, a dry run and your approval. You continue in the same `labs/opspilot/` folder.
