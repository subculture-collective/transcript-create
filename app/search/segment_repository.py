from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text


def _match_expressions(alias: str, q: str, filters: dict[str, Any], params: dict[str, Any]):
    mode = filters.get("match_mode", "topic")
    text_column = f"{alias}.text"
    tsv_column = f"{alias}.text_tsv"
    if mode == "exact_phrase":
        params["literal_q"] = q.strip().lower()
        return (
            f"position(lower(:literal_q) in lower({text_column})) > 0",
            text_column,
            "1.0",
            "position(lower(:literal_q) in lower(v.title)) > 0",
        )
    if mode == "whole_word":
        escaped = re.escape(q.strip()).replace(r"\ ", r"\s+")
        params["whole_word_q"] = rf"\m{escaped}\M"
        return (
            f"{text_column} ~* :whole_word_q",
            text_column,
            "1.0",
            "v.title ~* :whole_word_q",
        )
    return (
        f"{tsv_column} @@ websearch_to_tsquery('english', :q)",
        f"ts_headline('english', {text_column}, websearch_to_tsquery('english', :q))",
        f"ts_rank_cd({tsv_column}, websearch_to_tsquery('english', :q))",
        "v.title ILIKE :title_q",
    )


class SearchRepository:
    def search_native(
        self,
        db,
        q: str,
        video_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "relevance",
        filters: dict[str, Any] | None = None,
    ):
        from app.metrics import search_queries_total

        filters = filters or {}
        params = {"q": q, "limit": limit, "offset": offset, "title_q": f"%{q.strip()}%"}
        text_match, highlighted_text, text_rank, title_match = _match_expressions("s", q, filters, params)

        # Build WHERE clause with filters. Search transcript text and video title so
        # users can find newly processed videos by title from the main search box.
        where_clauses = [f"({text_match} OR {title_match})"]

        if video_id:
            where_clauses.append("s.video_id = :vid")
            params["vid"] = str(video_id)

        # Join with videos table for title search, sorting, and filter support.
        needs_video_join = True

        if needs_video_join:
            if filters.get("date_from"):
                where_clauses.append("v.uploaded_at >= :date_from")
                params["date_from"] = filters["date_from"]
            if filters.get("date_to"):
                where_clauses.append("v.uploaded_at <= :date_to")
                params["date_to"] = filters["date_to"]
            if filters.get("min_duration") is not None:
                where_clauses.append("v.duration_seconds >= :min_duration")
                params["min_duration"] = filters["min_duration"]
            if filters.get("max_duration") is not None:
                where_clauses.append("v.duration_seconds <= :max_duration")
                params["max_duration"] = filters["max_duration"]
            if filters.get("category"):
                where_clauses.append("v.category ILIKE :category")
                params["category"] = filters["category"]
            if filters.get("channel"):
                where_clauses.append("v.channel_name ILIKE :channel")
                params["channel"] = f"%{filters['channel']}%"
            if filters.get("language"):
                where_clauses.append("v.language = :language")
                params["language"] = filters["language"]

        # Speaker labels filter
        if filters.get("has_speaker_labels") is not None:
            if filters["has_speaker_labels"]:
                where_clauses.append("s.speaker_label IS NOT NULL")
            else:
                where_clauses.append("s.speaker_label IS NULL")

        # Build ORDER BY clause
        if sort_by == "date_desc":
            order_by = "v.uploaded_at DESC NULLS LAST, s.start_ms ASC"
        elif sort_by == "date_asc":
            order_by = "v.uploaded_at ASC NULLS LAST, s.start_ms ASC"
        elif sort_by == "duration_desc":
            order_by = "v.duration_seconds DESC NULLS LAST, s.start_ms ASC"
        elif sort_by == "duration_asc":
            order_by = "v.duration_seconds ASC NULLS LAST, s.start_ms ASC"
        else:  # relevance (default)
            order_by = "rank DESC, title_match DESC, s.start_ms ASC"

        # Build query
        from_clause = "segments s"
        select_fields = (
            "s.id, s.video_id, s.start_ms, s.end_ms, "
            f"CASE WHEN {text_match} THEN {highlighted_text} "
            "ELSE coalesce(v.title, s.text) END AS snippet, "
            f"{text_rank} AS rank, "
            f"CASE WHEN {title_match} THEN 1 ELSE 0 END AS title_match"
        )

        if needs_video_join:
            from_clause = "segments s JOIN videos v ON s.video_id = v.id"

        sql = f"""
            SELECT {select_fields}
            FROM {from_clause}
            WHERE {" AND ".join(where_clauses)}
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        """

        rows = db.execute(text(sql), params).mappings().all()

        # Track search query metric
        search_queries_total.labels(backend="postgres").inc()

        return rows

    def search_youtube(
        self,
        db,
        q: str,
        video_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "relevance",
        filters: dict[str, Any] | None = None,
    ):
        filters = filters or {}
        params = {"q": q, "limit": limit, "offset": offset, "title_q": f"%{q.strip()}%"}
        text_match, highlighted_text, text_rank, title_match = _match_expressions("ys", q, filters, params)

        # Keep transcript text search separate from title/youtube_id metadata search.
        # Applying a title match directly to every youtube_segments row makes title
        # searches scan/return every caption segment for matching videos.
        text_where = [text_match]
        title_where = [f"({title_match} OR v.youtube_id ILIKE :title_q)"]

        if video_id:
            text_where.append("yt.video_id = :vid")
            title_where.append("yt.video_id = :vid")
            params["vid"] = str(video_id)

        # Join with videos table for filter support
        needs_video_join = True

        if needs_video_join:
            if filters.get("date_from"):
                text_where.append("v.uploaded_at >= :date_from")
                title_where.append("v.uploaded_at >= :date_from")
                params["date_from"] = filters["date_from"]
            if filters.get("date_to"):
                text_where.append("v.uploaded_at <= :date_to")
                title_where.append("v.uploaded_at <= :date_to")
                params["date_to"] = filters["date_to"]
            if filters.get("min_duration") is not None:
                text_where.append("v.duration_seconds >= :min_duration")
                title_where.append("v.duration_seconds >= :min_duration")
                params["min_duration"] = filters["min_duration"]
            if filters.get("max_duration") is not None:
                text_where.append("v.duration_seconds <= :max_duration")
                title_where.append("v.duration_seconds <= :max_duration")
                params["max_duration"] = filters["max_duration"]
            if filters.get("category"):
                text_where.append("v.category ILIKE :category")
                title_where.append("v.category ILIKE :category")
                params["category"] = filters["category"]
            if filters.get("channel"):
                text_where.append("v.channel_name ILIKE :channel")
                title_where.append("v.channel_name ILIKE :channel")
                params["channel"] = f"%{filters['channel']}%"
            if filters.get("language"):
                text_where.append("v.language = :language")
                title_where.append("v.language = :language")
                params["language"] = filters["language"]

        # Build ORDER BY clause
        if sort_by == "date_desc":
            order_by = "uploaded_at DESC NULLS LAST, start_ms ASC"
        elif sort_by == "date_asc":
            order_by = "uploaded_at ASC NULLS LAST, start_ms ASC"
        elif sort_by == "duration_desc":
            order_by = "duration_seconds DESC NULLS LAST, start_ms ASC"
        elif sort_by == "duration_asc":
            order_by = "duration_seconds ASC NULLS LAST, start_ms ASC"
        else:  # relevance (default)
            order_by = "title_match DESC, rank DESC, start_ms ASC"

        sql = f"""
            WITH text_hits AS (
                SELECT
                    ys.id,
                    yt.video_id,
                    ys.start_ms,
                    ys.end_ms,
                    {highlighted_text} AS snippet,
                    {text_rank} AS rank,
                    0 AS title_match,
                    v.uploaded_at,
                    v.duration_seconds,
                    v.title AS video_title,
                    v.channel_name
                FROM youtube_segments ys
                JOIN youtube_transcripts yt ON yt.id = ys.youtube_transcript_id
                JOIN videos v ON yt.video_id = v.id
                WHERE {" AND ".join(text_where)}
            ), title_hits AS (
                SELECT DISTINCT ON (yt.video_id)
                    ys.id,
                    yt.video_id,
                    ys.start_ms,
                    ys.end_ms,
                    coalesce(v.title, ys.text) AS snippet,
                    0.0 AS rank,
                    1 AS title_match,
                    v.uploaded_at,
                    v.duration_seconds,
                    v.title AS video_title,
                    v.channel_name
                FROM youtube_transcripts yt
                JOIN videos v ON yt.video_id = v.id
                JOIN youtube_segments ys ON ys.youtube_transcript_id = yt.id
                WHERE {" AND ".join(title_where)}
                ORDER BY yt.video_id, ys.start_ms ASC
            )
            SELECT id, video_id, start_ms, end_ms, snippet, rank, title_match,
                   uploaded_at, duration_seconds, video_title, channel_name
            FROM (
                SELECT * FROM text_hits
                UNION ALL
                SELECT * FROM title_hits
            ) youtube_hits
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        """

        rows = db.execute(text(sql), params).mappings().all()
        return rows

    def search_best(
        self,
        db,
        q: str,
        video_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "relevance",
        filters: dict[str, Any] | None = None,
    ):
        from app.metrics import search_queries_total

        filters = filters or {}
        params = {"q": q, "limit": limit, "offset": offset, "title_q": f"%{q.strip()}%"}
        native_match, native_highlight, native_rank, title_match = _match_expressions("s", q, filters, params)
        youtube_match, youtube_highlight, youtube_rank, _ = _match_expressions("ys", q, filters, params)
        native_where = [f"({native_match} OR {title_match})"]
        youtube_where = [youtube_match]
        youtube_title_where = [f"({title_match} OR v.youtube_id ILIKE :title_q)"]

        if video_id:
            native_where.append("s.video_id = :vid")
            youtube_where.append("yt.video_id = :vid")
            youtube_title_where.append("yt.video_id = :vid")
            params["vid"] = str(video_id)

        if filters.get("date_from"):
            native_where.append("v.uploaded_at >= :date_from")
            youtube_where.append("v.uploaded_at >= :date_from")
            youtube_title_where.append("v.uploaded_at >= :date_from")
            params["date_from"] = filters["date_from"]
        if filters.get("date_to"):
            native_where.append("v.uploaded_at <= :date_to")
            youtube_where.append("v.uploaded_at <= :date_to")
            youtube_title_where.append("v.uploaded_at <= :date_to")
            params["date_to"] = filters["date_to"]
        if filters.get("min_duration") is not None:
            native_where.append("v.duration_seconds >= :min_duration")
            youtube_where.append("v.duration_seconds >= :min_duration")
            youtube_title_where.append("v.duration_seconds >= :min_duration")
            params["min_duration"] = filters["min_duration"]
        if filters.get("max_duration") is not None:
            native_where.append("v.duration_seconds <= :max_duration")
            youtube_where.append("v.duration_seconds <= :max_duration")
            youtube_title_where.append("v.duration_seconds <= :max_duration")
            params["max_duration"] = filters["max_duration"]
        if filters.get("channel"):
            native_where.append("v.channel_name ILIKE :channel")
            youtube_where.append("v.channel_name ILIKE :channel")
            youtube_title_where.append("v.channel_name ILIKE :channel")
            params["channel"] = f"%{filters['channel']}%"
        if filters.get("category"):
            native_where.append("v.category ILIKE :category")
            youtube_where.append("v.category ILIKE :category")
            youtube_title_where.append("v.category ILIKE :category")
            params["category"] = filters["category"]
        if filters.get("language"):
            native_where.append("v.language = :language")
            youtube_where.append("v.language = :language")
            youtube_title_where.append("v.language = :language")
            params["language"] = filters["language"]
        if filters.get("has_speaker_labels") is not None:
            if filters["has_speaker_labels"]:
                native_where.append("s.speaker_label IS NOT NULL")
                youtube_where.append("FALSE")
            else:
                native_where.append("s.speaker_label IS NULL")

        youtube_where.append("NOT EXISTS (SELECT 1 FROM segments native_s WHERE native_s.video_id = yt.video_id)")
        youtube_title_where.append("NOT EXISTS (SELECT 1 FROM segments native_s WHERE native_s.video_id = yt.video_id)")

        if sort_by == "date_desc":
            order_by = "uploaded_at DESC NULLS LAST, start_ms ASC"
        elif sort_by == "date_asc":
            order_by = "uploaded_at ASC NULLS LAST, start_ms ASC"
        elif sort_by == "duration_desc":
            order_by = "duration_seconds DESC NULLS LAST, start_ms ASC"
        elif sort_by == "duration_asc":
            order_by = "duration_seconds ASC NULLS LAST, start_ms ASC"
        else:
            order_by = "rank DESC, title_match DESC, start_ms ASC"

        sql = f"""
            SELECT id, video_id, start_ms, end_ms, snippet, source, rank, title_match,
                   uploaded_at, duration_seconds, video_title, channel_name
            FROM (
                SELECT
                    s.id,
                    s.video_id,
                    s.start_ms,
                    s.end_ms,
                    CASE WHEN {native_match}
                        THEN {native_highlight}
                        ELSE coalesce(v.title, s.text)
                    END AS snippet,
                    'whisper' AS source,
                    {native_rank} AS rank,
                    CASE WHEN {title_match} THEN 1 ELSE 0 END AS title_match,
                    v.uploaded_at,
                    v.duration_seconds,
                    v.title AS video_title,
                    v.channel_name
                FROM segments s
                JOIN videos v ON s.video_id = v.id
                WHERE {" AND ".join(native_where)}

                UNION ALL

                SELECT
                    ys.id,
                    yt.video_id,
                    ys.start_ms,
                    ys.end_ms,
                    CASE WHEN {youtube_match}
                        THEN {youtube_highlight}
                        ELSE coalesce(v.title, ys.text)
                    END AS snippet,
                    'youtube' AS source,
                    {youtube_rank} AS rank,
                    CASE WHEN {title_match} OR v.youtube_id ILIKE :title_q THEN 1 ELSE 0 END AS title_match,
                    v.uploaded_at,
                    v.duration_seconds,
                    v.title AS video_title,
                    v.channel_name
                FROM youtube_segments ys
                JOIN youtube_transcripts yt ON yt.id = ys.youtube_transcript_id
                JOIN videos v ON yt.video_id = v.id
                WHERE {" AND ".join(youtube_where)}

                UNION ALL

                SELECT DISTINCT ON (yt.video_id)
                    ys.id,
                    yt.video_id,
                    ys.start_ms,
                    ys.end_ms,
                    coalesce(v.title, ys.text) AS snippet,
                    'youtube' AS source,
                    0.0 AS rank,
                    1 AS title_match,
                    v.uploaded_at,
                    v.duration_seconds,
                    v.title AS video_title,
                    v.channel_name
                FROM youtube_transcripts yt
                JOIN videos v ON yt.video_id = v.id
                JOIN youtube_segments ys ON ys.youtube_transcript_id = yt.id
                WHERE {" AND ".join(youtube_title_where)}
                ORDER BY video_id, start_ms ASC
            ) best_hits
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        """
        rows = db.execute(text(sql), params).mappings().all()
        search_queries_total.labels(backend="postgres").inc()
        return rows
