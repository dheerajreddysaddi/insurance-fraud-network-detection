"""Claim scoring, relationship graph (NetworkX) and ranking of suspicious networks."""
from __future__ import annotations

from collections import defaultdict
from itertools import chain as _chain

import networkx as nx
import pandas as pd

CLAIMANT_PREFIX, CLAIM_PREFIX, PROVIDER_PREFIX = "CLM-", "CLAIM-", "PRV-"
LINK_TYPES = {"SHARED_PHONE", "SHARED_EMAIL", "DUPLICATE_INVOICE_ACROSS_CLAIMANTS", "SIMILAR_NARRATIVE"}
EDGE_TYPE_OF = {"SHARED_PHONE": "SHARES_PHONE", "SHARED_EMAIL": "SHARES_EMAIL"}
NETWORK_COLUMNS = ["network_id", "rank", "network_score", "flagged", "priority", "n_claimants", "n_claims",
                   "n_providers", "n_indicators", "indicator_types", "claimant_ids", "provider_ids", "claim_ids",
                   "unrecorded_edges", "total_claimed_cents", "total_paid_cents", "explanation"]


# ----------------------------------------------------- which records an indicator touches
def indicator_claimants(ind, owner) -> set:
    related = ind["related_entities"]
    return ({r for r in related if r.startswith(CLAIMANT_PREFIX)} | {owner[r] for r in related if r in owner})


def indicator_claims(ind, owner, claims_of) -> list:
    related = ind["related_entities"]
    explicit = [r for r in related if r in owner]       # claims named in the indicator
    if explicit:
        return explicit
    return list(_chain.from_iterable(claims_of.get(r, []) for r in related))


def _owner_maps(claims):
    owner = dict(zip(claims["claim_id"], claims["claimant_id"]))
    claims_of = defaultdict(list)
    for claim_id, who in owner.items():
        claims_of[who].append(claim_id)
    return owner, claims_of


# ------------------------------------------------------------------ claim-level scoring
def score_claims(claims, indicators, rules) -> pd.DataFrame:
    cats = {t: v["category"] for t, v in rules["indicators"].items()}
    owner, claims_of = _owner_maps(claims)
    attached = defaultdict(list)
    for ind in indicators:
        if cats[ind["indicator_type"]] != "SUSPICIOUS":
            continue
        for claim_id in set(indicator_claims(ind, owner, claims_of)):
            attached[claim_id].append(ind)
    threshold = rules["scoring"]["claim_flag_threshold"]
    rows = []
    for claim_id in sorted(owner):
        inds = attached.get(claim_id, [])
        total = sum(i["score"] for i in inds)
        rows.append({"claim_id": claim_id, "claimant_id": owner[claim_id], "rule_score": min(100, total),
                     "max_indicator_score": max((i["score"] for i in inds), default=0),
                     "n_indicators": len(inds),
                     "indicator_types": ",".join(sorted({i["indicator_type"] for i in inds})),
                     "rule_flagged": total >= threshold})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------- graph
def _add_link(G, a, b, kind, status, indicator_id, evidence):
    for n in (a, b):
        if n not in G:
            G.add_node(n, node_type="CLAIMANT" if n.startswith(CLAIMANT_PREFIX) else "PROVIDER")
    if not G.has_edge(a, b):
        G.add_edge(a, b, links=[])
    G[a][b]["links"].append({"kind": kind, "status": status, "indicator_id": indicator_id, "evidence": evidence})


