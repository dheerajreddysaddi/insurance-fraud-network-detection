"""Claims Explorer: search, filter, and open one claim with its related records."""
from datetime import date

import pandas as pd
import streamlit as st

from src import app_data, ui

TABLE_COLUMNS = ["claim_id", "claimant_id", "claimant_name", "providers", "status", "claim_date", "claimed_inr",
                 "approved_inr", "paid_inr", "risk_score", "risk_tier", "flagged", "network_id"]


def _frame(tables, a):
    names = tables["claimants"].assign(
        claimant_name=lambda d: d["first_name"] + " " + d["last_name"])[["claimant_id", "claimant_name"]]
    providers = tables["invoices"].groupby("claim_id")["provider_id"].agg(
        lambda s: ", ".join(sorted(set(s)))).rename("providers")
    paid = tables["payments"].groupby("claim_id")["amount_cents"].sum().rename("paid_cents")
    scores = a["claim_scores"][["claim_id", "risk_score", "risk_tier", "flagged", "network_id", "indicator_types"]]
    df = (tables["claims"].merge(names, on="claimant_id").merge(scores, on="claim_id")
          .merge(providers, on="claim_id", how="left").merge(paid, on="claim_id", how="left"))
    df["providers"] = df["providers"].fillna("")
    df["paid_cents"] = df["paid_cents"].fillna(0).astype(int)
    return df


def _filter(df):
    c1, c2, c3 = st.columns(3)
    q = c1.text_input("Search claim ID, claimant ID or name")
    provider = c2.text_input("Provider ID (e.g. PRV-000123)")
    statuses = c3.multiselect("Status", sorted(df["status"].unique()))
    c4, c5, c6 = st.columns(3)
    lo, hi = date.fromisoformat(df["claim_date"].min()), date.fromisoformat(df["claim_date"].max())
    picked = c4.date_input("Claim date range", value=(lo, hi), min_value=lo, max_value=hi)
    min_risk = c5.slider("Minimum risk score", 0, 100, 0)
    flagged_only = c6.checkbox("Flagged claims only")

    f = df
    if q.strip():
        ql = q.strip().lower()
        f = f[f["claim_id"].str.lower().str.contains(ql, regex=False)
              | f["claimant_id"].str.lower().str.contains(ql, regex=False)
              | f["claimant_name"].str.lower().str.contains(ql, regex=False)]
    if provider.strip():
        f = f[f["providers"].str.contains(provider.strip().upper(), regex=False)]
    if statuses:
        f = f[f["status"].isin(statuses)]
    if isinstance(picked, (tuple, list)) and len(picked) == 2:
        f = f[(f["claim_date"] >= picked[0].isoformat()) & (f["claim_date"] <= picked[1].isoformat())]
    f = f[f["risk_score"] >= min_risk]
    if flagged_only:
        f = f[f["flagged"]]
    return f


def render(ctx):
    if ctx["analysis"] is None:
        ui.no_detection()
        return
    tables, a = ctx["tables"], ctx["analysis"]
    st.header("Claims Explorer")
    base = _frame(tables, a)
    f = _filter(base).sort_values(["risk_score", "claim_id"], ascending=[False, True])
    st.caption(f"{len(f):,} of {len(base):,} claims match. Showing the first 1,000, highest risk first. "
               "Select a row to open the claim.")
    shown = f.head(1000).assign(claimed_inr=lambda d: d["claimed_cents"] / 100,
                                approved_inr=lambda d: d["approved_cents"] / 100,
                                paid_inr=lambda d: d["paid_cents"] / 100)
    money = st.column_config.NumberColumn(format="%.0f")
    row = ui.table_with_selection(shown[TABLE_COLUMNS], "claims_table",
                                  {"claimed_inr": money, "approved_inr": money, "paid_inr": money})
    if row is None:
        st.info("Select a claim in the table to see its policy, incident, providers, invoices, payments and indicators.")
        return
    st.divider()
    _detail(ctx, row["claim_id"])


