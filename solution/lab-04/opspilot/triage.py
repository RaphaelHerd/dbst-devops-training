"""Lab 2 - ticket triage with prompts (rules: .kiro/specs/opspilot-triage/requirements.md).

Ready: prompt rendering, the Bedrock calls, retries, routing, evaluation against the Gold set, problem proposal.
Built in this solution: parse_triage() (Task 2), check_reply() (Task 5), triage_structured() (Task 6, stretch goal).
"""
from __future__ import annotations

import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import jsonschema
import pandas as pd

from . import config, loaders
from .config import DATA_DIR, OUT_DIR, ROOT

PROMPTS = ROOT / "prompts" / "triage"
FIELDS = ["category", "priority", "summary", "customer_reply"]


# ---------- Task 2: parse and validate ----------

def parse_triage(raw: str, schema: dict) -> dict:
    """Turn the model's answer into a valid triage dict - or raise ValueError with a clear message.

    The answer may wrap the JSON object in text or in a ```json fence. Validate it against `schema` (jsonschema).
    """
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end < start:
        raise ValueError("the answer contains no JSON object")
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as error:
        raise ValueError(f"the JSON is broken: {error.msg}") from None
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    if errors:                                          # all errors at once - one retry can fix every field
        raise ValueError("; ".join(error.message for error in errors))
    return data


# ---------- Task 5: tone guard ----------

INTERNAL = re.compile(r"team-\w+|payment-api|checkout-web|booking-search|\brelease\b|\b\d+\.\d+\.\d+\b|"
                      r"CUST-[0-9a-f]{6}|<(?:EMAIL|IP|PHONE)>", re.IGNORECASE)
PROMISE = re.compile(r"guarantee|will be refunded|refund you|within \d+ (?:minutes?|hours?|days?)", re.IGNORECASE)
BLAME = re.compile(r"your fault|you entered|you did something wrong|you made a mistake", re.IGNORECASE)
POLITE = re.compile(r"sorry|apolog|thank", re.IGNORECASE)


def check_reply(reply: str) -> list[str]:
    """Return the tone rules a customer reply breaks - an empty list means the reply is fine."""
    broken = []
    if len(reply.split()) > 60:
        broken.append("longer than 60 words")
    if not POLITE.search(reply):
        broken.append("no thanks or apology")
    if INTERNAL.search(reply):
        broken.append("internal information")
    if PROMISE.search(reply):
        broken.append("promise about time or money")
    if BLAME.search(reply):
        broken.append("blames the customer")
    return broken


# ---------- Task 6 (stretch goal): structured outputs ----------

def triage_structured(client, system: str, ticket: str, schema: dict) -> tuple[dict, dict]:
    """Triage one ticket with structured outputs (output_config format json_schema). Returns (result, usage)."""
    response = client.messages.create(
        model=config.model_id(), max_tokens=1024,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        system=system, messages=[{"role": "user", "content": ticket}])
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined the request.")
    text = "".join(block.text for block in response.content if block.type == "text")
    return json.loads(text), {"in": response.usage.input_tokens, "out": response.usage.output_tokens}


# ---------- ready: catalog, prompt, schema ----------

def load_catalog() -> dict:
    return json.loads((DATA_DIR / "itsm" / "triage_catalog.json").read_text(encoding="utf-8"))


def load_examples() -> list[dict]:
    lines = (DATA_DIR / "gold" / "triage_examples.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def build_schema(catalog: dict) -> dict:
    """JSON schema of one triage answer. Only the catalog's categories and assignable priorities are allowed."""
    return {"type": "object",
            "properties": {
                "category": {"type": "string", "enum": [c["name"] for c in catalog["categories"]]},
                "priority": {"type": "string", "enum": [p["name"] for p in catalog["priorities"] if p["assignable"]]},
                "summary": {"type": "string"},
                "customer_reply": {"type": "string"}},
            "required": FIELDS,
            "additionalProperties": False}


def render_prompt(version: str, catalog: dict, examples: list[dict]) -> str:
    """The system prompt prompts/triage/<version>.md with {{categories}}, {{priorities}} and {{examples}} filled in."""
    path = PROMPTS / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"{path.relative_to(ROOT)} does not exist yet - write it first.")
    categories = "\n".join(f"- {c['name']}: {c['description']}" for c in catalog["categories"])
    priorities = "\n".join(f"- {p['name']}: {p['rule']}" for p in catalog["priorities"])
    shots = "\n\n".join(f"<example>\n<ticket>\nsubject: {e['ticket']['subject']}\n"
                        f"description: {e['ticket']['description']}\n</ticket>\n"
                        f"{json.dumps(e['answer'], ensure_ascii=False)}\n</example>" for e in examples)
    return (path.read_text(encoding="utf-8")
            .replace("{{categories}}", categories)
            .replace("{{priorities}}", priorities)
            .replace("{{examples}}", shots))


