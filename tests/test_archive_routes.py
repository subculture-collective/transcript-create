"""Tests for archive and grouped search routes."""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.schemas import EpisodeSearchGroup, GroupedSearchResponse, MentionMap, SearchMoment, VideoInfo


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
        db_session.execute(
            text("INSERT INTO search_suggestions (term, frequency) VALUES (:term, :frequency)"),
            {"term": "ice protests", "frequency": 7},
        )
        db_session.commit()

        response = client.get("/archive/intelligence?topic_limit=4&period_limit=3")

        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["creator_name"] == "HasAnAra"
        assert data["exploration_modes"] == ["timeline", "topics", "trending", "suggested"]
        assert data["trending_searches"][0]["term"] == "ice protests"
        assert data["topic_cards"]
        assert data["periods"]
        assert data["periods"][0]["evidence"]
        assert data["periods"][0]["evidence"][0]["video"]["youtube_id"] == "explore1"

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
