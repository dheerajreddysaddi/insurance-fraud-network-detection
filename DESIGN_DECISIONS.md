# Design decisions

## Architecture and stack
One Streamlit app, one database, no separate backend. Python 3.11 + pandas + NetworkX for analysis; SQLAlchemy Core so the same
code runs on SQLite (local, zero setup, foreign keys on) and PostgreSQL (hosted, so investigation history survives restarts).
Core rather than ORM keeps the SQL visible and easy to explain. Plotly draws the network from a NetworkX layout.
Alternatives not chosen: microservices, Docker as a requirement, scikit-learn or a graph neural network (see below).

## Components
| Module | Purpose |
|---|---|
| `data_generator.py` | Deterministic data, planted networks, injected exceptions, separate ground truth |
| `database.py` | Schema, constraints, engine, safe loading (never overwrites silently) |
| `validators.py` | Keys, FKs, enums, dates, lifecycles, reconciliation; expected vs unexpected exceptions |
| `fraud_detection.py` | Explainable indicators from `config/detection_rules.yaml` |
| `network_analysis.py` | Claim scores, relationship graph, network ranking and explanations |
| `investigations.py` | Lifecycle, append-only events, transactional changes |
| `evaluation.py` | Metrics against the answer key (used only after detection) |
| `app.py`, `views/` | Six screens; every number comes from persisted records |

## Data-model decisions
- Money is integer cents so reconciliation is exact. Dates are ISO text for identical behaviour on both databases.
- Claimant IDs use the specified `CLM-2026-` prefix; claims use `CLAIM-2026-` to avoid the ambiguity in the brief.
- Incident-to-claim is allowed to be 1:N by the schema but the generator makes it 1:1.
- Claim status is derived from status events; investigation status is a cached copy of the latest event. Event tables are
  insert-only. Foreign-key violations go to `quarantine_records`; foreign keys are never switched off.
- Edges are polymorphic, so they cannot be foreign keys; `validators` checks every endpoint.
- Full cardinalities and fields: `docs/schema.md`, `docs/data_dictionary.md`.

## Detection rules and thresholds
See the table in the README; all numbers live in `config/detection_rules.yaml`. Narrative similarity is Jaccard overlap of
normalized word sets (>= 0.85), computed only within the same incident type for speed. Exceptions (overpayment, quarantined
claim, unrecorded edge) are reported but not added to fraud-risk scores, because they are integrity or financial problems.

## Network construction and ranking
Nodes are claimants and providers. Claimant-claimant links come from shared phone/email at different addresses, duplicate
invoices and similar narratives. A claimant-provider link exists only if that claim already carries an indicator scoring >= 10.
Each link records its status: OBSERVED (in `relationship_edges`), INFERRED (derived by the detector) or
MISSING_FROM_EDGE_TABLE. Connected components with at least two claimants are scored as the sum of their indicators plus 10
per extra distinct indicator type; flagged at >= 80 with >= 2 types; HIGH priority at >= 150. A component is never assumed to
be fraud.

## False-positive control
Households sharing an address score 0 and create no link. Shared phone/email counts only across different addresses.
UNUSUAL_TIMING needs two signals. Repeat claimant-provider is a weak 5. Narrative matches only count across different
claimants. Networks need two distinct indicator types. These controls work at rule level (rules-only FPR 0.006), but the
network step still flags many ordinary claims (rules + network FPR 0.045; 0.064 on seed 777).
### False-positive findings

The evaluation results show that network-based detection can identify all planted suspicious networks, but it can also connect unrelated claimants into larger networks. With the default seed, 6 of 12 flagged networks were false positives. With seed 777, 7 of 13 flagged networks were false positives, including a large false-positive network containing 26 claimants.

These results suggest that weak indicators can combine through shared providers or other connections, causing unrelated claimants to be grouped together. The current aggregate metrics do not establish exactly which providers and signals caused each false-positive network, so those specific causes require further inspection in the Evaluation page.

Potential improvements include limiting the influence of high-volume providers, applying community detection, and evaluating suspicious connections at the claim level rather than relying only on network-level scores. These improvements are candidates for future work, not implemented features.

**Trade-off:** The current approach prioritizes recovering all planted suspicious networks, but this comes at the cost of additional false positives. Therefore, a high score should trigger investigation and must not be treated as proof of fraud.

## Results (calculated, not estimated)
Default seed, rules + network: precision 0.172, recall 1.000, F1 0.293, FPR 0.045; 6/6 planted networks recovered, 6 of 12
flagged networks false. Seed 777, same rules: precision 0.127, recall 1.000, FPR 0.064; 6/6 recovered, 7 of 13 false; the
rank-1 network was a 26-claimant false group. Planted counts (6 overpayments, 8 duplicate invoices, 5 quarantined claims,
2 unrecorded edges, 40 households) were identical on both seeds because they come from the generator's plan.

## Limitations and trade-offs
- The rules and the planted patterns share an author; seed 777 only partly answers that. Real fraud is not established by rules.
- Chaining weak signals through busy providers can merge unrelated claimants. Possible fixes (not implemented): community
  detection inside large components, capping provider bridges, or claim-level instead of network-level flags.
- One shared passcode protects writes; reviewer names are self-declared. No reset or delete action exists in the UI.
- A trained model would need labels from the same generator, which would make evaluation circular; rules are easier to test and defend.

## How testing demonstrates correctness
Unit tests cover metric formulas, boundary payments, same-claimant narrative exclusion, lifecycle rules and constraint
enforcement; negative tests corrupt copies of the data and confirm validators catch them; the five required exception types
have recall 1.0 in tests; a source-scan test confirms the detector never references the answer key; reproducibility is checked
by `scripts/verify_reproducibility.py`.
