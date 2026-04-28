"""No-op placeholder to keep revision chain valid.

Revision ID: f1acbe59c6cf
Revises: b6068e3005fd
Create Date: 2026-04-28
"""

# revision identifiers, used by Alembic.
revision = "f1acbe59c6cf"
down_revision = "b6068e3005fd"
branch_labels = None
depends_on = None


def upgrade():
    # Intentionally empty.
    pass


def downgrade():
    pass
