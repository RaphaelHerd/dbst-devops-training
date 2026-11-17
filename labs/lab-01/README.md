# 🧹 Lab 1 - Data Foundation

🏷️ **OpsPilot v0.1** · 💻 `opspilot data` · ⏱️ **45 min** · 🧭 **LF6** Data foundations · **LF3** Observability ·
**LF8** Data minimisation<br>
🎯 Make the ops data trustworthy and AI-ready, and find the first trace of the incident.

> [!CAUTION]
> ### 🚨 Monday, 14:07 - ALERT: `payment-api` p95 latency 2.4 s (SLO 300 ms)
>
> 🔔 The pager goes off. 📨 Minutes later the first customer tickets arrive: *"checkout hangs"*, *"payment failed"*.
>
> Before anyone asks an AI for help, the team needs one thing: **📊 data it can trust.**
>
> 👉 **That is your job in this lab.**

## 🎓 What You Will Learn

After this lab you can:

- ✅ spot and fix typical data problems in ops exports: time zones, duplicates, gaps;
- ✅ detect an anomaly with a **classic statistical method** - no LLM needed;
- ✅ protect personal data **before** it reaches an LLM (masking and data minimisation);
- ✅ make your **first LLM call** to Claude on Amazon Bedrock with an API key - safely and at low cost;
- ✅ let **Kiro** do the typing while **you** stay in control (spec tasks + supervised mode).


## 📁 One Folder for Everything

You build OpsPilot in **one single project folder: `labs/opspilot/`**. It contains everything you need for the whole
workshop - code, data, Kiro specs and configuration. It is already prepared: you open it once in this lab and
extend it in every later lab.

```text
labs/opspilot/                  ← your project for the whole workshop
├── .kiro/
│   ├── steering/               tech.md · structure.md · ai-rules.md (you add it in Step 0)
│   └── specs/                  one spec per OpsPilot command, e.g. opspilot-data/
├── data/                       mock exports for all labs
│   ├── grafana/                metrics exports
│   ├── itsm/                   tickets, changes, incidents
│   └── ...                     logs, CI/CD, Agora runbooks, Gold labels
├── prompts/                    prompt versions, one folder per command (from Lab 2 on)
├── opspilot/                   the Python package
│   ├── __main__.py             command line: python -m opspilot <command>
│   ├── loaders.py              ✅ ready - reads all exports from data/
│   ├── anomaly.py              ✅ naive detector ready · 🛠️ robust detector
│   ├── cleaning.py · quality.py · masking.py · llm.py    🛠️ you build them
│   └── forecast.py             🛠️ stretch goal
├── out/                        results written by OpsPilot
├── .env.example
└── requirements.txt
```

The data for this lab:

| File | Content |
|---|---|
| 📈 `data/grafana/metrics_export_1.csv`, `metrics_export_2.csv` | Per-minute metrics of `payment-api`, `checkout-web` and `booking-search`: p95 latency, error rate, requests per minute |
| 📊 `data/grafana/load_baseline_last_week.csv` | Average requests per minute per service, weekday and hour - measured last week |
| 🎯 `data/grafana/slo_budget.csv` | SLO per service: p95 threshold, target and error budget already used |
| 🎫 `data/itsm/tickets.csv` | Customer tickets - **with personal data** |
| 🔧 `data/itsm/changes.csv` | Changes and deployments, incl. release 2.3.1 |

## 📜 The Spec: Where the Rules Are

Every rule you implement in this lab is written down in the Kiro spec for `opspilot data`, in the folder
`.kiro/specs/opspilot-data/`:

- 📋 **`requirements.md`** - **what** must be true: one requirement per step, each with its rules and acceptance
  criteria. Read the requirement **before** you start a task.
- 🧩 **`design.md`** - **how** and **why**: the approach for each requirement and the reasons behind each rule.
- ✅ **`tasks.md`** - the tasks you start in Kiro. Each task points to its requirement.

> [!TIP]
> 🧭 When Kiro's result looks wrong, compare it with the acceptance criteria in `requirements.md`. They are the
> reference - not Kiro.