def ticket_message(row: pd.Series) -> str:
    return (f"<ticket>\nticket_id: {row['ticket_id']}\ncreated_at: {row['created_at']:%H:%M}\n"
            f"service: {row['service']}\ncustomer: {row['customer']}\nsubject: {row['subject']}\n"
            f"description: {row['description']}\n</ticket>")


def route(category: str, catalog: dict) -> str | None:
    """The team comes from the catalog - never from the LLM."""
    return {c["name"]: c["team"] for c in catalog["categories"]}.get(category)


# ---------- ready: Bedrock calls ----------

def _client():
    from anthropic import AnthropicBedrock             # key: AWS_BEARER_TOKEN_BEDROCK from the environment
    return AnthropicBedrock(aws_region=config.aws_region())


def _ask(client, system: str, messages: list[dict]) -> tuple[str, dict]:
    response = client.messages.create(model=config.model_id(), max_tokens=1024, output_config={"effort": "low"},
                                      system=system, messages=messages)
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined the request.")
    text = "".join(block.text for block in response.content if block.type == "text")
    return text, {"in": response.usage.input_tokens, "out": response.usage.output_tokens}


def _parse(raw: str, schema: dict) -> tuple[dict, bool]:
    """Use parse_triage() once it is built; until then a naive json.loads(). Returns (result, robust)."""
    try:
        return parse_triage(raw, schema), True
    except NotImplementedError:
        return json.loads(raw), False


def triage_one(client, system: str, row: pd.Series, schema: dict, catalog: dict, structured: bool) -> dict:
    record = {"ticket_id": row["ticket_id"], "created_at": f"{row['created_at']:%H:%M}", "retries": 0,
              "needs_human": False, "tokens_in": 0, "tokens_out": 0, "raw": ""}
    try:
        if structured:
            result, usage = triage_structured(client, system, ticket_message(row), schema)
            record.update(tokens_in=usage["in"], tokens_out=usage["out"])
        else:
            messages = [{"role": "user", "content": ticket_message(row)}]
            raw, usage = _ask(client, system, messages)
            record.update(raw=raw, tokens_in=usage["in"], tokens_out=usage["out"])
            try:
                result, robust = _parse(raw, schema)
            except ValueError as error:
                if not _robust_parser():
                    raise
                messages += [{"role": "assistant", "content": raw},
                             {"role": "user", "content": f"Your answer was not valid: {error}. "
                                                         "Answer again with the JSON object only."}]
                raw, usage = _ask(client, system, messages)
                record.update(raw=raw, retries=1, tokens_in=record["tokens_in"] + usage["in"],
                              tokens_out=record["tokens_out"] + usage["out"])
                result, robust = _parse(raw, schema)
        if isinstance(result, dict):
            record.update({k: None if result.get(k) is None else str(result.get(k)) for k in FIELDS})
        record["team"] = route(record.get("category"), catalog)
        hours = {p["name"]: p["sla_hours"] for p in catalog["priorities"]}.get(record.get("priority"))
        record["sla_due"] = f"{row['created_at'] + pd.Timedelta(hours=hours):%a %H:%M}" if hours else None
    except ValueError:
        record["needs_human"] = True
    record["tone"] = _tone(record.get("customer_reply"))
    return record


def _robust_parser() -> bool:
    try:
        parse_triage("{}", {})
    except NotImplementedError:
        return False
    except Exception:
        return True
    return True


def _tone(reply) -> list[str] | None:
    if not isinstance(reply, str):
        return None
    try:
        return check_reply(reply)
    except NotImplementedError:
        return None


# ---------- ready: run, evaluate, propose a problem ----------

def run(version: str, limit: int | None = None, structured: bool = False, workers: int = 4) -> list[dict]:
    from .masking import mask_tickets

    tickets, _ = mask_tickets(loaders.load_tickets())
    tickets = tickets.sort_values("created_at").head(limit) if limit else tickets.sort_values("created_at")
    catalog = load_catalog()
    system = render_prompt(version, catalog, load_examples())
    schema = build_schema(catalog)
    client = _client()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda row: triage_one(client, system, row, schema, catalog, structured),
                             (row for _, row in tickets.iterrows())))


