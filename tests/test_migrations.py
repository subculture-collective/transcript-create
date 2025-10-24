"""Tests for database migrations using Alembic.

These tests validate that migrations can be applied and reverted correctly.
"""

import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command


@pytest.fixture(scope="module")
def alembic_config():
    """Create Alembic config for testing."""
    # Get path to alembic.ini in the project root
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    return Config(str(alembic_ini_path))


@pytest.fixture(scope="module")
def test_db_url():
    """Get test database URL from environment."""
    return os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres")


@pytest.fixture(scope="function")
def clean_db(test_db_url):
    """Provide a clean database for each test."""
    engine = create_engine(test_db_url)

    # Drop all tables and alembic version
    with engine.begin() as conn:
        # Drop all tables in public schema
        conn.execute(
            text(
                """
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
            END $$;
        """
            )
        )

        # Drop all types
        conn.execute(
            text(
                """
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (
                    SELECT typname FROM pg_type
                    WHERE typtype = 'e'
                    AND typnamespace = 'public'::regnamespace::oid
                ) LOOP
                    EXECUTE 'DROP TYPE IF EXISTS ' || quote_ident(r.typname) || ' CASCADE';
                END LOOP;
            END $$;
        """
            )
        )

        # Drop all functions
        conn.execute(
            text(
                """
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT proname, oidvectortypes(proargtypes) as argtypes
                         FROM pg_proc INNER JOIN pg_namespace ns ON (pg_proc.pronamespace = ns.oid)
                         WHERE ns.nspname = 'public') LOOP
                    EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.proname) || '(' || r.argtypes || ') CASCADE';
                END LOOP;
            END $$;
        """
            )
        )

    engine.dispose()
    yield
    engine.dispose()


def test_migrations_upgrade_head(alembic_config, clean_db):
    """Test that all migrations can be applied successfully."""
    # Run upgrade to head
    command.upgrade(alembic_config, "head")

    # Verify key tables exist
    engine = create_engine(os.environ.get("DATABASE_URL"))
    with engine.begin() as conn:
        # Check that core tables exist
        result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"))
        tables = [row[0] for row in result]

        expected_tables = ["jobs", "videos", "transcripts", "segments", "users", "sessions", "favorites", "events"]
        for table in expected_tables:
            assert table in tables, f"Table {table} should exist after migrations"

    engine.dispose()


def test_migrations_downgrade_base(alembic_config, clean_db):
    """Test that all migrations can be applied and then reverted."""
    # Apply all migrations
    command.upgrade(alembic_config, "head")

    # Downgrade to base
    command.downgrade(alembic_config, "base")

    # Verify tables are removed
    engine = create_engine(os.environ.get("DATABASE_URL"))
    with engine.begin() as conn:
        result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        tables = [row[0] for row in result]

        # After downgrade, main tables should not exist (only alembic_version might remain)
        unexpected_tables = ["jobs", "videos", "transcripts", "segments"]
        for table in unexpected_tables:
            assert table not in tables, f"Table {table} should not exist after downgrade"

    engine.dispose()


def test_migrations_up_down_up(alembic_config, clean_db):
    """Test that migrations can be applied, reverted, and re-applied."""
    # Upgrade to head
    command.upgrade(alembic_config, "head")

    # Get current revision
    engine = create_engine(os.environ.get("DATABASE_URL"))
    with engine.begin() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        head_revision = result.scalar()

    # Downgrade one step
    command.downgrade(alembic_config, "-1")

    # Re-upgrade to head
    command.upgrade(alembic_config, "head")

    # Verify we're back at the same revision
    with engine.begin() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        current_revision = result.scalar()
        assert current_revision == head_revision

    engine.dispose()


def test_migration_history(alembic_config):
    """Test that migration history can be retrieved."""
    # This should not raise an error
    command.history(alembic_config, verbose=True)


def test_current_revision_empty_db(alembic_config, clean_db):
    """Test that current revision shows nothing on empty database."""
    # On an empty database (no migrations applied), current should work but show nothing
    # This should not raise an error
    command.current(alembic_config, verbose=True)


def test_stamp_and_upgrade(alembic_config, clean_db):
    """Test stamping a database and then upgrading."""
    # First upgrade to head
    command.upgrade(alembic_config, "head")

    # Get the current revision
    engine = create_engine(os.environ.get("DATABASE_URL"))
    with engine.begin() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        revision = result.scalar()

    # Downgrade to base
    command.downgrade(alembic_config, "base")

    # Stamp at the revision we were at
    command.stamp(alembic_config, revision)

    # Verify stamped correctly
    with engine.begin() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        stamped_revision = result.scalar()
        assert stamped_revision == revision

    # Upgrade should be a no-op since we're already at head
    command.upgrade(alembic_config, "head")

    engine.dispose()
