"""Tests for database migrations using Alembic.

These tests validate that migrations can be applied and reverted correctly.
"""

import os
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command
from alembic.config import Config


@pytest.fixture(autouse=True)
def allow_session_token_contract_migration(monkeypatch):
    """Existing full-history tests intentionally exercise the controlled cutover."""
    monkeypatch.setenv("ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION", "true")


@pytest.fixture(scope="module")
def alembic_config():
    """Create Alembic config for testing."""
    # Get path to alembic.ini in the project root
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    return Config(str(alembic_ini_path))


@pytest.fixture(scope="module")
def test_db_url():
    """Create an isolated database for destructive migration tests."""
    from app.settings import settings

    original_url = settings.DATABASE_URL
    base_url = make_url(
        os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/transcripts")
    )
    admin_url = base_url.set(database="postgres")
    migration_url = base_url.set(database="hasanara_migration_test")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS hasanara_migration_test WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE hasanara_migration_test"))

    settings.DATABASE_URL = migration_url.render_as_string(hide_password=False)
    try:
        yield settings.DATABASE_URL
    finally:
        settings.DATABASE_URL = original_url
        with admin_engine.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS hasanara_migration_test WITH (FORCE)"))
        admin_engine.dispose()


@contextmanager
def get_engine(db_url: str):
    """Context manager for database engine that ensures proper cleanup."""
    engine = create_engine(db_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="function")
def clean_db(test_db_url):
    """Provide a clean database for each test."""
    with get_engine(test_db_url) as engine:
        # The database is dedicated to migration tests, so resetting the schema
        # is both deterministic and safe. It also removes extension-owned
        # objects as a unit instead of trying to drop their functions directly.
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO public"))

    yield


def test_migrations_upgrade_head(alembic_config, clean_db, test_db_url):
    """Test that all migrations can be applied successfully."""
    # Run upgrade to head
    command.upgrade(alembic_config, "head")

    # Verify key tables exist
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            # Check that core tables exist
            result = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            )
            tables = [row[0] for row in result]

            expected_tables = ["jobs", "videos", "transcripts", "segments", "users", "sessions", "favorites", "events"]
            for table in expected_tables:
                assert table in tables, f"Table {table} should exist after migrations"


def test_migrations_downgrade_base(alembic_config, clean_db, test_db_url):
    """Test that all migrations can be applied and then reverted."""
    # Apply all migrations
    command.upgrade(alembic_config, "head")

    # Downgrade to base
    command.downgrade(alembic_config, "base")

    # Verify tables are removed
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            tables = [row[0] for row in result]

            # After downgrade, main tables should not exist (only alembic_version might remain)
            unexpected_tables = ["jobs", "videos", "transcripts", "segments"]
            for table in unexpected_tables:
                assert table not in tables, f"Table {table} should not exist after downgrade"


def test_migrations_up_down_up(alembic_config, clean_db, test_db_url):
    """Test that migrations can be applied, reverted, and re-applied."""
    # Upgrade to head
    command.upgrade(alembic_config, "head")

    # Get current revision
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            head_revision = result.scalar()

    # Downgrade one step
    command.downgrade(alembic_config, "-1")

    # Re-upgrade to head
    command.upgrade(alembic_config, "head")

    # Verify we're back at the same revision
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            current_revision = result.scalar()
            assert current_revision == head_revision


def test_migration_history(alembic_config):
    """Test that migration history can be retrieved."""
    # This should not raise an error
    command.history(alembic_config, verbose=True)


def test_current_revision_empty_db(alembic_config, clean_db):
    """Test that current revision shows nothing on empty database."""
    # On an empty database (no migrations applied), current should work but show nothing
    # This should not raise an error
    command.current(alembic_config, verbose=True)


def test_stamp_and_upgrade(alembic_config, clean_db, test_db_url):
    """Test stamping a database and then upgrading."""
    # First upgrade to head
    command.upgrade(alembic_config, "head")

    # Get the current revision
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            revision = result.scalar()

    # Downgrade to base
    command.downgrade(alembic_config, "base")

    # Stamp at the revision we were at
    command.stamp(alembic_config, revision)

    # Verify stamped correctly
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            stamped_revision = result.scalar()
            assert stamped_revision == revision

    # Upgrade should be a no-op since we're already at head
    command.upgrade(alembic_config, "head")


