"""No-op: suppress MSSQL DATETIME2 churn

Revision ID: b6068e3005fd
Revises: 6802e919005e
Create Date: 2026-04-28 01:33:58.444479

"""
# revision identifiers, used by Alembic.
revision = 'b6068e3005fd'
down_revision = '6802e919005e'
branch_labels = None
depends_on = None


def upgrade():
    # Intentionally empty — SQL Server columns are already valid.
    pass


def downgrade():
    pass
