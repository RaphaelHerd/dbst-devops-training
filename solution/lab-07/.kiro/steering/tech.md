# Tech Stack

- **Python 3.10 or newer.** OpsPilot is a package, run with `python -m opspilot <command>`.
- **pandas and numpy** for all data work; **jsonschema** to validate LLM answers.
- **Claude on Amazon Bedrock** through the Anthropic Python SDK: `AnthropicBedrock` from `anthropic[bedrock]`
  (`bedrock-runtime` endpoint). The SDK reads the API key from `AWS_BEARER_TOKEN_BEDROCK`. `OPSPILOT_MODEL` is an
  inference profile ID, e.g. `us.anthropic.claude-haiku-5-5`. Do not use `AnthropicBedrockMantle`.
- **boto3** for the Bedrock embeddings (Amazon Titan Text Embeddings V2, `bedrock-runtime`). Vectors are kept in a
  NumPy matrix in memory and cached in `out/embeddings.json` - no vector database.
- **MCP** with the Python SDK 2.x (`mcp[cli]`): `from mcp.server import MCPServer` (formerly FastMCP), stdio
  transport. On stdio, stdout belongs to the protocol - tools never print to it.
- **Configuration** comes from `.env`, read by `opspilot/config.py`: `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION`,
  `OPSPILOT_MODEL`.
- **No web frameworks, no databases, no other cloud services.** All ops data are CSV exports in `data/`. The
  deployment platform of Lab 7 is simulated in `out/platform_state.json`.

## Conventions

- Keep the code base small: no extra files, layers or helpers that a task does not need.
- Type hints and a short docstring on every public function.
- Pure functions where possible: a table goes in, a **new** table comes out. Never change an input table in place.
- Timestamps are always timezone-aware **Europe/Berlin**.
- Read only from `data/`; write only to `out/`.
- A task that is not built yet raises `NotImplementedError`.

## Commands

| Purpose | Command |
|---|---|
| Install | `pip install -r requirements.txt` |
| Run | `python -m opspilot <command>` - `data`, `triage`, `change-review`, `ask`, `similar`, `investigate`, `serve`, `remediate`, `eval` |
| Check a task | Compare the output with the expected result in the README and in `design.md` (Verification) |