def test_linked_identity_migration_backfills_legacy_oauth_and_ownership(alembic_config, clean_db, test_db_url):
    """The expand revision preserves valid ownership and clears orphan UUIDs."""
    command.upgrade(alembic_config, "20260712_opinions")
    valid_user_id = "00000000-0000-0000-0000-000000000123"
    orphan_user_id = "00000000-0000-0000-0000-000000000999"
    token = "legacy-session-token"
    duplicate_token = "duplicate-legacy-token"
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO users (id, email, name, oauth_provider, oauth_subject, role)
                VALUES (:id, 'person@example.com', 'Person', 'google', 'google-subject', 'user')
            """),
                {"id": valid_user_id},
            )
            conn.execute(
                text("""
                INSERT INTO sessions (user_id, token) VALUES (:user_id, :token)
            """),
                {"user_id": valid_user_id, "token": token},
            )
            conn.execute(
                text("""
                INSERT INTO sessions (user_id, token) VALUES
                    (:user_id, :token), (:user_id, :token)
            """),
                {"user_id": valid_user_id, "token": duplicate_token},
            )
            conn.execute(text("""
                INSERT INTO users (id, oauth_provider, oauth_subject, role)
                VALUES ('00000000-0000-0000-0000-000000000126', 'legacy', 'legacy-subject', 'user')
            """))
            conn.execute(
                text("""
                INSERT INTO jobs (kind, input_url, owner_user_id, meta)
                VALUES ('single', 'https://example.test/valid', :valid, CAST(:meta AS jsonb)),
                       ('single', 'https://example.test/orphan', :orphan, CAST(:meta AS jsonb))
            """),
                {"valid": valid_user_id, "orphan": orphan_user_id, "meta": '{"owner_user_id":"wrong","keep":true}'},
            )
            conn.execute(
                text("""
                INSERT INTO source_deletions
                    (video_id, youtube_id, owner_user_id, deleted_by_user_id, backup_exclusion_until)
                VALUES (gen_random_uuid(), 'valid', :valid, :valid, now()),
                       (gen_random_uuid(), 'orphan', :orphan, :orphan, now())
            """),
                {"valid": valid_user_id, "orphan": orphan_user_id},
            )

    command.upgrade(alembic_config, "20260714_linked_identities")
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            session_columns = dict(conn.execute(text("""
                SELECT attname, attnotnull
                FROM pg_attribute
                WHERE attrelid = 'sessions'::regclass
                  AND attname IN ('token', 'token_hash')
                  AND NOT attisdropped
            """)).all())
            assert session_columns == {"token": False, "token_hash": False}
            identity = conn.execute(text("""
                SELECT user_id, provider, subject, provider_email FROM user_identities
                WHERE provider = 'google' AND subject = 'google-subject'
            """)).mappings().one()
            assert str(identity["user_id"]) == valid_user_id
            assert identity["provider_email"] == "person@example.com"
            session = conn.execute(text("SELECT token, token_hash, last_seen_at FROM sessions")).mappings().one()
            assert session["token"] == token
            assert session["token_hash"].strip() == sha256(token.encode()).hexdigest()
            assert session["last_seen_at"] is not None
            assert (
                conn.execute(
                    text("SELECT count(*) FROM sessions WHERE token = :token"),
                    {
                        "token": duplicate_token,
                    },
                ).scalar_one()
                == 0
            )
            assert conn.execute(text("""
                SELECT count(*) FROM user_identities
                WHERE provider = 'legacy' OR subject = 'legacy-subject'
            """)).scalar_one() == 0
            ownership = conn.execute(text("""
                SELECT input_url, owner_user_id, meta FROM jobs ORDER BY input_url
            """)).mappings().all()
            assert ownership[0]["owner_user_id"] is None
            assert str(ownership[1]["owner_user_id"]) == valid_user_id
            assert ownership[0]["meta"] == {"keep": True}
            assert ownership[1]["meta"] == {"keep": True, "owner_user_id": valid_user_id}
            assert conn.execute(text("""
                SELECT count(*) FROM jobs
                WHERE (owner_user_id IS NULL AND meta ? 'owner_user_id')
                   OR (owner_user_id IS NOT NULL AND meta->>'owner_user_id' IS DISTINCT FROM owner_user_id::text)
            """)).scalar_one() == 0
            deletions = conn.execute(text("""
                SELECT youtube_id, owner_user_id, deleted_by_user_id
                FROM source_deletions ORDER BY youtube_id
            """)).mappings().all()
            assert deletions[0]["owner_user_id"] is None
            assert deletions[0]["deleted_by_user_id"] is None
            assert str(deletions[1]["owner_user_id"]) == valid_user_id
            assert str(deletions[1]["deleted_by_user_id"]) == valid_user_id
            fk_actions = conn.execute(text("""
                SELECT conname, confdeltype
                FROM pg_constraint
                WHERE conname IN (
                    'jobs_owner_user_id_fkey', 'source_deletions_owner_user_id_fkey',
                    'source_deletions_deleted_by_user_id_fkey'
                )
            """)).all()
            assert dict(fk_actions) == {
                "jobs_owner_user_id_fkey": "n",
                "source_deletions_owner_user_id_fkey": "n",
                "source_deletions_deleted_by_user_id_fkey": "n",
            }


def test_linked_identity_role_constraint_and_downgrade_data_reconciliation(alembic_config, clean_db, test_db_url):
    command.upgrade(alembic_config, "20260714_linked_identities")
    with get_engine(test_db_url) as engine:
        with engine.connect() as conn:
            transaction = conn.begin()
            conn.execute(text("""
                INSERT INTO users (id, role) VALUES ('00000000-0000-0000-0000-000000000124', 'moderator')
            """))
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(text("""
                    INSERT INTO users (id, role) VALUES ('00000000-0000-0000-0000-000000000125', 'owner')
                """))
            transaction.rollback()

    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            user_id = "00000000-0000-0000-0000-000000000124"
            conn.execute(text("INSERT INTO users (id, role) VALUES (:id, 'user')"), {"id": user_id})
            conn.execute(
                text("""
                INSERT INTO sessions (user_id, token_hash)
                VALUES (:user_id, :token_hash)
            """),
                {"user_id": user_id, "token_hash": "a" * 64},
            )
            conn.execute(
                text("""
                INSERT INTO source_deletions
                    (video_id, youtube_id, owner_user_id, deleted_by_user_id, backup_exclusion_until)
                VALUES (gen_random_uuid(), 'nullable-deletion', :user_id, NULL, now())
            """),
                {"user_id": user_id},
            )

    command.downgrade(alembic_config, "20260712_opinions")
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM sessions")).scalar_one() == 0
            assert conn.execute(text("""
                SELECT count(*) FROM source_deletions WHERE deleted_by_user_id IS NULL
            """)).scalar_one() == 0


def test_fresh_schema_linked_identity_contract(clean_db, test_db_url):
    """A blank database accepts the schema in dependency order with its contracts."""
    schema = (Path(__file__).resolve().parent.parent / "sql" / "schema.sql").read_text()
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            conn.exec_driver_sql(schema)
            columns = {(row.table_name, row.attname): row.attnotnull for row in conn.execute(text("""
                SELECT attrelid::regclass::text AS table_name, attname, attnotnull
                FROM pg_attribute
                WHERE attrelid IN ('sessions'::regclass, 'source_deletions'::regclass)
                  AND attname IN ('token', 'token_hash', 'owner_user_id', 'deleted_by_user_id')
                  AND NOT attisdropped
            """)).mappings()}
            assert ("sessions", "token") not in columns
            assert columns[("sessions", "token_hash")] is True
            assert columns[("source_deletions", "owner_user_id")] is False
            assert columns[("source_deletions", "deleted_by_user_id")] is False

            foreign_keys = dict(conn.execute(text("""
                SELECT conname, confdeltype
                FROM pg_constraint
                WHERE conname IN (
                    'jobs_owner_user_id_fkey', 'source_deletions_owner_user_id_fkey',
                    'source_deletions_deleted_by_user_id_fkey'
                )
            """)).fetchall())
            assert foreign_keys == {
                "jobs_owner_user_id_fkey": "n",
                "source_deletions_owner_user_id_fkey": "n",
                "source_deletions_deleted_by_user_id_fkey": "n",
            }
            oauth_foreign_key = conn.execute(text("""
                SELECT confdeltype
                FROM pg_constraint
                WHERE conrelid = 'oauth_requests'::regclass AND contype = 'f'
            """)).scalar_one()
            assert oauth_foreign_key == "c"
            unique_constraints = set(conn.execute(text("""
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid IN ('sessions'::regclass, 'source_deletions'::regclass,
                                   'user_identities'::regclass, 'oauth_requests'::regclass)
                  AND contype = 'u'
            """)).scalars())
            assert "UNIQUE (video_id)" in unique_constraints
            assert "UNIQUE (token_hash)" in unique_constraints
            assert "UNIQUE (provider, subject)" in unique_constraints
            assert "UNIQUE (user_id, provider)" in unique_constraints
            assert "UNIQUE (state_hash)" in unique_constraints
            checks = set(conn.execute(text("""
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid IN ('user_identities'::regclass, 'oauth_requests'::regclass)
                  AND contype = 'c'
            """)).scalars())
            assert "CHECK ((provider = ANY (ARRAY['google'::text, 'twitch'::text])))" in checks
            assert "CHECK ((intent = ANY (ARRAY['login'::text, 'link'::text, 'merge'::text])))" in checks
            assert any("link_user_id IS NULL" in check and "link_user_id IS NOT NULL" in check for check in checks)
            indexes = set(conn.execute(text("""
                SELECT indexname FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = 'oauth_requests'
            """)).scalars())
            assert "oauth_requests_expiry_idx" in indexes
            cleanup_columns = dict(conn.execute(text("""
                SELECT attname, atthasdef
                FROM pg_attribute
                WHERE attrelid='source_deletions'::regclass
                  AND attname IN ('raw_path', 'wav_path', 'cleanup_status', 'cleanup_attempts',
                                  'cleanup_error', 'cleanup_started_at', 'cleanup_completed_at',
                                  'cleanup_lease_until', 'cleanup_next_attempt_at', 'cleanup_lease_token') AND NOT attisdropped
            """)).all())
            assert set(cleanup_columns) == {
                "raw_path",
                "wav_path",
                "cleanup_status",
                "cleanup_attempts",
                "cleanup_error",
                "cleanup_started_at",
                "cleanup_completed_at",
                "cleanup_lease_until",
                "cleanup_next_attempt_at",
                "cleanup_lease_token",
            }
            assert cleanup_columns["cleanup_status"] is True
            assert cleanup_columns["cleanup_attempts"] is True
            assert "source_deletions_cleanup_pending_idx" in set(conn.execute(text("""
                SELECT indexname FROM pg_indexes
                WHERE schemaname='public' AND tablename='source_deletions'
            """)).scalars())


def _user_fk_catalog(conn):
    return set(conn.execute(text("""
        SELECT conrelid::regclass::text AS table_name,
               att.attname AS column_name,
               confdeltype AS delete_action
        FROM pg_constraint constraint_row
        CROSS JOIN LATERAL unnest(constraint_row.conkey) AS key(attnum)
        JOIN pg_attribute att ON att.attrelid=constraint_row.conrelid AND att.attnum=key.attnum
        WHERE constraint_row.contype='f'
          AND constraint_row.confrelid='users'::regclass
        ORDER BY table_name, column_name
    """)).all())


def _source_cleanup_contract(conn):
    columns = set(conn.execute(text("""
        SELECT attname FROM pg_attribute
        WHERE attrelid='source_deletions'::regclass AND NOT attisdropped
          AND attname IN ('raw_path', 'wav_path', 'cleanup_status', 'cleanup_attempts',
                          'cleanup_error', 'cleanup_started_at', 'cleanup_completed_at',
                          'cleanup_lease_until', 'cleanup_next_attempt_at', 'cleanup_lease_token')
    """)).scalars())
    indexes = set(conn.execute(text("""
        SELECT indexname FROM pg_indexes
        WHERE schemaname='public' AND tablename='source_deletions'
          AND indexname='source_deletions_cleanup_pending_idx'
    """)).scalars())
    return columns, indexes


def _table_catalog_contract(conn, table_names):
    """Return the runtime table shape, including defaults, constraints, and indexes."""
    table_names = tuple(table_names)
    columns = conn.execute(
        text("""
        SELECT attrelid::regclass::text AS table_name,
               attname,
               format_type(atttypid, atttypmod),
               attnotnull,
               pg_get_expr(adbin, adrelid) AS default_expression
        FROM pg_attribute
        LEFT JOIN pg_attrdef ON adrelid = attrelid AND adnum = attnum
        WHERE attrelid = ANY(CAST(:table_names AS regclass[]))
          AND attnum > 0 AND NOT attisdropped
        ORDER BY table_name, attnum
    """),
        {"table_names": list(table_names)},
    ).all()
    constraints = conn.execute(
        text("""
        SELECT conrelid::regclass::text AS table_name,
               contype,
               pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = ANY(CAST(:table_names AS regclass[]))
        ORDER BY table_name, contype, pg_get_constraintdef(oid)
    """),
        {"table_names": list(table_names)},
    ).all()
    indexes = conn.execute(
        text("""
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = ANY(:table_names)
        ORDER BY tablename, indexname
    """),
        {"table_names": list(table_names)},
    ).all()
    return columns, constraints, indexes


def test_upgraded_and_fresh_schema_have_complete_user_fk_and_cleanup_inventory(alembic_config, clean_db, test_db_url):
    """Fresh bootstrap and upgraded deployments retain identical user-data rules."""
    parity_tables = (
        "user_vocabularies",
        "saved_searches",
        "archive_label_feedback",
        "archive_opinion_revisions",
    )
    command.upgrade(alembic_config, "head")
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            upgraded_fks = _user_fk_catalog(conn)
            upgraded_cleanup = _source_cleanup_contract(conn)
            upgraded_catalog = _table_catalog_contract(conn, parity_tables)
    assert upgraded_fks == {
        ("api_keys", "user_id", "c"),
        ("archive_label_feedback", "user_id", "n"),
        ("archive_opinion_revisions", "corrected_by", "n"),
        ("audit_logs", "user_id", "n"),
        ("events", "user_id", "n"),
        ("favorites", "user_id", "c"),
        ("jobs", "owner_user_id", "n"),
        ("oauth_requests", "link_user_id", "c"),
        ("sessions", "user_id", "c"),
        ("saved_searches", "user_id", "c"),
        ("source_deletions", "deleted_by_user_id", "n"),
        ("source_deletions", "owner_user_id", "n"),
        ("user_identities", "user_id", "c"),
        ("user_searches", "user_id", "c"),
        ("user_vocabularies", "user_id", "c"),
    }

    schema = (Path(__file__).resolve().parent.parent / "sql" / "schema.sql").read_text()
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
            conn.exec_driver_sql(schema)
            fresh_fks = _user_fk_catalog(conn)
            fresh_cleanup = _source_cleanup_contract(conn)
            fresh_catalog = _table_catalog_contract(conn, parity_tables)
    assert fresh_fks == upgraded_fks
    assert fresh_cleanup == upgraded_cleanup
    assert fresh_catalog == upgraded_catalog


def _sessions_contract(conn):
    columns = dict(conn.execute(text("""
        SELECT attname, attnotnull
        FROM pg_attribute
        WHERE attrelid = 'sessions'::regclass
          AND attname IN ('token', 'token_hash')
          AND NOT attisdropped
    """)).all())
    unique_constraints = set(conn.execute(text("""
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'sessions'::regclass AND contype = 'u'
    """)).scalars())
    return columns, unique_constraints


def _session_credential_catalog(conn):
    """Return credential column types, nullability, unique constraints, and indexes."""
    columns = conn.execute(text("""
        SELECT attname, format_type(atttypid, atttypmod), attnotnull
        FROM pg_attribute
        WHERE attrelid = 'sessions'::regclass
          AND attname IN ('token', 'token_hash')
          AND NOT attisdropped
        ORDER BY attname
    """)).all()
    constraints = conn.execute(text("""
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'sessions'::regclass AND contype = 'u'
        ORDER BY conname
    """)).all()
    indexes = conn.execute(text("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'sessions'
          AND indexname IN ('sessions_token_idx', 'sessions_token_hash_key')
        ORDER BY indexname
    """)).all()
    return columns, constraints, indexes


