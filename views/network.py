"""Network Analysis: ranked suspicious groups, a readable graph, and a table alternative."""
import networkx as nx
import plotly.graph_objects as go
import streamlit as st

from src import app_data, network_analysis, ui

STATUS_STYLE = {  # status -> (colour, dash, legend label)
    "OBSERVED": ("#6B7280", "solid", "Observed (in edge table)"),
    "INFERRED": (ui.ACCENT, "dash", "Inferred by the detector"),
    "MISSING_FROM_EDGE_TABLE": ("#C0392B", "dot", "In the data, missing from edge table"),
}
MAX_GRAPH_NODES = 40


def _short(node):
    return ("C" if node.startswith("CLM-") else "P") + str(int(node[-6:]))


def _edge_status(links):
    statuses = {link["status"] for link in links}
    for s in ("MISSING_FROM_EDGE_TABLE", "INFERRED", "OBSERVED"):
        if s in statuses:
            return s


def _figure(sub, claimants, providers):
    pos = nx.spring_layout(sub, seed=42)
    fig = go.Figure()
    lines = {s: ([], []) for s in STATUS_STYLE}
    mid_x, mid_y, mid_text = [], [], []
    for a, b, data in sub.edges(data=True):
        xs, ys = lines[_edge_status(data["links"])]
        xs += [pos[a][0], pos[b][0], None]
        ys += [pos[a][1], pos[b][1], None]
        mid_x.append((pos[a][0] + pos[b][0]) / 2)
        mid_y.append((pos[a][1] + pos[b][1]) / 2)
        mid_text.append(f"{a} - {b}<br>" + "<br>".join(f"{l['kind']} ({l['status']})" for l in data["links"]))
    for status, (xs, ys) in lines.items():
        if xs:
            color, dash, label = STATUS_STYLE[status]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=color, width=2, dash=dash),
                                     hoverinfo="skip", name=label))
    fig.add_trace(go.Scatter(x=mid_x, y=mid_y, mode="markers", marker=dict(size=12, opacity=0),
                             hoverinfo="text", hovertext=mid_text, showlegend=False))
    cl = [n for n in sub.nodes if n.startswith("CLM-")]
    pr = [n for n in sub.nodes if n.startswith("PRV-")]
    for nodes, symbol, color, name, hover in (
            (cl, "circle", ui.ACCENT, "Claimant",
             lambda n: f"{n}<br>{claimants.loc[n, 'first_name']} {claimants.loc[n, 'last_name']}<br>{claimants.loc[n, 'city']}"),
            (pr, "square", "#374151", "Provider",
             lambda n: f"{n}<br>{providers.loc[n, 'provider_name']}<br>{providers.loc[n, 'provider_type']}")):
        if nodes:
            fig.add_trace(go.Scatter(
                x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes], mode="markers+text",
                text=[_short(n) for n in nodes], textposition="bottom center",
                marker=dict(size=24, color=color, symbol=symbol, line=dict(color="white", width=1)),
                hovertext=[hover(n) for n in nodes], hoverinfo="text", name=name))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="white",
                      legend=dict(orientation="h", y=-0.05))
    return fig


def render(ctx):
    if ctx["analysis"] is None:
        ui.no_detection()
        return
    tables, a = ctx["tables"], ctx["analysis"]
    nets, G = a["networks"], a["graph"]
    st.header("Network Analysis")
    if len(nets) == 0:
        st.info("No connected groups were found.")
        return
    only_flagged = st.checkbox("Show only flagged networks", value=True)
    shown = nets[nets["flagged"]] if only_flagged else nets
    if shown.empty:
        st.info("No flagged networks. Untick the box to see weaker groups.")
        return
    st.dataframe(shown[["rank", "network_id", "network_score", "priority", "flagged", "n_claimants", "n_claims",
                        "n_providers", "indicator_types", "unrecorded_edges"]], hide_index=True, use_container_width=True)
    choice = st.selectbox("Open network", list(shown["network_id"]), format_func=lambda n: (
        f"#{int(nets.loc[nets.network_id == n, 'rank'].iloc[0])}  {n}  "
        f"(score {int(nets.loc[nets.network_id == n, 'network_score'].iloc[0])})"))
    row = nets[nets["network_id"] == choice].iloc[0]

    st.info(row["explanation"])
    m = st.columns(5)
    m[0].metric("Claimants", int(row["n_claimants"]))
    m[1].metric("Claims", int(row["n_claims"]))
    m[2].metric("Providers", int(row["n_providers"]))
    m[3].metric("Network score", f"{int(row['network_score'])} ({row['priority']})")
    m[4].metric("Claimed / paid", f"{ui.money(row['total_claimed_cents'])} / {ui.money(row['total_paid_cents'])}")

    nodes = set(row["claimant_ids"]) | set(row["provider_ids"])
    sub = G.subgraph(nodes)
    st.subheader("Relationship graph")
    if sub.number_of_nodes() > MAX_GRAPH_NODES:
        st.warning(f"{sub.number_of_nodes()} nodes is too crowded to read. Use the connection table below.")
    else:
        st.plotly_chart(_figure(sub, tables["claimants"].set_index("claimant_id"),
                                tables["providers"].set_index("provider_id")), use_container_width=True)
        st.caption("C130 means CLM-2026-000130 and P364 means PRV-000364. Circles are claimants, squares are providers. "
                   "A line is dashed or dotted if any of its evidence is inferred or missing from the edge table. "
                   "Hover over a line for every piece of evidence.")

    t1, t2, t3, t4 = st.tabs(["Connections (table)", "Claimants", "Claims", "Evidence"])
    with t1:
        edges = network_analysis.edges_table(G, nodes)
        wanted = st.multiselect("Link status", list(STATUS_STYLE), default=list(STATUS_STYLE))
        st.dataframe(edges[edges["status"].isin(wanted)], hide_index=True, use_container_width=True)
        st.caption("OBSERVED = recorded in relationship_edges. INFERRED = derived by the detector from claim or invoice "
                   "data. MISSING_FROM_EDGE_TABLE = true in the data but absent from the recorded edges.")
    with t2:
        members = tables["claimants"][tables["claimants"]["claimant_id"].isin(row["claimant_ids"])]
        st.dataframe(members[["claimant_id", "first_name", "last_name", "phone", "email", "address_line", "city"]],
                     hide_index=True, use_container_width=True)
    with t3:
        cs = a["claim_scores"][a["claim_scores"]["claim_id"].isin(row["claim_ids"])]
        claims = tables["claims"][["claim_id", "claim_date", "status", "claimed_cents", "approved_cents"]]
        st.dataframe(cs[["claim_id", "claimant_id", "risk_score", "indicator_types"]].merge(claims, on="claim_id"),
                     hide_index=True, use_container_width=True)
    inds = app_data.indicators_for_network(a["indicators"], a["rules"], a["owner"], row["claimant_ids"])
    with t4:
        if not inds:
            st.caption("No indicators.")
        else:
            by_id = {i["indicator_id"]: i for i in inds}
            pick = st.selectbox("Indicator", list(by_id), format_func=lambda k: (
                f"{by_id[k]['indicator_type']} - {by_id[k]['entity_id']} (score {by_id[k]['score']})"))
            ind = by_id[pick]
            st.write(ind["explanation"])
            st.caption("Rule: " + ind["rule_description"])
            st.json(ind["evidence"])

    ui.investigation_launcher("NETWORK", choice, row["priority"], [i["indicator_id"] for i in inds],
                              key=f"net_{choice}")