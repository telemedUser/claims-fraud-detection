from datetime import datetime, timezone
from uuid import uuid4

from hypothesis import strategies as st

from app.core.finding import DetectionMethod, FactKey, FindingDraft, FindingStatus

statuses = st.sampled_from(list(FindingStatus))
methods = st.sampled_from(list(DetectionMethod))
capped_methods = st.sampled_from([DetectionMethod.AI, DetectionMethod.ML])
uncapped_methods = st.sampled_from(
    [m for m in DetectionMethod if m not in (DetectionMethod.AI, DetectionMethod.ML)]
)


@st.composite
def finding_drafts(draw, method=methods, status=statuses) -> FindingDraft:
    return FindingDraft(
        use_case_id=draw(st.integers(1, 40)),
        check_id=draw(st.text("abcdefgh_0123456789", min_size=1, max_size=12)),
        agent="Billing_Intelligence",
        category="billing",
        severity=draw(st.sampled_from(["low", "medium", "high"])),
        status=draw(status),
        explanation="x",
        method=draw(method),
        fact_key=FactKey("t", draw(st.text("abc", max_size=4)), ()),
    )


def finding_kwargs() -> dict:
    return dict(
        finding_id=uuid4(),
        claim_id=uuid4(),
        run_id=uuid4(),
        created_at=datetime.now(timezone.utc),
        rule_version="v1",
    )