def test_drop_plaintext_session_tokens_reconciles_session_contract(alembic_config, clean_db, test_db_url):
    """0200 retains only valid, unambiguous credentials without hash overwrites.

    Production maintenance must drain writers and long-lived transactions before
    this migration, because its table changes require an exclusive lock.
    """
    command.upgrade(alembic_config, "20260714_linked_identities")
    matching_token = "matching-dual-token"
    safe_token = "safe-plaintext-token"
    duplicate_token = "duplicate-plaintext-token"
    swapped_one = "swapped-one"
    swapped_two = "swapped-two"
    valid_hash_only = "b" * 64
    user_ids = [f"00000000-0000-0000-0000-000000000{number:03d}" for number in range(201, 213)]
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, role) VALUES " + ", ".join(f"('{user_id}', 'user')" for user_id in user_ids)
                )
            )
            conn.execute(
                text("""
                INSERT INTO sessions (user_id, token, token_hash, user_agent) VALUES
                    (:matching_user, :matching_token, :matching_hash, 'matching-dual'),
                    (:safe_user, :safe_token, NULL, 'safe'),
                    (:hash_user, NULL, :valid_hash, 'hash-only'),
                    (:null_user, NULL, NULL, 'null-null'),
                    (:invalid_user, NULL, :invalid_hash, 'invalid-hash'),
                    (:blank_user, '', NULL, 'blank-token'),
                    (:mismatch_user, :safe_token, :mismatch_hash, 'mismatched-dual'),
                    (:malformed_dual_user, :safe_token, :invalid_dual_hash, 'malformed-dual'),
                    (:duplicate_one_user, :duplicate_token, NULL, 'duplicate-one'),
                    (:duplicate_two_user, :duplicate_token, NULL, 'duplicate-two'),
                    (:swap_one_user, :swapped_one, :swapped_two_hash, 'swapped-one'),
                    (:swap_two_user, :swapped_two, :swapped_one_hash, 'swapped-two')
            """),
                {
                    "matching_user": user_ids[0],
                    "matching_token": matching_token,
                    "matching_hash": sha256(matching_token.encode()).hexdigest(),
                    "safe_user": user_ids[1],
                    "safe_token": safe_token,
                    "hash_user": user_ids[2],
                    "valid_hash": valid_hash_only,
                    "null_user": user_ids[3],
                    "invalid_user": user_ids[4],
                    "invalid_hash": "not-a-sha256-hash",
                    "blank_user": user_ids[5],
                    "mismatch_user": user_ids[6],
                    "mismatch_hash": sha256("different-token".encode()).hexdigest(),
                    "malformed_dual_user": user_ids[7],
                    "invalid_dual_hash": "also-not-a-sha256-hash",
                    "duplicate_one_user": user_ids[8],
                    "duplicate_two_user": user_ids[9],
                    "duplicate_token": duplicate_token,
                    "swap_one_user": user_ids[10],
                    "swap_two_user": user_ids[11],
                    "swapped_one": swapped_one,
                    "swapped_two": swapped_two,
                    "swapped_one_hash": sha256(swapped_one.encode()).hexdigest(),
                    "swapped_two_hash": sha256(swapped_two.encode()).hexdigest(),
                },
            )

    command.upgrade(alembic_config, "20260714_0200")
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            columns, unique_constraints = _sessions_contract(conn)
            assert columns == {"token_hash": True}
            assert "UNIQUE (token_hash)" in unique_constraints
            sessions = conn.execute(text("""
                SELECT user_agent, token_hash FROM sessions ORDER BY user_agent
            """)).all()
            assert sessions == [
                ("hash-only", valid_hash_only),
                ("matching-dual", sha256(matching_token.encode()).hexdigest()),
                ("safe", sha256(safe_token.encode()).hexdigest()),
            ]
            assert conn.execute(text("""
                SELECT count(*) FROM sessions
                WHERE token_hash !~ '^[0-9a-f]{64}$'
            """)).scalar_one() == 0
            with pytest.raises(sa.exc.IntegrityError):
                with conn.begin_nested():
                    conn.execute(
                        text("""
                        INSERT INTO sessions (user_id, token_hash)
                        VALUES (:user_id, :token_hash)
                    """),
                        {"user_id": user_ids[0], "token_hash": valid_hash_only},
                    )


