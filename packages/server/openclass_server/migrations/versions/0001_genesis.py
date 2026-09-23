"""Genesis snapshots and atomic classification history.

Definitions are frozen here rather than importing mutable application metadata.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_genesis"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "classifiers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "ontology_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("classifier_id", sa.String(36), sa.ForeignKey("classifiers.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(36), sa.ForeignKey("ontology_versions.id")),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("classifier_id", "version_number"),
    )
    op.create_table(
        "observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "classification_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "observation_id", sa.String(36), sa.ForeignKey("observations.id"), nullable=False
        ),
        sa.Column("classifier_id", sa.String(36), sa.ForeignKey("classifiers.id"), nullable=False),
        sa.Column(
            "ontology_version_id",
            sa.String(36),
            sa.ForeignKey("ontology_versions.id"),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "unknown_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("classifier_id", sa.String(36), sa.ForeignKey("classifiers.id"), nullable=False),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("classification_runs.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "ontology_events",
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("id", sa.String(36), nullable=False, unique=True),
        sa.Column("classifier_id", sa.String(36), sa.ForeignKey("classifiers.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    for table in ("ontology_versions", "classification_runs", "unknown_events", "ontology_events"):
        op.create_index(f"ix_{table}_classifier_id", table, ["classifier_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION openclass_immutable() RETURNS trigger AS $$
                      BEGIN RAISE EXCEPTION 'OpenClass history is append-only'; END;
                      $$ LANGUAGE plpgsql""")
        for table in ("ontology_versions", "ontology_events"):
            op.execute(f"""CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {table}
                           FOR EACH ROW EXECUTE FUNCTION openclass_immutable()""")
    else:
        for table in ("ontology_versions", "ontology_events"):
            for operation in ("UPDATE", "DELETE"):
                op.execute(f"""CREATE TRIGGER immutable_{table}_{operation.lower()}
                    BEFORE {operation} ON {table} BEGIN
                    SELECT RAISE(ABORT, 'OpenClass history is append-only'); END""")


def downgrade() -> None:
    for table in (
        "ontology_events",
        "unknown_events",
        "classification_runs",
        "observations",
        "ontology_versions",
        "classifiers",
    ):
        op.drop_table(table)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION openclass_immutable()")
    # Leave the shared vector extension installed.
