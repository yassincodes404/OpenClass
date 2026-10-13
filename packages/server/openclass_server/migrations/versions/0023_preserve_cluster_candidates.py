"""Preserve cluster_candidates, candidate_evidence, and candidate_reviews across re-clustering."""

import sqlalchemy as sa
from alembic import op

revision = "0023_preserve_cluster_candidates"
down_revision = "0022_integration_routes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "unknown_clusters",
        sa.Column("decision_service_id", sa.String(36), nullable=True),
    )
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))
        op.create_table(
            "cluster_candidates_new",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column(
                "cluster_id",
                sa.String(36),
                sa.ForeignKey("unknown_clusters.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("type", sa.String(30), nullable=False),
            sa.Column("canonical_name", sa.String(200), nullable=True),
            sa.Column("display_name", sa.String(200), nullable=True),
            sa.Column("definition", sa.Text(), nullable=True),
            sa.Column("aliases", sa.JSON(), nullable=False),
            sa.Column("existing_match", sa.String(200), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("provider", sa.String(50), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.execute(
            sa.text(
                """
                INSERT INTO cluster_candidates_new (
                    id, project_id, cluster_id, type, canonical_name, display_name,
                    definition, aliases, existing_match, confidence, reason, status,
                    provider, created_at
                )
                SELECT
                    id, project_id, cluster_id, type, canonical_name, display_name,
                    definition, aliases, existing_match, confidence, reason, status,
                    provider, created_at
                FROM cluster_candidates
                """
            )
        )
        op.drop_table("cluster_candidates")
        op.rename_table("cluster_candidates_new", "cluster_candidates")
        op.create_index(
            "ix_cluster_candidates_project_id",
            "cluster_candidates",
            ["project_id"],
        )
        op.execute(sa.text("PRAGMA foreign_keys=ON"))
    else:
        inspector = sa.inspect(bind)
        for fk in inspector.get_foreign_keys("cluster_candidates"):
            fk_name = fk.get("name")
            if fk.get("constrained_columns") == ["cluster_id"] and isinstance(fk_name, str):
                op.drop_constraint(fk_name, "cluster_candidates", type_="foreignkey")
        op.alter_column(
            "cluster_candidates",
            "cluster_id",
            existing_type=sa.String(36),
            nullable=True,
        )
        op.create_foreign_key(
            "fk_cluster_candidates_cluster_id_unknown_clusters",
            "cluster_candidates",
            "unknown_clusters",
            ["cluster_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint(
            "fk_cluster_candidates_cluster_id_unknown_clusters",
            "cluster_candidates",
            type_="foreignkey",
        )
    op.drop_column("unknown_clusters", "decision_service_id")