@pytest.mark.parametrize("flag", [None, "false", "0"])
def test_drop_plaintext_session_tokens_requires_explicit_opt_in(
    alembic_config, clean_db, test_db_url, monkeypatch, flag
):
    """0200 must not alter the expand contract without an exact true opt-in."""
    command.upgrade(alembic_config, "20260714_linked_identities")
    if flag is None:
        monkeypatch.delenv("ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION", raising=False)
    else:
        monkeypatch.setenv("ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION", flag)

    with pytest.raises(RuntimeError, match="ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION=true"):
        command.upgrade(alembic_config, "20260714_0200")

    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            assert _sessions_contract(conn) == ({"token": False, "token_hash": False}, {"UNIQUE (token_hash)"})


def test_drop_plaintext_session_tokens_allows_explicit_opt_in(alembic_config, clean_db, test_db_url, monkeypatch):
    command.upgrade(alembic_config, "20260714_linked_identities")
    monkeypatch.setenv("ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION", "true")

    command.upgrade(alembic_config, "20260714_0200")

    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            assert _sessions_contract(conn) == ({"token_hash": True}, {"UNIQUE (token_hash)"})


@pytest.mark.parametrize("flag", [None, "false", "0"])
def test_drop_event_session_token_requires_explicit_opt_in(alembic_config, clean_db, monkeypatch, flag):
    command.upgrade(alembic_config, "20260714_0300")
    if flag is None:
        monkeypatch.delenv("ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION", raising=False)
    else:
        monkeypatch.setenv("ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION", flag)

    with pytest.raises(RuntimeError, match="ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION=true"):
        command.upgrade(alembic_config, "20260807_event_token")


