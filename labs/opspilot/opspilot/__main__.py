"""Command line: python -m opspilot <command>. Ready to use - you do not need to change this file."""
from __future__ import annotations

import argparse
import sys

from . import __version__, config, loaders

SPEC = ".kiro/specs/opspilot-data/requirements.md"


def _fmt_ms(value: float, decimals: int = 1) -> str:
    return f"{value / 1000:.{decimals}f} s" if value >= 1000 else f"{value:.0f} ms"


_REPORTED: set[int] = set()


def _run(task: int, title: str, func, *args):
    """Run one task. Tasks that are not built yet are reported once and skipped."""
    try:
        return func(*args)
    except NotImplementedError:
        if task not in _REPORTED:
            _REPORTED.add(task)
            print(f"⏳ Task {task} - {title}: not built yet. See {SPEC}, Requirement {task}.")
        return None


def cmd_naive(raw) -> None:
    from .anomaly import naive_detect

    hits = naive_detect(raw)
    print("Naive anomaly detection - payment-api, p95 latency")
    for _, row in hits.iterrows():
        print(f"  ⚠️ {row['ts']:%H:%M}   p95 = {_fmt_ms(row['p95_latency_ms'], 2):<8}   z = {row['z']:+.1f}")
    print(f"{len(hits)} anomalies found")


def print_events(events, slo) -> None:
    thresholds = dict(zip(slo["service"], slo["slo_p95_ms"]))
    for service in sorted({e.service for e in events}):
        print(f"Anomaly events - {service}, p95 latency")
        for e in (e for e in events if e.service == service):
            line = (f"  🔴 {e.start:%H:%M}  baseline ≈ {round(e.baseline_ms, -1):.0f} ms  →  "
                    f"peak ≈ {_fmt_ms(e.peak_ms)}  (SLO {thresholds.get(service, '?')} ms)")
            if e.deployment_version and e.minutes_since_deployment is not None:
                line += f"  |  {e.minutes_since_deployment:.0f} min after deployment {e.deployment_version}"
            print(line)
    print(f"{len(events)} event{'s' if len(events) != 1 else ''} found")


def cmd_data(args) -> int:
    from . import anomaly, cleaning, forecast, llm, masking, quality

    raw = loaders.load_metrics_raw()
    if args.naive:
        cmd_naive(raw)
        return 0

    print("OpsPilot data - Lab 1")
    result = _run(1, "Clean the metrics", cleaning.clean_metrics, raw)
    if result is None:
        return 1
    clean, log = result
    print(f"✅ Task 1 - {log['rows_in']:,} rows in, {log['rows_out']:,} rows out: {log['utc_converted']} UTC "
          f"timestamps converted, {log['duplicates_removed']} duplicates removed, "
          f"{log['zero_latency_set_missing']} latency zeros set to missing")

    slo = loaders.load_slo()
    features = _run(2, "Quality report and features", quality.add_features, clean, loaders.load_changes(),
                    loaders.load_load_baseline())
    events = _run(3, "Robust anomaly detection", anomaly.detect_events, features if features is not None else clean)

    tickets = loaders.load_tickets()
    masked = _run(4, "Mask personal data", masking.mask_tickets, tickets)
    masked_tickets, mask_counts = masked if masked is not None else (None, None)

    report = _run(2, "Quality report and features", quality.write_quality_report, raw, clean, log, mask_counts,
                  config.OUT_DIR / "data_quality.md")
    if report is not None and features is not None:
        print("✅ Task 2 - features added, report written to out/data_quality.md")
    if events is not None:
        print_events(events, slo)

    if args.preview_prompt or args.summary:
        if not events:
            print("ℹ️ The prompt needs an anomaly event - finish Task 3 first.")
            return 1
        event = events[0]
        if args.preview_prompt:
            source = masked_tickets if masked_tickets is not None else tickets
            if masked_tickets is None:
                print("⚠️ Masking is not built yet - this preview shows the RAW tickets.")
            print("\n----- prompt preview: nothing has been sent -----")
            print(llm.build_prompt(event, llm.select_recent_tickets(source, event.start)))
            print("----- end of preview -----")
        if args.summary:
            if masked_tickets is None:
                print("🛑 Nothing is sent to the LLM before Task 4 (masking) is built.")
                return 1
            try:
                summary = _run(5, "Bedrock summary", llm.summarise_incident, event,
                               llm.select_recent_tickets(masked_tickets, event.start))
            except Exception as error:                      # missing .env values, expired key, network, ...
                print(f"🛑 The Bedrock call failed - {type(error).__name__}: {error}")
                return 1
            if summary is not None:
                print(f"📣 {summary}")

    if args.forecast:
        result = _run(6, "SLO forecast", forecast.forecast_error_budget, clean, slo)
        if result is not None:
            when = f"{result['exhausted_at']:%H:%M}" if result["exhausted_at"] is not None else "not in sight"
            print(f"⏳ Error budget of {result['service']}: {result['remaining_min']} of {result['budget_total_min']} "
                  f"bad minutes left - exhausted at about {when} if the latency stays at this level.")
    return 0


