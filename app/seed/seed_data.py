"""Fictional seed data: hospitals, doctors, diseases, policies, claim history and the demo scenarios.

Single source of truth. ``app/seed/run.py`` (database seeding), ``app/seed/docgen.py`` (demo documents) and
the disease catalogue in ``app/db/repos.py`` read from here. Plain data only: no imports from the rest of the
app, so it can be loaded anywhere.

All GSTINs carry a valid mod-36 check character (see ``app/core/validators/gstin.py``).
"""
from datetime import date

HOSPITALS = {
    "H001": {"name": "City General Hospital", "city": "Pune", "address": "12 MG Road, Pune, Maharashtra 411001",
             "phone": "+91 20 5555 0101", "registered": True, "tax_id": "27AAACC1111A1ZQ",
             "specialties": ["General Surgery", "General Medicine", "Orthopaedics"],
             "avg_claim": 45000, "std_claim": 15000, "flagged_claims_ratio": 0.02, "years_active": 18,
             "baseline_monthly_claims": 40, "state_code": "27", "bed_count": 250,
             "empanelled_from": "2015-01-01", "empanelled_to": None},
    "H002": {"name": "Sunrise Care Clinic", "city": "Nagpur", "address": "88 Wardha Road, Nagpur, Maharashtra 440015",
             "phone": "+91 712 555 0202", "registered": True, "tax_id": "27AAACS2222B1Z2",
             "specialties": ["General Medicine"],
             "avg_claim": 30000, "std_claim": 9000, "flagged_claims_ratio": 0.31, "years_active": 1,
             "baseline_monthly_claims": 6, "state_code": "27", "bed_count": 20,
             "empanelled_from": "2025-06-01", "empanelled_to": None},
    "H003": {"name": "Unlicensed Health Point", "city": "Nagpur", "address": "Shop 4, Station Road, Nagpur 440001",
             "phone": "+91 98 0000 0000", "registered": False, "tax_id": None, "specialties": [],
             "avg_claim": 20000, "std_claim": 5000, "flagged_claims_ratio": 0.55, "years_active": 0,
             "baseline_monthly_claims": 3, "state_code": "27", "bed_count": 4,
             "empanelled_from": None, "empanelled_to": None},  # never in an insurer network
    "H004": {"name": "Lakeview Multispeciality Hospital", "city": "Mumbai",
             "address": "3 Powai Lake Road, Mumbai, Maharashtra 400076", "phone": "+91 22 5555 0404",
             "registered": True, "tax_id": "27AAACL4444D1ZT",
             "specialties": ["General Medicine", "Orthopaedics", "Ophthalmology", "Urology"],
             "avg_claim": 60000, "std_claim": 20000, "flagged_claims_ratio": 0.03, "years_active": 12,
             "baseline_monthly_claims": 55, "state_code": "27", "bed_count": 400,
             "empanelled_from": "2016-04-01", "empanelled_to": None},
    "H005": {"name": "Green Valley Medical Centre", "city": "Bengaluru",
             "address": "21 Indiranagar 100ft Road, Bengaluru, Karnataka 560038", "phone": "+91 80 5555 0505",
             "registered": True, "tax_id": "29AAACG5555E1ZM",
             "specialties": ["General Medicine", "Pulmonology", "Ophthalmology"],
             "avg_claim": 35000, "std_claim": 12000, "flagged_claims_ratio": 0.04, "years_active": 9,
             "baseline_monthly_claims": 30, "state_code": "29", "bed_count": 150,
             "empanelled_from": "2018-07-01", "empanelled_to": None},
}

