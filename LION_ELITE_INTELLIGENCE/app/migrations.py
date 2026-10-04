"""Additive schema migrations.

`Base.metadata.create_all()` creates tables that do not exist yet. It does
**not** alter tables that do. So adding a column to an existing model is
silently a no-op against a database that already has that table — the model
declares the column, the ORM selects it, and Postgres rejects the query with
`column leads.organization_id does not exist`. The app would come up and then
fail on first read.

There is no Alembic in this project and introducing it mid-flight would mean
stamping a baseline against a live database. This runner is the smaller tool
that fits what is already here: a list of idempotent, additive statements
applied at startup, in order, each safe to run any number of times.

Rules for anything added here:

* Additive only. No DROP, no type narrowing, no NOT NULL on an existing table
  without a default — a deploy must never be able to lose a column or reject
  rows that were already valid.
* Idempotent. Every statement re-runs harmlessly, because startup runs on every
  deploy and on every worker process.
* New columns on existing tables are nullable. A backfill is a separate,
  explicit step; a migration that cannot complete without one is a migration
  that fails halfway.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("lion-elite-migrations")

# (table, column, type) — applied as ADD COLUMN when absent.
#
# Postgres supports `ADD COLUMN IF NOT EXISTS`; SQLite (the local default in
# database.py) does not, so presence is checked with the inspector instead of
# relying on dialect syntax. That keeps one code path for both.
ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    # Multi-tenancy. `leads` and `opportunities` predate the Organization model
    # and were global: every organization could read every other's leads. These
    # are nullable because existing rows have no owner yet — see
    # `backfill_organization_id`, which assigns them to the first organization
    # rather than guessing per row.
    ("leads", "organization_id", "INTEGER"),
    ("opportunities", "organization_id", "INTEGER"),
    # Provenance for records that arrived from BuildPipeline rather than being
    # entered by hand, so a bad import can be identified and reversed without
    # guessing from timestamps.
    ("leads", "source_system", "VARCHAR(50)"),
    ("leads", "external_id", "VARCHAR(255)"),
)

# Indexes to create when missing. Scoped lookups are the hot path once records
# carry an organization, and an unindexed tenant filter degrades every query.
ADDITIVE_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_leads_organization_id", "leads", "organization_id"),
    ("ix_opportunities_organization_id", "opportunities", "organization_id"),
    ("ix_leads_external_id", "leads", "external_id"),
)


def _existing_columns(engine: Engine, table: str) -> set[str]:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _existing_indexes(engine: Engine, table: str) -> set[str]:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table) if index.get("name")}


def run_migrations(engine: Engine) -> dict[str, list[str]]:
    """Apply additive migrations. Safe to call on every startup.

    Returns what it changed, so a deploy log says whether a column was added on
    this boot or was already there — the difference matters when a schema error
    appears and the question is whether the migration ran.
    """
    added_columns: list[str] = []
    added_indexes: list[str] = []

    with engine.begin() as connection:
        for table, column, column_type in ADDITIVE_COLUMNS:
            if table not in inspect(engine).get_table_names():
                # The table does not exist yet, so create_all will build it from
                # the model with this column already present. Nothing to add.
                continue
            if column in _existing_columns(engine, table):
                continue
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))
            added_columns.append(f"{table}.{column}")
            logger.info("migration: added column %s.%s", table, column)

    with engine.begin() as connection:
        for index_name, table, column in ADDITIVE_INDEXES:
            if table not in inspect(engine).get_table_names():
                continue
            if column not in _existing_columns(engine, table):
                continue
            if index_name in _existing_indexes(engine, table):
                continue
            connection.execute(text(f"CREATE INDEX {index_name} ON {table} ({column})"))
            added_indexes.append(index_name)
            logger.info("migration: created index %s", index_name)

    return {"columns": added_columns, "indexes": added_indexes}


def backfill_organization_id(engine: Engine) -> dict[str, int]:
    """Assign ownerless leads and opportunities to the first organization.

    Every lead in the database today was created before tenancy existed, and all
    of it belongs to Lion Elite — it is the only organization. Rather than
    inferring an owner per row, this assigns the lowest organization id, which
    is the Lion Elite workspace.

    It is deliberately conservative: it only touches rows where
    `organization_id IS NULL`, so it cannot move a record that has already been
    assigned, and it does nothing at all when no organization exists yet. A
    second organization signing up later never causes a re-assignment, because
    by then no rows are null.
    """
    tables = inspect(engine).get_table_names()
    if "organizations" not in tables:
        return {"leads": 0, "opportunities": 0}

    with engine.begin() as connection:
        first_org = connection.execute(text("SELECT MIN(id) FROM organizations")).scalar()
        if first_org is None:
            # No organization yet. Leaving rows null is correct — an unscoped row
            # is visible to nobody once reads are filtered, which is the safe
            # direction to fail.
            return {"leads": 0, "opportunities": 0}

        counts: dict[str, int] = {}
        for table in ("leads", "opportunities"):
            if table not in tables:
                counts[table] = 0
                continue
            if "organization_id" not in _existing_columns(engine, table):
                counts[table] = 0
                continue
            result = connection.execute(
                text(f"UPDATE {table} SET organization_id = :org WHERE organization_id IS NULL"),
                {"org": first_org},
            )
            counts[table] = result.rowcount or 0
            if counts[table]:
                logger.info("migration: assigned %s %s rows to organization %s", counts[table], table, first_org)

    return counts
