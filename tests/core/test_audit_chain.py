from dataclasses import replace
from datetime import datetime, timezone

from app.core.audit_chain import GENESIS_PREV_HASH, append, verify_chain


def _fields(i):
    return {
        "ts": datetime(2024, 1, 1, 0, 0, i, tzinfo=timezone.utc),
        "actor_id": "u1",
        "event_type": "x",
        "entity_type": "claim",
        "entity_id": str(i),
        "request_id": f"r{i}",
        "detail": {"n": i, "b": [1, 2]},
    }


def _chain(n=5):
    events, tail = [], None
    for i in range(n):
        tail = append(tail, _fields(i))
        events.append(tail)
    return events


def test_valid_chain():
    ev = _chain()
    assert ev[0].prev_hash == GENESIS_PREV_HASH
    assert [e.seq for e in ev] == [1, 2, 3, 4, 5]
    assert verify_chain(ev) is None
    assert verify_chain([]) is None


def test_tamper_detail():
    ev = _chain()
    ev[2] = replace(ev[2], detail={"n": 99})
    assert verify_chain(ev) == 3


def test_reorder():
    ev = _chain()
    ev[1], ev[2] = ev[2], ev[1]
    assert verify_chain(ev) == 3


def test_delete_middle():
    ev = _chain()
    del ev[2]
    assert verify_chain(ev) == 4


def test_wrong_prev_hash():
    ev = _chain()
    ev[3] = replace(ev[3], prev_hash="f" * 64)
    assert verify_chain(ev) == 4


def test_bad_genesis():
    ev = _chain()
    ev[0] = replace(ev[0], prev_hash="f" * 64)
    assert verify_chain(ev) == 1