def _detail(ctx, claim_id):
    tables, a = ctx["tables"], ctx["analysis"]
    pick = lambda name, col, val: tables[name][tables[name][col] == val]  # noqa: E731
    claim = pick("claims", "claim_id", claim_id).iloc[0]
    policy = pick("policies", "policy_id", claim["policy_id"]).iloc[0]
    incident = pick("incidents", "incident_id", claim["incident_id"]).iloc[0]
    claimant = pick("claimants", "claimant_id", claim["claimant_id"]).iloc[0]
    invoices = pick("invoices", "claim_id", claim_id)
    payments = pick("payments", "claim_id", claim_id)
    events = pick("claim_status_events", "claim_id", claim_id).sort_values("event_id")
    providers = tables["providers"][tables["providers"]["provider_id"].isin(invoices["provider_id"])]
    score = a["claim_scores"][a["claim_scores"]["claim_id"] == claim_id].iloc[0]
    paid = int(payments["amount_cents"].sum())
    approved = claim["approved_cents"]

    st.subheader(claim_id)
    m = st.columns(5)
    m[0].metric("Status", claim["status"])
    m[1].metric("Claimed", ui.money(claim["claimed_cents"]))
    m[2].metric("Approved", ui.money(approved))
    m[3].metric("Paid", ui.money(paid))
    m[4].metric("Risk score", f"{int(score['risk_score'])} ({score['risk_tier']})")
    if pd.notna(approved) and paid > approved:
        st.error(f"Payments exceed the approved amount by {ui.money(paid - approved)}. This is recorded as a "
                 "financial exception; it is not fraud evidence on its own.")
    elif pd.notna(approved):
        st.caption(f"Approved minus paid: {ui.money(approved - paid)}")
    if score["network_id"]:
        st.caption(f"The claimant belongs to flagged network {score['network_id']} (see Network Analysis).")

    t1, t2, t3, t4 = st.tabs(["Policy, claimant & incident", "Providers, invoices & payments",
                              "Status history", "Indicators"])
    with t1:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Policy**")
            ui.kv_table({"Policy": policy["policy_id"], "Type": policy["policy_type"], "Status": policy["status"],
                         "Period": f"{policy['start_date']} to {policy['end_date']}",
                         "Premium": ui.money(policy["premium_cents"]),
                         "Coverage limit": ui.money(policy["coverage_limit_cents"])})
            st.markdown("**Claimant**")
            ui.kv_table({"Claimant": claimant["claimant_id"], "Name": f"{claimant['first_name']} {claimant['last_name']}",
                         "Phone": claimant["phone"], "Email": claimant["email"],
                         "Address": f"{claimant['address_line']}, {claimant['city']} {claimant['postal_code']}"})
        with c2:
            st.markdown("**Incident**")
            ui.kv_table({"Incident": incident["incident_id"], "Type": incident["incident_type"],
                         "Date": incident["incident_date"], "Location": incident["location"],
                         "Claim filed": claim["claim_date"]})
            st.markdown("**Narrative**")
            st.write(incident["narrative"])
    with t2:
        st.markdown("**Providers**")
        st.dataframe(providers[["provider_id", "provider_name", "provider_type", "status", "city"]], hide_index=True)
        st.markdown("**Invoices**")
        st.dataframe(invoices[["invoice_id", "provider_id", "provider_invoice_ref", "service_date", "invoice_date",
                               "amount_cents", "description"]], hide_index=True)
        st.caption(f"Invoice total {ui.money(invoices['amount_cents'].sum())} vs claimed {ui.money(claim['claimed_cents'])}.")
        st.markdown("**Payments**")
        if payments.empty:
            st.caption("No payments recorded for this claim.")
        else:
            st.dataframe(payments[["payment_id", "invoice_id", "payment_date", "amount_cents", "payment_method"]],
                         hide_index=True)
    with t3:
        st.dataframe(events[["event_date", "from_status", "to_status"]], hide_index=True)
    with t4:
        matched = app_data.indicators_for_claim(a["indicators"], claim_id, claim["claimant_id"])
        if not matched:
            st.caption("No indicators reference this claim or its claimant.")
        for ind in matched:
            scope = "this claim" if claim_id in ind["related_entities"] or ind["claim_id"] == claim_id else "claimant"
            with st.expander(f"{ind['indicator_type']} - {ind['severity']} (score {ind['score']}, applies to {scope})"):
                st.write(ind["explanation"])
                st.caption("Rule: " + ind["rule_description"])
                st.json(ind["evidence"])

    ui.investigation_launcher("CLAIM", claim_id, score["risk_tier"], [i["indicator_id"] for i in matched],
                              key=f"claim_{claim_id}")