def cmd_triage(args) -> int:
    import time

    from . import triage

    if args.compare:
        triage.compare()
        return 0
    start = time.time()
    try:
        results = triage.run(args.prompt, args.limit, args.structured)
    except NotImplementedError as error:
        lab1 = "opspilot-data" in str(error)
        print("🛑 Lab 1 Task 4 (masking) must be built first - nothing is sent to the LLM unmasked." if lab1
              else f"⏳ {error}")
        return 1
    except (FileNotFoundError, RuntimeError) as error:
        print(f"🛑 {error}")
        return 1
    label = args.prompt + ("-structured" if args.structured else "")
    catalog = triage.load_catalog()
    scores = triage.evaluate(results, catalog)
    triage.save(label, results, scores)
    for r in results[:args.show]:
        print(f"\n--- {r['ticket_id']} - raw answer ---\n{(r['raw'] or '')[:600]}")
    if args.show:
        print()
    triage.report(label, scores, triage._robust_parser(), time.time() - start)
    problem = triage.propose_problem(results, catalog)
    if problem:
        print(problem)
    return 0


def cmd_change_review(args) -> int:
    from . import review

    try:
        if args.naive:
            review.naive()
            return 0
        return review.review(use_llm=not args.checks)
    except RuntimeError as error:                       # missing .env values, a refusal, ...
        print(f"🛑 {error}")
        return 1


def _knowledge(action, *args) -> int:
    """Run one Lab 4 action and report tasks that are not built yet."""
    try:
        action(*args)
        return 0
    except NotImplementedError as error:
        print(f"⏳ {error}")
    except FileNotFoundError as error:
        print(f"⏳ Task 3 - {error}")
    except Exception as error:                          # missing .env values, expired key, network, ...
        print(f"🛑 {type(error).__name__}: {error}")
    return 1


def cmd_ask(args) -> int:
    from . import knowledge as kb

    if args.chunks:
        return _knowledge(kb.print_chunks)
    if args.eval:
        return _knowledge(kb.print_eval)
    if not args.question:
        print('🛑 Add a question in quotes, e.g. python -m opspilot ask "checkout is slow"')
        return 1
    if args.keyword:
        return _knowledge(kb.print_keyword, args.question)
    return _knowledge(kb.print_search if args.search else kb.print_answer, args.question)


def cmd_similar(args) -> int:
    from . import knowledge as kb

    if args.alerts:
        return _knowledge(kb.print_alert_groups, args.threshold)
    if args.ticket:
        return _knowledge(kb.print_articles, args.ticket)
    if not args.text:
        print('🛑 Describe the problem in quotes, e.g. python -m opspilot similar "payment step hangs"')
        return 1
    return _knowledge(kb.print_logs if args.logs else kb.print_incidents, args.text)


