"""Runtime-role grants and append-only enforcement.

The app connects as mesh_app, which gets DML on every table except the ledger and audit
tables, where it may only SELECT and INSERT. Triggers refuse UPDATE and DELETE on every
append-only table for any role (the owner included), and refuse TRUNCATE unless the
session sets mesh.allow_reset = 'on' (only the demo reset does, as the owner).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "mesh_app"
LEDGER_AND_AUDIT = ("journal_entries", "postings", "audit_events")
OTHER_APPEND_ONLY = (
    "invoice_versions",
    "confirmations",
    "run_computations",
    "statements",
    "approvals",
)


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            EXECUTE 'GRANT USAGE ON SCHEMA public TO {APP_ROLE}';
            EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
                     TO {APP_ROLE}';
            EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}';
            EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public
                     GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}';
            EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public
                     GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}';
            EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON {", ".join(LEDGER_AND_AUDIT)}
                     FROM {APP_ROLE}';
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION mesh_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'TRUNCATE' AND current_setting('mesh.allow_reset', true) = 'on' THEN
            RETURN NULL;
          END IF;
          RAISE EXCEPTION 'table % is append-only: % refused', TG_TABLE_NAME, TG_OP
            USING ERRCODE = 'insufficient_privilege';
        END $$;
        """
    )
    for table in (*LEDGER_AND_AUDIT, *OTHER_APPEND_ONLY):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION mesh_forbid_change()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION mesh_forbid_change()"
        )


def downgrade() -> None:
    for table in (*LEDGER_AND_AUDIT, *OTHER_APPEND_ONLY):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS mesh_forbid_change()")
