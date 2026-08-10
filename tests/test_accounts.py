"""Behavioral tests for canonical account and opaque-session operations."""

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from sqlalchemy import text

from app.accounts import (
    FinalAdminError,
    IdentityConflictError,
    LastIdentityError,
    create_session,
    delete_account,
    link_identity,
    merge_account_identity,
    sign_in_identity,
    unlink_identity,
)
from app.audit import ACTION_USER_DATA_DELETION, write_audit_event
from app.auth.providers import ProviderProfile
from app.settings import settings


def google_profile(subject: str, email: str | None) -> ProviderProfile:
    return ProviderProfile("google", subject, email, True, "Google Person", "https://example.com/google.png")


def twitch_profile(subject: str, email: str | None) -> ProviderProfile:
    return ProviderProfile("twitch", subject, email, True, "Twitch Person", "https://example.com/twitch.png")


def identity_count(db, user_id) -> int:
    return db.execute(
        text("SELECT count(*) FROM user_identities WHERE user_id=:user_id"), {"user_id": str(user_id)}
    ).scalar_one()


def test_sign_in_creates_user_and_identity(db_session):
    result = sign_in_identity(db_session, google_profile("g-1", "a@example.com"))

    assert result.created is True
    assert result.user["role"] == "user"
    assert identity_count(db_session, result.user["id"]) == 1


def test_sign_in_existing_identity_returns_same_user_and_does_not_replace_canonical_email(db_session):
    first = sign_in_identity(db_session, google_profile("g-1", "a@example.com"))
    second = sign_in_identity(db_session, google_profile("g-1", "new@example.com"))

    assert second.user["id"] == first.user["id"]
    assert second.created is False
    assert second.user["email"] == "a@example.com"
    identity = db_session.execute(
        text("SELECT provider_email FROM user_identities WHERE user_id=:user_id"), {"user_id": str(first.user["id"])}
    ).scalar_one()
    assert identity == "new@example.com"


def test_link_collision_never_merges_by_email(db_session):
    owner = sign_in_identity(db_session, google_profile("g-1", "same@example.com"))
    other = sign_in_identity(db_session, twitch_profile("t-1", "same@example.com"))

    with pytest.raises(IdentityConflictError):
        link_identity(db_session, owner.user["id"], twitch_profile("t-1", "same@example.com"))

    assert other.user["id"] != owner.user["id"]


def test_linking_provider_already_on_authenticated_account_is_a_conflict(db_session):
    owner = sign_in_identity(db_session, google_profile("g-1", "a@example.com"))

    with pytest.raises(IdentityConflictError):
        link_identity(db_session, owner.user["id"], google_profile("g-1", "a@example.com"))


