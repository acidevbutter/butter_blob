"""document blob processing states

Revision ID: blob_processing_states
Revises: 81a60bb21391
Create Date: 2026-09-06 21:15:00.000000

The status and action columns are VARCHAR, so the new application enum values
need no database DDL. This revision records their introduction in the migration
chain for deployments that track schema/application compatibility.
"""

from collections.abc import Sequence

revision: str = "blob_processing_states"
down_revision: str | None = "81a60bb21391"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
