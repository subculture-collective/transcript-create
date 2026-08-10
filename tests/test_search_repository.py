from app import crud
from app.search.highlights import HIGHLIGHT_END, HIGHLIGHT_START, POSTGRES_HEADLINE_OPTIONS
from app.search.repositories import PostgresSearchBackend
from app.search.segment_repository import SearchRepository
from app.search.types import SearchRequest


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, statement, params):
        self.calls.append({"statement": statement, "params": params})
        return FakeResult(self.rows)


def test_search_native_builds_expected_sql_and_params():
    rows = [
        {
            "id": 1,
            "video_id": "v1",
            "start_ms": 10,
            "end_ms": 20,
            "snippet": f"🚀 {HIGHLIGHT_START}hello{HIGHLIGHT_END}",
            "rank": 1.0,
        }
    ]
    db = FakeDB(rows)
    repo = SearchRepository()

    result = repo.search_native(
        db,
        q="hello world",
        video_id="video-1",
        limit=5,
        offset=2,
        sort_by="date_desc",
        filters={
            "date_from": "2024-01-01",
            "date_to": "2024-12-31",
            "min_duration": 10,
            "max_duration": 600,
            "channel": "Hasan",
            "language": "en",
            "category": "news",
            "has_speaker_labels": True,
        },
    )

    assert result == [
        {
            **rows[0],
            "snippet": "🚀 hello",
            "highlights": [{"start": 2, "end": 7}],
        }
    ]
    sql = str(db.calls[0]["statement"])
    assert "FROM segments s JOIN videos v ON s.video_id = v.id" in sql
    assert "CASE WHEN s.text_tsv @@ websearch_to_tsquery('english', :q)" in sql
    assert "ORDER BY v.uploaded_at DESC NULLS LAST, s.start_ms ASC" in sql
    assert db.calls[0]["params"]["title_q"] == "%hello world%"
    assert db.calls[0]["params"]["vid"] == "video-1"
    assert db.calls[0]["params"]["channel"] == "%Hasan%"
    assert db.calls[0]["params"]["language"] == "en"
    assert db.calls[0]["params"]["headline_options"] == POSTGRES_HEADLINE_OPTIONS


def test_search_native_whole_word_mode_uses_unstemmed_full_text_index():
    db = FakeDB([])
    SearchRepository().search_native(
        db,
        q="house",
        filters={"match_mode": "whole_word"},
    )

    sql = str(db.calls[0]["statement"])
    assert "to_tsvector('simple', coalesce(s.text, '')) @@ plainto_tsquery('simple', :q)" in sql
    assert "websearch_to_tsquery" not in sql


def test_search_best_exact_phrase_mode_uses_unstemmed_phrase_query_for_both_sources():
    db = FakeDB([])
    SearchRepository().search_best(
        db,
        q="public housing",
        filters={"match_mode": "exact_phrase"},
    )

    sql = str(db.calls[0]["statement"])
    assert "to_tsvector('simple', coalesce(s.text, '')) @@ phraseto_tsquery('simple', :q)" in sql
    assert "to_tsvector('simple', coalesce(ys.text, '')) @@ phraseto_tsquery('simple', :q)" in sql


def test_search_youtube_builds_expected_sql_and_params():
    rows = [
        {
            "id": 2,
            "video_id": "v2",
            "start_ms": 30,
            "end_ms": 40,
            "snippet": f"{HIGHLIGHT_START}caption{HIGHLIGHT_END}",
            "rank": 0.7,
            "title_match": 1,
            "uploaded_at": None,
            "duration_seconds": None,
            "video_title": "Title",
            "channel_name": "Channel",
        }
    ]
    db = FakeDB(rows)
    repo = SearchRepository()

    result = repo.search_youtube(db, q="caption", limit=3, offset=1, sort_by="relevance", filters={})

    assert result == [{**rows[0], "snippet": "caption", "highlights": [{"start": 0, "end": 7}]}]
    sql = str(db.calls[0]["statement"])
    assert "WITH text_hits AS (" in sql
    assert "title_hits AS (" in sql
    assert "ORDER BY title_match DESC, rank DESC, start_ms ASC" in sql
    assert db.calls[0]["params"]["title_q"] == "%caption%"
    assert db.calls[0]["params"]["headline_options"] == POSTGRES_HEADLINE_OPTIONS


def test_search_best_builds_expected_sql_and_preserves_source():
    rows = [
        {
            "id": 3,
            "video_id": "v3",
            "start_ms": 50,
            "end_ms": 60,
            "snippet": f"<script>x</script> {HIGHLIGHT_START}best{HIGHLIGHT_END}",
            "source": "youtube",
            "rank": 0.5,
            "title_match": 1,
            "uploaded_at": None,
            "duration_seconds": None,
            "video_title": "Best Title",
            "channel_name": "Best Channel",
        }
    ]
    db = FakeDB(rows)
    repo = SearchRepository()

    result = repo.search_best(db, q="best", limit=7, offset=0, sort_by="duration_asc", filters={})

    assert result == [
        {
            **rows[0],
            "snippet": "<script>x</script> best",
            "highlights": [{"start": 19, "end": 23}],
        }
    ]
    sql = str(db.calls[0]["statement"])
    assert "NOT EXISTS (SELECT 1 FROM segments native_s WHERE native_s.video_id = yt.video_id)" in sql
    assert "s.text_tsv @@ websearch_to_tsquery('english', :q) OR v.title ILIKE :title_q" not in sql
    assert "FROM segments s" in sql
    assert "WHERE s.text_tsv @@ websearch_to_tsquery('english', :q)" in sql
    assert "JOIN LATERAL" in sql
    assert "WHERE v.title ILIKE :title_q" in sql
    assert "ORDER BY duration_seconds ASC NULLS LAST, start_ms ASC" in sql
    assert db.calls[0]["params"]["headline_options"] == POSTGRES_HEADLINE_OPTIONS