def test_merge_existing_provider_account_preserves_data_and_rotates_access(db_session):
    target = sign_in_identity(db_session, google_profile("merge-target", "target@example.com"))
    source = sign_in_identity(db_session, twitch_profile("merge-source", "source@example.com"))
    db_session.execute(
        text("UPDATE users SET role='admin', plan='pro' WHERE id=:id"),
        {"id": str(source.user["id"])},
    )
    create_session(db_session, target.user["id"], user_agent="target-old", ip_address=None)
    create_session(db_session, source.user["id"], user_agent="source-old", ip_address=None)
    db_session.execute(
        text("""
            INSERT INTO saved_searches (id, user_id, query, filters) VALUES
                (:target_saved, :target, 'shared', '{"owner":"target"}'::jsonb),
                (:source_saved, :source, 'shared', '{"owner":"source"}'::jsonb),
                (:source_unique, :source, 'source-only', '{}'::jsonb)
        """),
        {
            "target_saved": str(uuid.uuid4()),
            "source_saved": str(uuid.uuid4()),
            "source_unique": str(uuid.uuid4()),
            "target": str(target.user["id"]),
            "source": str(source.user["id"]),
        },
    )
    db_session.execute(
        text("""
            INSERT INTO api_keys (user_id, name, key_hash, key_prefix)
            VALUES (:source, 'absorbed key', :hash, 'tc_merge')
        """),
        {"source": str(source.user["id"]), "hash": "b" * 64},
    )

    merged = merge_account_identity(
        db_session,
        target.user["id"],
        twitch_profile("merge-source", "source@example.com"),
        user_agent="merged-session",
        ip_address="127.0.0.1",
    )

    assert merged.source_user_id == str(source.user["id"])
    assert merged.user["role"] == "admin"
    assert merged.user["plan"] == "pro"
    assert db_session.execute(
        text("SELECT count(*) FROM users WHERE id=:id"), {"id": str(source.user["id"])}
    ).scalar_one() == 0
    assert db_session.execute(
        text("SELECT count(*) FROM user_identities WHERE user_id=:id"),
        {"id": str(target.user["id"])},
    ).scalar_one() == 2
    searches = db_session.execute(
        text("SELECT query, filters FROM saved_searches WHERE user_id=:id ORDER BY query"),
        {"id": str(target.user["id"])},
    ).mappings().all()
    assert searches == [
        {"query": "shared", "filters": {"owner": "target"}},
        {"query": "source-only", "filters": {}},
    ]
    assert db_session.execute(
        text("SELECT count(*) FROM sessions WHERE user_id=:id"), {"id": str(target.user["id"])}
    ).scalar_one() == 1
    assert db_session.execute(
        text("SELECT count(*) FROM api_keys WHERE key_hash=:hash"), {"hash": "b" * 64}
    ).scalar_one() == 0


def test_merge_rejects_overlapping_provider_without_mutation(db_session):
    target = sign_in_identity(db_session, google_profile("overlap-target", "target@example.com"))
    source = sign_in_identity(db_session, twitch_profile("overlap-source", "source@example.com"))
    link_identity(db_session, source.user["id"], google_profile("overlap-other", "other@example.com"))

    from app.accounts import AccountMergeConflictError

    with pytest.raises(AccountMergeConflictError):
        merge_account_identity(
            db_session,
            target.user["id"],
            twitch_profile("overlap-source", "source@example.com"),
            user_agent=None,
            ip_address=None,
        )

    assert identity_count(db_session, target.user["id"]) == 1
    assert identity_count(db_session, source.user["id"]) == 2


def test_unlink_rejects_final_identity(db_session):
    user = sign_in_identity(db_session, google_profile("g-1", "a@example.com"))

    with pytest.raises(LastIdentityError) as exc_info:
        unlink_identity(db_session, user.user["id"], "google")

    assert getattr(exc_info.value, "error_code", None) == "last_identity"


def test_bootstrap_identity_promotes_a_preexisting_backfilled_account_once(db_session, monkeypatch):
    original = sign_in_identity(db_session, google_profile("bootstrap", "admin@example.com"))
    assert original.user["role"] == "user"

    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_IDENTITIES", frozenset({"google:bootstrap"}))
    result = sign_in_identity(db_session, google_profile("bootstrap", "changed@example.com"))
    repeat = sign_in_identity(db_session, google_profile("bootstrap", "changed@example.com"))

    assert result.user["role"] == "admin"
    assert repeat.user["role"] == "admin"
    assert (
        db_session.execute(text("SELECT count(*) FROM audit_logs WHERE action='bootstrap_admin_promoted'")).scalar_one()
        == 1
    )


def test_bootstrap_identity_promotes_a_preexisting_moderator_once(db_session, monkeypatch):
    original = sign_in_identity(db_session, google_profile("bootstrap-moderator", "moderator@example.com"))
    db_session.execute(
        text("UPDATE users SET role='moderator' WHERE id=:user_id"), {"user_id": str(original.user["id"])}
    )
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_IDENTITIES", frozenset({"google:bootstrap-moderator"}))

    result = sign_in_identity(db_session, google_profile("bootstrap-moderator", "changed@example.com"))
    repeat = sign_in_identity(db_session, google_profile("bootstrap-moderator", "changed@example.com"))

    assert result.user["role"] == "admin"
    assert repeat.user["role"] == "admin"
    assert (
        db_session.execute(text("SELECT count(*) FROM audit_logs WHERE action='bootstrap_admin_promoted'")).scalar_one()
        == 1
    )


