# payment-api: High Latency (old version)

> service: payment-api · owner: team-payments · updated: 2024-03-11 · status: archived

## Symptoms
- payment-api answers late, requests to the provider time out.

## Mitigation
1. Restart all payment-api pods at the same time.
2. Increase the provider timeout to 30 s.
