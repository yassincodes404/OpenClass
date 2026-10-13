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
        op.execute(
            sa.text(
                """
                CREATE TABLE cluster_candidates_new (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
                    cluster_id VARCHAR(36) NULL REFERENCES unknown_clusters(id) ON DELETE SET NULL,
                    type VARCHAR(30) NOT NULL,
                    canonical_name VARCHAR(200) NULL,
                    display_name VARCHAR(200) NULL,
                    definition TEXT NULL,
                    aliases JSON NOT NULL,
                    existing_match VARCHAR(200) NULL,
                    confidence FLOAT NOT NULL,
                    reason TEXT NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
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
        op.execute(sa.text("DROP TABLE cluster_candidates"))
        op.execute(sa.text("ALTER TABLE cluster_candidates_new RENAME TO cluster_candidates"))
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
