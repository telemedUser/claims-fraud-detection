"""Helpers for tests that check what the database holds (replacement for reading store.py globals)."""
from sqlalchemy import select

from app.db import models as m
from app.db.repos import open_repos


def db_snapshot() -> tuple[frozenset, frozenset, frozenset]:
    """Ids of every claim, invoice and document row. Equal snapshots mean nothing was written."""
    with open_repos() as repos:
        s = repos.session
        return (frozenset(s.scalars(select(m.Claim.id))), frozenset(s.scalars(select(m.Invoice.id))),
                frozenset(s.scalars(select(m.Document.id))))
