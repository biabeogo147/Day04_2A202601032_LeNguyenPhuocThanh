"""Allow sessions to own optional conversation context."""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "context",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    with op.batch_alter_table("sessions") as batch:
        batch.alter_column(
            "profile_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )


def downgrade() -> None:
    connection = op.get_bind()
    anonymous_session_ids = sa.select(sa.column("id")).select_from(
        sa.table(
            "sessions",
            sa.column("id"),
            sa.column("profile_id"),
        )
    ).where(sa.column("profile_id").is_(None))
    run_ids = sa.select(sa.column("id")).select_from(
        sa.table(
            "runs",
            sa.column("id"),
            sa.column("session_id"),
        )
    ).where(sa.column("session_id").in_(anonymous_session_ids))
    connection.execute(
        sa.delete(sa.table("trace_events", sa.column("run_id"))).where(
            sa.column("run_id").in_(run_ids)
        )
    )
    connection.execute(
        sa.delete(sa.table("runs", sa.column("session_id"))).where(
            sa.column("session_id").in_(anonymous_session_ids)
        )
    )
    connection.execute(
        sa.delete(sa.table("messages", sa.column("session_id"))).where(
            sa.column("session_id").in_(anonymous_session_ids)
        )
    )
    connection.execute(
        sa.delete(sa.table("sessions", sa.column("profile_id"))).where(
            sa.column("profile_id").is_(None)
        )
    )
    with op.batch_alter_table("sessions") as batch:
        batch.alter_column(
            "profile_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch.drop_column("context")
