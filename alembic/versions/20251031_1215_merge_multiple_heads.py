"""merge_multiple_heads

Create a merge revision that consolidates multiple parallel heads into a
single linear head so automated 'upgrade to head' works in CI and the
migrations container. This revision is a no-op migration.

Revision ID: merge_multiple_heads_20251031
Revises: a1b2c3d4e5f6, security_hardening_001, 002_advanced_features
Create Date: 2025-10-31 12:15:00.000000

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "merge_multiple_heads_20251031"
down_revision: Union[str, Sequence[str], None] = (
    "a1b2c3d4e5f6",
    "security_hardening_001",
    "002_advanced_features",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge migration: brings multiple heads together."""
    # This is intentionally empty. It only exists to merge parallel
    # migration heads so Alembic can compute a single 'head'.
    pass


def downgrade() -> None:
    # Downgrade would be non-trivial in a merged graph; keep as no-op.
    pass