def test_drop_event_session_token_contract_and_downgrade(alembic_config, clean_db, test_db_url, monkeypatch):
    command.upgrade(alembic_config, "20260714_0300")
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            conn.execute(text("""
                    CREATE FUNCTION null_legacy_event_session_token()
                    RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN
                        NEW.session_token := NULL;
                        RETURN NEW;
                    END;
                    $$
                """))
            conn.execute(text("""
                    CREATE TRIGGER events_null_legacy_session_token
                    BEFORE INSERT OR UPDATE OF session_token ON events
                    FOR EACH ROW EXECUTE FUNCTION null_legacy_event_session_token()
                """))
    monkeypatch.setenv("ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION", "true")
    command.upgrade(alembic_config, "20260807_event_token")

    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            assert not conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema='public' AND table_name='events'
                          AND column_name='session_token'
                    )
                """)).scalar_one()
            assert not conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_proc
                        WHERE proname = 'null_legacy_event_session_token'
                    )
                """)).scalar_one()

    command.downgrade(alembic_config, "20260714_0300")
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            nullable = conn.execute(text("""
                    SELECT is_nullable FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='events'
                      AND column_name='session_token'
                """)).scalar_one()
            assert nullable == "YES"


def test_drop_plaintext_session_tokens_downgrade_invalidates_sessions(alembic_config, clean_db, test_db_url):
    """Downgrade invalidates sessions and exactly restores the expand catalog."""
    command.upgrade(alembic_config, "20260714_linked_identities")
    user_id = "00000000-0000-0000-0000-000000000208"
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            expand_catalog = _session_credential_catalog(conn)
            conn.execute(text("INSERT INTO users (id, role) VALUES (:id, 'user')"), {"id": user_id})
            conn.execute(
                text("""
                INSERT INTO sessions (user_id, token_hash) VALUES (:user_id, :token_hash)
            """),
                {"user_id": user_id, "token_hash": "c" * 64},
            )

    command.upgrade(alembic_config, "20260714_0200")
    command.downgrade(alembic_config, "20260714_linked_identities")
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            columns, unique_constraints = _sessions_contract(conn)
            assert columns == {"token": False, "token_hash": False}
            assert "UNIQUE (token_hash)" in unique_constraints
            assert conn.execute(text("SELECT count(*) FROM sessions")).scalar_one() == 0
            assert _session_credential_catalog(conn) == expand_catalog

    command.upgrade(alembic_config, "20260714_0200")
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            assert _sessions_contract(conn) == ({"token_hash": True}, {"UNIQUE (token_hash)"})


