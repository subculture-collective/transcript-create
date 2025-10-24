#!/usr/bin/env python3
"""Run Alembic database migrations.

This script runs pending Alembic migrations against the database specified
in the DATABASE_URL environment variable or app settings.

Usage:
    python scripts/run_migrations.py [command]

Commands:
    upgrade    - Apply all pending migrations (default)
    downgrade  - Downgrade one migration
    current    - Show current migration revision
    history    - Show migration history
    stamp      - Stamp the database with a specific revision (for existing databases)

Examples:
    # Apply all pending migrations
    python scripts/run_migrations.py upgrade

    # Downgrade one migration
    python scripts/run_migrations.py downgrade

    # Show current revision
    python scripts/run_migrations.py current

    # Stamp existing database at baseline (for databases created from schema.sql)
    python scripts/run_migrations.py stamp head
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic.config import Config

from alembic import command


def run_migrations(alembic_command: str = "upgrade", revision: str = "head"):
    """Run Alembic migrations.

    Args:
        alembic_command: The Alembic command to run (upgrade, downgrade, current, history, stamp)
        revision: The revision to migrate to (default: head for upgrade, -1 for downgrade)
    """
    # Get the alembic.ini path
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"

    # Create Alembic config
    alembic_cfg = Config(str(alembic_ini_path))

    # Run the specified command
    if alembic_command == "upgrade":
        print(f"Running migrations: upgrade to {revision}")
        command.upgrade(alembic_cfg, revision)
        print("✓ Migrations applied successfully")
    elif alembic_command == "downgrade":
        print(f"Running migrations: downgrade to {revision}")
        command.downgrade(alembic_cfg, revision)
        print("✓ Downgrade completed successfully")
    elif alembic_command == "current":
        print("Current migration revision:")
        command.current(alembic_cfg, verbose=True)
    elif alembic_command == "history":
        print("Migration history:")
        command.history(alembic_cfg, verbose=True)
    elif alembic_command == "stamp":
        print(f"Stamping database at revision: {revision}")
        command.stamp(alembic_cfg, revision)
        print("✓ Database stamped successfully")
    else:
        print(f"Unknown command: {alembic_command}")
        print("Valid commands: upgrade, downgrade, current, history, stamp")
        sys.exit(1)


def get_default_revision(cmd: str) -> str:
    """Return the default revision for a given Alembic command."""
    if cmd in ("upgrade", "stamp"):
        return "head"
    elif cmd == "downgrade":
        return "-1"
    else:
        return ""

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    rev = sys.argv[2] if len(sys.argv) > 2 else get_default_revision(cmd)

    try:
        run_migrations(cmd, rev)
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        sys.exit(1)