def test_concurrent_sign_ins_converge_on_one_identity(test_engine):
    """The identity constraint, not an in-memory check, resolves callback races."""
    profile = google_profile("concurrent-sign-in", "race@example.com")

    def sign_in():
        from app.db import SessionLocal

        with SessionLocal(bind=test_engine) as session:
            result = sign_in_identity(session, profile)
            session.commit()
            return result

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: sign_in(), range(2)))
        assert {str(result.user["id"]) for result in results}
        assert len({str(result.user["id"]) for result in results}) == 1
    finally:
        with test_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM user_identities WHERE provider='google' AND subject='concurrent-sign-in'")
            )
            connection.execute(text("DELETE FROM users WHERE email='race@example.com'"))


def test_concurrent_links_allow_one_owner_and_reject_the_collision(test_engine):
    user_ids = (uuid.uuid4(), uuid.uuid4())
    barrier = Barrier(2)
    profile = twitch_profile("concurrent-link", "link-race@example.com")
    with test_engine.begin() as connection:
        for user_id in user_ids:
            connection.execute(
                text("INSERT INTO users (id, email, role) VALUES (:id, :email, 'user')"),
                {"id": str(user_id), "email": f"{user_id}@example.com"},
            )

    def link(user_id):
        from app.db import SessionLocal

        with SessionLocal(bind=test_engine) as session:
            barrier.wait()
            try:
                identity = link_identity(session, user_id, profile)
                session.commit()
                return identity["user_id"]
            except IdentityConflictError:
                session.rollback()
                return None

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            owners = list(executor.map(link, user_ids))
        assert sum(owner is not None for owner in owners) == 1
        assert {str(owner) for owner in owners if owner is not None} <= {str(user_id) for user_id in user_ids}
    finally:
        with test_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM user_identities WHERE provider='twitch' AND subject='concurrent-link'")
            )
            connection.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": [str(user_id) for user_id in user_ids]}
            )


def test_session_database_value_cannot_replay_cookie(db_session):
    user = sign_in_identity(db_session, google_profile("g-1", "a@example.com"))
    raw_token = create_session(db_session, user.user["id"], user_agent=None, ip_address=None)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    stored = db_session.execute(
        text("""
        SELECT token_hash FROM sessions
        WHERE user_id = :user_id AND token_hash = :token_hash
    """),
        {"user_id": str(user.user["id"]), "token_hash": token_hash},
    ).scalar_one()
    from app.common.session import get_user_from_session

    assert stored == token_hash
    assert stored != raw_token
    assert get_user_from_session(db_session, raw_token)["id"] == user.user["id"]
    assert get_user_from_session(db_session, stored) is None


