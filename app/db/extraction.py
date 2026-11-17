"""Persist extraction output and normalised facts."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.extraction.base import ExtractionOutput
from app.core.normalise import normalise_fields
from app.db.models import ExtractionResult, NormalisedFact


def store_extraction(session: Session, *, claim_id: uuid.UUID, document_id: uuid.UUID, adapter: str,
                     output: ExtractionOutput) -> tuple[list[ExtractionResult], list[NormalisedFact]]:
    """Replace any earlier results for the document. One ExtractionResult row per page (fields on that
    page, file metadata on every row); one NormalisedFact row per extracted field."""
    for model in (ExtractionResult, NormalisedFact):
        for row in session.scalars(select(model).where(model.document_id == document_id)):
            session.delete(row)
    session.flush()

    pages = output.pages or [{"page": 1, "text": ""}]
    results = []
    for p in pages:
        page_fields = [f for f in output.fields if f.get("page") == p["page"]]
        row = ExtractionResult(document_id=document_id, adapter=adapter, page=p["page"], text=p["text"],
                               fields=page_fields, metadata_=dict(output.metadata))
        session.add(row)
        results.append(row)

    facts = []
    for nf in normalise_fields(output.fields):
        row = NormalisedFact(claim_id=claim_id, document_id=document_id, field=nf.field,
                             original_value=nf.original, normalised_value=nf.normalised,
                             page=nf.page, source_field=nf.source_field)
        session.add(row)
        facts.append(row)
    session.flush()
    return results, facts
