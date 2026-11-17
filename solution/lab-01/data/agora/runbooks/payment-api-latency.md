# payment-api: High Latency

> service: payment-api · owner: team-payments · updated: 2026-10-02 · status: current

## Symptoms
- The p95 latency of payment-api is above the SLO of 300 ms (alert PaymentApiLatencyHigh).
- Customers say the last step of their booking hangs or takes very long: the payment page keeps spinning.
- Customer tickets mention hanging payments, failed payments or money taken without a booking confirmation.

## Diagnosis
1. Open the Grafana dashboard "payment-api overview": check p95 latency, error rate and requests per minute.
2. Compare the start of the latency increase with the last deployment in the change calendar. A jump within minutes
   after a release points to the release.
3. Search the payment-api logs for provider timeouts and retries.
4. Check the payment provider status page. If the provider reports a problem, follow the runbook
   "Payment provider degraded".

## Mitigation: rollback
1. If the latency started within 30 minutes after a release, roll back to the previous version first - investigate
   later.
2. Start the pipeline job "rollback" for payment-api with the previous version. A canary instance goes first.
3. Watch the p95 latency for 10 minutes. It must fall below 300 ms.
4. Record the rollback in the change ticket.

## Escalation
- If the rollback does not help within 15 minutes, page the on-call engineer of team-payments.
- If customers were charged more than once, inform the service desk lead and the finance team for refunds.