def test_delete_account_scrubs_retained_records_without_committing(db_session):
    user_id = uuid.uuid4()
    job_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO users (id, email, role) VALUES (:id, 'delete@example.com', 'user')"), {"id": str(user_id)}
    )
    db_session.execute(
        text("""
        INSERT INTO jobs (id, kind, input_url, owner_user_id, meta)
        VALUES (:job_id, 'single', 'https://example.com/delete', :user_id,
                CAST(:meta AS jsonb))
    """),
        {
            "job_id": str(job_id),
            "user_id": str(user_id),
            "meta": '{"owner_user_id": "' + str(user_id) + '", "api_key_id": "key"}',
        },
    )
    db_session.execute(
        text("""
        INSERT INTO source_deletions (video_id, youtube_id, owner_user_id, deleted_by_user_id, backup_exclusion_until)
        VALUES (:video_id, 'delete', :user_id, :user_id, now() + interval '1 day')
    """),
        {"video_id": str(uuid.uuid4()), "user_id": str(user_id)},
    )
    db_session.execute(
        text(
            "INSERT INTO events (user_id, type, payload) VALUES (:user_id, 'search', '{\"email\": \"delete@example.com\"}')"
        ),
        {"user_id": str(user_id)},
    )
    write_audit_event(
        db_session,
        ACTION_USER_DATA_DELETION,
        user_id=user_id,
        details={"email": "delete@example.com"},
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )

    delete_account(db_session, user_id)

    assert db_session.in_transaction()
    assert db_session.execute(text("SELECT count(*) FROM users WHERE id=:id"), {"id": str(user_id)}).scalar_one() == 0
    assert db_session.execute(
        text("SELECT owner_user_id, meta FROM jobs WHERE id=:id"), {"id": str(job_id)}
    ).mappings().one() == {"owner_user_id": None, "meta": {}}
    tombstone = (
        db_session.execute(
            text("SELECT owner_user_id, deleted_by_user_id FROM source_deletions WHERE youtube_id='delete'")
        )
        .mappings()
        .one()
    )
    assert tombstone == {"owner_user_id": None, "deleted_by_user_id": None}
    assert db_session.execute(
        text("SELECT user_id, payload FROM events WHERE type='search' ORDER BY id DESC LIMIT 1")
    ).mappings().one() == {"user_id": None, "payload": {}}
    audit = (
        db_session.execute(
            text("SELECT user_id, ip_address, user_agent, details FROM audit_logs WHERE action=:action"),
            {"action": ACTION_USER_DATA_DELETION},
        )
        .mappings()
        .one()
    )
    assert audit == {"user_id": None, "ip_address": None, "user_agent": None, "details": {}}


