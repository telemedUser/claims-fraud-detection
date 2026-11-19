import type { DemoKind } from '../../api'

/** One-click demo scenarios. Kinds match app/seed/docgen.py. `score` is the expected final score from the weighted
 *  rules (agent weights in app/rules/risk_scoring.v1.yaml); with LLM analysis on, the LLM can add up to 25 points.
 *  `look` says where to see the issue. */
export type Scenario = { kind: DemoKind; title: string; agent: string; score: number; look: string }

export const SCENARIO_GROUPS: { label: string; items: Scenario[] }[] = [
  {
    label: 'Overall',
    items: [
      { kind: 'small_claim', title: 'Small claim, auto-approved', agent: 'All agents', score: 0,
        look: 'Same-day fever visit for 1,830. Low risk and below the 2,000 limit, so it is auto-approved.' },
      { kind: 'clean', title: 'Genuine claim', agent: 'All agents', score: 0,
        look: 'Appendectomy at City General for 41,850. Every agent passes, but above 2,000 a person still reviews it.' },
      { kind: 'suspicious', title: 'Suspicious claim', agent: 'All agents', score: 100,
        look: 'Many red flags at once: duplicate bill, claimed 1,20,000 against a 1,00,000 bill, cashless bill, altered lab report.' },
    ],
  },
  {
    label: 'Bill (Invoice Validation)',
    items: [
      { kind: 'bill_overclaim', title: 'Claimed more than billed', agent: 'Invoice Validation', score: 90,
        look: 'Claim form says 48,500. The bill total and the amount paid are 41,850.' },
      { kind: 'bill_duplicate', title: 'Bill number already used', agent: 'Invoice Validation', score: 56,
        look: 'Bill INV-1001 was already claimed at City General in January.' },
      { kind: 'bill_unpaid', title: 'Bill not fully paid', agent: 'Invoice Validation', score: 53,
        look: 'Bill shows 30,000 paid and 11,850 balance due, but the full 41,850 is claimed.' },
    ],
  },
  {
    label: 'Documents (Document Forensics)',
    items: [
      { kind: 'docs_mismatch', title: 'Details differ across documents', agent: 'Document Forensics', score: 38,
        look: 'Discharge summary names patient "S. Verma" and a discharge date 2 days later than the bill.' },
      { kind: 'docs_edited', title: 'Files saved by Photoshop', agent: 'Document Forensics', score: 75,
        look: 'Not visible on the page: open the PDF properties to see Producer "Adobe Photoshop 25.0".' },
    ],
  },
  {
    label: 'Medical records (Medical Review)',
    items: [
      { kind: 'medical_mismatch', title: "Treatment doesn't fit the diagnosis", agent: 'Medical Review', score: 30,
        look: 'Viral fever with an antibiotic (Azithromycin) on the prescription and an ICU day on the bill.' },
      { kind: 'medical_lab_altered', title: 'Lab report altered, wrong ICD code', agent: 'Medical Review', score: 42,
        look: 'Lab report shows platelets 85,000 (the lab issued 2,10,000); discharge summary codes viral fever as A97.0 (dengue).' },
    ],
  },
  {
    label: 'Hospital and doctor (Provider Profile)',
    items: [
      { kind: 'provider_mismatch', title: 'Wrong GSTIN, doctor outside specialty', agent: 'Provider Profile', score: 45,
        look: "Bill header shows Lakeview's GSTIN 27AAACL4444D1ZT; the appendectomy is under an orthopaedic surgeon." },
    ],
  },
  {
    label: 'Policyholder (User Profile)',
    items: [
      { kind: 'history_flags', title: 'Earlier denied claim, frequent claims', agent: 'User Profile', score: 32,
        look: 'R. Singh (POL-2002) had a claim denied and made 3 claims in 90 days. The documents themselves are clean.' },
    ],
  },
]

export const SCENARIOS: Scenario[] = SCENARIO_GROUPS.flatMap((g) => g.items)
