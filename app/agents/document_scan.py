import io
import re
from datetime import datetime

from app.agents.base import Agent
from app.db.repos import open_repos
from app.models import Claim, DocumentInfo, Finding

# Exact (normalised) producer names of image/document editors. Matching is never by substring.
EDITOR_PRODUCERS = frozenset({
    "adobe photoshop", "adobe illustrator", "gimp", "canva", "pixlr", "microsoft paint", "paint",
    "coreldraw", "inkscape", "microsoft word", "libreoffice writer", "wps office", "wps writer",
})

# Document types for which a creation date before admission is expected (no finding).
PRE_ADMISSION_EXEMPT_TYPES = frozenset({"prescription", "medical_report"})

# Configurable gap (hours) between creation and modification before a finding is raised, per doc type.
MOD_GAP_HOURS = {"medical_bill": 1.0, "prescription": 24.0, "medical_report": 24.0, "other": 24.0}
MAX_SEVERITY = "medium"
ALTERNATIVE_EXPLANATIONS = ("alternative explanations: the document may have been re-saved, annotated, "
                            "digitally signed, re-exported or converted by the provider or claimant, or "
                            "reissued as a corrected copy; verify with the provider before drawing conclusions")


def normalise_producer(value) -> str:
    """Lower-case and drop versions/punctuation: 'Adobe Photoshop 25.0' -> 'adobe photoshop'."""
    v = re.sub(r"\(.*?\)", " ", str(value or "").lower())
    v = re.sub(r"\bv?\d+(\.\d+)*\b", " ", v)
    v = re.sub(r"[^a-z ]+", " ", v)
    return " ".join(v.split())


def is_editor(*values) -> bool:
    return any(normalise_producer(v) in EDITOR_PRODUCERS for v in values if v)

ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}


def _parse_pdf_date(s: str | None):
    # PDF dates look like D:20260115103000+05'30'
    if not s:
        return None
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", s)
    if not m:
        return None
    parts = [int(x) if x else 0 for x in m.groups()]
    try:
        return datetime(*parts)
    except ValueError:
        return None


class DocumentScanAgent(Agent):
    """Inspects uploaded files: type, duplicates, and PDF/image metadata."""
    name = "document_scan"

    async def analyze(self, claim: Claim, documents: list[DocumentInfo]):
        f: list[Finding] = []
        if not documents:
            f.append(Finding(code="NO_DOCUMENTS", severity="high", detail="No supporting documents were uploaded."))
            return self.result(f)

        types = {d.doc_type for d in documents}
        if types != {"other"}:  # only when the client labelled the documents
            if "medical_bill" not in types:
                f.append(Finding(code="MISSING_MEDICAL_BILL", severity="medium", detail="No itemised medical bill was uploaded."))
            if "medical_report" not in types:
                f.append(Finding(code="MISSING_MEDICAL_REPORT", severity="low", detail="No medical report or discharge summary was uploaded."))

        with open_repos() as repos:
            reused = repos.seen_doc_hashes(d.sha256 for d in documents)
        for doc in documents:
            tag = doc.filename
            if doc.content_type not in ALLOWED_TYPES:
                f.append(Finding(code="UNEXPECTED_FILE_TYPE", severity="medium", detail=f"{tag}: type {doc.content_type}."))
                continue
            if doc.sha256 in reused:
                f.append(Finding(code="DOCUMENT_REUSED", severity="high", detail=f"{tag}: identical file was used in an earlier claim."))
            if doc.content_type == "application/pdf":
                f.extend(self._scan_pdf(tag, doc, claim))
            else:
                f.extend(self._scan_image(tag, doc, claim))
        return self.result(f)

    def _scan_pdf(self, tag, doc, claim):
        out: list[Finding] = []
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(doc.data))
            meta = reader.metadata or {}
        except Exception:
            return [Finding(code="PDF_UNREADABLE", severity="medium", detail=f"{tag}: could not parse PDF.")]
        producer = " ".join(str(meta.get(k, "")) for k in ("/Producer", "/Creator"))
        if is_editor(meta.get("/Producer"), meta.get("/Creator")):
            out.append(Finding(code="EDITING_SOFTWARE", severity=MAX_SEVERITY,
                               detail=f"{tag}: created or edited with '{producer.strip()}', not typical for hospital billing systems; {ALTERNATIVE_EXPLANATIONS}."))
        created = _parse_pdf_date(meta.get("/CreationDate"))
        modified = _parse_pdf_date(meta.get("/ModDate"))
        gap_h = MOD_GAP_HOURS.get(doc.doc_type, MOD_GAP_HOURS["other"])
        if created and modified and (modified - created).total_seconds() > gap_h * 3600:
            out.append(Finding(code="MODIFIED_AFTER_CREATION", severity="low",
                               detail=f"{tag}: modified {(modified - created).days} day(s) after creation "
                                      f"(threshold {gap_h:g}h for {doc.doc_type}); {ALTERNATIVE_EXPLANATIONS}."))
        if (created and doc.doc_type not in PRE_ADMISSION_EXEMPT_TYPES
                and created.date() < claim.admission_date):
            out.append(Finding(code="DOC_CREATED_BEFORE_ADMISSION", severity=MAX_SEVERITY,
                               detail=f"{tag}: file created {created.date()}, before admission {claim.admission_date}; "
                                      f"{ALTERNATIVE_EXPLANATIONS}."))
        if not meta:
            out.append(Finding(code="METADATA_STRIPPED", severity="low", detail=f"{tag}: PDF has no metadata."))
        return out

    def _scan_image(self, tag, doc, claim):
        out: list[Finding] = []
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(doc.data))
            exif = img.getexif()
        except Exception:
            return [Finding(code="IMAGE_UNREADABLE", severity="medium", detail=f"{tag}: could not parse image.")]
        software = str(exif.get(305, ""))  # Software tag
        if software and is_editor(software):
            out.append(Finding(code="EDITING_SOFTWARE", severity=MAX_SEVERITY,
                               detail=f"{tag}: image software tag '{software}' is an editor; {ALTERNATIVE_EXPLANATIONS}."))
        if not exif:
            out.append(Finding(code="METADATA_STRIPPED", severity="low", detail=f"{tag}: image has no EXIF data."))
        return out
