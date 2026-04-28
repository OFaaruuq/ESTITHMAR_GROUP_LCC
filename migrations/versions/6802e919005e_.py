"""No-op: suppress bogus DATETIME2 vs DateTime churn on SQL Server.

Revision ID: 6802e919005e
Revises:
Create Date: 2026-04-28 01:30:23.377641

Alembic autogenerate often emits ``ALTER COLUMN … DATETIME2 → DATETIME`` when metadata uses
generic ``DateTime``. On SQL Server this fails if the column has a default constraint and/or
indexes on that column (5074/4922).

The physical column type (DATETIME2) is already correct for SQLAlchemy. Do **not** apply those
alters; stamp this revision so ``alembic_version`` tracks deploys.

Future ``flask db migrate``: review diffs and strip datetime-only changes for MSSQL, or use
explicit ``mssql.DATETIME2()`` in models where needed so autogen stays quiet.
"""

# revision identifiers, used by Alembic.
revision = "6802e919005e"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Intentionally empty — see module docstring.
    pass


def downgrade():
    pass
