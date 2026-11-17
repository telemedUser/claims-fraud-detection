"""In-memory data store seeded with fictional sample data.

Replace with real registries / a claims database in production. Agents and the API only use the
functions below, so swapping the backend does not touch agent code. `reset()` restores the seed.
"""
import copy
from datetime import date

_HOSPITALS = {
    "H001": {"name": "City General Hospital", "city": "Pune", "address": "12 MG Road, Pune, Maharashtra 411001",
             "phone": "+91 20 5555 0101", "registered": True, "tax_id": "27AAACC1111A1Z5",
             "specialties": ["General Surgery", "General Medicine", "Orthopaedics"],
             "avg_claim": 45000, "std_claim": 15000, "flagged_claims_ratio": 0.02, "years_active": 18},
    "H002": {"name": "Sunrise Care Clinic", "city": "Nagpur", "address": "88 Wardha Road, Nagpur, Maharashtra 440015",
             "phone": "+91 712 555 0202", "registered": True, "tax_id": "27AAACS2222B1Z9",
             "specialties": ["General Medicine"],
             "avg_claim": 30000, "std_claim": 9000, "flagged_claims_ratio": 0.31, "years_active": 1},
    "H003": {"name": "Unlicensed Health Point", "city": "Nagpur", "address": "Shop 4, Station Road, Nagpur 440001",
             "phone": "+91 98 0000 0000", "registered": False, "tax_id": None, "specialties": [],
             "avg_claim": 20000, "std_claim": 5000, "flagged_claims_ratio": 0.55, "years_active": 0},
    "H004": {"name": "Lakeview Multispeciality Hospital", "city": "Mumbai",
             "address": "3 Powai Lake Road, Mumbai, Maharashtra 400076", "phone": "+91 22 5555 0404",
             "registered": True, "tax_id": "27AAACL4444D1Z2",
             "specialties": ["General Medicine", "Orthopaedics", "Ophthalmology", "Urology"],
             "avg_claim": 60000, "std_claim": 20000, "flagged_claims_ratio": 0.03, "years_active": 12},
    "H005": {"name": "Green Valley Medical Centre", "city": "Bengaluru",
             "address": "21 Indiranagar 100ft Road, Bengaluru, Karnataka 560038", "phone": "+91 80 5555 0505",
             "registered": True, "tax_id": "29AAACG5555E1Z7",
             "specialties": ["General Medicine", "Pulmonology", "Ophthalmology"],
             "avg_claim": 35000, "std_claim": 12000, "flagged_claims_ratio": 0.04, "years_active": 9},
}

_DOCTORS = {
    "D001": {"name": "Dr. Asha Rao", "qualification": "MBBS, MS (General Surgery)", "registration_no": "MMC-2009-11872",
             "specialty": "General Surgery", "license_valid": True, "hospital_ids": ["H001"],
             "claims_per_month": 40, "flagged_claims_ratio": 0.01},
    "D002": {"name": "Dr. K. Mehta", "qualification": "MBBS", "registration_no": None,
             "specialty": "General Medicine", "license_valid": True, "hospital_ids": ["H002", "H003", "H001"],
             "claims_per_month": 210, "flagged_claims_ratio": 0.28},
    "D003": {"name": "Dr. Unknown", "qualification": "-", "registration_no": None, "specialty": "General Medicine",
             "license_valid": False, "hospital_ids": ["H003"], "claims_per_month": 15, "flagged_claims_ratio": 0.4},
    "D004": {"name": "Dr. Priya Nair", "qualification": "MBBS, MD (Medicine)", "registration_no": "MMC-2012-20431",
             "specialty": "General Medicine", "license_valid": True, "hospital_ids": ["H004"],
             "claims_per_month": 35, "flagged_claims_ratio": 0.02},
    "D005": {"name": "Dr. Vikram Shah", "qualification": "MBBS, MS (Ortho)", "registration_no": "MMC-2007-09114",
             "specialty": "Orthopaedics", "license_valid": True, "hospital_ids": ["H004", "H001"],
             "claims_per_month": 48, "flagged_claims_ratio": 0.03},
    "D006": {"name": "Dr. Meera Iyer", "qualification": "MBBS, MD (Pulmonology)", "registration_no": "KMC-2011-55302",
             "specialty": "Pulmonology", "license_valid": True, "hospital_ids": ["H005"],
             "claims_per_month": 30, "flagged_claims_ratio": 0.01},
    "D007": {"name": "Dr. Arjun Menon", "qualification": "MBBS, MS (Ophthalmology)", "registration_no": "KMC-2014-61877",
             "specialty": "Ophthalmology", "license_valid": True, "hospital_ids": ["H005", "H004"],
             "claims_per_month": 52, "flagged_claims_ratio": 0.02},
}

