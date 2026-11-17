"""Property test for the audit hash chain. Requirements 17.5, 17.6."""
from dataclasses import replace
from datetime import datetime

from hypothesis import assume, given, settings, strategies as st

from app.core.audit_chain import HASHED_FIELDS, append, verify_chain

_text = st.text(max_size=20)
_ts = st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1))
_detail = st.dictionaries(st.text(max_size=8), st.integers(-1000, 1000), max_size=4)

_field_values = {
    "ts": _ts,
    "actor_id": _text,
    "event_type": _text,
    "entity_type": _text,
    "entity_id": _text,
    "request_id": _text,
    "detail": _detail,
}

_fields = st.fixed_dictionaries(_field_values)


def _build(field_list):
    events, tail = [], None
    for f in field_list:
        tail = append(tail, f)
        events.append(tail)
    return events


chains = st.lists(_fields, min_size=1, max_size=12).map(_build)


@st.composite
def _chain_and_mutation(draw):
    events = draw(chains)
    k = draw(st.integers(0, len(events) - 1))
    name = draw(st.sampled_from(HASHED_FIELDS))
    new = draw(_field_values[name])
    assume(new != getattr(events[k], name))
    return events, k, name, new


def _pos(events, seq):
    return [e.seq for e in events].index(seq)


# Feature: claims-fraud-detection-service, Property 27: Audit chain integrity
# **Validates: Requirements 17.5, 17.6**
@settings(max_examples=100)
@given(chains)
def test_built_chain_verifies(events):
    assert verify_chain(events) is None


# Feature: claims-fraud-detection-service, Property 27: Audit chain integrity
# **Validates: Requirements 17.5, 17.6**
@settings(max_examples=100)
@given(_chain_and_mutation())
def test_field_mutation_detected_at_or_before_k(data):
    events, k, name, new = data
    mutated = list(events)
    mutated[k] = replace(events[k], **{name: new})
    bad = verify_chain(mutated)
    assert bad is not None
    assert _pos(mutated, bad) <= k


# Feature: claims-fraud-detection-service, Property 27: Audit chain integrity
# **Validates: Requirements 17.5, 17.6**
@settings(max_examples=100)
@given(st.data())
def test_deletion_detected_at_or_before_successor(data):
    # Deleting the first or last event leaves a valid (partial) chain, so only
    # interior events are deleted.
    events = data.draw(st.lists(_fields, min_size=3, max_size=12).map(_build))
    k = data.draw(st.integers(1, len(events) - 2))
    remaining = events[:k] + events[k + 1:]
    bad = verify_chain(remaining)
    assert bad is not None
    assert _pos(remaining, bad) <= k  # the successor now sits at position k


# Feature: claims-fraud-detection-service, Property 27: Audit chain integrity
# **Validates: Requirements 17.5, 17.6**
@settings(max_examples=100)
@given(st.data())
def test_swap_detected_at_or_before_first_affected(data):
    events = data.draw(st.lists(_fields, min_size=2, max_size=12).map(_build))
    i = data.draw(st.integers(0, len(events) - 2))
    j = data.draw(st.integers(i + 1, len(events) - 1))
    swapped = list(events)
    swapped[i], swapped[j] = swapped[j], swapped[i]
    bad = verify_chain(swapped)
    assert bad is not None
    # A swapped-in first event is accepted as a partial-chain anchor, so
    # detection can land on position 1 when i == 0.
    assert _pos(swapped, bad) <= max(i, 1)