# ``licence_valid_to``: licence expiry on record (None = not on record).
# ``affiliation_dates``: hospital id -> (start, end) of the affiliation; end None = still active.
DOCTORS = {
    "D001": {"name": "Dr. Asha Rao", "qualification": "MBBS, MS (General Surgery)", "registration_no": "MMC-2009-11872",
             "specialty": "General Surgery", "license_valid": True, "hospital_ids": ["H001"],
             "claims_per_month": 40, "flagged_claims_ratio": 0.01, "licence_valid_to": "2029-12-31",
             "affiliation_dates": {"H001": ("2010-06-01", None)}},
    "D002": {"name": "Dr. K. Mehta", "qualification": "MBBS", "registration_no": None,
             "specialty": "General Medicine", "license_valid": True, "hospital_ids": ["H002", "H003", "H001"],
             "claims_per_month": 210, "flagged_claims_ratio": 0.28, "licence_valid_to": "2027-06-30",
             "affiliation_dates": {"H002": ("2025-06-01", None), "H003": ("2024-01-01", "2026-06-30"),
                                   "H001": ("2023-02-01", None)}},
    "D003": {"name": "Dr. Unknown", "qualification": "-", "registration_no": None, "specialty": "General Medicine",
             "license_valid": False, "hospital_ids": ["H003"], "claims_per_month": 15, "flagged_claims_ratio": 0.4,
             "licence_valid_to": "2024-03-31", "affiliation_dates": {"H003": ("2023-01-01", None)}},
    "D004": {"name": "Dr. Priya Nair", "qualification": "MBBS, MD (Medicine)", "registration_no": "MMC-2012-20431",
             "specialty": "General Medicine", "license_valid": True, "hospital_ids": ["H004"],
             "claims_per_month": 35, "flagged_claims_ratio": 0.02, "licence_valid_to": "2030-01-31",
             "affiliation_dates": {"H004": ("2014-03-01", None)}},
    "D005": {"name": "Dr. Vikram Shah", "qualification": "MBBS, MS (Ortho)", "registration_no": "MMC-2007-09114",
             "specialty": "Orthopaedics", "license_valid": True, "hospital_ids": ["H004", "H001"],
             "claims_per_month": 48, "flagged_claims_ratio": 0.03, "licence_valid_to": "2028-09-30",
             "affiliation_dates": {"H004": ("2012-08-01", None), "H001": ("2020-01-01", None)}},
    "D006": {"name": "Dr. Meera Iyer", "qualification": "MBBS, MD (Pulmonology)", "registration_no": "KMC-2011-55302",
             "specialty": "Pulmonology", "license_valid": True, "hospital_ids": ["H005"],
             "claims_per_month": 30, "flagged_claims_ratio": 0.01, "licence_valid_to": "2029-05-31",
             "affiliation_dates": {"H005": ("2015-09-01", None)}},
    "D007": {"name": "Dr. Arjun Menon", "qualification": "MBBS, MS (Ophthalmology)", "registration_no": "KMC-2014-61877",
             "specialty": "Ophthalmology", "license_valid": True, "hospital_ids": ["H005", "H004"],
             "claims_per_month": 52, "flagged_claims_ratio": 0.02, "licence_valid_to": "2031-02-28",
             "affiliation_dates": {"H005": ("2016-01-01", None), "H004": ("2019-04-01", None)}},
    # Invented doctor used by the fabricated-looking demo bill: no registration, not licensed.
    "D008": {"name": "Dr. R. Sharma", "qualification": "MBBS", "registration_no": None,
             "specialty": "Urology", "license_valid": False, "hospital_ids": ["H004"],
             "claims_per_month": 2, "flagged_claims_ratio": 0.0, "licence_valid_to": None,
             "affiliation_dates": {}},
}

# Disease catalogue with typical cost and stay, used for coverage and plausibility checks.
# ``specialties``: the specialties expected to treat the condition (Provider Profile specialty-fit checks).
DISEASES = {
    "appendicitis": {"name": "Acute appendicitis", "category": "Surgical", "typical_cost": [30000, 80000], "typical_stay_days": [2, 5],
                     "specialties": ["General Surgery"]},
    "viral_fever": {"name": "Viral fever", "category": "Medical", "typical_cost": [5000, 25000], "typical_stay_days": [0, 3],
                    "specialties": ["General Medicine", "Paediatrics", "Pulmonology"]},
    "dengue": {"name": "Dengue fever", "category": "Medical", "typical_cost": [15000, 60000], "typical_stay_days": [3, 7],
               "specialties": ["General Medicine", "Paediatrics"]},
    "pneumonia": {"name": "Pneumonia", "category": "Medical", "typical_cost": [30000, 90000], "typical_stay_days": [3, 8],
                  "specialties": ["General Medicine", "Pulmonology", "Paediatrics"]},
    "fracture": {"name": "Limb fracture (surgical fixation)", "category": "Orthopaedic", "typical_cost": [40000, 150000], "typical_stay_days": [2, 6],
                 "specialties": ["Orthopaedics"]},
    "cataract": {"name": "Cataract surgery", "category": "Ophthalmic", "typical_cost": [25000, 60000], "typical_stay_days": [0, 1],
                 "specialties": ["Ophthalmology"]},
    "kidney_stone": {"name": "Kidney stone (lithotripsy)", "category": "Urology", "typical_cost": [35000, 90000], "typical_stay_days": [1, 3],
                     "specialties": ["Urology"]},
    "cosmetic": {"name": "Cosmetic / aesthetic surgery", "category": "Elective", "typical_cost": [50000, 300000], "typical_stay_days": [0, 2],
                 "specialties": ["Plastic Surgery"]},
    "dental": {"name": "Dental treatment (outpatient)", "category": "Dental", "typical_cost": [2000, 40000], "typical_stay_days": [0, 0],
               "specialties": ["Dentistry"]},
}

