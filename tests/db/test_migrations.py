"""Alembic migrations create and drop the full schema (task 8.3)."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db.models import Base

ROOT = Path(__file__).resolve().parents[2]


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "app" / "db" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_creates_all_tables_and_downgrade_removes_them(tmp_path):
    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    cfg = _config(url)

    command.upgrade(cfg, "head")
    assert _tables(url) == set(Base.metadata.tables)

    command.downgrade(cfg, "base")
    assert _tables(url) == set()


def test_upgrade_preserves_columns_and_constraints(tmp_path):
    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    command.upgrade(_config(url), "head")
    engine = create_engine(url)
    try:
        insp = inspect(engine)
        for name, table in Base.metadata.tables.items():
            assert {c["name"] for c in insp.get_columns(name)} == {c.name for c in table.columns}, name
            assert len(insp.get_foreign_keys(name)) == len(table.foreign_key_constraints), name
        uniques = {u["name"] for u in insp.get_unique_constraints("documents")}
        assert "uq_documents_claim_sha256" in uniques
    finally:
        engine.dispose()
