"""Append-only supervisor reviews: advisory findings attached to historical runs."""

import sqlalchemy as sa
from alembic import op

revision = "0002_supervisor_reviews"
down_revision = "0001_genesis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supervisor_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("classifier_id", sa.String(36), sa.ForeignKey("classifiers.id"), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("classification_runs.id"), nullable=False),
        sa.Column(
            "ontology_version_id",
            sa.String(36),
            sa.ForeignKey("ontology_versions.id"),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    # run_id is deliberately not unique: multiple providers may review the same run.
    op.create_index("ix_supervisor_reviews_classifier_id", "supervisor_reviews", ["classifier_id"])
    op.create_index("ix_supervisor_reviews_run_id", "supervisor_reviews", ["run_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """CREATE TRIGGER immutable_supervisor_reviews
               BEFORE UPDATE OR DELETE ON supervisor_reviews
               FOR EACH ROW EXECUTE FUNCTION openclass_immutable()"""
        )
    else:
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"""CREATE TRIGGER immutable_supervisor_reviews_{operation.lower()}
                    BEFORE {operation} ON supervisor_reviews BEGIN
                    SELECT RAISE(ABORT, 'OpenClass history is append-only'); END"""
            )


def downgrade() -> None:
    op.drop_table("supervisor_reviews")
