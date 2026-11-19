# Design Document - `opspilot ask` and `opspilot similar`

## Overview

```text
data/agora/runbooks/*.md ──► chunk_runbook() ──► 14 chunks ─┐
data/itsm/incidents.csv ───► incident_entries() ─► 12 entries ┴─► embed() ──► matrix 26 × 512 (in memory)
                                                                                    │
question ──► embed() ──► query vector ──► top_k() ──► 3 sources ──► prompts/ask/answer.md ──► Claude ──► answer [1]
                                                                                    
data/logs/payment-api.jsonl ─► template() ─► 8 distinct messages ─► embed() ─► top_k()   (similar --logs)
data/grafana/alerts.csv ─────► template() ─► 8 distinct texts ────► embed() ─► cluster() (similar --alerts)
```

## Components and Interfaces

| Module / file | Function | Status |
|---|---|---|
| `knowledge.py` | `embed(texts)` - Titan Text Embeddings V2, 512 dimensions, cache `out/embeddings.json` | ✅ ready |
| `knowledge.py` | `load_chunks()`, `load_incidents()`, `incident_entries()`, `knowledge()`, `search()` | ✅ ready |
| `knowledge.py` | `search_runbooks()`, `similar_incidents()`, `search_logs()` - reused as agent tools in Lab 5 | ✅ ready |
| `knowledge.py` | `template()`, `load_logs()`, `log_templates()`, `load_alerts()`, `answer()`, printing | ✅ ready |
| `knowledge.py` | `chunk_runbook(text, source) -> list[dict]` | 🛠️ Task 1 |
| `knowledge.py` | `top_k(query, matrix, k) -> list[(row, similarity)]` | 🛠️ Task 2 |
| `prompts/ask/answer.md` | The answer prompt | 🛠️ Task 3 |
| `knowledge.py` | `cluster(vectors, threshold) -> list[int]` | 🛠️ Task 4 |
| `__main__.py` | `ask "<question>" [--keyword] [--search]`, `ask --chunks`, `ask --eval` | ✅ ready |
| `__main__.py` | `similar "<text>" [--logs]`, `similar --ticket <id>`, `similar --alerts [--threshold 0.45]` | ✅ ready |

## Data Models

**Runbook** (`data/agora/runbooks/*.md`, Agora export):

```markdown
# payment-api: High Latency

> service: payment-api · owner: team-payments · updated: 2026-10-02 · status: current

## Symptoms
- ...
```

**Chunk** and **incident entry**: `{"id", "source", "title", "section", "service", "updated", "text"}`. An incident
entry has the incident ID as `id` and `section`.

**Log line** (`payment-api.jsonl`): `ts`, `level`, `service`, `version`, `instance`, `message`, `trace_id`.

**Alert** (`alerts.csv`): `alert_id`, `fired_at`, `rule`, `service`, `severity`, `summary`.

**Test question** (`data/gold/ask_questions.csv`): `question`, `expected` (chunk `id`).

## Approach and Rationale per Requirement

### Requirement 1 - Chunk the runbooks

| Rule | How | Why |
|---|---|---|
| One chunk per section | Split at `## ` headings. | A section answers one question (symptoms, diagnosis, rollback). One vector for a whole runbook mixes everything and is close to every question - and to none. |
| Title in every chunk | `text` starts with `<title> - <section>`. | "Escalation" alone says nothing. With the title, the chunk knows it is about payment-api latency. |
| Metadata | `service`, `updated`, `source`, `section`. | For citing the source, for filtering and for preferring the newer document. |
| Skip archived runbooks | `status: archived` → no chunks. | Two versions of one runbook give contradictory answers. The archived one says "restart all pods at the same time". |
| Text unchanged | No cleaning of the section text. | What goes into the index is exactly what is in Agora - including anything hidden in it. |

### Requirement 2 - Find by meaning

| Rule | How | Why |
|---|---|---|
| Embeddings | Titan Text Embeddings V2 via `bedrock-runtime`, 512 dimensions. | Texts with a similar meaning get vectors that point in a similar direction. |
| Cosine similarity | `matrix @ query / (norm(rows) * norm(query))`. | The angle between two vectors measures meaning - independent of the text length. |
| Vectorised | One matrix-vector product, then `argsort`. | Fast for thousands of rows; a vector database does the same at a larger scale. |
| In memory | A NumPy matrix, vectors cached in `out/embeddings.json`. | 26 entries need no server. The cache saves time and cost on every re-run. |
| Hit rate | 8 test questions with the expected section. | Measure the retrieval before you trust the answers - like the Gold set in Lab 2. |

### Requirement 3 - The answer prompt

| Rule | How | Why |
|---|---|---|
| Sources only | Numbered `<source>` blocks, citations `[1]`. | Every statement can be checked in the runbook. Grounding reduces invented steps. |
| "No answer" allowed | An explicit sentence for missing knowledge. | An LLM that may say "I don't know" invents less. |
| Sources are data | The rule is in the prompt, the sources are inside tags. | Retrieved text comes from many authors. One of the runbooks contains a hidden instruction. |
| Newer wins | The `updated` date is in every source. | Runbooks age. The date lets the model and the reader judge. |

### Requirement 4 - Group alerts by meaning

| Rule | How | Why |
|---|---|---|
| Templates first (ready) | Numbers become `<N>`; identical texts are counted once. | 12 fires of the same rule are one fact. Deduplication in code is exact and free. |
| Leader clustering | Compare with the first member of each group, in order. | Simple, explainable and deterministic - you can follow every decision by hand. |
| Threshold | `--threshold` from -1 to 1, default 0.45. | High: every text alone. Low: everything in one group. The right value is found by looking at the result. |

### Ready: logs, incidents and knowledge articles

- **Log templates:** booking IDs, charge IDs and numbers become placeholders; 1,980 lines become 8 distinct
  messages, each with count, first and last time and versions. Only the 8 templates are embedded.
- **`similar "<text>"`:** the closest past incidents with root cause and resolution.
- **`similar --ticket <id>`:** the closest runbook sections for a **masked** ticket (Lab 1 masking) - knowledge
  articles for the service desk.

## Verification

| Task | Command | Expected result |
|---|---|---|
| 1 | `python -m opspilot ask --chunks` | `6 runbooks · 1 archived, skipped · 14 chunks` |
| 2 | `python -m opspilot ask "checkout is slow" --search` | 3 sources with similarities, the payment-api latency runbook among them |
| 2 | `python -m opspilot ask --eval` | The hit rate of the 8 test questions |
| 3 | `python -m opspilot ask "What do I check first when payments take long?"` | An answer with citations `[1]`, `[2]`, ... and the source list |
| 4 | `python -m opspilot similar --alerts --threshold 1.0` / `--threshold -1` | 8 groups / 1 group |

Embeddings and LLM answers depend on the model, so similarities and wording may differ a little from the README.
