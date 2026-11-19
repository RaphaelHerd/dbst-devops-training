# Project Structure

```text
opspilot/                       project root - everything for the whole workshop lives here
├── .kiro/
│   ├── steering/               tech.md · structure.md · ai-rules.md
│   └── specs/                  one spec per lab (requirements.md, design.md, tasks.md)
├── data/                       mock exports - READ ONLY
│   ├── grafana/                metric exports, load baseline, SLO budget, alerts
│   ├── itsm/                   tickets, changes, incidents, triage catalog, cause codes
│   ├── cicd/                   pipeline runs and logs, release diff, security advisories, platform, releases
│   ├── logs/                   application logs (JSON lines)
│   ├── agora/runbooks/         runbooks from the knowledge base (Markdown)
│   └── gold/                   Gold labels, examples and test questions for measuring the LLM
├── prompts/                    one folder per command, one file per prompt version (e.g. triage/v2.md)
├── opspilot/                   the Python package
│   ├── __main__.py             command line (one sub-command per lab)
│   ├── config.py               paths, time zone, .env
│   ├── loaders.py              read the exports
│   └── <one module per topic>  cleaning, quality, anomaly, masking, llm, forecast, triage, review, knowledge, agent,
│                               serve, remediate, evaluate
├── opspilot_server.py          the MCP server file a host (Kiro) starts - Lab 6
├── out/                        everything OpsPilot writes (git-ignored)
├── .env                        secrets from the trainer (git-ignored)
└── requirements.txt
```

## Rules

- New features go into a module of `opspilot/` that is named after its topic.
- Each lab gets its own spec in `.kiro/specs/opspilot-<topic>/`, e.g. `opspilot-triage`, `opspilot-knowledge`.
- Prompts live in `prompts/`, not in the Python code. A new prompt version is a new file, so versions can be compared.
- Never write into `data/`. Results and reports go to `out/`.