# Disease catalogue with typical cost and stay, used for coverage and plausibility checks.
DISEASES = {
    "appendicitis": {"name": "Acute appendicitis", "category": "Surgical", "typical_cost": [30000, 80000], "typical_stay_days": [2, 5]},
    "viral_fever": {"name": "Viral fever", "category": "Medical", "typical_cost": [5000, 25000], "typical_stay_days": [0, 3]},
    "dengue": {"name": "Dengue fever", "category": "Medical", "typical_cost": [15000, 60000], "typical_stay_days": [3, 7]},
    "pneumonia": {"name": "Pneumonia", "category": "Medical", "typical_cost": [30000, 90000], "typical_stay_days": [3, 8]},
    "fracture": {"name": "Limb fracture (surgical fixation)", "category": "Orthopaedic", "typical_cost": [40000, 150000], "typical_stay_days": [2, 6]},
    "cataract": {"name": "Cataract surgery", "category": "Ophthalmic", "typical_cost": [25000, 60000], "typical_stay_days": [0, 1]},
    "kidney_stone": {"name": "Kidney stone (lithotripsy)", "category": "Urology", "typical_cost": [35000, 90000], "typical_stay_days": [1, 3]},
    "cosmetic": {"name": "Cosmetic / aesthetic surgery", "category": "Elective", "typical_cost": [50000, 300000], "typical_stay_days": [0, 2]},
    "dental": {"name": "Dental treatment (outpatient)", "category": "Dental", "typical_cost": [2000, 40000], "typical_stay_days": [0, 0]},
}

_POLICIES = {
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
_CLAIM_HISTORY = {
    "U001": [
        {"claim_id": "C-100", "date": date(2026, 1, 10), "amount": 18000, "hospital_id": "H001", "invoice_number": "INV-1001"},
    ],
    "U002": [
        {"claim_id": "C-200", "date": date(2026, 9, 1), "amount": 48000, "hospital_id": "H002", "invoice_number": "INV-2001"},
        {"claim_id": "C-201", "date": date(2026, 9, 20), "amount": 52000, "hospital_id": "H002", "invoice_number": "INV-2002"},
        {"claim_id": "C-202", "date": date(2026, 10, 15), "amount": 49500, "hospital_id": "H003", "invoice_number": "INV-2003"},
    ],
}

# invoice numbers already seen, per hospital (duplicate detection)
_SEEN_INVOICES = {("H001", "INV-1001"), ("H002", "INV-2001"), ("H002", "INV-2002"), ("H003", "INV-2003")}

HOSPITALS: dict = {}
DOCTORS: dict = {}
POLICIES: dict = {}
CLAIM_HISTORY: dict = {}
SEEN_INVOICES: set = set()
SEEN_DOC_HASHES: set[str] = set()  # document hashes already submitted (reused documents)


def reset() -> None:
    """Restores the seed data in place (other modules hold references to these objects)."""
    for live, seed in ((HOSPITALS, _HOSPITALS), (DOCTORS, _DOCTORS), (POLICIES, _POLICIES), (CLAIM_HISTORY, _CLAIM_HISTORY)):
        live.clear()
        live.update(copy.deepcopy(seed))
    SEEN_INVOICES.clear()
    SEEN_INVOICES.update(_SEEN_INVOICES)
    SEEN_DOC_HASHES.clear()


reset()


def hospital(hid):
    return HOSPITALS.get(hid)


def doctor(did):
    return DOCTORS.get(did)


def disease(disease_id):
    return DISEASES.get(disease_id)


def policy(policy_number):
    return POLICIES.get(policy_number)


def doctors_at(hospital_id):
    return {did: d for did, d in DOCTORS.items() if hospital_id in d["hospital_ids"] and d["license_valid"]}


def history(claimant_id):
    return CLAIM_HISTORY.get(claimant_id, [])


def invoice_seen(hospital_id, invoice_number):
    return (hospital_id, invoice_number) in SEEN_INVOICES


def register_claim(claim, doc_hashes):
    SEEN_INVOICES.add((claim.hospital_id, claim.invoice.invoice_number))
    SEEN_DOC_HASHES.update(doc_hashes)
    CLAIM_HISTORY.setdefault(claim.claimant_id, []).append({
        "claim_id": claim.claim_id, "date": claim.submitted_on, "amount": claim.claimed_amount,
        "hospital_id": claim.hospital_id, "invoice_number": claim.invoice.invoice_number,
    })
