"""Lab 4 - knowledge and search by meaning (rules: .kiro/specs/opspilot-knowledge/requirements.md).

Ready: keyword search, Bedrock embeddings with a cache, the in-memory index, search_runbooks(), similar_incidents(),
search_logs(), article suggestions, the hit-rate check, alert templates and the answer call.
To build: chunk_runbook() (Task 1), top_k() (Task 2), cluster() (Task 4). Task 3 is the prompt prompts/ask/answer.md.
"""
from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from . import config, loaders
from .config import DATA_DIR, OUT_DIR, ROOT

RUNBOOKS = DATA_DIR / "agora" / "runbooks"
PROMPT = ROOT / "prompts" / "ask" / "answer.md"
CACHE = OUT_DIR / "embeddings.json"
STOP_WORDS = {"a", "an", "the", "is", "are", "was", "be", "it", "my", "our", "i", "we", "do", "does", "what", "why",
              "how", "who", "when", "where", "which", "to", "of", "in", "on", "at", "for", "and", "or", "if", "not"}


# ---------- Task 1: chunk a runbook ----------

def chunk_runbook(text: str, source: str) -> list[dict]:
    """One chunk per '## ' section with its metadata - and no chunk at all for an archived runbook."""
    raise NotImplementedError("Task 1 - see .kiro/specs/opspilot-knowledge/requirements.md, Requirement 1")


# ---------- Task 2: the nearest vectors ----------

def top_k(query: np.ndarray, matrix: np.ndarray, k: int = 3) -> list[tuple[int, float]]:
    """The k rows of `matrix` most similar to `query` (cosine similarity), best first: [(row, similarity), ...]."""
    raise NotImplementedError("Task 2 - see .kiro/specs/opspilot-knowledge/requirements.md, Requirement 2")


# ---------- Task 4: group by meaning ----------

def cluster(vectors: np.ndarray, threshold: float) -> list[int]:
    """A group number for every vector: it joins the first group whose first member is similar enough."""
    raise NotImplementedError("Task 4 - see .kiro/specs/opspilot-knowledge/requirements.md, Requirement 4")


# ---------- ready: embeddings with a cache ----------

def embed(texts: list[str]) -> np.ndarray:
    """One vector per text from the Bedrock embedding model. Known texts come from out/embeddings.json."""
    model = config.embed_model_id()
    keys = [hashlib.sha256(f"{model}\n{t}".encode("utf-8")).hexdigest()[:24] for t in texts]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    missing = {k: t for k, t in zip(keys, texts) if k not in cache}
    if missing:
        import boto3                                    # key: AWS_BEARER_TOKEN_BEDROCK from the environment
        client = boto3.client("bedrock-runtime", region_name=config.aws_region())

        def one(text: str) -> list[float]:
            body = json.dumps({"inputText": text, "dimensions": 512, "normalize": True})
            response = client.invoke_model(modelId=model, body=body, contentType="application/json",
                                           accept="application/json")
            return json.loads(response["body"].read())["embedding"]

        with ThreadPoolExecutor(max_workers=4) as pool:
            vectors = list(pool.map(one, missing.values()))
        cache.update({k: [round(x, 6) for x in v] for k, v in zip(missing, vectors)})
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache), encoding="utf-8")
        print(f"🧮 {len(missing)} new text{'s' if len(missing) != 1 else ''} embedded with {model} - "
              f"cached in out/embeddings.json")
    return np.array([cache[k] for k in keys], dtype=float)


# ---------- ready: the knowledge (runbooks and past incidents) ----------

def load_chunks() -> tuple[list[dict], int, int]:
    """All chunks of all runbooks (Task 1). Returns (chunks, number of runbooks, number skipped)."""
    files = sorted(RUNBOOKS.glob("*.md"))
    chunks, skipped = [], 0
    for path in files:
        part = chunk_runbook(path.read_text(encoding="utf-8"), path.name)
        skipped += not part
        chunks += part
    return chunks, len(files), skipped


def load_incidents() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "itsm" / "incidents.csv", dtype=str)


def incident_entries(incidents: pd.DataFrame) -> list[dict]:
    """Past incidents as knowledge entries - same fields as a runbook chunk."""
    return [{"id": r.incident_id, "source": "itsm/incidents.csv", "title": r.title, "section": r.incident_id,
             "service": r.service, "updated": r.opened_at[:10],
             "text": f"{r.incident_id}: {r.title}\n{r.description}\nRoot cause: {r.root_cause}\n"
                     f"Resolution: {r.resolution}"} for r in incidents.itertuples()]


