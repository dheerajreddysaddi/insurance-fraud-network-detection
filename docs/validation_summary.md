# Validation summary

- Validated at (UTC): 2026-10-29T09:57:38+00:00
- Generation seed: 20261022
- **Unexpected failures: 0**
- Benign shared-address groups (informational, never a violation): 40

## Row counts

| Table | Rows |
|---|---:|
| claimants | 2000 |
| detection_runs | 0 |
| incidents | 5000 |
| investigations | 0 |
| providers | 500 |
| quarantine_records | 5 |
| relationship_edges | 8000 |
| investigation_events | 0 |
| policies | 2799 |
| claims | 5000 |
| claim_status_events | 18948 |
| fraud_indicators | 0 |
| invoices | 6938 |
| investigation_indicators | 0 |
| payments | 5379 |

## Checks

Expected = planted anomalies found as intended. Unexpected = a real problem.

| Check | Violations | Expected (planted) | Unexpected |
|---|---:|---:|---:|
| pk:claimants | 0 | 0 | 0 |
| pk:detection_runs | 0 | 0 | 0 |
| pk:incidents | 0 | 0 | 0 |
| pk:investigations | 0 | 0 | 0 |
| pk:providers | 0 | 0 | 0 |
| pk:quarantine_records | 0 | 0 | 0 |
| pk:relationship_edges | 0 | 0 | 0 |
| pk:investigation_events | 0 | 0 | 0 |
| pk:policies | 0 | 0 | 0 |
| pk:claims | 0 | 0 | 0 |
| pk:claim_status_events | 0 | 0 | 0 |
| pk:fraud_indicators | 0 | 0 | 0 |
| pk:invoices | 0 | 0 | 0 |
| pk:investigation_indicators | 0 | 0 | 0 |
| pk:payments | 0 | 0 | 0 |
| fk:policies.claimant_id | 0 | 0 | 0 |
| fk:claims.claimant_id | 0 | 0 | 0 |
| fk:claims.incident_id | 0 | 0 | 0 |
| fk:claims.policy_id | 0 | 0 | 0 |
| fk:claim_status_events.claim_id | 0 | 0 | 0 |
| fk:invoices.provider_id | 0 | 0 | 0 |
| fk:invoices.claim_id | 0 | 0 | 0 |
| fk:payments.claim_id | 0 | 0 | 0 |
| fk:payments.invoice_id | 0 | 0 | 0 |
| edges:unknown_endpoint | 0 | 0 | 0 |
| edges:self_loop | 0 | 0 | 0 |
| enum:policies.policy_type | 0 | 0 | 0 |
| enum:policies.status | 0 | 0 | 0 |
| enum:providers.provider_type | 0 | 0 | 0 |
| enum:providers.status | 0 | 0 | 0 |
| enum:incidents.incident_type | 0 | 0 | 0 |
| enum:claims.status | 0 | 0 | 0 |
| enum:claim_status_events.from_status | 0 | 0 | 0 |
| enum:claim_status_events.to_status | 0 | 0 | 0 |
| enum:payments.payment_method | 0 | 0 | 0 |
| enum:relationship_edges.edge_type | 0 | 0 | 0 |
| enum:relationship_edges.src_type | 0 | 0 | 0 |
| enum:relationship_edges.dst_type | 0 | 0 | 0 |
| date_format:claimants.date_of_birth | 0 | 0 | 0 |
| date_format:claimants.registered_date | 0 | 0 | 0 |
| date_format:providers.registered_date | 0 | 0 | 0 |
| date_format:policies.start_date | 0 | 0 | 0 |
| date_format:policies.end_date | 0 | 0 | 0 |
| date_format:incidents.incident_date | 0 | 0 | 0 |
| date_format:claims.claim_date | 0 | 0 | 0 |
| date_format:claims.decision_date | 0 | 0 | 0 |
| date_format:claim_status_events.event_date | 0 | 0 | 0 |
| date_format:invoices.invoice_date | 0 | 0 | 0 |
| date_format:invoices.service_date | 0 | 0 | 0 |
| date_format:payments.payment_date | 0 | 0 | 0 |
| date_format:relationship_edges.effective_from | 0 | 0 | 0 |
| date_format:quarantine_records.quarantined_date | 0 | 0 | 0 |
| order:policy_end_before_start | 0 | 0 | 0 |
| order:incident_outside_policy_period | 0 | 0 | 0 |
| order:claim_before_incident | 0 | 0 | 0 |
| order:decision_before_claim | 0 | 0 | 0 |
| lifecycle:claim_on_cancelled_policy | 0 | 0 | 0 |
| lifecycle:claimant_differs_from_policy_holder | 0 | 0 | 0 |
| order:invoice_before_service | 0 | 0 | 0 |
| order:service_before_incident | 0 | 0 | 0 |
| order:payment_before_invoice | 0 | 0 | 0 |
| order:payment_before_decision | 0 | 0 | 0 |
| lifecycle:payment_invoice_claim_mismatch | 0 | 0 | 0 |
| lifecycle:claim_transitions | 0 | 0 | 0 |
| lifecycle:claim_status_vs_latest_event | 0 | 0 | 0 |
| finance:invoice_total_vs_claimed | 0 | 0 | 0 |
| finance:payment_exceeds_approved | 6 | 6 | 0 |
| finance:payment_without_approval | 0 | 0 | 0 |
| finance:approved_exceeds_claimed | 0 | 0 | 0 |
| lifecycle:claim_status_vs_payments | 0 | 0 | 0 |
| finance:duplicate_invoice_across_claimants | 8 | 8 | 0 |
| quarantine:policy_actually_exists | 0 | 0 | 0 |
| quarantine:claim_nonexistent_policy | 5 | 5 | 0 |
| edges:attribute_pair_missing | 2 | 2 | 0 |
