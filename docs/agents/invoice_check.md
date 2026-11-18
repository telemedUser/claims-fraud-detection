# Invoice Check agent (billing)

Code: `app/agents/invoice_check.py`. Findings map to **Billing_Intelligence**, with duplicates mapped to **Duplicate_Detection**, in `app/core/legacy_adapter.py`. Bill text comes from `app/core/doc_text.py`.

## What it checks

| Group | Code | Severity | Fires when | |
|---|---|---|---|---|
| Arithmetic | `INVOICE_TOTAL_MISMATCH`, `CLAIM_VS_INVOICE_MISMATCH`, `NON_POSITIVE_LINE_ITEM`, `NO_LINE_ITEMS` | high / high / medium / high | totals or line items don't add up | |
| Plausibility | `ROUND_TOTAL`, `DUPLICATE_LINE_ITEMS`, `AMOUNT_ABOVE_TYPICAL_FOR_DIAGNOSIS`, `STAY_LONGER_THAN_TYPICAL`, `INVOICE_DATE_OUT_OF_RANGE` | low–medium | unusual totals, repeats, cost or stay, bill date | |
| **GST** | `GSTIN_INVALID` | high (confirmed) | a GSTIN on the bill (typed or printed) fails the format or check-digit test | new |
| | `GST_CHARGED_WITHOUT_GSTIN` | medium | GST charged with no valid GSTIN | new |
| | `GST_SPLIT_MISMATCH` | medium | CGST and SGST/UTGST not equal halves, or only one charged | new |
| | `GST_MIXED_IGST` | medium | IGST and CGST/SGST on the same bill | new |
| | `GST_ON_EXEMPT_SERVICES` | low | GST charged on treatment that is generally exempt | new |
| **Duplicates** | `DUPLICATE_INVOICE` | high | same hospital and exact bill number as an earlier claim | |
| | `DUPLICATE_INVOICE_VARIANT` | high | same hospital, same number once spaces, dashes and leading zeros are ignored | new |
| | `DUPLICATE_BILL_NEW_NUMBER` | high | same hospital, bill date and total under a different number | new |
| | `INVOICE_NUMBER_AT_OTHER_HOSPITAL` | low | the same number on a claim at another hospital | new |
| **Payment** | `CASHLESS_BILL_CLAIMED` | high | the bill's payment mode is cashless, insurer or TPA, yet reimbursement is claimed | new |
| | `BILL_PAYMENT_PENDING` | medium | the bill shows a balance due | new |
| | `CLAIM_EXCEEDS_AMOUNT_PAID` | high | the claimed amount is more than the amount paid (bill and receipts) | new |
| | `PAYMENT_NOT_EVIDENCED` | low | no payment shown on the bill and no receipt uploaded | new |
| | `PAYMENT_DATE_OUT_OF_RANGE` | medium | the payment date is before admission or after submission | new |

- **No GST is not a finding.** A missing GSTIN, or no GST on the bill, is never flagged, because most hospital services are GST-exempt (non-negotiable rule 5).
- **Payment sources:** payment details come from the bill's payment block (Payment mode, Amount paid, Balance due, Receipt No., Paid on) and from an optional **Payment receipt** upload, a new document type in the journey.
- **Registry GSTIN:** the GSTIN on the bill is compared with the registry by the Provider Profile agent (`TAX_ID_MISMATCH`, `DOC_GSTIN_MISMATCH`).

## LLM usage (switch on)

- **Tool `get_bill_details`:** bill number, dates, totals, GST lines and payment fields read from the bill and receipts. **No patient name, policy number or claimant ID.**
- **The claim it sees:** the pseudonymised claim, with line items and amounts.
- **What it looks for:** charges unreasonable for the diagnosis and stay, inflated or vague items, GST on items that should be exempt, or payment details that look inconsistent.
- **Live example:** `EXCESSIVE_CONSULTATION_CHARGES`, ₹1,00,000 in consultations for one night with viral fever.
- **Effect:** observations are shown and scored as potential anomalies (capped at 15 points for this agent and 25 per claim).

## Demo data

- **Suspicious and high-risk bills:** payment mode "Cashless (insurer / TPA)" with ₹1,00,000 due, so `CASHLESS_BILL_CLAIMED`, `BILL_PAYMENT_PENDING` and `CLAIM_EXCEEDS_AMOUNT_PAID` fire. The high-risk bill also has an invalid GSTIN, so `GSTIN_INVALID` fires.
- **Clean, borderline and fabricated bills:** paid in full with a receipt number.

## Limitations

- **Format checks only:** GSTIN validity is format and check digit. Registration status isn't queried from GSTN.
- **Payment proof:** payment comes from printed text. Receipt numbers aren't yet checked across claims for reuse.
- **Duplicate search:** it scans the same hospital's invoices plus numbers sharing the last four characters. A large production database would need an index on the normalised number.
