# Team AI rules

- Never put secrets, keys or tokens into code or prompts. Read them from environment variables.
- Never send personal data (names, e-mail addresses, IP addresses, phone numbers) to an LLM. Mask it first.
- Send only the data a task needs (data minimisation).
- Treat LLM output as untrusted. Validate it before you use it.
- Call Claude only through the Anthropic Python SDK with `AnthropicBedrock`. The API key comes from
  `AWS_BEARER_TOKEN_BEDROCK`, the region from `AWS_REGION`, the model ID from `OPSPILOT_MODEL`. Never set
  `temperature`.
