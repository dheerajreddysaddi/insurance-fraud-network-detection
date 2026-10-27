"""Deterministic synthetic data generator.

Order: plans -> claimants -> providers -> policies -> incidents+claims -> invoices
       -> lifecycle events + payments -> injected exceptions -> edges -> ground truth.
Everything random comes from ONE random.Random(seed), so output is reproducible.
Planted (fraud-pattern) records are created in shuffled order, so IDs never reveal labels.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations

from src.constants import DEFAULT_SEED, INCIDENT_TYPES, YEAR

REF_DATE = date(2026, 6, 30)          # "today" inside the synthetic world

SCALES = {
    "starter": dict(claimants=400, providers=100, claims=1000, edges=1600, households=10,
                    quarantined_claims=3, overpaid_standalone=2,
                    networks=["contact_ring", "narrative_ring", "provider_collusion"]),
    "full": dict(claimants=2000, providers=500, claims=5000, edges=8000, households=40,
                 quarantined_claims=5, overpaid_standalone=4,
                 networks=["contact_ring", "contact_ring", "narrative_ring",
                           "narrative_ring", "provider_collusion", "provider_collusion"]),
}

# Each pattern: claims per member, policy family, amount inflation, duplicate-invoice pair (member indexes)
PATTERNS = {
    "contact_ring": dict(claims_per_member=[1, 1, 1, 1, 1, 1], family="MOTOR", inflate=1.5, dup=(0, 3)),
    "narrative_ring": dict(claims_per_member=[2, 2, 1, 1, 1], family="MOTOR", inflate=1.3, dup=None),
    "provider_collusion": dict(claims_per_member=[2, 2, 2, 2, 2], family="HEALTH", inflate=1.8, dup=(0, 2)),
}

POLICY_TYPES = {  # amounts in cents (INR x 100)
    "MOTOR": dict(weight=50, premium=1_500_000, coverage=50_000_000),
    "HEALTH": dict(weight=30, premium=1_200_000, coverage=30_000_000),
    "PROPERTY": dict(weight=20, premium=800_000, coverage=100_000_000),
}
MEDIAN_CLAIM_INR = {"MOTOR": 40000, "HEALTH": 60000, "PROPERTY": 90000}
FAMILY_PROVIDER_TYPES = {"MOTOR": ["REPAIRER", "TOWING", "ASSESSOR"],
                         "HEALTH": ["MEDICAL"], "PROPERTY": ["REPAIRER", "ASSESSOR"]}

FIRST = ["Aarav", "Vivaan", "Aditya", "Diya", "Ananya", "Isha", "Rohan", "Kavya", "Arjun", "Meera",
         "Sanjay", "Priya", "Rahul", "Neha", "Karan", "Pooja", "Vikram", "Anjali", "Suresh", "Lakshmi",
         "Imran", "Fatima", "David", "Maria", "John", "Sara", "Ravi", "Sunita", "Manoj", "Deepa"]
LAST = ["Sharma", "Reddy", "Patel", "Khan", "Singh", "Iyer", "Nair", "Gupta", "Das", "Joshi",
        "Mehta", "Rao", "Verma", "Menon", "Naidu", "Kapoor", "Bose", "Chopra", "Fernandes", "Pillai",
        "Ghosh", "Malhotra", "Sethi", "Yadav", "Banerjee", "Kulkarni", "Shetty", "Hussain", "Thomas", "Bhat"]
STREETS = ["MG Road", "Station Road", "Park Street", "Lake View Road", "Temple Street", "Gandhi Nagar",
           "Market Road", "Church Lane", "Hill Road", "Canal Street", "Residency Road", "Rose Garden Lane"]
CITIES = ["Hyderabad", "Pune", "Chennai", "Bengaluru", "Mumbai", "Kolkata", "Jaipur", "Kochi"]
PROVIDER_SUFFIX = {"REPAIRER": ["Auto Works", "Motors", "Garage", "Body Shop"],
                   "MEDICAL": ["Medical Centre", "Clinic", "Hospital", "Diagnostics"],
                   "TOWING": ["Towing", "Roadside Assist"],
                   "ASSESSOR": ["Loss Assessors", "Surveyors"]}
INVOICE_DESCRIPTIONS = {
    "REPAIRER": ["Panel repair and repaint", "Replacement parts and labour",
                 "Bumper and headlamp replacement", "Engine bay repair"],
    "MEDICAL": ["Consultation and diagnostics", "Surgical procedure charges",
                "Hospital stay charges", "Physiotherapy sessions"],
    "TOWING": ["Vehicle towing and recovery"],
    "ASSESSOR": ["Loss assessment and survey report"],
}

PLACES = ["Gachibowli", "Kothrud", "Adyar", "Indiranagar", "Andheri", "Salt Lake", "Malviya Nagar",
          "Edappally", "Banjara Hills", "Hinjewadi", "T Nagar", "Whitefield", "Powai", "Park Circus",
          "Vaishali Nagar", "Kakkanad", "Madhapur", "Baner", "Velachery", "Koramangala"]
LANDMARKS = ["the railway station", "a shopping mall", "the office complex", "a petrol pump",
             "the main bus stand", "a public park", "the city hospital", "a weekly market",
             "the school gate", "a metro station", "the old bridge", "a temple junction"]
WEATHER = ["heavy rain", "clear", "dense fog", "strong wind", "humid", "light drizzle"]
OUTCOMES = ["Police report was filed", "Photos were taken at the scene", "A witness was present",
            "The insurer was notified immediately", "No injuries were reported", "The matter was reported the same day"]
OPENINGS = {
    "COLLISION": "Policyholder reported a vehicle collision", "THEFT": "Policyholder reported a vehicle theft",
    "WINDSHIELD_DAMAGE": "Policyholder reported a cracked windshield", "VANDALISM": "Policyholder reported vandalism to the vehicle",
    "HOSPITALIZATION": "Policyholder was admitted to hospital", "OUTPATIENT_TREATMENT": "Policyholder received outpatient treatment",
    "SURGERY": "Policyholder underwent a planned surgery", "FIRE": "Policyholder reported a fire at the premises",
    "WATER_DAMAGE": "Policyholder reported water damage at the premises", "BURGLARY": "Policyholder reported a burglary at the premises",
    "STORM_DAMAGE": "Policyholder reported storm damage to the premises",
}
FACTS = {
    "MOTOR": ["The other vehicle fled the scene", "Front bumper was crushed", "Airbags did not deploy",
              "The road surface was wet", "The vehicle was parked at the time", "Rear lights were broken",
              "The driver was alone in the vehicle", "Traffic was moving slowly", "A tow truck was called",
              "The dashboard camera was not recording"],
    "HEALTH": ["Symptoms started two days earlier", "Admission was through the emergency ward",
               "The treating doctor advised rest", "Diagnostic tests were repeated twice",
               "A specialist was consulted", "The patient stayed overnight", "Medication was prescribed for ten days",
               "A follow-up visit was scheduled", "The condition was not pre-existing", "Family members accompanied the patient"],
    "PROPERTY": ["The electrical wiring was old", "Neighbours raised the alarm", "Furniture in the living room was damaged",
                 "The ceiling showed visible cracks", "The main door lock was broken", "Appliances stopped working",
                 "The fire brigade arrived within minutes", "Water entered through the terrace", "Walls need repainting",
                 "Valuables were reported missing"],
}

GT_COLUMNS = {
    "networks": ["network_id", "pattern", "n_claimants", "n_claims", "description"],
    "network_members": ["network_id", "entity_type", "entity_id", "role"],
    "anomalies": ["anomaly_id", "issue_type", "entity_type", "entity_id", "network_id",
                  "expected_decision", "note"],
    "benign_groups": ["group_id", "claimant_id", "shared_attribute"],
    "claim_labels": ["claim_id", "claimant_id", "network_id", "is_suspicious_network",
                     "data_exception_type", "benign_household_member"],
}


@dataclass
class Dataset:
    tables: dict
    ground_truth: dict   # name -> (columns, rows). NEVER fed to the detector.
    scale: str
    seed: int


# ------------------------------------------------------------------ small helpers
def _days(n: int) -> timedelta:
    return timedelta(days=n)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", text.lower())).strip()


def invoice_fingerprint(provider_id, amount_cents, service_date, description) -> str:
    raw = f"{provider_id}|{amount_cents}|{service_date}|{normalize_text(description)}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _rand_time(rng) -> str:
    return f"{rng.randint(1, 12)}:{rng.randint(0, 59):02d}{rng.choice(['am', 'pm'])}"


def _new_slots(rng, family) -> dict:
    return {"place": rng.choice(PLACES), "landmark": rng.choice(LANDMARKS), "weather": rng.choice(WEATHER),
            "facts": rng.sample(FACTS[family], 3), "outcome": rng.choice(OUTCOMES), "time": _rand_time(rng)}


def _render_narrative(incident_type, s) -> str:
    return (f"{OPENINGS[incident_type]} at {s['place']} near {s['landmark']} around {s['time']} "
            f"in {s['weather']} conditions. " + ". ".join(s["facts"]) + f". {s['outcome']}.")


def _claim_amount_cents(rng, family, coverage_cents, inflate=1.0) -> int:
    inr = max(2000, int(rng.lognormvariate(math.log(MEDIAN_CLAIM_INR[family]), 0.8) * inflate))
    return min(inr * 100, coverage_cents)


def _unique_phone(rng, used) -> str:
    while True:
        phone = f"+000-{rng.randint(100, 999)}-{rng.randint(100000, 999999)}"  # +000 = clearly fictional
        if phone not in used:
            used.add(phone)
            return phone


def _email(first, last, n) -> str:
    return f"{first}.{last}.{n}@example.test".lower()   # .test is a reserved, non-routable domain


# --------------------------------------------------------------------- planning
def _make_plans(rng, cfg) -> list[dict]:
    plans = []
    for i, pattern in enumerate(cfg["networks"], 1):
        spec = PATTERNS[pattern]
        anchor = date(2025, 1, 1) + _days(rng.randint(0, 400))
        member_incidents = []
        for k in spec["claims_per_member"]:
            dates = [anchor + _days(rng.randint(0, 10))]            # tight timing cluster
            for _ in range(k - 1):
                dates.append(dates[-1] + _days(rng.randint(20, 60)))
            member_incidents.append(dates)
        family = spec["family"]
        plan = {"network_id": f"NET-{i:02d}", "pattern": pattern, **spec, "anchor": anchor,
                "member_incidents": member_incidents,
                "incident_type": rng.choice(INCIDENT_TYPES[family]),
                "slots": _new_slots(rng, family)}
        if spec["dup"]:
            a, b = spec["dup"]
            plan["dup_service_date"] = max(member_incidents[a][0], member_incidents[b][0]) + _days(rng.randint(0, 3))
            plan["dup_amount"] = rng.randint(30000, 120000) * 100
            plan["dup_ref"] = f"R{rng.randint(100000, 999999)}"
            plan["dup_description"] = ("Replacement parts and labour" if family == "MOTOR"
                                       else "Hospital stay charges")
        plans.append(plan)
    return plans


# ----------------------------------------------------------------------- generate
def generate(scale: str = "starter", seed: int = DEFAULT_SEED) -> Dataset:
    cfg = SCALES[scale]
    rng = random.Random(seed)
    iso = lambda d: d.isoformat()  # noqa: E731
    plans = _make_plans(rng, cfg)
    plan_by_id = {p["network_id"]: p for p in plans}

    # ---------------- claimants (planted members are shuffled in with baseline ones)
    n_planted_claimants = sum(len(p["claims_per_member"]) for p in plans)
    n_planted_claims = sum(sum(p["claims_per_member"]) for p in plans)
    specs = [("base", None, None)] * (cfg["claimants"] - n_planted_claimants)
    specs += [("net", p["network_id"], i) for p in plans for i in range(len(p["claims_per_member"]))]
    rng.shuffle(specs)

    used_phones, used_addr = set(), set()
    claimants, base_ids, member_of = [], [], {}
    for n, (kind, net, idx) in enumerate(specs, 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        while True:
            addr, city = f"{rng.randint(1, 999)} {rng.choice(STREETS)}", rng.choice(CITIES)
            if (addr, city) not in used_addr:
                used_addr.add((addr, city))
                break
        c = {"claimant_id": f"CLM-{YEAR}-{n:06d}", "first_name": first, "last_name": last,
             "date_of_birth": iso(date(1955, 1, 1) + _days(rng.randint(0, 365 * 49))),
             "phone": _unique_phone(rng, used_phones), "email": _email(first, last, n),
             "address_line": addr, "city": city, "postal_code": str(rng.randint(100000, 999999)),
             "registered_date": iso(date(2018, 1, 1) + _days(rng.randint(0, 365 * 4)))}
        claimants.append(c)
        if kind == "net":
            plan_by_id[net].setdefault("member_ids", {})[idx] = c["claimant_id"]
            member_of[c["claimant_id"]] = (net, idx)
        else:
            base_ids.append(c["claimant_id"])
    cl_by_id = {c["claimant_id"]: c for c in claimants}

    # ---------------- benign households: same surname + same address (+ sometimes a shared phone)
    households, pool = [], base_ids[:]
    rng.shuffle(pool)
    for h in range(1, cfg["households"] + 1):
        members = [pool.pop() for _ in range(rng.choice([2, 3]))]
        head, share_phone = cl_by_id[members[0]], rng.random() < 0.4
        for mid in members[1:]:
            m = cl_by_id[mid]
            m["last_name"] = head["last_name"]
            for f in ("address_line", "city", "postal_code"):
                m[f] = head[f]
            m["email"] = _email(m["first_name"], m["last_name"], int(mid[-6:]))
            if share_phone:
                m["phone"] = head["phone"]
        households.append((f"HH-{h:03d}", members, "address+surname" + ("+phone" if share_phone else "")))

    # ---------------- planted shared contact details (contact rings only)
    hidden_pairs = []   # relationships that exist in the data but are deliberately NOT in the edge table
    for p in plans:
        if p["pattern"] != "contact_ring":
            continue
        m = [cl_by_id[p["member_ids"][i]] for i in range(6)]
        phone_a, phone_b = _unique_phone(rng, used_phones), _unique_phone(rng, used_phones)
        for i in (0, 1, 2):
            m[i]["phone"] = phone_a
        for i in (3, 4):
            m[i]["phone"] = phone_b
        m[3]["email"] = m[2]["email"]                       # shared email, pair (2,3)
        hidden_pairs.append((p["network_id"], m[2]["claimant_id"], m[3]["claimant_id"]))

    # ---------------- providers (skewed activity: a few legitimately busy ones)
    n_prov = cfg["providers"]
    ptypes = rng.choices(["REPAIRER", "MEDICAL", "TOWING", "ASSESSOR"], weights=[45, 35, 10, 10], k=n_prov)
    perm = list(range(n_prov))
    rng.shuffle(perm)                                       # popularity rank is unrelated to the ID
    providers, provider_by_id, prov_by_type = [], {}, defaultdict(lambda: ([], []))
    for n in range(1, n_prov + 1):
        ptype = ptypes[n - 1]
        status = "INACTIVE" if rng.random() < 0.03 else "ACTIVE"
        row = {"provider_id": f"PRV-{n:06d}", "provider_name": f"{rng.choice(LAST)} {rng.choice(PROVIDER_SUFFIX[ptype])}",
               "provider_type": ptype, "phone": _unique_phone(rng, used_phones),
               "email": f"info{n}@provider{n}.example.test", "address_line": f"{rng.randint(1, 300)} {rng.choice(STREETS)}",
               "city": rng.choice(CITIES), "registered_date": iso(date(2015, 1, 1) + _days(rng.randint(0, 365 * 7))),
               "status": status}
        providers.append(row)
        provider_by_id[row["provider_id"]] = row
        if status == "ACTIVE":
            ids, weights = prov_by_type[ptype]
            ids.append(row["provider_id"])
            weights.append(1 / ((perm[n - 1] + 1) ** 0.7))

    for p in plans:                                         # planted networks use ordinary providers
        if p["pattern"] == "contact_ring":
            p["providers"] = [rng.choice(prov_by_type["REPAIRER"][0])]
        elif p["pattern"] == "narrative_ring":
            p["providers"] = rng.sample(prov_by_type["REPAIRER"][0], 2)
        else:
            p["providers"] = [rng.choice(prov_by_type["MEDICAL"][0])]

    preferred = {}

    def pick_provider(family, claimant_id):
        allowed = FAMILY_PROVIDER_TYPES[family]
        pref = preferred.get(claimant_id)
        if pref and provider_by_id[pref]["provider_type"] in allowed and rng.random() < 0.6:
            return pref                                    # genuine repeat customer of one provider
        ids, weights = prov_by_type[rng.choice(allowed)]
        pid = rng.choices(ids, weights=weights)[0]
        if claimant_id not in preferred and rng.random() < 0.3:
            preferred[claimant_id] = pid
        return pid

    # ---------------- policies
    policies, policy_of = [], defaultdict(list)
    ptype_names = list(POLICY_TYPES)
    ptype_weights = [POLICY_TYPES[t]["weight"] for t in ptype_names]
    span = (date(2025, 6, 30) - date(2023, 1, 1)).days
    for c in claimants:
        cid = c["claimant_id"]
        planted = cid in member_of
        n_pol = 1 if planted else rng.choices([1, 2, 3], [65, 30, 5])[0]
        for _ in range(n_pol):
            if planted:
                net, idx = member_of[cid]
                plan = plan_by_id[net]
                ptype = plan["family"]
                start = plan["member_incidents"][idx][0] - _days(rng.randint(5, 25))  # policy bought shortly before loss
            else:
                ptype = rng.choices(ptype_names, weights=ptype_weights)[0]
                start = date(2023, 1, 1) + _days(rng.randint(0, span))
            end = start + _days(364)
            cancelled = (not planted) and rng.random() < 0.03
            status = "CANCELLED" if cancelled else ("EXPIRED" if end < REF_DATE else "ACTIVE")
            base = POLICY_TYPES[ptype]
            row = {"policy_id": f"POL-{YEAR}-{len(policies) + 1:06d}", "claimant_id": cid, "policy_type": ptype,
                   "start_date": iso(start), "end_date": iso(end),
                   "premium_cents": int(base["premium"] * rng.uniform(0.8, 1.3)) // 100 * 100,
                   "coverage_limit_cents": int(base["coverage"] * rng.choice([0.6, 1.0, 1.5])) // 100 * 100,
                   "status": status}
            policies.append(row)
            policy_of[cid].append(row)

    # ---------------- incidents + claims
    base_set = set(base_ids)
    elig = [p for p in policies if p["status"] != "CANCELLED" and p["claimant_id"] in base_set]
    propensity = {cid: rng.lognormvariate(0, 0.6) for cid in base_ids}   # some claimants genuinely claim more
    elig_w = [propensity[p["claimant_id"]] for p in elig]

    n_base_claims = cfg["claims"] - n_planted_claims
    jobs = [("base", None, None, None)] * n_base_claims
    jobs += [("net", p["network_id"], i, j) for p in plans
             for i, k in enumerate(p["claims_per_member"]) for j in range(k)]
    rng.shuffle(jobs)

    incidents, claims, claim_meta = [], [], {}
    for n, (kind, net, idx, seq) in enumerate(jobs, 1):
        if kind == "base":
            pol = rng.choices(elig, weights=elig_w)[0]
            lo, end = date.fromisoformat(pol["start_date"]), date.fromisoformat(pol["end_date"])
            hi = min(end, REF_DATE - _days(25))
            r = rng.random()
            if r < 0.02:
                inc = lo                                   # boundary case: loss on policy start date
            elif r < 0.04 and end <= hi:
                inc = end                                  # boundary case: loss on policy end date
            else:
                inc = lo + _days(rng.randint(0, (hi - lo).days))
            claim_date = inc + _days(rng.randint(1, 20))
            family, claimant = pol["policy_type"], pol["claimant_id"]
            itype = rng.choice(INCIDENT_TYPES[family])
            slots = _new_slots(rng, family)
            provider = pick_provider(family, claimant)
            claimed = _claim_amount_cents(rng, family, pol["coverage_limit_cents"])
            meta = dict(network_id=None, dup=False, fast=False, force_approve=False)
        else:
            plan = plan_by_id[net]
            claimant = plan["member_ids"][idx]
            pol = policy_of[claimant][0]
            inc = plan["member_incidents"][idx][seq]
            claim_date = inc + _days(rng.randint(0, 1))     # filed almost immediately
            family, itype = plan["family"], plan["incident_type"]
            if plan["pattern"] == "provider_collusion":
                slots = _new_slots(rng, family)
            else:                                           # repeated narrative: same story, only the time differs
                slots = dict(plan["slots"], time=_rand_time(rng))
            provider = plan["providers"][(idx + seq) % len(plan["providers"])]
            is_dup = plan["dup"] is not None and seq == 0 and idx in plan["dup"]
            claimed = (plan["dup_amount"] if is_dup
                       else _claim_amount_cents(rng, family, pol["coverage_limit_cents"], plan["inflate"]))
            collusion = plan["pattern"] == "provider_collusion"
            meta = dict(network_id=net, dup=is_dup, fast=collusion, force_approve=collusion)
        meta["provider_id"] = provider
        claim_id = f"CLAIM-{YEAR}-{n:06d}"
        incidents.append({"incident_id": f"INC-{YEAR}-{n:06d}", "incident_date": iso(inc), "location": slots["place"],
                          "incident_type": itype, "narrative": _render_narrative(itype, slots)})
        claims.append({"claim_id": claim_id, "claimant_id": claimant, "policy_id": pol["policy_id"],
                       "incident_id": f"INC-{YEAR}-{n:06d}", "claim_date": iso(claim_date),
                       "claimed_cents": claimed, "approved_cents": None, "decision_date": None,
                       "status": "SUBMITTED"})
        claim_meta[claim_id] = meta
    incident_date_of = {i["incident_id"]: date.fromisoformat(i["incident_date"]) for i in incidents}

    # ---------------- invoices (split of the claimed amount, so totals reconcile by construction)
    invoices, inv_by_claim = [], defaultdict(list)
    inv_seq, used_refs = defaultdict(int), defaultdict(set)
    for cl in claims:
        cid, meta = cl["claim_id"], claim_meta[cl["claim_id"]]
        plan = plan_by_id.get(meta["network_id"])
        inc = incident_date_of[cl["incident_id"]]
        n_inv = 1 if meta["dup"] else rng.choices([1, 2, 3], [65, 30, 5])[0]
        weights = [rng.uniform(0.3, 1.0) for _ in range(n_inv)]
        amounts = [int(cl["claimed_cents"] * w / sum(weights)) // 100 * 100 for w in weights[:-1]]
        amounts.append(cl["claimed_cents"] - sum(amounts))
        for k in range(n_inv):
            pid = meta["provider_id"]
            if plan is None and k > 0 and rng.random() < 0.15:
                pid = pick_provider({"MOTOR": "MOTOR", "HEALTH": "HEALTH", "PROPERTY": "PROPERTY"}[
                    next(p["policy_type"] for p in policy_of[cl["claimant_id"]] if p["policy_id"] == cl["policy_id"])],
                    cl["claimant_id"])
            ptype = provider_by_id[pid]["provider_type"]
            if meta["dup"]:
                ref, desc = plan["dup_ref"], plan["dup_description"]
                service = plan["dup_service_date"]
                invoice_date = service + _days(rng.randint(0, 3))
            else:
                while True:
                    ref = f"R{rng.randint(100000, 999999)}"
                    if ref not in used_refs[pid]:
                        used_refs[pid].add(ref)
                        break
                desc = rng.choice(INVOICE_DESCRIPTIONS[ptype])
                service = inc + _days(rng.randint(0, 2) if plan else rng.randint(0, 10))
                invoice_date = service + _days(0 if (plan and meta["fast"]) else rng.randint(0, 5))
            inv_seq[pid] += 1
            row = {"invoice_id": f"INV-PRV-{int(pid[-6:]):06d}-{inv_seq[pid]:06d}", "claim_id": cid,
                   "provider_id": pid, "provider_invoice_ref": ref, "invoice_date": iso(invoice_date),
                   "service_date": iso(service), "amount_cents": amounts[k], "description": desc,
                   "fingerprint": invoice_fingerprint(pid, amounts[k], iso(service), desc)}
            invoices.append(row)
            inv_by_claim[cid].append(row)

    # ---------------- claim lifecycle events + payments (status is DERIVED from the events)
    payments_raw, transitions = [], []
    for cl in claims:
        cid, meta, invs = cl["claim_id"], claim_meta[cl["claim_id"]], inv_by_claim[cl["claim_id"]]
        cd = date.fromisoformat(cl["claim_date"])
        trans = [("SUBMITTED", cd)]
        approved, decision, pay_total, last_pay = None, None, 0, None
        d1 = cd + _days(1 if meta["fast"] else rng.randint(1, 5))
        if d1 <= REF_DATE:
            trans.append(("UNDER_REVIEW", d1))
            d2 = d1 + _days(0 if meta["fast"] else rng.randint(2, 25))
            if d2 <= REF_DATE:
                rejected = rng.random() < 0.12 and not meta["force_approve"]
                decision = d2
                if rejected:
                    trans.append(("REJECTED", d2))
                    approved = 0
                else:
                    factor = 1.0 if meta["force_approve"] else rng.uniform(0.7, 1.0)
                    approved = int(cl["claimed_cents"] * factor) // 100 * 100
                    trans.append(("APPROVED", d2))
                    mode = "ALL" if meta["force_approve"] else rng.choices(["ALL", "FIRST", "NONE"], [85, 5, 10])[0]
                    if mode == "FIRST" and len(invs) == 1:
                        mode = "ALL"
                    total_inv = sum(i["amount_cents"] for i in invs)
                    alloc = [approved * i["amount_cents"] // total_inv for i in invs]
                    alloc[-1] = approved - sum(alloc[:-1])
                    paid_idx = {"ALL": range(len(invs)), "FIRST": range(1), "NONE": range(0)}[mode]
                    for k in paid_idx:
                        lag = rng.randint(0, 1) if meta["fast"] else rng.randint(1, 10)
                        pdate = max(d2, date.fromisoformat(invs[k]["invoice_date"])) + _days(lag)
                        if pdate <= REF_DATE and alloc[k] > 0:
                            payments_raw.append({"claim_id": cid, "invoice_id": invs[k]["invoice_id"],
                                                 "payment_date": iso(pdate), "amount_cents": alloc[k],
                                                 "payment_method": rng.choice(["BANK_TRANSFER", "CHEQUE", "UPI"])})
                            pay_total += alloc[k]
                            last_pay = pdate if last_pay is None else max(last_pay, pdate)
                    if pay_total > 0:
                        trans.append(("PAID" if pay_total == approved else "PARTIALLY_PAID", last_pay))
        cl["status"] = trans[-1][0]
        cl["approved_cents"] = approved
        cl["decision_date"] = iso(decision) if decision else None
        for step, (to_status, d) in enumerate(trans):
            transitions.append((iso(d), cid, step, trans[step - 1][0] if step else None, to_status))

    # ---------------- injected exception: payment exceeds approved amount
    paid_by_group = defaultdict(list)
    for cl in claims:
        if cl["status"] == "PAID":
            paid_by_group[claim_meta[cl["claim_id"]]["network_id"]].append(cl)
    overpaid = []
    for p in plans:
        if p["pattern"] == "provider_collusion" and paid_by_group.get(p["network_id"]):
            overpaid.append((rng.choice(paid_by_group[p["network_id"]]), p["network_id"]))
    standalone = paid_by_group.get(None, [])
    for cl in rng.sample(standalone, min(cfg["overpaid_standalone"], len(standalone))):
        overpaid.append((cl, ""))
    for cl, net in overpaid:
        last_inv = inv_by_claim[cl["claim_id"]][-1]
        last_date = max(date.fromisoformat(p["payment_date"]) for p in payments_raw if p["claim_id"] == cl["claim_id"])
        payments_raw.append({"claim_id": cl["claim_id"], "invoice_id": last_inv["invoice_id"],
                             "payment_date": iso(min(last_date + _days(rng.randint(1, 7)), REF_DATE)),
                             "amount_cents": max(100, int(cl["approved_cents"] * rng.uniform(0.1, 0.35)) // 100 * 100),
                             "payment_method": "BANK_TRANSFER"})

    payments_raw.sort(key=lambda p: (p["payment_date"], p["claim_id"], p["invoice_id"], p["amount_cents"]))
    payments = [{"payment_id": f"PAY-{YEAR}-{i:06d}", **p} for i, p in enumerate(payments_raw, 1)]
    transitions.sort()
    events = [{"event_id": f"CEV-{i:06d}", "claim_id": cid, "from_status": fr, "to_status": to, "event_date": d}
              for i, (d, cid, _step, fr, to) in enumerate(transitions, 1)]

    # ---------------- injected exception: claim -> nonexistent policy (goes to quarantine, never to claims)
    quarantine, quarantined_claim_ids = [], []
    for q in range(1, cfg["quarantined_claims"] + 1):
        claim_id = f"CLAIM-{YEAR}-{len(claims) + q:06d}"
        payload = {"claim_id": claim_id, "claimant_id": rng.choice(base_ids),
                   "policy_id": f"POL-{YEAR}-{900000 + q}", "claim_date": iso(date(2026, 1, 1) + _days(rng.randint(0, 150))),
                   "claimed_cents": rng.randint(20, 90) * 100000}
        quarantine.append({"quarantine_id": f"QRN-{q:06d}", "entity_type": "CLAIM", "entity_id": claim_id,
                           "issue_type": "CLAIM_NONEXISTENT_POLICY",
                           "raw_payload": json.dumps(payload, sort_keys=True),
                           "reason": f"policy_id {payload['policy_id']} does not exist in policies",
                           "quarantined_date": iso(REF_DATE)})
        quarantined_claim_ids.append(claim_id)

    # ---------------- observed relationship edges
    hidden_set = {frozenset((a, b)) for _, a, b in hidden_pairs}
    edges = _build_edges(rng, cfg, claimants, policies, claims, invoices, hidden_set)

    tables = {"claimants": claimants, "providers": providers, "policies": policies, "incidents": incidents,
              "claims": claims, "claim_status_events": events, "invoices": invoices, "payments": payments,
              "relationship_edges": edges, "quarantine_records": quarantine}
    for name, cols in __import__("src.database", fromlist=["TABLE_COLUMNS"]).TABLE_COLUMNS.items():
        if name in tables:   # fail fast if a generated row has unexpected/missing keys
            assert all(set(r) == set(cols) for r in tables[name][:50]), f"column mismatch in {name}"
    assert len(claims) == cfg["claims"] and len(claimants) == cfg["claimants"] and len(providers) == cfg["providers"]
    assert len(edges) == cfg["edges"]

    ground_truth = _build_ground_truth(plans, claims, claim_meta, invoices, households, hidden_pairs,
                                       overpaid, quarantined_claim_ids)
    return Dataset(tables=tables, ground_truth=ground_truth, scale=scale, seed=seed)


# ------------------------------------------------------------------------- edges
def _build_edges(rng, cfg, claimants, policies, claims, invoices, hidden_set) -> list[dict]:
    cl = {c["claimant_id"]: c for c in claimants}
    claim_by = {c["claim_id"]: c for c in claims}
    store = {}

    def add(etype, stype, sid, dtype, did, evidence, eff):
        store[(etype, sid, did)] = {"edge_type": etype, "src_type": stype, "src_id": sid, "dst_type": dtype,
                                    "dst_id": did, "evidence": evidence, "effective_from": eff, "source": "OBSERVED"}

    # mandatory edges: shared contact details / address
    for field, etype in (("phone", "SHARES_PHONE"), ("email", "SHARES_EMAIL"), ("address", "SHARES_ADDRESS")):
        groups = defaultdict(list)
        for c in claimants:
            key = (c["address_line"], c["city"], c["postal_code"]) if field == "address" else c[field]
            groups[key].append(c["claimant_id"])
        for ids in groups.values():
            for a, b in combinations(sorted(ids), 2):
                if etype == "SHARES_EMAIL" and frozenset((a, b)) in hidden_set:
                    continue          # planted relationship deliberately missing from the observed edges
                add(etype, "CLAIMANT", a, "CLAIMANT", b, f"shared {field}",
                    max(cl[a]["registered_date"], cl[b]["registered_date"]))

    # mandatory edges: claimant-provider (via invoices)
    pairs = defaultdict(set)
    for inv in invoices:
        pairs[(claim_by[inv["claim_id"]]["claimant_id"], inv["provider_id"])].add(inv["claim_id"])
    for (cid, pid), claim_ids in pairs.items():
        add("CLAIMANT_PROVIDER", "CLAIMANT", cid, "PROVIDER", pid, f"claims={len(claim_ids)}",
            min(claim_by[x]["claim_date"] for x in claim_ids))

    needed = cfg["edges"] - len(store)
    if needed < 0:
        raise ValueError(f"Mandatory edges ({len(store)}) exceed the target ({cfg['edges']}); raise the target.")

    # low-signal structural edges fill the remainder (random, seeded)
    fill = [("CLAIMANT_POLICY", "CLAIMANT", p["claimant_id"], "POLICY", p["policy_id"], "owns policy", p["start_date"])
            for p in policies]
    seen = set()
    for inv in invoices:
        key = (inv["claim_id"], inv["provider_id"])
        if key not in seen:
            seen.add(key)
            fill.append(("CLAIM_PROVIDER", "CLAIM", inv["claim_id"], "PROVIDER", inv["provider_id"],
                         "invoiced by provider", claim_by[inv["claim_id"]]["claim_date"]))
    if len(fill) < needed:
        raise ValueError("Not enough structural edges to reach the edge target.")
    rng.shuffle(fill)
    for args in fill[:needed]:
        add(*args)

    rows = sorted(store.values(), key=lambda r: (r["edge_type"], r["src_id"], r["dst_id"]))
    return [{"edge_id": f"EDG-{i:06d}", **r} for i, r in enumerate(rows, 1)]


# ------------------------------------------------------------------ ground truth
def _build_ground_truth(plans, claims, claim_meta, invoices, households, hidden_pairs, overpaid, quarantined):
    networks, members, anomalies = [], [], []
    inv_by_claim = defaultdict(list)
    for inv in invoices:
        inv_by_claim[inv["claim_id"]].append(inv["invoice_id"])
    claims_by_net = defaultdict(list)
    for cl in claims:
        claims_by_net[claim_meta[cl["claim_id"]]["network_id"]].append(cl)

    def anomaly(issue, etype, eid, net, decision, note):
        anomalies.append({"anomaly_id": f"ANM-{len(anomalies) + 1:04d}", "issue_type": issue, "entity_type": etype,
                          "entity_id": eid, "network_id": net, "expected_decision": decision, "note": note})

    for p in plans:
        net = p["network_id"]
        networks.append({"network_id": net, "pattern": p["pattern"], "n_claimants": len(p["member_ids"]),
                         "n_claims": len(claims_by_net[net]), "description": p["pattern"].replace("_", " ")})
        for cid in p["member_ids"].values():
            members.append({"network_id": net, "entity_type": "CLAIMANT", "entity_id": cid, "role": "MEMBER"})
        for pid in p["providers"]:
            members.append({"network_id": net, "entity_type": "PROVIDER", "entity_id": pid, "role": "SHARED_PROVIDER"})
        for cl in claims_by_net[net]:
            members.append({"network_id": net, "entity_type": "CLAIM", "entity_id": cl["claim_id"], "role": "CLAIM"})
            if claim_meta[cl["claim_id"]]["dup"]:
                for inv_id in inv_by_claim[cl["claim_id"]]:
                    anomaly("DUPLICATE_INVOICE_ACROSS_CLAIMANTS", "INVOICE", inv_id, net, "REVIEW_RECOMMENDED",
                            "same provider, ref, amount, service date and description on two claimants' claims")
    for net, a, b in hidden_pairs:
        anomaly("PLANTED_EDGE_NOT_IN_OBSERVED_EDGES", "RELATIONSHIP", f"{a}|{b}", net, "INFER_FROM_ATTRIBUTES",
                "shared email exists on both claimants but no SHARES_EMAIL edge was recorded")
    for cl, net in overpaid:
        anomaly("PAYMENT_EXCEEDS_APPROVED", "CLAIM", cl["claim_id"], net, "EXCEPTION_REVIEW",
                "total payments exceed approved_cents")
    for cid in quarantined:
        anomaly("CLAIM_NONEXISTENT_POLICY", "CLAIM", cid, "", "DATA_EXCEPTION_REVIEW",
                "claim references a policy that does not exist (quarantined)")
    benign, benign_claimants = [], set()
    for gid, mem, attr in households:
        for m in mem:
            benign.append({"group_id": gid, "claimant_id": m, "shared_attribute": attr})
            benign_claimants.add(m)
        anomaly("BENIGN_SHARED_ADDRESS", "CLAIMANT", mem[0], "", "NO_FLAG_FROM_ADDRESS_ALONE",
                f"household {gid}: {len(mem)} claimants share address ({attr}); not evidence of fraud")

    exceptions = defaultdict(list)
    for a in anomalies:
        if a["entity_type"] == "CLAIM" and a["issue_type"] == "PAYMENT_EXCEEDS_APPROVED":
            exceptions[a["entity_id"]].append(a["issue_type"])
    labels = []
    for cl in claims:
        net = claim_meta[cl["claim_id"]]["network_id"]
        labels.append({"claim_id": cl["claim_id"], "claimant_id": cl["claimant_id"], "network_id": net or "",
                       "is_suspicious_network": 1 if net else 0,
                       "data_exception_type": ";".join(exceptions.get(cl["claim_id"], [])),
                       "benign_household_member": 1 if cl["claimant_id"] in benign_claimants else 0})
    rows = {"networks": networks, "network_members": members, "anomalies": anomalies,
            "benign_groups": benign, "claim_labels": labels}
    return {name: (GT_COLUMNS[name], rows[name]) for name in GT_COLUMNS}