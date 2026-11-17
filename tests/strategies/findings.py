from datetime import datetime, timezone

from hypothesis import strategies as st

from app.core.finding import Finding

from tests.strategies.finding_drafts import finding_drafts

_CLAIM_ID = st.uuids(version=4)
_RUN_ID = st.uuids(version=4)
_CREATED = st.just(datetime(2024, 1, 1, tzinfo=timezone.utc))


@st.composite
def findings(draw, claim_id=None, run_id=None) -> Finding:
    """A persisted Finding.

    Fact keys come from a tiny alphabet (see finding_drafts), so independent
    draws collide on correlation_key often. Sources are optional so unions
    vary between group members.
    """
    draft = draw(finding_drafts())
    draft = draft.model_copy(
        update={"source_field": draw(st.sampled_from([None, "f1", "f2", "f3"]))}
    )
    return Finding.from_draft(
        draft,
        finding_id=draw(st.uuids(version=4)),
        claim_id=claim_id or draw(_CLAIM_ID),
        run_id=run_id or draw(_RUN_ID),
        created_at=draw(_CREATED),
        rule_version="v1",
    )


def finding_lists(max_size: int = 12):
    """Lists of findings with unique finding_id and a shared claim/run."""
    return st.lists(findings(), max_size=max_size, unique_by=lambda f: f.finding_id)
