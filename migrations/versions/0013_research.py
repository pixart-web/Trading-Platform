"""Immutable research plans/results, durable holdout consumption and model evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_studies",
        sa.Column("study_id", sa.Uuid(), primary_key=True),
        sa.Column("plan_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_table(
        "research_reports",
        sa.Column("report_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "study_id", sa.Uuid(), sa.ForeignKey("research_studies.study_id"), nullable=False
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_table(
        "research_holdout_consumption",
        sa.Column("asset_id", sa.String(128), primary_key=True),
        sa.Column(
            "study_id", sa.Uuid(), sa.ForeignKey("research_studies.study_id"), nullable=False
        ),
        sa.Column("selection_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_table(
        "research_model_registry",
        sa.Column("artifact_id", sa.Uuid(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_table(
        "research_model_events",
        sa.Column(
            "artifact_id",
            sa.Uuid(),
            sa.ForeignKey("research_model_registry.artifact_id"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    # Export claims before downgrade. Removing consumption history invalidates holdout governance.
    for name in (
        "research_model_events",
        "research_model_registry",
        "research_holdout_consumption",
        "research_reports",
        "research_studies",
    ):
        op.drop_table(name)