def test_head_and_fresh_schema_share_hash_only_sessions_contract(alembic_config, clean_db, test_db_url):
    """Alembic head and fresh bootstrap expose the same sessions contract."""
    command.upgrade(alembic_config, "head")
    with get_engine(test_db_url) as engine:
        with engine.begin() as conn:
            upgraded_contract = _session_credential_catalog(conn)
            upgraded_session_contract = _sessions_contract(conn)
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
            schema = (Path(__file__).resolve().parent.parent / "sql" / "schema.sql").read_text()
            conn.exec_driver_sql(schema)
            fresh_contract = _session_credential_catalog(conn)
            fresh_session_contract = _sessions_contract(conn)
    assert upgraded_contract == fresh_contract
    assert upgraded_session_contract == fresh_session_contract == ({"token_hash": True}, {"UNIQUE (token_hash)"})


def test_diarization_role_speaker_updates_do_not_enqueue_search_outbox(alembic_config, clean_db, test_db_url):
    """The least-privilege diarization update bypasses the native outbox trigger."""
    command.upgrade(alembic_config, "head")
    # Never mutate the deployment role: PostgreSQL roles are cluster-wide and
    # it may own grants in another database on a shared development cluster.
    role = "hasanara_diarization_test"
    with get_engine(test_db_url) as engine:
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN EXECUTE 'DROP OWNED BY {role}'; EXECUTE 'DROP ROLE {role}'; END IF; END $$"
                    )
                )
                conn.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD 'diarization-test-password'"))
                conn.execute(text(f"GRANT CONNECT ON DATABASE hasanara_migration_test TO {role}"))
                conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
                conn.execute(
                    text(
                        f"GRANT SELECT (id, state, wav_path, diarization_state, duration_seconds, updated_at, created_at) ON videos TO {role}"
                    )
                )
                conn.execute(
                    text(f"GRANT UPDATE (diarization_state, diarization_error, updated_at) ON videos TO {role}")
                )
                conn.execute(
                    text(
                        f"GRANT SELECT (id, video_id, start_ms, end_ms, text, speaker_label, confidence, avg_logprob, temperature, token_count) ON segments TO {role}"
                    )
                )
                conn.execute(text(f"GRANT UPDATE (speaker_label) ON segments TO {role}"))
                job_id = "00000000-0000-0000-0000-000000000301"
                video_id = "00000000-0000-0000-0000-000000000302"
                conn.execute(
                    text("INSERT INTO jobs(id, kind, input_url) VALUES (:id, 'single', 'https://example.test/job')"),
                    {"id": job_id},
                )
                conn.execute(
                    text("INSERT INTO videos(id, job_id, youtube_id) VALUES (:id, :job, 'role-outbox-video')"),
                    {"id": video_id, "job": job_id},
                )
                segment_id = conn.execute(
                    text(
                        "INSERT INTO segments(video_id, start_ms, end_ms, text) VALUES (:video_id, 0, 1, 'before') RETURNING id"
                    ),
                    {"video_id": video_id},
                ).scalar_one()
                before = conn.execute(
                    text("SELECT count(*) FROM search_index_outbox WHERE source = 'native' AND document_id = :id"),
                    {"id": segment_id},
                ).scalar_one()

            diarization_url = make_url(test_db_url).set(username=role, password="diarization-test-password")
            with get_engine(diarization_url.render_as_string(hide_password=False)) as diarization_engine:
                with diarization_engine.begin() as conn:
                    conn.execute(
                        text("UPDATE segments SET speaker_label = 'Speaker 1' WHERE id = :id"), {"id": segment_id}
                    )
                with pytest.raises(sa.exc.ProgrammingError):
                    with diarization_engine.begin() as conn:
                        conn.execute(text("UPDATE segments SET text = 'denied' WHERE id = :id"), {"id": segment_id})

            with engine.begin() as conn:
                assert (
                    conn.execute(
                        text("SELECT count(*) FROM search_index_outbox WHERE source = 'native' AND document_id = :id"),
                        {"id": segment_id},
                    ).scalar_one()
                    == before
                )
                conn.execute(text("UPDATE segments SET text = 'indexed' WHERE id = :id"), {"id": segment_id})
                assert (
                    conn.execute(
                        text("SELECT count(*) FROM search_index_outbox WHERE source = 'native' AND document_id = :id"),
                        {"id": segment_id},
                    ).scalar_one()
                    == before + 1
                )
        finally:
            with engine.begin() as conn:
                conn.execute(text("RESET ROLE"))
                conn.execute(text(f"DROP OWNED BY {role}"))
                conn.execute(text(f"DROP ROLE IF EXISTS {role}"))


def test_native_search_outbox_update_scope_downgrades_to_broad_trigger(alembic_config, clean_db, test_db_url):
    command.upgrade(alembic_config, "20260714_0300")
    with get_engine(test_db_url) as engine:
        with engine.connect() as conn:
            definition = conn.execute(
                text("SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE tgname = 'segments_search_outbox'")
            )
            assert "UPDATE OF video_id, start_ms, end_ms, text" in definition.scalar_one()
    command.downgrade(alembic_config, "20260714_0200")
    with get_engine(test_db_url) as engine:
        with engine.connect() as conn:
            updated_columns = conn.execute(
                text("SELECT tgattr::text FROM pg_trigger WHERE tgname = 'segments_search_outbox'")
            )
            assert updated_columns.scalar_one() == ""