def knowledge() -> tuple[list[dict], np.ndarray]:
    """The in-memory index: runbook chunks plus past incidents, and one vector per entry."""
    entries = load_chunks()[0] + incident_entries(load_incidents())
    return entries, embed([e["text"] for e in entries])


def search(query: str, entries: list[dict], matrix: np.ndarray, k: int = 3) -> list[tuple[dict, float]]:
    return [(entries[i], score) for i, score in top_k(embed([query])[0], matrix, k)]


def search_runbooks(query: str, k: int = 3) -> list[tuple[dict, float]]:
    """The k runbook sections closest in meaning to the query."""
    chunks = load_chunks()[0]
    return search(query, chunks, embed([c["text"] for c in chunks]), k)


def similar_incidents(text: str, k: int = 3) -> list[tuple[dict, float]]:
    """The k past incidents closest in meaning to a problem description."""
    entries = incident_entries(load_incidents())
    return search(text, entries, embed([e["text"] for e in entries]), k)


# ---------- ready: logs and alerts as templates ----------

def template(message: str) -> str:
    """The message without its variable parts: bookings, charges and numbers become placeholders."""
    message = re.sub(r"\bB-\d+", "<BOOKING>", message)
    message = re.sub(r"\bch_[0-9a-f]+", "<CHARGE>", message)
    return re.sub(r"\b\d+(?:\.\d+)?\b", "<N>", message)


def load_logs() -> pd.DataFrame:
    lines = (DATA_DIR / "logs" / "payment-api.jsonl").read_text(encoding="utf-8").splitlines()
    df = pd.DataFrame([json.loads(line) for line in lines if line.strip()])
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(config.TIMEZONE)
    return df