def cmd_investigate(args) -> int:
    import json

    from . import agent

    now = agent.at(args.at)
    if args.tool:                                       # call one tool directly - no LLM
        name, kwargs = args.tool[0], {}
        for pair in args.tool[1:]:
            key, _, value = pair.partition("=")
            kwargs[key] = int(value) if value.isdigit() else value
        if name not in agent.FUNCTIONS:
            print(f"🛑 Unknown tool '{name}'. Tools: {', '.join(agent.FUNCTIONS)}")
            return 1
        try:
            result = agent.FUNCTIONS[name](**kwargs, now=now)
        except NotImplementedError as error:
            print(f"⏳ {error}")
            return 1
        except Exception as error:
            print(f"🛑 {type(error).__name__}: {error}")
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        if name == "recent_changes" and not agent.RECENT_CHANGES_TOOL:
            print("⏳ Task 1 - the function works, but RECENT_CHANGES_TOOL is not defined yet: the agent cannot see it.")
        return 0

    alert, _ = agent.alert_at()
    try:
        if args.no_tools:
            print(f"🚨 {alert}\n\n💭 {agent.guess(alert)}")
            return 0
        system = agent.prompt(args.prompt)
        print(f"🕵️ Investigation · {alert}\n   agent time {now:%H:%M} · prompt {args.prompt} · "
              f"at most {args.max_steps} steps and {args.max_seconds} s")
        agent.STEPS_LOG.unlink(missing_ok=True)
        result = agent.investigate(agent.client(), system, alert, now, args.max_steps, args.max_seconds)
    except NotImplementedError as error:
        print(f"⏳ {error}")
        return 1
    except FileNotFoundError as error:
        print(f"⏳ Task 3 - {error}")
        return 1
    except Exception as error:                          # missing .env values, expired key, network, ...
        print(f"🛑 {type(error).__name__}: {error}")
        return 1
    agent.print_report(result, alert, now, args.prompt)
    return 0


def cmd_serve(args) -> int:
    from . import serve

    if args.kiro_config:
        serve.write_kiro_config()
    elif args.audit:
        serve.print_audit()
    elif args.test:
        return serve.run_test()
    else:
        serve.main()
    return 0


def cmd_remediate(args) -> int:
    from . import remediate

    try:
        if args.status:
            remediate.print_status()
        elif args.reset:
            remediate.reset()
        elif args.stop or args.resume:
            remediate.stop_switch(on=args.stop)
        elif args.postmortem:
            remediate.postmortem()
        else:
            code = remediate.run(args.action, args.naive)
            print()
            remediate.print_status()
            return code
    except FileNotFoundError as error:
        print(f"⏳ Task 4 - {error}")
        return 1
    except Exception as error:                          # missing .env values, expired key, network, ...
        print(f"🛑 {type(error).__name__}: {error}")
        return 1
    return 0


