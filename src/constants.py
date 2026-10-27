"""Shared constants: seed, ID year, enumerations. Single source of truth."""

DEFAULT_SEED = 20261022
YEAR = 2026

INCIDENT_TYPES = {
    "MOTOR": ("COLLISION", "THEFT", "WINDSHIELD_DAMAGE", "VANDALISM"),
    "HEALTH": ("HOSPITALIZATION", "OUTPATIENT_TREATMENT", "SURGERY"),
    "PROPERTY": ("FIRE", "WATER_DAMAGE", "BURGLARY", "STORM_DAMAGE"),
}

ENUMS = {
    "policy_type": tuple(INCIDENT_TYPES),
    "policy_status": ("ACTIVE", "EXPIRED", "CANCELLED"),
    "provider_type": ("REPAIRER", "MEDICAL", "TOWING", "ASSESSOR"),
    "provider_status": ("ACTIVE", "INACTIVE"),
    "incident_type": tuple(t for v in INCIDENT_TYPES.values() for t in v),
    "claim_status": ("SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED",
                     "PARTIALLY_PAID", "PAID"),
    "payment_method": ("BANK_TRANSFER", "CHEQUE", "UPI"),
    "edge_type": ("SHARES_PHONE", "SHARES_EMAIL", "SHARES_ADDRESS",
                  "CLAIMANT_PROVIDER", "CLAIMANT_POLICY", "CLAIM_PROVIDER"),
    "edge_entity": ("CLAIMANT", "PROVIDER", "POLICY", "CLAIM"),
    "severity": ("LOW", "MEDIUM", "HIGH"),
    "subject_type": ("CLAIM", "NETWORK"),
    "investigation_status": ("OPEN", "IN_REVIEW", "ESCALATED",
                             "CLOSED_NO_ACTION", "CLOSED_ACTION_TAKEN"),
    "investigation_event_type": ("OPENED", "STATUS_CHANGE", "NOTE", "DECISION"),
}