def log_templates(logs: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct message: level, template, count, first and last time, versions."""
    df = logs.assign(template=logs["message"].map(template))
    return (df.groupby(["level", "template"])
              .agg(count=("ts", "size"), first=("ts", "min"), last=("ts", "max"),
                   versions=("version", lambda v: ", ".join(sorted(set(v)))))
              .reset_index().sort_values("count", ascending=False, ignore_index=True))


def search_logs(query: str, k: int = 3, until: pd.Timestamp | None = None) -> list[tuple[dict, float]]:
    """The k log message templates closest in meaning to the query - 8 templates instead of 1,980 lines.
    With `until`, only log lines up to that time count (Lab 5: the agent knows nothing about the future)."""
    logs = load_logs()
    templates = log_templates(logs if until is None else logs[logs["ts"] <= until])
    rows = templates.to_dict("records")
    return search(query, rows, embed(list(templates["template"])), k)


def load_alerts() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "grafana" / "alerts.csv", dtype=str)
    df["fired_at"] = pd.to_datetime(df["fired_at"], utc=True).dt.tz_convert(config.TIMEZONE)
    return df


# ---------- ready: the answer with sources ----------

def answer(question: str, k: int = 3) -> tuple[str, list[tuple[dict, float]]]:
    """Retrieve the k closest entries, put them into the prompt as numbered sources, let Claude answer."""
    if not PROMPT.exists():
        raise FileNotFoundError(f"{PROMPT.relative_to(ROOT).as_posix()} does not exist yet - write it first.")
    entries, matrix = knowledge()
    hits = search(question, entries, matrix, k)
    sources = "\n".join(f'<source id="{n}" ref="{e["id"]}" updated="{e["updated"]}">\n{e["text"]}\n</source>'
                        for n, (e, _) in enumerate(hits, 1))
    from anthropic import AnthropicBedrock             # key: AWS_BEARER_TOKEN_BEDROCK from the environment
    response = AnthropicBedrock(aws_region=config.aws_region()).messages.create(
        model=config.model_id(), max_tokens=1024, output_config={"effort": "low"},
        system=PROMPT.read_text(encoding="utf-8"),
        messages=[{"role": "user", "content": f"<context>\n{sources}\n</context>\n\n<question>\n{question}\n"
                                              f"</question>"}])
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined the request.")
    return "".join(b.text for b in response.content if b.type == "text").strip(), hits


# ---------- ready: printing for the command line ----------

def _where(e: dict) -> str:
    return f"{e['service']} · {e['updated']}"


def print_keyword(question: str) -> None:
    words = [w for w in re.findall(r"[a-z0-9-]+", question.lower()) if w not in STOP_WORDS]
    files = sorted(RUNBOOKS.glob("*.md"))
    hits = [p.name for p in files
            if set(words) <= set(re.findall(r"[a-z0-9-]+", p.read_text(encoding="utf-8").lower()))]
    print(f"Agora keyword search for: {', '.join(words)}\n{len(hits)} of {len(files)} runbooks contain all words")
    for name in hits:
        print(f"   📄 {name}")


def print_chunks() -> None:
    chunks, files, skipped = load_chunks()
    for c in chunks:
        print(f"   🧩 {c['id']:<45} {_where(c)} · {len(c['text'].split())} words")
    print(f"✅ Task 1 - {files} runbooks · {skipped} archived, skipped · {len(chunks)} chunks")


def print_search(question: str) -> None:
    entries, matrix = knowledge()
    print(f'🔎 "{question}" - top 3 of {len(entries)} entries by meaning')
    for n, (e, score) in enumerate(search(question, entries, matrix), 1):
        print(f"   {n}. {score:.2f}  {e['id']:<45} {_where(e)}")


def print_eval() -> None:
    questions = pd.read_csv(DATA_DIR / "gold" / "ask_questions.csv")
    entries, matrix = knowledge()
    vectors = embed(list(questions["question"]))
    hits = 0
    for q, vector in zip(questions.itertuples(), vectors):
        found = [entries[i]["id"] for i, _ in top_k(vector, matrix, 3)]
        hits += q.expected in found
        print(f"   {'✅' if q.expected in found else '❌'} {q.question:<48} → {found[0]}")
    print(f"Hit rate: {hits} of {len(questions)} questions find the expected section in the top 3")


def print_answer(question: str) -> None:
    text, hits = answer(question)
    print(f"💬 {text}\n\nSources:")
    for n, (e, score) in enumerate(hits, 1):
        print(f"   [{n}] {e['id']}  ({_where(e)} · similarity {score:.2f})")


def print_incidents(text: str) -> None:
    print(f'🔎 past incidents like "{text}"')
    for e, score in similar_incidents(text):
        lines = e["text"].splitlines()
        print(f"   {score:.2f}  {lines[0]} · {_where(e)}\n         {lines[2]}\n         {lines[3]}")


def print_logs(query: str) -> None:
    logs = load_logs()
    print(f'🔎 log messages like "{query}" - {len(logs):,} lines, {len(log_templates(logs))} distinct messages')
    for t, score in search_logs(query):
        print(f"   {score:.2f}  {t['level']:<5} {t['template']}\n"
              f"         {t['count']} lines · {t['first']:%H:%M}-{t['last']:%H:%M} · version {t['versions']}")


def print_articles(ticket_id: str) -> None:
    from .masking import mask_tickets
    try:
        tickets, _ = mask_tickets(loaders.load_tickets())
    except NotImplementedError:
        print("🛑 Lab 1 Task 4 (masking) must be built first - no ticket text leaves your machine unmasked.")
        return
    row = tickets[tickets["ticket_id"] == ticket_id]
    if row.empty:
        print(f"🛑 Ticket {ticket_id} not found in data/itsm/tickets.csv.")
        return
    subject, description = row.iloc[0]["subject"], row.iloc[0]["description"]
    print(f'📚 knowledge articles for {ticket_id} "{subject}"')
    for c, score in search_runbooks(f"{subject}\n{description}"):
        print(f"   {score:.2f}  {c['id']:<45} {_where(c)}")


def print_alert_groups(threshold: float) -> None:
    alerts = load_alerts()
    alerts["template"] = alerts["summary"].map(template)
    distinct = (alerts.groupby("template")
                      .agg(count=("alert_id", "size"), first=("fired_at", "min"), last=("fired_at", "max"),
                           severity=("severity", lambda s: "critical" if "critical" in set(s) else s.iloc[0]))
                      .reset_index().sort_values("first", ignore_index=True))
    distinct["group"] = cluster(embed(list(distinct["template"])), threshold)
    print(f"Alert groups - {len(alerts)} alerts · {len(distinct)} distinct alert texts · threshold {threshold}")
    for _, part in distinct.groupby("group", sort=False):
        icon = "🔴" if "critical" in set(part["severity"]) else "🟡"
        n = part["count"].sum()
        print(f"{icon} group {part['group'].iloc[0] + 1} · {n} alert{'s' if n != 1 else ''} · "
              f"{part['first'].min():%H:%M}-{part['last'].max():%H:%M}")
        for t in part.itertuples():
            print(f"     {t.count:>3} × {t.template}")
