import io
import re
from datetime import datetime

from app.agents.base import Agent
from app.data import store
from app.models import Claim, DocumentInfo, Finding

EDITOR_TOOLS = re.compile(r"photoshop|gimp|canva|illustrator|pixlr|paint|coreldraw|inkscape|word|libreoffice|wps", re.I)
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

        for doc in documents:
            tag = doc.filename
            if doc.content_type not in ALLOWED_TYPES:
                f.append(Finding(code="UNEXPECTED_FILE_TYPE", severity="medium", detail=f"{tag}: type {doc.content_type}."))
                continue
            if doc.sha256 in store.SEEN_DOC_HASHES:
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
        if EDITOR_TOOLS.search(producer):
            out.append(Finding(code="EDITING_SOFTWARE", severity="medium",
                               detail=f"{tag}: created or edited with '{producer.strip()}', not typical for hospital billing systems."))
        created = _parse_pdf_date(meta.get("/CreationDate"))
        modified = _parse_pdf_date(meta.get("/ModDate"))
        if created and modified and (modified - created).total_seconds() > 3600:
            out.append(Finding(code="MODIFIED_AFTER_CREATION", severity="medium",
                               detail=f"{tag}: modified {(modified - created).days} day(s) after creation."))
        if created and created.date() < claim.admission_date:
            out.append(Finding(code="DOC_CREATED_BEFORE_ADMISSION", severity="high",
                               detail=f"{tag}: file created {created.date()}, before admission {claim.admission_date}."))
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
        if software and EDITOR_TOOLS.search(software):
            out.append(Finding(code="EDITING_SOFTWARE", severity="high", detail=f"{tag}: image edited with '{software}'."))
        if not exif:
            out.append(Finding(code="METADATA_STRIPPED", severity="low", detail=f"{tag}: image has no EXIF data."))
        return out
