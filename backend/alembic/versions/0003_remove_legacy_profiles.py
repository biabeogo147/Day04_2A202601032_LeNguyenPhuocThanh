"""Remove legacy profiles and keep conversation context on sessions."""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT
                sessions.id AS session_id,
                sessions.context AS session_context,
                profiles.age_group,
                profiles.goals,
                profiles.conditions,
                profiles.medications,
                profiles.allergies,
                profiles.pregnancy_status,
                profiles.budget_max_vnd,
                profiles.preferred_dosage_forms
            FROM sessions
            LEFT JOIN profiles ON profiles.id = sessions.profile_id
            WHERE sessions.profile_id IS NOT NULL
            """
        )
    ).mappings()
    for row in rows:
        existing = json.loads(row["session_context"] or "{}")
        if not existing:
            existing = {
                "age_group": row["age_group"],
                "goals": json.loads(row["goals"] or "[]"),
                "conditions": json.loads(row["conditions"] or "[]"),
                "medications": json.loads(row["medications"] or "[]"),
                "allergies": json.loads(row["allergies"] or "[]"),
                "pregnancy_status": row["pregnancy_status"],
                "budget_max_vnd": row["budget_max_vnd"],
                "preferred_dosage_forms": json.loads(
                    row["preferred_dosage_forms"] or "[]"
                ),
            }
        connection.execute(
            sa.text("UPDATE sessions SET context = :context WHERE id = :session_id"),
            {"context": json.dumps(existing, ensure_ascii=False), "session_id": row["session_id"]},
        )

    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("profile_id")
    op.drop_table("profiles")


def downgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("age_group", sa.String(length=32), nullable=False),
        sa.Column("goals", sa.JSON(), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("medications", sa.JSON(), nullable=False),
        sa.Column("allergies", sa.JSON(), nullable=False),
        sa.Column("pregnancy_status", sa.String(length=32), nullable=False),
        sa.Column("budget_max_vnd", sa.Integer(), nullable=False),
        sa.Column("preferred_dosage_forms", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("profile_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_sessions_profile_id_profiles",
            "profiles",
            ["profile_id"],
            ["id"],
        )