def test_delete_account_comprehensively_removes_personal_data_and_retains_archive(db_session):
    """Account removal anonymizes retained archive data without deleting it."""
    user_id, job_id, video_id, transcript_id = (uuid.uuid4() for _ in range(4))
    db_session.execute(
        text("INSERT INTO users (id, email, role) VALUES (:id, 'complete-delete@example.com', 'user')"),
        {"id": str(user_id)},
    )
    token = create_session(db_session, user_id, user_agent="test", ip_address="127.0.0.1")
    db_session.execute(
        text("INSERT INTO user_identities (user_id, provider, subject) VALUES (:id, 'google', :subject)"),
        {"id": str(user_id), "subject": f"complete-{user_id}"},
    )
    db_session.execute(
        text(
            "INSERT INTO jobs (id, kind, input_url, owner_user_id, meta) VALUES (:job, 'single', 'https://example.test', :user, CAST(:meta AS jsonb))"
        ),
        {
            "job": str(job_id),
            "user": str(user_id),
            "meta": '{"owner_user_id": "' + str(user_id) + '", "api_key_id": "private"}',
        },
    )
    db_session.execute(
        text("INSERT INTO videos (id, job_id, youtube_id) VALUES (:video, :job, :youtube)"),
        {"video": str(video_id), "job": str(job_id), "youtube": f"archive-{video_id}"},
    )
    db_session.execute(
        text("INSERT INTO transcripts (id, video_id, model) VALUES (:id, :video, 'base')"),
        {"id": str(transcript_id), "video": str(video_id)},
    )
    db_session.execute(
        text("INSERT INTO favorites (user_id, video_id, start_ms, end_ms) VALUES (:user, :video, 0, 1)"),
        {"user": str(user_id), "video": str(video_id)},
    )
    db_session.execute(
        text("INSERT INTO user_searches (user_id, query) VALUES (:user, 'private search')"), {"user": str(user_id)}
    )
    db_session.execute(
        text(
            "INSERT INTO saved_searches (id, user_id, query, filters) VALUES (:id, :user, 'saved private search', '{}'::jsonb)"
        ),
        {"id": str(uuid.uuid4()), "user": str(user_id)},
    )
    db_session.execute(
        text(
            "INSERT INTO api_keys (user_id, name, key_hash, key_prefix) VALUES (:user, 'private', :hash, 'tc_test...')"
        ),
        {"user": str(user_id), "hash": "a" * 64},
    )
    db_session.execute(
        text(
            "INSERT INTO source_deletions (video_id, youtube_id, owner_user_id, deleted_by_user_id, backup_exclusion_until) VALUES (:video, :youtube, :user, :user, now())"
        ),
        {"video": str(uuid.uuid4()), "youtube": f"tombstone-{user_id}", "user": str(user_id)},
    )
    db_session.execute(
        text(
            "INSERT INTO events (user_id, type, payload) VALUES (:user, 'private', '{\"email\": \"complete-delete@example.com\"}')"
        ),
        {"user": str(user_id)},
    )
    write_audit_event(db_session, "private", user_id=user_id, details={"email": "complete-delete@example.com"})

    delete_account(db_session, user_id)

    assert token
    assert db_session.execute(text("SELECT count(*) FROM users WHERE id=:id"), {"id": str(user_id)}).scalar_one() == 0
    for table in ("sessions", "user_identities", "favorites", "user_searches", "saved_searches"):
        assert (
            db_session.execute(
                text(f"SELECT count(*) FROM {table} WHERE user_id=:id"), {"id": str(user_id)}
            ).scalar_one()
            == 0
        )
    api_key_state = db_session.execute(
        text("SELECT revoked_at IS NOT NULL FROM api_keys WHERE user_id=:id"), {"id": str(user_id)}
    ).scalar_one_or_none()
    assert api_key_state is None or api_key_state is True
    assert db_session.execute(
        text("SELECT owner_user_id, meta FROM jobs WHERE id=:id"), {"id": str(job_id)}
    ).mappings().one() == {"owner_user_id": None, "meta": {}}
    assert db_session.execute(
        text("SELECT owner_user_id, deleted_by_user_id FROM source_deletions WHERE youtube_id=:youtube"),
        {"youtube": f"tombstone-{user_id}"},
    ).mappings().one() == {"owner_user_id": None, "deleted_by_user_id": None}
    assert db_session.execute(text("SELECT user_id, payload FROM events WHERE type='private'")).mappings().one() == {
        "user_id": None,
        "payload": {},
    }
    assert db_session.execute(
        text("SELECT user_id, details FROM audit_logs WHERE action='private'")
    ).mappings().one() == {"user_id": None, "details": {}}
    assert db_session.execute(text("SELECT count(*) FROM videos WHERE id=:id"), {"id": str(video_id)}).scalar_one() == 1
    assert (
        db_session.execute(
            text("SELECT count(*) FROM transcripts WHERE id=:id"), {"id": str(transcript_id)}
        ).scalar_one()
        == 1
    )


def test_delete_account_rejects_the_final_admin_without_mutation(db_session):
    user_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO users (id, email, role) VALUES (:id, 'admin@example.com', 'admin')"), {"id": str(user_id)}
    )
    token = create_session(db_session, user_id, user_agent=None, ip_address=None)

    with pytest.raises(FinalAdminError):
        delete_account(db_session, user_id)

    assert token
    assert db_session.execute(text("SELECT role FROM users WHERE id=:id"), {"id": str(user_id)}).scalar_one() == "admin"
    assert (
        db_session.execute(text("SELECT count(*) FROM sessions WHERE user_id=:id"), {"id": str(user_id)}).scalar_one()
        == 1
    )


