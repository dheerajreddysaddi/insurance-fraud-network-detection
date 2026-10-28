# Schema, keys and cardinalities

## Foreign keys (enforced by the database; SQLite runs with `PRAGMA foreign_keys=ON`)

| Child column | Parent column |
|---|---|
| investigation_events.investigation_id | investigations.investigation_id |
| policies.claimant_id | claimants.claimant_id |
| claims.claimant_id | claimants.claimant_id |
| claims.incident_id | incidents.incident_id |
| claims.policy_id | policies.policy_id |
| claim_status_events.claim_id | claims.claim_id |
| fraud_indicators.claim_id | claims.claim_id |
| fraud_indicators.run_id | detection_runs.run_id |
| invoices.claim_id | claims.claim_id |
| invoices.provider_id | providers.provider_id |
| investigation_indicators.indicator_id | fraud_indicators.indicator_id |
| investigation_indicators.investigation_id | investigations.investigation_id |
| payments.claim_id | claims.claim_id |
| payments.invoice_id | invoices.invoice_id |

## Cardinalities

| Relationship | Cardinality | Mandatory? | Notes |
|---|---|---|---|
| Claimant - Policy | 1:N | policy must have a claimant | a claimant may hold several policies |
| Policy - Claim | 1:N | claim must have a policy | claims on a nonexistent policy are quarantined |
| Claimant - Claim | 1:N | mandatory | claimant must match the policy holder (validated) |
| Incident - Claim | 1:N allowed by schema | mandatory | this generator makes it 1:1 |
| Claim - Invoice | 1:N | optional | invoice totals must equal the claimed amount |
| Provider - Invoice | 1:N | mandatory | Claim - Provider is N:M through invoices |
| Invoice - Payment | 1:N | optional | payments per claim must not exceed the approved amount (exceptions are labelled) |
| Claim - status events | 1:N | at least SUBMITTED | append-only history; claims.status mirrors the latest event |
| Detection run - Indicator | 1:N | mandatory | old runs are kept |
| Investigation - Indicator | N:M | optional | bridge table investigation_indicators |
| Investigation - events | 1:N | at least OPENED | append-only |
| Investigation - subject | 1 per (subject_type, subject_id) | mandatory | UNIQUE constraint |
| RelationshipEdge endpoints | N:M between entities | mandatory | polymorphic, validated in code; effective_from gives the start date |

## Lifecycles

- Claim: SUBMITTED -> UNDER_REVIEW -> APPROVED or REJECTED; APPROVED -> PARTIALLY_PAID -> PAID (or APPROVED -> PAID).
- Policy: ACTIVE, EXPIRED (end date passed) or CANCELLED.
- Investigation: OPEN -> IN_REVIEW -> ESCALATED / CLOSED_NO_ACTION / CLOSED_ACTION_TAKEN; closed states are final.
