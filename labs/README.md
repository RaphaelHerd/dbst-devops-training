# 🧭 OpsPilot - The Story Behind the Labs

> [!NOTE]
> 🎭 Everything in these labs is **fictional**. You work only with mock data exports - no real systems, no real
> customer data.

## 🏢 The Setting

You are part of the **platform operations team** of a fictional **online booking platform**. Customers search for
trips, book them and pay online. Many services run behind the checkout. The one in focus is **`payment-api`**, which
handles every single payment.

Your team works with these tools:

| | Tool | What it holds |
|:-:|---|---|
| 🎫 | **ITSM** | Tickets, incidents and changes |
| 📈 | **Grafana** | Metrics: latency, error rate, load |
| 📜 | **Log platform** | Application logs |
| 🔧 | **CI/CD** | Pipeline runs and code changes |
| 📚 | **Agora** | Knowledge base with runbooks |

📁 In this workshop you work with **exports** of these tools only. They are part of your OpsPilot project, in the
folder `labs/opspilot/data/`.

## 🚨 Monday Afternoon: The Incident

| Time | | What happens |
|---|:-:|---|
| **14:00** | 🟢 | Rollout of release **2.3.1** of `payment-api` starts |
| **14:03** | 🟢 | Release 2.3.1 is live on all instances |
| **14:05** | 🔴 | The p95 latency jumps from about 250 ms to **2.4 s** (SLO: 300 ms) |
| **14:07** | 🔔 | The latency alert fires |
| **from 14:10** | 📨 | **40 customer tickets** arrive: *"checkout hangs"*, *"payment failed"*, *"charged twice?"* |

> [!IMPORTANT]
> ❓ **Nobody knows the cause yet.** Is it the release? The database? A partner bank? Or just a busy Monday?

## 🎯 Your Mission: Build OpsPilot

You build **OpsPilot**, an AI assistant for operations, in **Python** with **Kiro** and an **LLM on Amazon Bedrock**.

- 📁 Everything lives in **one folder: `labs/opspilot/`** - code, data, Kiro specs and configuration. You open it in
  Lab 1 and extend it lab by lab until the end.
- 🧩 Each lab adds **one command** and solves the **next part** of the incident.
- 🔗 Each lab builds on the result of the previous one.
- 🛟 Stuck? The folder `solution/` next to `labs/` holds the finished project of every lab (`solution/lab-01/`, ...),
  so you can always continue with the next one.

### 🗺️ Roadmap

| Lab | Version | Command | Chapter |
|:-:|:-:|---|---|
| 1 | `v0.1` | `opspilot data` | 🧹 Data Foundation |
| 2 | `v0.2` | `opspilot triage` | 🎫 Ticket Triage |
| 3 | `v0.3` | `opspilot change-review` | 🔍 Change & Pipeline Review |
| 4 | `v0.4` | `opspilot ask` / `opspilot similar` | 📚 Knowledge & Search |
| 5 | `v0.5` | `opspilot investigate` | 🕵️ Investigation Agent |
| 6 | `v0.6` | `opspilot serve` | 🔌 OpsPilot as MCP Server |
| 7 | `v0.7` | `opspilot remediate` | 🛡️ Safe Remediation *(optional)* |
| 8 | `v1.0` | `opspilot eval` | ✅ Harden & Evaluate *(optional)* |