def cmd_eval(args) -> int:
    from . import evaluate

    try:
        if args.cases:
            evaluate.print_cases()
        elif args.compare:
            evaluate.compare()
        elif args.attack:
            evaluate.red_team(args.prompt)
        else:
            evaluate.evaluate(args.prompt)
    except FileNotFoundError as error:
        print(f"⏳ Task 2 - {error}")
        return 1
    except Exception as error:                          # missing .env values, expired key, network, ...
        print(f"🛑 {type(error).__name__}: {error}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config.load_env()
    parser = argparse.ArgumentParser(prog="python -m opspilot",
                                     description=f"OpsPilot {__version__} - an AI assistant for operations")
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    data = commands.add_parser("data", help="Lab 1: clean the ops data, detect anomalies, summarise with Claude")
    data.add_argument("--naive", action="store_true", help="run the naive anomaly detection (Step 1)")
    data.add_argument("--preview-prompt", action="store_true", help="show the prompt without sending it (Step 5)")
    data.add_argument("--summary", action="store_true", help="ask Claude for a one-sentence summary (Step 7)")
    data.add_argument("--forecast", action="store_true", help="SLO error-budget forecast (stretch goal)")
    tri = commands.add_parser("triage", help="Lab 2: triage the tickets with a prompt version, measured on the Gold set")
    tri.add_argument("--prompt", default="v1", help="prompt version: prompts/triage/<version>.md (default v1)")
    tri.add_argument("--limit", type=int, help="triage only the first N tickets (quick try)")
    tri.add_argument("--show", type=int, default=0, help="print the raw answers of the first N tickets")
    tri.add_argument("--structured", action="store_true", help="use structured outputs (stretch goal)")
    tri.add_argument("--compare", action="store_true", help="compare all prompt versions you have run")
    rev = commands.add_parser("change-review", help="Lab 3: review release 2.3.1 - logs, diff, prompt chain, gate")
    rev.add_argument("--naive", action="store_true", help="one prompt with the end of the log (Step 1)")
    rev.add_argument("--checks", action="store_true", help="only the checks in code, no LLM call")
    ask = commands.add_parser("ask", help="Lab 4: answer a question from the runbooks and past incidents, with sources")
    ask.add_argument("question", nargs="?", help="your question, in quotes")
    ask.add_argument("--keyword", action="store_true", help="Agora keyword search instead (Step 1)")
    ask.add_argument("--chunks", action="store_true", help="show the runbook chunks (Step 2)")
    ask.add_argument("--search", action="store_true", help="only the 3 closest sources, no LLM (Step 3)")
    ask.add_argument("--eval", action="store_true", help="hit rate on the test questions (Step 3)")
    sim = commands.add_parser("similar", help="Lab 4: similar incidents, log messages, articles and alert groups")
    sim.add_argument("text", nargs="?", help="the problem or the log message you look for, in quotes")
    sim.add_argument("--logs", action="store_true", help="search the payment-api log messages by meaning")
    sim.add_argument("--ticket", metavar="TICKET_ID", help="suggest knowledge articles for a ticket")
    sim.add_argument("--alerts", action="store_true", help="group the alerts by meaning (Step 6)")
    sim.add_argument("--threshold", type=float, default=0.45,
                     help="similarity a group needs, from -1 to 1 (default 0.45)")
    inv = commands.add_parser("investigate", help="Lab 5: an agent investigates the 14:07 alert with read-only tools")
    inv.add_argument("--prompt", default="v1", help="system prompt: prompts/investigate/<version>.md (default v1)")
    inv.add_argument("--at", default="14:12", metavar="HH:MM", help="the agent's current time (default 14:12)")
    inv.add_argument("--max-steps", type=int, default=8, help="at most this many tool calls (default 8)")
    inv.add_argument("--max-seconds", type=int, default=120, help="at most this many seconds (default 120)")
    inv.add_argument("--no-tools", action="store_true", help="one prompt without tools (Step 1)")
    inv.add_argument("--tool", nargs="+", metavar="ITEM",
                     help="call one tool directly, no LLM: the tool name, then key=value pairs, "
                          "e.g. --tool recent_changes service=payment-api hours=6")
    srv = commands.add_parser("serve", help="Lab 6: OpsPilot's read-only tools as an MCP server (stdio)")
    srv.add_argument("--test", action="store_true", help="start the server like Kiro does and call every tool")
    srv.add_argument("--kiro-config", action="store_true", help="write .kiro/settings/mcp.json for this machine")
    srv.add_argument("--audit", action="store_true", help="show the last calls from out/mcp_audit.jsonl")
    rem = commands.add_parser("remediate", help="Lab 7: propose, check, dry-run, approve and run a mitigation "
                                                "on the simulated platform")
    rem.add_argument("--action", metavar='"TEXT"', help='an action typed by hand, e.g. "rollback payment-api 2.3.0"')
    rem.add_argument("--naive", action="store_true", help="execute the action without any check (Step 1)")
    rem.add_argument("--status", action="store_true", help="show the simulated platform")
    rem.add_argument("--reset", action="store_true", help="reset the platform to 14:20, clear audit and stop switch")
    rem.add_argument("--stop", action="store_true", help="press the red button: OpsPilot executes nothing")
    rem.add_argument("--resume", action="store_true", help="turn the stop switch off")
    rem.add_argument("--postmortem", action="store_true", help="draft the post-mortem (stretch goal)")
    ev = commands.add_parser("eval", help="Lab 8: evaluate the cause-code proposal on the Gold set, attack OpsPilot")
    ev.add_argument("--prompt", default="v1", help="prompt version: prompts/eval/<version>.md (default v1)")
    ev.add_argument("--cases", action="store_true", help="show the Gold set per service, type and cause code")
    ev.add_argument("--compare", action="store_true", help="compare all prompt versions you have evaluated")
    ev.add_argument("--attack", action="store_true", help="run the red-team attacks against the prompt version")
    args = parser.parse_args(argv)
    if args.command == "data":
        return cmd_data(args)
    if args.command == "triage":
        return cmd_triage(args)
    if args.command == "change-review":
        return cmd_change_review(args)
    if args.command == "ask":
        return cmd_ask(args)
    if args.command == "similar":
        return cmd_similar(args)
    if args.command == "investigate":
        return cmd_investigate(args)
    if args.command == "serve":
        return cmd_serve(args)
    if args.command == "remediate":
        return cmd_remediate(args)
    if args.command == "eval":
        return cmd_eval(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