def evaluate(results: list[dict], catalog: dict) -> dict:
    gold = pd.read_csv(DATA_DIR / "gold" / "triage_gold.csv").set_index("ticket_id")
    df = pd.DataFrame(results).set_index("ticket_id")
    n = len(df)
    allowed = {c["name"] for c in catalog["categories"]}
    seen = set(df["category"].dropna()) if "category" in df else set()
    scores = {"tickets": n, "parsed": int((~df["needs_human"]).sum()), "retries": int(df["retries"].sum()),
              "needs_human": int(df["needs_human"].sum()), "categories_seen": len(seen),
              "categories_not_allowed": len(seen - allowed),
              "tokens_in": int(df["tokens_in"].sum()), "tokens_out": int(df["tokens_out"].sum())}
    for field in ("category", "priority", "team"):
        scores[field] = int((df.get(field) == gold.loc[df.index, field]).sum()) if field in df else 0
    checked = [t for t in df["tone"] if t is not None]
    scores["tone_checked"] = len(checked)
    scores["tone_ok"] = sum(1 for t in checked if not t)
    return scores


def propose_problem(results: list[dict], catalog: dict) -> str | None:
    """Group related tickets into one problem (rule in the catalog) - pure Python, no LLM."""
    rule = catalog["problem_rule"]
    df = pd.DataFrame([r for r in results if r.get("team")])
    if df.empty:
        return None
    df["minute"] = pd.to_datetime(df["created_at"], format="%H:%M")
    span = pd.Timedelta(minutes=rule["window_minutes"])
    sla = {p["name"]: p["sla_hours"] for p in catalog["priorities"]}[rule["priority"]]
    for team, group in df.groupby("team"):
        group = group.sort_values("minute")
        reached = [t for t in group["minute"] if ((group["minute"] > t - span) & (group["minute"] <= t)).sum()
                   >= rule["min_tickets"]]
        if reached:
            trigger = reached[0]
            categories = " · ".join(f"{k} {v}" for k, v in group["category"].value_counts().items())
            return (f"📌 Problem proposal: {len(group)} related tickets from {group['created_at'].iloc[0]} to "
                    f"{group['created_at'].iloc[-1]} → {team} · {rule['priority']} since {trigger:%H:%M} "
                    f"(rule: ≥ {rule['min_tickets']} tickets for one team within {rule['window_minutes']} min) · "
                    f"SLA due {trigger + pd.Timedelta(hours=sla):%H:%M}\n   {categories}")
    return None


def save(version: str, results: list[dict], scores: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / f"triage_{version}.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    history = OUT_DIR / "triage_eval.csv"
    new = not history.exists()
    with history.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "prompt", *scores])
        w.writerow([datetime.now().strftime("%H:%M:%S"), version, *scores.values()])


def pct(part: int, whole: int) -> str:
    return f"{part:>3}/{whole}  ({round(100 * part / whole) if whole else 0:>3} %)"


def report(version: str, scores: dict, robust: bool, seconds: float) -> None:
    n = scores["tickets"]
    print(f"Triage - prompt {version} · {n} tickets · parser: {'robust' if robust else 'naive'} · {seconds:.0f} s")
    print(f"  parsed     {pct(scores['parsed'], n)}   retries {scores['retries']}   needs human {scores['needs_human']}")
    print(f"  category   {pct(scores['category'], n)}   values seen: {scores['categories_seen']} "
          f"({scores['categories_not_allowed']} not allowed)")
    print(f"  priority   {pct(scores['priority'], n)}")
    print(f"  team       {pct(scores['team'], n)}")
    if scores["tone_checked"]:
        print(f"  tone       {pct(scores['tone_ok'], scores['tone_checked'])} replies without a rule break")
    else:
        print("  tone       not checked yet (Task 5)")
    print(f"  tokens     {scores['tokens_in']:,} in · {scores['tokens_out']:,} out")
    print(f"Results: out/triage_{version}.jsonl · history: out/triage_eval.csv")


def compare() -> None:
    history = OUT_DIR / "triage_eval.csv"
    if not history.exists():
        print("No runs yet.")
        return
    df = pd.read_csv(history).drop_duplicates("prompt", keep="last")
    print(f"{'prompt':<15}{'parsed':>8}{'retries':>9}{'human':>7}{'category':>10}{'priority':>10}{'team':>7}{'tone ok':>9}")
    for _, r in df.iterrows():
        n = r["tickets"]
        tone = f"{r['tone_ok']}/{r['tone_checked']}" if r["tone_checked"] else "-"
        print(f"{r['prompt']:<15}{r['parsed'] / n:>8.0%}{r['retries']:>9}{r['needs_human']:>7}{r['category'] / n:>10.0%}"
              f"{r['priority'] / n:>10.0%}{r['team'] / n:>7.0%}{tone:>9}")