def test_legacy_postgres_search_paths_return_plain_snippets(monkeypatch):
    monkeypatch.setattr(
        "app.metrics.search_queries_total.labels", lambda **_kwargs: type("Metric", (), {"inc": lambda self: None})()
    )
    native_db = FakeDB(
        [
            {
                "id": 4,
                "video_id": "v4",
                "start_ms": 0,
                "end_ms": 1,
                "snippet": f"literal <img onerror=x> {HIGHLIGHT_START}match{HIGHLIGHT_END}",
                "rank": 1.0,
            }
        ]
    )
    youtube_db = FakeDB(
        [
            {
                "id": 5,
                "video_id": "v5",
                "start_ms": 0,
                "end_ms": 1,
                "snippet": f"{HIGHLIGHT_START}match{HIGHLIGHT_END} &lt;safe&gt;",
                "rank": 1.0,
            }
        ]
    )

    native = crud.search_segments(native_db, q="match")
    youtube = crud.search_youtube_segments(youtube_db, q="match")

    assert native[0]["snippet"] == "literal <img onerror=x> match"
    assert native[0]["highlights"] == [{"start": 24, "end": 29}]
    assert youtube[0]["snippet"] == "match &lt;safe&gt;"
    assert youtube[0]["highlights"] == [{"start": 0, "end": 5}]
    assert native_db.calls[0]["params"]["headline_options"] == POSTGRES_HEADLINE_OPTIONS
    assert youtube_db.calls[0]["params"]["headline_options"] == POSTGRES_HEADLINE_OPTIONS


def test_crud_wrappers_delegate_to_search_repository(monkeypatch):
    calls = {}

    def fake_native(db, **kwargs):
        calls["native"] = (db, kwargs)
        return [{"id": 1, "video_id": "v1", "start_ms": 0, "end_ms": 1, "snippet": "n", "rank": 1.0}]

    def fake_youtube(db, **kwargs):
        calls["youtube"] = (db, kwargs)
        return [{"id": 2, "video_id": "v2", "start_ms": 0, "end_ms": 1, "snippet": "y", "rank": 1.0}]

    def fake_best(db, **kwargs):
        calls["best"] = (db, kwargs)
        return [{"id": 3, "video_id": "v3", "start_ms": 0, "end_ms": 1, "snippet": "b", "source": "whisper"}]

    monkeypatch.setattr(crud._search_repository, "search_native", fake_native)
    monkeypatch.setattr(crud._search_repository, "search_youtube", fake_youtube)
    monkeypatch.setattr(crud._search_repository, "search_best", fake_best)

    db = object()
    assert crud.search_segments_advanced(db, q="q", limit=4, offset=2) == [
        {"id": 1, "video_id": "v1", "start_ms": 0, "end_ms": 1, "snippet": "n", "rank": 1.0}
    ]
    assert crud.search_youtube_segments_advanced(db, q="q", limit=4, offset=2) == [
        {"id": 2, "video_id": "v2", "start_ms": 0, "end_ms": 1, "snippet": "y", "rank": 1.0}
    ]
    assert crud.search_best_segments_advanced(db, q="q", limit=4, offset=2) == [
        {"id": 3, "video_id": "v3", "start_ms": 0, "end_ms": 1, "snippet": "b", "source": "whisper"}
    ]

    assert calls["native"][0] is db
    assert calls["youtube"][1]["q"] == "q"
    assert calls["best"][1]["offset"] == 2


def test_postgres_backend_uses_repository(monkeypatch):
    calls = {}

    class FakeRepository:
        def search_native(self, db, **kwargs):
            calls["db"] = db
            calls["kwargs"] = kwargs
            return [
                {
                    "id": 7,
                    "video_id": "v7",
                    "start_ms": 10,
                    "end_ms": 20,
                    "snippet": "snip",
                    "highlights": [{"start": 0, "end": 4}],
                    "rank": 1.5,
                }
            ]

    backend = PostgresSearchBackend(db=object(), repository=FakeRepository())
    results = backend.search(SearchRequest(q="hello", source="native", limit=5, offset=2, sort_by="date_desc"))

    assert calls["db"] is backend.db
    assert calls["kwargs"]["q"] == "hello"
    assert results[0].id == 7
    assert results[0].video_id == "v7"
    assert results[0].snippet == "snip"
    assert results[0].highlights == ({"start": 0, "end": 4},)