def build_graph(tables, indicators, rules, claim_scores) -> nx.Graph:
    cats = {t: v["category"] for t, v in rules["indicators"].items()}
    owner, _ = _owner_maps(tables["claims"])
    e = tables["relationship_edges"]
    observed = {(t, frozenset((s, d))) for t, s, d in zip(e["edge_type"], e["src_id"], e["dst_id"])}
    G = nx.Graph()

    # claimant-claimant links from evidence (a group becomes a chain: enough to connect its members)
    for ind in indicators:
        t = ind["indicator_type"]
        if t not in LINK_TYPES or cats[t] != "SUSPICIOUS":
            continue
        members = sorted(indicator_claimants(ind, owner))
        for a, b in zip(members, members[1:]):
            if t in EDGE_TYPE_OF:
                status = "OBSERVED" if (EDGE_TYPE_OF[t], frozenset((a, b))) in observed else "MISSING_FROM_EDGE_TABLE"
            else:
                status = "INFERRED"
            _add_link(G, a, b, t, status, ind["indicator_id"], ind["explanation"])

    # claimant-provider links, only when the claim already carries a meaningful indicator
    min_score = rules["networks"]["provider_link_min_score"]
    strength = dict(zip(claim_scores["claim_id"], claim_scores["max_indicator_score"]))
    cp_observed = {(s, d) for t, s, d in zip(e["edge_type"], e["src_id"], e["dst_id"]) if t == "CLAIMANT_PROVIDER"}
    seen = set()
    inv = tables["invoices"][["claim_id", "provider_id"]].drop_duplicates().sort_values(["claim_id", "provider_id"])
    for claim_id, provider_id in zip(inv["claim_id"], inv["provider_id"]):
        if strength.get(claim_id, 0) < min_score:
            continue
        claimant = owner[claim_id]
        if (claimant, provider_id) in seen:
            continue
        seen.add((claimant, provider_id))
        status = "OBSERVED" if (claimant, provider_id) in cp_observed else "MISSING_FROM_EDGE_TABLE"
        _add_link(G, claimant, provider_id, "CLAIMANT_PROVIDER", status, "",
                  f"claim {claim_id} carries an indicator and was invoiced by {provider_id}")
    return G


def edges_table(G, nodes=None) -> pd.DataFrame:
    """One row per piece of evidence behind each connection (tabular alternative to the graph)."""
    rows = []
    for a, b, data in G.edges(data=True):
        if nodes is not None and not (a in nodes and b in nodes):
            continue
        for link in data["links"]:
            rows.append({"from": a, "to": b, "link_type": link["kind"], "status": link["status"],
                         "indicator_id": link["indicator_id"], "evidence": link["evidence"]})
    return pd.DataFrame(rows, columns=["from", "to", "link_type", "status", "indicator_id", "evidence"])


# ----------------------------------------------------------------------- ranking
def explain_network(flagged, score, high_score, inds, n_claimants, providers, unrecorded) -> str:
    by_type = defaultdict(list)
    for i in inds:
        by_type[i["indicator_type"]].append(i)
    parts = []
    if "SHARED_PHONE" in by_type:
        parts.append(f"{len(by_type['SHARED_PHONE'])} phone number(s) shared by claimants at different addresses")
    if "SHARED_EMAIL" in by_type:
        parts.append(f"{len(by_type['SHARED_EMAIL'])} email address(es) shared by claimants at different addresses")
    if "SIMILAR_NARRATIVE" in by_type:
        n = sum(len([r for r in i["related_entities"] if r.startswith(CLAIM_PREFIX)]) for i in by_type["SIMILAR_NARRATIVE"])
        parts.append(f"{n} claims with near-identical incident narratives")
    if "DUPLICATE_INVOICE_ACROSS_CLAIMANTS" in by_type:
        n = sum(len([r for r in i["related_entities"] if r.startswith("INV-PRV-")])
                for i in by_type["DUPLICATE_INVOICE_ACROSS_CLAIMANTS"])
        parts.append(f"{n} invoices duplicated across different claimants")
    if "UNUSUAL_TIMING" in by_type:
        parts.append(f"{len(by_type['UNUSUAL_TIMING'])} claim(s) with unusual timing")
    if "REPEAT_CLAIMANT_PROVIDER" in by_type:
        parts.append(f"{len(by_type['REPEAT_CLAIMANT_PROVIDER'])} repeated claimant-provider pattern(s)")
    lead = ("High-priority review" if score >= high_score else "Review recommended") if flagged else "Weak evidence only"
    text = f"{lead}: {n_claimants} claimants connected; " + "; ".join(parts) + "."
    if providers:
        text += f" Linked through provider(s) {', '.join(providers[:3])}."
    if unrecorded:
        text += f" {unrecorded} relationship(s) found in the data are missing from the recorded edges."
    return text + " This is a review recommendation, not a fraud verdict."