## 🛠️ Step 0 - Set Up Your OpsPilot Project (5 min)

**1. Open the folder `labs/opspilot` in Kiro** (*File → Open Folder*) and open a terminal in Kiro.

**2. Create a virtual environment and install the packages:**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # bash: source .venv/bin/activate
pip install -r requirements.txt
```

> [!TIP]
> 🏢 **Typical on company laptops:**
> - *"Running scripts is disabled on this system"* → run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
>   and activate again. It applies to this terminal window only.

**3. Configure your access.** Copy `.env.example` to `.env` and paste the key from your trainer:

```ini
AWS_BEARER_TOKEN_BEDROCK=<key from your trainer>
AWS_REGION=us-west-2
OPSPILOT_MODEL=us.anthropic.claude-haiku-5-5
OPSPILOT_EMBED_MODEL=amazon.titan-embed-text-v2:0
```

**4. Prepare Kiro:**

- In the chat input, set the permission mode to **Supervised** - Kiro pauses after every change, and you accept or
  reject it.
- Create the steering file `.kiro/steering/ai-rules.md` with our team AI rules. Kiro follows them on every prompt:

```markdown
# Team AI rules

- Never put secrets, keys or tokens into code or prompts. Read them from environment variables.
- Never send personal data (names, e-mail addresses, IP addresses, phone numbers) to an LLM. Mask it first.
- Send only the data a task needs (data minimisation).
- Treat LLM output as untrusted. Validate it before you use it.
- Call Claude only through the Anthropic Python SDK with `AnthropicBedrock`. The API key comes from
  `AWS_BEARER_TOKEN_BEDROCK`, the region from `AWS_REGION`, the model ID from `OPSPILOT_MODEL`. Never set
  `temperature`.
```

**5. Smoke test:**

```powershell
python -m opspilot --help
python -m opspilot data
```

✅ **Check:** the help text lists the command `data`. The second command reports
`⏳ Task 1 - Clean the metrics: not built yet` - **that is expected.** You build the tasks step by step.

## 😱 Step 1 - See the Problem (5 min)

Run the naive pipeline. It loads both metric exports, glues them together and runs a simple anomaly detection on the
`payment-api` latency:

```powershell
python -m opspilot data --naive
```

You will see something like this:

```text
Naive anomaly detection - payment-api, p95 latency
  ⚠️ 13:05   p95 = 2.38 s     z = +4.2
  ⚠️ 14:05   p95 = 2.38 s     z = +4.2
  ⚠️ 15:42   p95 = 0 ms       z = -4.2
