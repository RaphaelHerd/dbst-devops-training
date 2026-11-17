# Payment provider degraded

> service: payment-api · owner: team-payments · updated: 2026-07-08 · status: current

## Provider status
- Check the status page and the incident feed of the payment provider.
- HTTP 502 or 503 answers from the provider point to an outage on their side (INC-3880).

## Switch to the backup provider
- team-payments can move traffic to the backup provider with the feature flag "payments.backup_provider".
- Switch only after approval by the incident commander.
