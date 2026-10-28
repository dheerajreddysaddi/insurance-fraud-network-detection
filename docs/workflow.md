# Workflow

| Step | Where |
|---|---|
| 1. Generate or load data | `scripts/generate_data.py` (writes CSV, ground truth, database) |
| 2. Validate | `scripts/validate_data.py`, Overview > data-quality summary |
| 3. Run indicator detection | `scripts/run_detection.py` or sidebar **Run detection now** (saves a new run; old runs are kept) |
| 4. Build the relationship graph | `network_analysis.build_graph` (nodes: claimants, providers) |
| 5. Rank networks and entities | `network_analysis.rank_networks`; Overview and Network Analysis |
| 6. Show evidence and exceptions | Claims Explorer, Network Analysis, Fraud Indicators & Exceptions |
| 7. Open an investigation | **Open investigation** on a claim or network, or the Workspace form |
| 8. Status, notes, decision | Investigation Workspace (OPEN, IN_REVIEW, ESCALATED, CLOSED_*; closing needs a note) |
| 9. Preserve history | `investigation_events` is insert-only |
| 10. Recompute metrics from saved records | Every page reads the database; Evaluation compares with the answer key |

A closed investigation records a review outcome. It is not a confirmed fraud label.