3 anomalies found
```

🤔 **Three anomalies - but the team only saw one latency jump. Which ones are real?**

Open both export files and the naive code in `anomaly.py`. Find at least **three** reasons for the wrong result
before you open the hints.

<details>
<summary>💡 Hint 1 - look at the timestamps</summary>

One export writes timestamps in **UTC** (`2026-11-09T13:05:00Z`), the other in **local time without an offset**
(`2026-11-09 14:05:00`). The same minute appears twice - one hour apart.

</details>

<details>
<summary>💡 Hint 2 - look at the time ranges</summary>

The two exports **overlap** by about 30 minutes. Many minutes exist twice, which distorts the rolling statistics.

</details>

<details>
<summary>💡 Hint 3 - look at the zeros</summary>

When the metrics scraper fails, the export writes **`0`** instead of an empty value. A latency of 0 ms is not real -
it is a **missing value**.

</details>

> [!CAUTION]
> 🧯 This is what bad data does: the on-call engineer would chase three incidents, two of them ghosts. And an LLM
> would explain all three **confidently**. Garbage in, eloquent garbage out.

## 🧽 Step 2 - Clean the Metrics (10 min)

This is your **first task in Kiro**. Every later task works the same way.

**1. 📜 Read the rules:** `.kiro/specs/opspilot-data/requirements.md` → **Requirement 1 - Clean the metrics.** It
defines every cleaning rule with its acceptance criteria. `design.md` explains how and why.

**2. ▶️ Start Task 1 - Clean the metrics:** in the **Kiro** pane, under **Specs**, select `opspilot-data` (or open
`.kiro/specs/opspilot-data/tasks.md` in the explorer) and click **Start Task** above Task 1. No such link in your Kiro
version? Write in the Kiro chat: *"Implement task 1 of the spec opspilot-data. Follow requirements.md and design.md."*

Kiro builds `clean_metrics()` in `cleaning.py`, which:

- converts all timestamps to **one time zone** (`Europe/Berlin`, timezone-aware);
- removes **duplicate** rows (same service and same minute);
- turns the fake **zeros** into missing values and leaves short gaps visibly empty - no invented values;
- writes the result to `out/metrics_clean.csv`.

**3. 🔍 Review before you accept:** in **Supervised** mode Kiro pauses after every change. **Accept** or **Reject**
each change (or **Accept All** / **Reject All**). **View all changes** shows everything at once; **Revert** undoes it.
Ask yourself:

- Are the UTC timestamps **converted**, not just stripped of their `Z`?
- Which duplicate is kept - and why does it not matter here?
- Are the zeros replaced only in the latency column, not in the error rate (where 0 is a real value)?

**4. ✅ Check:** Kiro marks the task as completed in `tasks.md`. Then run:

```powershell
python -m opspilot data
```

The first line must read:

```text
✅ Task 1 - 1,086 rows in, 993 rows out: 573 UTC timestamps converted, 93 duplicates removed, 5 latency zeros set to missing
```

> [!IMPORTANT]
> 🐢 Start **one task at a time** - never all tasks at once. Every task is a review step, and the review is where you
> learn.

## 📋 Step 3 - Data-Quality Report and Features (5 min)

📜 **Rules:** `requirements.md` → **Requirement 2 - Quality report and features.**

Start **Task 2 - Quality report and features.** Kiro builds `quality.py`, which:

- writes `out/data_quality.md`: rows per export, duplicates removed, missing values per column, time range, time zone
  fixes;
- adds **features** to the clean metrics:
  - 🕐 `hour` and `weekday` - seasonality: Monday 14:00 is always busier than Sunday 04:00;
  - 🚀 `minutes_since_deployment` and `last_deployment_version` - based on `changes.csv`;
  - 📊 `load_level` - requests per minute compared with the same hour last week (low / normal / high).

✅ **Check:**

```powershell
python -m opspilot data
```

The output now contains `✅ Task 2 - features added, report written to out/data_quality.md`. Open the report. Do
the numbers match what you found in Step 1?

## 📈 Step 4 - Detect the Anomaly, the Right Way (5 min)

📜 **Rules:** `requirements.md` → **Requirement 3 - Robust anomaly detection.**

Start **Task 3 - Robust anomaly detection.** It replaces the naive detector with one that:

- runs on the **clean** data;
- compares each minute with the **previous 30 minutes** (rolling z-score, the current minute excluded);
- reports a threshold breach of **|z| > 3** that lasts **at least 2 minutes** as **one event** - not 20 single alarms.

✅ **Check:**

```powershell
python -m opspilot data
```

Expected result:

```text
Anomaly events - payment-api, p95 latency
  🔴 14:05  baseline ≈ 250 ms  →  peak ≈ 2.4 s  (SLO 300 ms)  |  2 min after deployment 2.3.1