def rank_networks(G, tables, indicators, rules) -> pd.DataFrame:
    cfg = rules["networks"]
    cats = {t: v["category"] for t, v in rules["indicators"].items()}
    claims = tables["claims"]
    owner, claims_of = _owner_maps(claims)
    claimed = dict(zip(claims["claim_id"], claims["claimed_cents"]))
    paid = tables["payments"].groupby("claim_id")["amount_cents"].sum().to_dict()
    inds_of = defaultdict(dict)
    for ind in indicators:
        if cats[ind["indicator_type"]] != "SUSPICIOUS":
            continue
        for who in indicator_claimants(ind, owner):
            inds_of[who][ind["indicator_id"]] = ind

    rows = []
    for comp in nx.connected_components(G):
        members = sorted(n for n in comp if n.startswith(CLAIMANT_PREFIX))
        if len(members) < 2:
            continue
        providers = sorted(n for n in comp if n.startswith(PROVIDER_PREFIX))
        merged = {}
        for who in members:
            merged.update(inds_of.get(who, {}))
        inds = [merged[k] for k in sorted(merged)]
        types = sorted({i["indicator_type"] for i in inds})
        score = sum(i["score"] for i in inds) + cfg["multi_signal_bonus"] * max(0, len(types) - 1)
        flagged = score >= cfg["network_flag_threshold"] and len(types) >= cfg["min_distinct_types"]
        claim_ids = sorted(c for who in members for c in claims_of.get(who, []))
        unrecorded = sum(1 for _, _, d in G.subgraph(comp).edges(data=True)
                         for link in d["links"] if link["status"] == "MISSING_FROM_EDGE_TABLE")
        priority = ("HIGH" if score >= cfg["high_priority_score"] else "MEDIUM") if flagged else "LOW"
        rows.append({
            "network_id": "SUSNET-" + members[0], "network_score": int(score), "flagged": bool(flagged),
            "priority": priority, "n_claimants": len(members), "n_claims": len(claim_ids),
            "n_providers": len(providers), "n_indicators": len(inds), "indicator_types": ",".join(types),
            "claimant_ids": members, "provider_ids": providers, "claim_ids": claim_ids,
            "unrecorded_edges": unrecorded,
            "total_claimed_cents": int(sum(claimed[c] for c in claim_ids)),
            "total_paid_cents": int(sum(paid.get(c, 0) for c in claim_ids)),
            "explanation": explain_network(flagged, score, cfg["high_priority_score"], inds, len(members),
                                           providers, unrecorded)})
    if not rows:
        return pd.DataFrame(columns=NETWORK_COLUMNS)
    df = pd.DataFrame(rows).sort_values(["network_score", "network_id"], ascending=[False, True]).reset_index(drop=True)
    df.insert(1, "rank", range(1, len(df) + 1))
    return df[NETWORK_COLUMNS]


def finalize_claim_scores(claim_scores, networks, rules) -> pd.DataFrame:
    cfg, sc = rules["networks"], rules["scoring"]
    membership = {}
    if len(networks):
        for r in networks[networks["flagged"].astype(bool)].itertuples(index=False):
            for who in r.claimant_ids:
                membership[who] = r.network_id
    cs = claim_scores.copy()
    cs["network_id"] = cs["claimant_id"].map(membership).fillna("")
    cs["in_flagged_network"] = cs["network_id"] != ""
    cs["risk_score"] = (cs["rule_score"] + cs["in_flagged_network"].astype(int) * cfg["claim_network_bonus"]).clip(upper=100)
    cs["flagged"] = cs["rule_flagged"] | cs["in_flagged_network"]
    cs["risk_tier"] = ["HIGH" if s >= sc["high_risk_threshold"] else "MEDIUM" if f else "LOW" if s > 0 else "NONE"
                       for s, f in zip(cs["risk_score"], cs["flagged"])]
    return cs


def analyze(tables, indicators, rules) -> dict:
    scores = score_claims(tables["claims"], indicators, rules)
    G = build_graph(tables, indicators, rules, scores)
    networks = rank_networks(G, tables, indicators, rules)
    return {"claim_scores": finalize_claim_scores(scores, networks, rules), "graph": G, "networks": networks}