POLICIES = {
    "POL-1001": {"holder_name": "A. Kumar", "claimant_id": "U001", "date_of_birth": "1992-04-18", "plan": "Family Floater Gold",
                 "sum_insured": 500000, "valid_from": "2026-01-01", "valid_to": "2026-12-31",
                 "network_hospital_ids": ["H001", "H004", "H005"],
                 "covered_disease_ids": ["appendicitis", "viral_fever", "dengue", "pneumonia", "fracture", "cataract", "kidney_stone"]},
    "POL-2002": {"holder_name": "R. Singh", "claimant_id": "U002", "date_of_birth": "1985-09-02", "plan": "Individual Silver",
                 "sum_insured": 300000, "valid_from": "2026-03-01", "valid_to": "2027-02-28",
                 "network_hospital_ids": ["H001", "H002", "H005"],
                 "covered_disease_ids": ["appendicitis", "viral_fever", "dengue", "pneumonia"]},
}

# claimant_id -> past claims
CLAIM_HISTORY = {
    "U001": [
        {"claim_id": "C-100", "date": date(2026, 1, 10), "amount": 18000, "hospital_id": "H001", "invoice_number": "INV-1001"},
    ],
    "U002": [
        {"claim_id": "C-200", "date": date(2026, 9, 1), "amount": 48000, "hospital_id": "H002", "invoice_number": "INV-2001"},
        {"claim_id": "C-201", "date": date(2026, 9, 20), "amount": 52000, "hospital_id": "H002", "invoice_number": "INV-2002"},
        {"claim_id": "C-202", "date": date(2026, 10, 15), "amount": 49500, "hospital_id": "H003", "invoice_number": "INV-2003"},
    ],
}

# Extra detail for the history claims above (kept separate so CLAIM_HISTORY keeps its shape).
# ``decision`` is the investigator outcome recorded for that claim (deny = identified as fraudulent).
HISTORY_DETAILS = {
    "C-100": {"admission": date(2026, 1, 8), "discharge": date(2026, 1, 9), "disease": "viral_fever", "decision": "approve"},
    "C-200": {"admission": date(2026, 8, 28), "discharge": date(2026, 8, 30), "disease": "viral_fever", "decision": "approve"},
    "C-201": {"admission": date(2026, 9, 16), "discharge": date(2026, 9, 18), "disease": "dengue", "decision": "approve"},
    "C-202": {"admission": date(2026, 10, 12), "discharge": date(2026, 10, 13), "disease": "viral_fever", "decision": "deny"},
}
# SIMULATED laboratory registry (app/core/lab_registry.py): report-number prefix -> lab. Keys are synthetic demo
# values used to compute the verification code printed on each generated lab report.
LABS = {
    "PCL": {"name": "Pune Central Laboratory", "city": "Pune", "key": "demo-lab-key-pcl-2026"},
    "NDL": {"name": "Nagpur Diagnostics", "city": "Nagpur", "key": "demo-lab-key-ndl-2026"},
    "LVL": {"name": "Lakeview Hospital Laboratory", "city": "Mumbai", "key": "demo-lab-key-lvl-2026"},
    "GVL": {"name": "Green Valley Lab Services", "city": "Bengaluru", "key": "demo-lab-key-gvl-2026"},
}
HOSPITAL_LAB = {"H001": "PCL", "H002": "NDL", "H003": "NDL", "H004": "LVL", "H005": "GVL"}

# Inactive account that owns seeded decisions. It has no usable password and a non-console role, so it can never log in.
SYSTEM_USER = {"username": "system", "role": "System"}

# invoice numbers already seen, per hospital (duplicate detection)
SEEN_INVOICES = {("H001", "INV-1001"), ("H002", "INV-2001"), ("H002", "INV-2002"), ("H003", "INV-2003")}

# Number of recent minimal claims seeded at H002 so its monthly volume far exceeds its baseline (6).
SURGE_CLAIMS_AT_H002 = 30

# The four demo scenarios of Requirement 1.4. ``case`` is a docgen case kind. ``expected`` is the intended
# outcome, asserted by the routing tests of task 9.4. ``preauth`` is stored on the claim (claims.preauth_amount).
SCENARIOS = {
    "clean": {"case": "clean", "invoice_number": "INV-DEMO-CLEAN", "expected": "low",
              "summary": "Appendectomy at City General with matching documents, valid GSTIN."},
    "high_risk": {"case": "high_risk", "invoice_number": "INV-2002", "expected": "investigate",
                  "summary": "Duplicate invoice, invalid GSTIN, 14-day stay for viral fever, provider volume surge."},
    "fabricated": {"case": "fabricated", "invoice_number": "INV-DEMO-FAB", "expected": "not_low",
                   "summary": "Editor-produced bill with a round total and an invented doctor."},
    "borderline": {"case": "borderline", "invoice_number": "INV-DEMO-BORDER", "expected": "manual_review",
                   "summary": "No discharge summary and the claim exceeds the pre-authorised amount."},
}
