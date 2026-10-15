"""Add checkpoint_revision to decision_run_checkpoints for CAS and lease fencing."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_checkpoint_revision_and_lease_fencing"
down_revision = "0027_workspace_isolation_and_checkpoint_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decision_run_checkpoints",
        sa.Column("checkpoint_revision", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    with op.batch_alter_table("decision_run_checkpoints") as batch_op:
        batch_op.drop_column("checkpoint_revision")