1 event found
```

🎯 **One event, at 14:05, two minutes after release 2.3.1 went live.** That is the first real trace of the incident -
a correlation, **not** a proof.

## 👀 Step 5 - Preview the Prompt (2 min)

In Step 7, OpsPilot will send the anomaly and three recent customer tickets to the LLM. Before anything leaves your
machine, look at **what** would be sent:

```powershell
python -m opspilot data --preview-prompt
```

🤔 **Read the preview carefully. What should never leave your machine?**

<details>
<summary>💡 What you should notice</summary>

Customer names, e-mail addresses and an IP address - in the ticket fields **and** inside the free text
("Regards, Anna Schmidt", "my IP is 203.0.113.42").

</details>

## 🔒 Step 6 - Mask Personal Data (5 min)

📜 **Rules:** `requirements.md` → **Requirement 4 - Mask personal data.**

Start **Task 4 - Mask personal data.** Kiro builds `masking.py`, which:

1. **minimises** first: only `ticket_id`, `created_at`, `service`, `subject` and `description` go into the prompt;
2. replaces each customer with a stable **pseudonym** such as `CUST-3f9a1c` - the same customer always gets the
   same pseudonym, so tickets can still be grouped;
3. masks **e-mail addresses** → `<EMAIL>`, **IP addresses** → `<IP>` and **phone numbers** → `<PHONE>` in the free
   text;
4. counts every masked item and adds the counts to `out/data_quality.md`.

✅ **Check:**

```powershell
python -m opspilot data --preview-prompt
```

The preview must not contain a single e-mail address, IP address or phone number. You see placeholders such as
`CUST-1c7e22`, `<EMAIL>`, `<IP>` and `<PHONE>` instead.

## 🤖 Step 7 - Ask Claude for a One-Sentence Summary (5 min)

📜 **Rules:** `requirements.md` → **Requirement 5 - Bedrock summary.**

Start **Task 5 - Bedrock summary.** Kiro builds `llm.py` with `summarise_incident()`. It sends the anomaly event and
the **masked** tickets to Claude on Amazon Bedrock and asks for **one sentence** for the on-call channel.

🔍 **Review the code Kiro proposes.** It should look like this:

```python
import os

from anthropic import AnthropicBedrock

# reads the Bedrock API key from AWS_BEARER_TOKEN_BEDROCK - the key never appears in the code
client = AnthropicBedrock(aws_region=os.environ["AWS_REGION"])

response = client.messages.create(
    model=os.environ["OPSPILOT_MODEL"],   # e.g. us.anthropic.claude-haiku-5-5
    max_tokens=1024,                      # room for the model's thinking plus the short answer
    output_config={"effort": "low"},      # a short, simple task: low effort = fast and cheap
    system=(
        "You are an SRE assistant. Write exactly one sentence for the on-call channel. "
        "State only facts from the data. Do not claim a root cause."
    ),
    messages=[{"role": "user", "content": prompt}],
)

if response.stop_reason == "refusal":
    raise RuntimeError("The model declined the request.")
summary = " ".join(block.text for block in response.content if block.type == "text")
```

> [!NOTE]
> 🌍 `OPSPILOT_MODEL` is an **inference profile ID** with a prefix: `us.anthropic.claude-haiku-5-5` routes the
> requests within US Regions. Without the prefix, Bedrock answers *"on-demand throughput isn't supported"*.

> [!CAUTION]
> 🚫 Reject the change if Kiro's code contains **any** of these:
> - a hard-coded key, region or model ID;
> - `temperature=...` - this model rejects it with an error;
> - `response.content[0].text` - the first block can be the model's *thinking*, not the answer;
> - `AnthropicBedrockMantle` - that endpoint does not offer this model (error 404);
> - unmasked tickets in the prompt.

✅ **Check:**

```powershell
python -m opspilot data --summary
```

Expected result (wording varies):

```text
📣 Since 14:05, payment-api p95 latency has risen from about 250 ms to 2.4 s (SLO 300 ms), two minutes after
   release 2.3.1 went live; customers report hanging checkouts and failed payments.
```

## ⭐ Stretch Goal - SLO Forecast (optional)

📜 **Rules:** `requirements.md` → **Requirement 6 - SLO forecast.**

Done early? Start **Task 6 - SLO forecast.** Estimate when the **error budget** of `payment-api` runs out if the
latency stays at the current level. Use a simple linear projection - no LLM needed.

✅ **Check:**

```powershell
python -m opspilot data --forecast
```

Expected result: `32 of 216 bad minutes left - exhausted at about 17:02`.

## ➡️ Next

**Lab 2 - Ticket Triage** 🎫: the service desk is flooded with 40 tickets. OpsPilot turns them into one prioritised
problem - with prompts you engineer and measure. You continue in the same `labs/opspilot/` folder.
