"""Tests for archive and grouped search routes."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import call, patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.schemas import (
    ArchiveIntelligenceResponse,
    ArchivePeriodOption,
    ArchivePeriodOptionsResponse,
    ArchiveSummary,
    ArchiveVideoMetadataUpdate,
    ArchivePersonUpdate,
    ArchiveVideoTagUpdate,
    EpisodeSearchGroup,
    GroupedSearchResponse,
    MentionMap,
    SearchMoment,
    VideoInfo,
)
from app.archive.video_metadata_repository import create_person, create_tag, set_video_metadata
from app.routes import archive as archive_routes


def _create_completed_video(db_session, *, youtube_id: str, title: str, uploaded_at: datetime, duration_seconds: int = 120):
    job_id = uuid.uuid4()
    video_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO jobs (id, kind, input_url, state) VALUES (:id, 'single', :url, 'completed')"),
        {"id": str(job_id), "url": f"https://youtube.com/watch?v={youtube_id}"},
    )
    db_session.execute(
        text(
            """
            INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state, uploaded_at, created_at, updated_at)
            VALUES (:id, :job_id, :youtube_id, 0, :title, :duration_seconds, 'completed', :uploaded_at, :uploaded_at, :uploaded_at)
            """
        ),
        {
            "id": str(video_id),
            "job_id": str(job_id),
            "youtube_id": youtube_id,
            "title": title,
            "duration_seconds": duration_seconds,
            "uploaded_at": uploaded_at,
        },
    )
    db_session.commit()
    return video_id


def _create_user_session(db_session, *, email: str = "user@example.com") -> str:
    user_id = uuid.uuid4()
    session_token = secrets.token_urlsafe(32)
    db_session.execute(
        text("INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) VALUES (:id, :email, 'google', :subject, 'free')"),
        {"id": str(user_id), "email": email, "subject": f"{email}-subject"},
    )
    db_session.execute(
        text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
        {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
    )
    db_session.commit()
    return session_token


class TestArchiveRoutes:
    def test_archive_summary(self, client: TestClient, db_session):
        video_id = _create_completed_video(
            db_session,
            youtube_id="archive123",
            title="Archive Video",
            uploaded_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            duration_seconds=360,
        )
        db_session.execute(
            text("INSERT INTO segments (video_id, start_ms, end_ms, text, speaker_label) VALUES (:vid, 0, 1000, :text, NULL)"),
            {"vid": str(video_id), "text": "archive searchable words here"},
        )
        db_session.execute(
            text(
                """
                INSERT INTO archive_summary_stats (
                    id, video_count, total_duration_seconds, transcript_word_count, archive_updated_at, calculated_at
                ) VALUES (
                    'default', 1, 360, 4, :updated_at, :updated_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    video_count = EXCLUDED.video_count,
                    total_duration_seconds = EXCLUDED.total_duration_seconds,
                    transcript_word_count = EXCLUDED.transcript_word_count,
                    archive_updated_at = EXCLUDED.archive_updated_at,
                    calculated_at = EXCLUDED.calculated_at
                """
            ),
            {"updated_at": datetime(2026, 5, 1, tzinfo=timezone.utc)},
        )
        db_session.execute(
            text("INSERT INTO search_suggestions (term, frequency) VALUES (:term, :frequency)"),
            {"term": "archive query", "frequency": 11},
        )
        db_session.commit()

        response = client.get("/archive/summary?recent_limit=5&popular_limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["video_count"] == 1
        assert data["total_duration_seconds"] == 360
        assert data["transcript_word_count"] == 4
        assert data["recent_videos"]
        assert data["popular_searches"][0]["term"] == "archive query"

    def test_archive_intelligence_route_returns_explore_contract(self, client: TestClient, db_session):
        video_id = _create_completed_video(
            db_session,
            youtube_id="explore1",
            title="Explore VOD",
            uploaded_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            duration_seconds=3600,
        )
        db_session.execute(
            text("INSERT INTO segments (video_id, start_ms, end_ms, text, speaker_label) VALUES (:vid, 1000, 5000, :text, NULL)"),
            {"vid": str(video_id), "text": "ICE protests and Gaza coverage made this a major news segment."},
        )
        person = create_person(db_session, {"display_name": "Guest One", "slug": "guest-one"})
        tag = create_tag(db_session, {"label": "Chadvice", "slug": "chadvice"})
        set_video_metadata(
            db_session,
            video_id,
            people=[{"slug": person["slug"], "role": "guest"}],
            tags=[{"slug": tag["slug"]}],
        )
        db_session.execute(
            text("INSERT INTO search_suggestions (term, frequency) VALUES (:term, :frequency)"),
            {"term": "ice protests", "frequency": 7},
        )
        db_session.commit()

        response = client.get("/archive/intelligence?topic_limit=4&period_limit=3&granularity=month&date_from=2026-05-01&date_to=2026-05-31")

        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["creator_name"] == "HasAnAra"
        assert data["exploration_modes"] == ["timeline", "topics", "trending", "suggested"]
        assert data["trending_searches"][0]["term"] == "ice protests"
        assert data["topic_cards"]
        assert data["periods"]
        assert data["periods"][0]["evidence"]
        assert data["periods"][0]["evidence"][0]["video"]["youtube_id"] == "explore1"
        assert data["periods"][0]["evidence"][0]["video"]["people"] == [
            {"slug": "guest-one", "display_name": "Guest One", "aliases": [], "description": None, "role": "guest"}
        ]
        assert data["periods"][0]["evidence"][0]["video"]["tags"] == [
            {"slug": "chadvice", "label": "Chadvice", "kind": "category", "description": None}
        ]

    @patch("app.routes.archive.invalidate_cache")
    def test_admin_set_archive_video_metadata_invalidates_video_cache(self, mock_invalidate_cache, db_session):
        video_id = _create_completed_video(
            db_session,
            youtube_id="cache123",
            title="Cache Video",
            uploaded_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            duration_seconds=3600,
        )
        person = create_person(db_session, {"display_name": "Guest One", "slug": "guest-one"})
        tag = create_tag(db_session, {"label": "Chadvice", "slug": "chadvice"})

        response = archive_routes.admin_set_archive_video_metadata(
            video_id=video_id,
            payload=ArchiveVideoMetadataUpdate(
                people=[{"slug": person["slug"], "role": "guest"}],
                tags=[{"slug": tag["slug"]}],
            ),
            db=db_session,
            user=object(),
        )

        assert response.model_dump()["people"][0]["slug"] == "guest-one"
        mock_invalidate_cache.assert_called_once_with("video", video_id)

    @patch("app.routes.archive.invalidate_cache_pattern")
    def test_admin_person_and_tag_updates_invalidate_video_cache_pattern(self, mock_invalidate_cache_pattern, db_session):
        person = create_person(db_session, {"display_name": "Guest One", "slug": "guest-one"})
        tag = create_tag(db_session, {"label": "Chadvice", "slug": "chadvice"})

        archive_routes.admin_update_archive_person(
            slug=person["slug"],
            payload=ArchivePersonUpdate(display_name="Guest Two"),
            db=db_session,
            user=object(),
        )
        archive_routes.admin_update_archive_tag(
            slug=tag["slug"],
            payload=ArchiveVideoTagUpdate(label="Chadvice Plus"),
            db=db_session,
            user=object(),
        )
        archive_routes.admin_seed_archive_metadata_tags(db=db_session, user=object())

        assert mock_invalidate_cache_pattern.call_args_list == [call("video:*"), call("video:*"), call("video:*")]

    @patch("app.routes.archive.get_archive_intelligence")
    def test_archive_intelligence_route_passes_query_params(self, mock_get_archive_intelligence, client: TestClient):
        mock_get_archive_intelligence.return_value = ArchiveIntelligenceResponse(
            summary=ArchiveSummary(),
            exploration_modes=[],
            trending_searches=[],
            suggested_searches=[],
            topic_cards=[],
            periods=[],
        )

        response = client.get("/archive/intelligence?topic_limit=4&period_limit=3&granularity=week&date_from=2026-05-01&date_to=2026-05-31&period=2026-05")

        assert response.status_code == 200
        mock_get_archive_intelligence.assert_called_once()
        _, kwargs = mock_get_archive_intelligence.call_args
        assert kwargs["topic_limit"] == 4
        assert kwargs["period_limit"] == 3
        assert kwargs["granularity"] == "week"
        assert str(kwargs["date_from"]) == "2026-05-01"
        assert str(kwargs["date_to"]) == "2026-05-31"
        assert kwargs["period"] == "2026-05"

    @patch("app.routes.archive.get_archive_period_options")
    def test_archive_intelligence_periods_route(self, mock_get_archive_period_options, client: TestClient):
        mock_get_archive_period_options.return_value = ArchivePeriodOptionsResponse(
            periods=[
                ArchivePeriodOption(
                    slug="2026-05",
                    label="May 2026",
                    kind="month",
                    date_from=datetime(2026, 5, 1, tzinfo=timezone.utc).date(),
                    date_to=datetime(2026, 5, 31, tzinfo=timezone.utc).date(),
                    description=None,
                    video_count=1,
                    total_duration_seconds=360,
                )
            ]
        )

        response = client.get("/archive/intelligence/periods?kind=month&limit=5")

        assert response.status_code == 200
        data = response.json()
        assert data["periods"][0]["slug"] == "2026-05"
        mock_get_archive_period_options.assert_called_once()
        _, kwargs = mock_get_archive_period_options.call_args
        assert kwargs["kind"] == "month"
        assert kwargs["limit"] == 5

    def test_admin_archive_period_routes_registered(self, client: TestClient):
        spec = client.get("/openapi.json").json()
        expected_paths = {
            "/admin/archive/periods": {"get", "post"},
            "/admin/archive/periods/{slug}": {"patch"},
            "/admin/archive/periods/{slug}/refresh": {"post"},
            "/admin/archive/periods/seed": {"post"},
            "/admin/archive/metadata/people": {"get", "post"},
            "/admin/archive/metadata/people/{slug}": {"patch"},
            "/admin/archive/metadata/tags": {"get", "post"},
            "/admin/archive/metadata/tags/{slug}": {"patch"},
            "/admin/archive/metadata/videos": {"get"},
            "/admin/archive/metadata/videos/{video_id}": {"get", "put"},
            "/admin/archive/metadata/seed-tags": {"post"},
        }

        for path, methods in expected_paths.items():
            assert path in spec["paths"]
            assert methods.issubset(set(spec["paths"][path].keys()))

    def test_admin_archive_period_routes_require_auth(self, client: TestClient):
        assert client.get("/admin/archive/periods").status_code == 401
        assert (
            client.post(
                "/admin/archive/periods",
                json={"label": "Test Period", "kind": "event", "date_from": "2026-01-01", "date_to": "2026-01-02"},
            ).status_code
            == 401
        )
        assert client.patch("/admin/archive/periods/test-period", json={"label": "Updated"}).status_code == 401
        assert client.post("/admin/archive/periods/test-period/refresh").status_code == 401
        assert client.post("/admin/archive/periods/seed").status_code == 401
        assert client.get("/admin/archive/metadata/people").status_code == 401
        assert client.post("/admin/archive/metadata/people", json={"display_name": "Test"}).status_code == 401
        assert client.patch("/admin/archive/metadata/people/test", json={"display_name": "Updated"}).status_code == 401
        assert client.get("/admin/archive/metadata/tags").status_code == 401
        assert client.post("/admin/archive/metadata/tags", json={"label": "Test"}).status_code == 401
        assert client.patch("/admin/archive/metadata/tags/test", json={"label": "Updated"}).status_code == 401
        assert client.get("/admin/archive/metadata/videos").status_code == 401
        assert client.get(f"/admin/archive/metadata/videos/{uuid.uuid4()}").status_code == 401
        assert client.put(f"/admin/archive/metadata/videos/{uuid.uuid4()}", json={"people": [], "tags": []}).status_code == 401
        assert client.post("/admin/archive/metadata/seed-tags").status_code == 401

    def test_admin_archive_period_routes_require_admin(self, client: TestClient, db_session):
        session_token = _create_user_session(db_session, email="not-admin@example.com")
        cookies = {"tc_session": session_token}

        assert client.get("/admin/archive/periods", cookies=cookies).status_code == 403
        assert (
            client.post(
                "/admin/archive/periods",
                json={"label": "Test Period", "kind": "event", "date_from": "2026-01-01", "date_to": "2026-01-02"},
                cookies=cookies,
            ).status_code
            == 403
        )
        assert client.patch("/admin/archive/periods/test-period", json={"label": "Updated"}, cookies=cookies).status_code == 403
        assert client.post("/admin/archive/periods/test-period/refresh", cookies=cookies).status_code == 403
        assert client.post("/admin/archive/periods/seed", cookies=cookies).status_code == 403
        assert client.get("/admin/archive/metadata/people", cookies=cookies).status_code == 403
        assert client.post("/admin/archive/metadata/people", json={"display_name": "Test"}, cookies=cookies).status_code == 403
        assert client.patch("/admin/archive/metadata/people/test", json={"display_name": "Updated"}, cookies=cookies).status_code == 403
        assert client.get("/admin/archive/metadata/tags", cookies=cookies).status_code == 403
        assert client.post("/admin/archive/metadata/tags", json={"label": "Test"}, cookies=cookies).status_code == 403
        assert client.patch("/admin/archive/metadata/tags/test", json={"label": "Updated"}, cookies=cookies).status_code == 403
        assert client.get("/admin/archive/metadata/videos", cookies=cookies).status_code == 403
        assert client.get(f"/admin/archive/metadata/videos/{uuid.uuid4()}", cookies=cookies).status_code == 403
        assert client.put(f"/admin/archive/metadata/videos/{uuid.uuid4()}", json={"people": [], "tags": []}, cookies=cookies).status_code == 403
        assert client.post("/admin/archive/metadata/seed-tags", cookies=cookies).status_code == 403

    def test_video_info_includes_public_metadata_arrays(self, client: TestClient, db_session):
        video_id = _create_completed_video(
            db_session,
            youtube_id="metadata123",
            title="Metadata Video",
            uploaded_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            duration_seconds=180,
        )
        person = create_person(db_session, {"display_name": "Guest One", "slug": "guest-one"})
        tag = create_tag(db_session, {"label": "Chadvice", "slug": "chadvice"})
        set_video_metadata(
            db_session,
            video_id,
            people=[{"slug": person["slug"], "role": "guest"}],
            tags=[{"slug": tag["slug"]}],
        )
        db_session.commit()

        response = client.get(f"/videos/{video_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["people"] == [
            {"slug": "guest-one", "display_name": "Guest One", "aliases": [], "description": None, "role": "guest"}
        ]
        assert data["tags"] == [{"slug": "chadvice", "label": "Chadvice", "kind": "category", "description": None}]

    def test_archive_timeline(self, client: TestClient, db_session):
        first_video = _create_completed_video(
            db_session,
            youtube_id="timeline1",
            title="Timeline One",
            uploaded_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
            duration_seconds=180,
        )
        second_video = _create_completed_video(
            db_session,
            youtube_id="timeline2",
            title="Timeline Two",
            uploaded_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
            duration_seconds=240,
        )
        for vid, text_value in ((first_video, "first archive transcript"), (second_video, "second archive transcript")):
            db_session.execute(
                text("INSERT INTO segments (video_id, start_ms, end_ms, text, speaker_label) VALUES (:vid, 0, 1000, :text, NULL)"),
                {"vid": str(vid), "text": text_value},
            )
        db_session.commit()

        response = client.get("/archive/timeline?granularity=month&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["buckets"]) >= 2
        assert data["buckets"][0]["video_count"] >= 1

    @patch("app.crud.get_grouped_search")
    def test_grouped_search_route(self, mock_grouped_search, client: TestClient):
        video = VideoInfo(id=uuid.uuid4(), youtube_id="yt123", title="Grouped Video", duration_seconds=120)
        moment = SearchMoment(id=1, video_id=video.id, start_ms=1000, end_ms=2000, snippet="match here", source="whisper")
        mock_grouped_search.return_value = GroupedSearchResponse(total_moments=1, total_videos=1, groups=[EpisodeSearchGroup(video=video, moments=[moment])], query_time_ms=7)

        response = client.get("/search/grouped?q=match&source=native")
        assert response.status_code == 200
        data = response.json()
        assert data["total_moments"] == 1
        assert data["groups"][0]["video"]["youtube_id"] == "yt123"
        assert data["groups"][0]["moments"][0]["snippet"] == "match here"

    @patch("app.crud.get_mention_map")
    def test_mention_map_route(self, mock_mention_map, client: TestClient):
        video = VideoInfo(id=uuid.uuid4(), youtube_id="yt456", title="Mention Video", duration_seconds=90)
        moment = SearchMoment(id=2, video_id=video.id, start_ms=500, end_ms=1500, snippet="mention here", source="youtube")
        grouped = EpisodeSearchGroup(video=video, moments=[moment])
        mock_mention_map.return_value = MentionMap(
            query="mention",
            total_moments=1,
            total_videos=1,
            first_mentioned_year=2021,
            most_discussed_period="2024",
            most_discussed_count=3,
            recent_mentions_90d=6,
            related_topics=["copyright", "openai"],
            top_episodes_count=1,
            first_mention=moment,
            latest_mention=moment,
            top_episodes=[grouped],
            query_time_ms=4,
        )

        response = client.get("/search/mention-map?q=mention&source=youtube")
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "mention"
        assert data["first_mentioned_year"] == 2021
        assert data["most_discussed_period"] == "2024"
        assert data["recent_mentions_90d"] == 6
        assert data["related_topics"] == ["copyright", "openai"]
        assert data["top_episodes_count"] == 1
        assert data["first_mention"]["snippet"] == "mention here"
        assert data["top_episodes"][0]["video"]["youtube_id"] == "yt456"