def test_job_ownership_normalization_is_the_shared_runtime_contract():
    """New writes and deletion scrubbing share the canonical metadata shape."""
    from app.crud import normalize_job_ownership_meta

    owner_id = str(uuid.uuid4())
    assert normalize_job_ownership_meta(
        {"owner_user_id": "forged", "api_key_id": "forged", "safe": True},
        owner_user_id=owner_id,
        api_key_id="authoritative-key",
    ) == {"owner_user_id": owner_id, "api_key_id": "authoritative-key", "safe": True}
    assert (
        normalize_job_ownership_meta(
            {"owner_user_id": owner_id, "api_key_id": "authoritative-key"},
            owner_user_id=None,
            api_key_id=None,
        )
        == {}
    )


def test_concurrent_admin_deletions_leave_an_admin(test_engine):
    """Independent committed sessions share the transaction advisory lock."""
    from app.db import SessionLocal

    user_ids = (uuid.uuid4(), uuid.uuid4())
    barrier = Barrier(2)
    with test_engine.begin() as connection:
        for user_id in user_ids:
            connection.execute(
                text("INSERT INTO users (id, email, role) VALUES (:id, :email, 'admin')"),
                {"id": str(user_id), "email": f"delete-race-{user_id}@example.com"},
            )

    def remove(user_id):
        with SessionLocal(bind=test_engine) as session:
            barrier.wait(timeout=5)
            try:
                delete_account(session, user_id)
                session.commit()
                return True
            except FinalAdminError:
                session.rollback()
                return False

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(remove, user_id) for user_id in user_ids]
            outcomes = [future.result(timeout=10) for future in futures]
        with test_engine.connect() as connection:
            remaining = connection.execute(
                text("SELECT count(*) FROM users WHERE id = ANY(CAST(:ids AS uuid[])) AND role='admin'"),
                {"ids": [str(user_id) for user_id in user_ids]},
            ).scalar_one()
        assert outcomes.count(True) == 1
        assert remaining == 1
    finally:
        with test_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM users WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [str(user_id) for user_id in user_ids]},
            )


def test_account_deletion_serializes_with_admin_role_mutation(test_engine):
    """The production advisory lock prevents a demotion/deletion final-admin race."""
    from app.accounts import FinalAdminError, lock_admin_role_mutation, prepare_account_deletion
    from app.db import SessionLocal

    user_ids = (uuid.uuid4(), uuid.uuid4())
    demotion_locked, release_demotion, deletion_finished = Event(), Event(), Event()
    with test_engine.begin() as connection:
        for user_id in user_ids:
            connection.execute(
                text("INSERT INTO users (id, email, role) VALUES (:id, :email, 'admin')"),
                {"id": str(user_id), "email": f"mutation-race-{user_id}@example.com"},
            )

    def demote():
        with SessionLocal(bind=test_engine) as session:
            lock_admin_role_mutation(session)
            assert session.execute(text("SELECT count(*) FROM users WHERE role='admin'")).scalar_one() == 2
            demotion_locked.set()
            assert release_demotion.wait(5)
            session.execute(text("UPDATE users SET role='user' WHERE id=:id"), {"id": str(user_ids[0])})
            session.commit()

    def prepare_deletion():
        assert demotion_locked.wait(5)
        with SessionLocal(bind=test_engine) as session:
            try:
                prepare_account_deletion(session, user_ids[1])
                session.rollback()
                return "prepared"
            except FinalAdminError:
                session.rollback()
                return "final_admin"
            finally:
                deletion_finished.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            demotion = executor.submit(demote)
            deletion = executor.submit(prepare_deletion)
            assert demotion_locked.wait(5)
            assert not deletion_finished.wait(0.2)
            release_demotion.set()
            demotion.result(timeout=10)
            assert deletion.result(timeout=10) == "final_admin"
        with test_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM users WHERE id = ANY(CAST(:ids AS uuid[])) AND role='admin'"),
                    {"ids": [str(user_id) for user_id in user_ids]},
                ).scalar_one()
                >= 1
            )
    finally:
        with test_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM users WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [str(user_id) for user_id in user_ids]},
            )
