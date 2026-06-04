from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.exceptions import ValidationError


DEFAULT_TAG_SEEDS: tuple[dict[str, str], ...] = (
    {"slug": "chadvice", "label": "Chadvice"},
    {"slug": "okbuddy", "label": "OKBuddy"},
    {"slug": "gaming", "label": "Gaming"},
    {"slug": "guests", "label": "Guests"},
    {"slug": "news", "label": "News"},
    {"slug": "politics", "label": "Politics"},
    {"slug": "react", "label": "React"},
    {"slug": "debate", "label": "Debate"},
    {"slug": "interview", "label": "Interview"},
)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "item"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return loaded if isinstance(loaded, list) else [loaded]
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if item is not None and str(item) != ""]


def _normalize_person_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["aliases"] = _string_list(data.get("aliases"))
    return data


def _normalize_tag_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _in_clause(prefix: str, values: list[Any]) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {}
    placeholders: list[str] = []
    for idx, value in enumerate(values):
        key = f"{prefix}_{idx}"
        placeholders.append(f":{key}")
        params[key] = value
    return ", ".join(placeholders), params


def _extract_existing_row(db, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    return db.execute(text(sql), params).mappings().first()


def _upsert_row(db, sql: str, params: dict[str, Any], duplicate_message: str):
    try:
        return db.execute(text(sql), params).mappings().first()
    except IntegrityError as exc:
        raise ValidationError(duplicate_message, field="slug") from exc


def seed_default_tags(db) -> dict[str, int]:
    inserted = 0
    for seed in DEFAULT_TAG_SEEDS:
        db.execute(
            text(
                """
                INSERT INTO archive_video_tags (
                    slug, label, kind, status, sort_order, created_at, updated_at
                ) VALUES (
                    :slug, :label, 'category', 'published', 0, now(), now()
                )
                ON CONFLICT (slug) DO UPDATE SET
                    label = EXCLUDED.label,
                    kind = EXCLUDED.kind,
                    status = EXCLUDED.status,
                    updated_at = now()
                """
            ),
            seed,
        )
        inserted += 1
    return {"tags": inserted}


def create_person(db, payload: dict) -> dict:
    display_name = (payload.get("display_name") or "").strip()
    if not display_name:
        raise ValidationError("display_name is required", field="display_name")
    raw_slug = payload.get("slug")
    slug = slugify(str(raw_slug)) if raw_slug and str(raw_slug).strip() else slugify(display_name)
    params = {
        "slug": slug,
        "display_name": display_name,
        "aliases": json.dumps(_string_list(payload.get("aliases"))),
        "description": payload.get("description"),
        "status": payload.get("status") or "published",
        "sort_order": int(payload.get("sort_order") or 0),
    }
    row = _upsert_row(
        db,
        """
        INSERT INTO archive_people (
            slug, display_name, aliases, description, status, sort_order, created_at, updated_at
        ) VALUES (
            :slug, :display_name, CAST(:aliases AS JSONB), :description, :status, :sort_order, now(), now()
        )
        RETURNING *
        """,
        params,
        f"Archive person slug '{slug}' already exists",
    )
    return dict(_normalize_person_row(row) or {})


def update_person(db, slug: str, payload: dict) -> dict | None:
    current = _extract_existing_row(
        db,
        "SELECT * FROM archive_people WHERE slug = :slug",
        {"slug": slug},
    )
    if current is None:
        return None

    updates: list[str] = []
    params: dict[str, Any] = {"slug": slug}
    for field in ("display_name", "description", "status", "sort_order"):
        if field in payload and payload[field] is not None:
            updates.append(f"{field} = :{field}")
            params[field] = payload[field]
    if "aliases" in payload and payload["aliases"] is not None:
        updates.append("aliases = CAST(:aliases AS JSONB)")
        params["aliases"] = json.dumps(_string_list(payload["aliases"]))
    if not updates:
        return dict(_normalize_person_row(current) or {})
    updates.append("updated_at = now()")
    row = _upsert_row(
        db,
        f"""
        UPDATE archive_people
        SET {', '.join(updates)}
        WHERE slug = :slug
        RETURNING *
        """,
        params,
        f"Archive person slug '{params.get('slug', slug)}' already exists",
    )
    return dict(_normalize_person_row(row) or {})


def list_people_admin(
    db,
    q: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    where_parts: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if q:
        where_parts.append("(p.display_name ILIKE :q OR p.slug ILIKE :q OR p.description ILIKE :q OR p.aliases::text ILIKE :q)")
        params["q"] = f"%{q}%"
    if status:
        where_parts.append("p.status = :status")
        params["status"] = status
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    rows = db.execute(
        text(
            f"""
            SELECT p.*
            FROM archive_people p
            {where_sql}
            ORDER BY p.sort_order ASC, p.display_name ASC, p.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    return [dict(_normalize_person_row(row) or {}) for row in rows]


def create_tag(db, payload: dict) -> dict:
    label = (payload.get("label") or "").strip()
    if not label:
        raise ValidationError("label is required", field="label")
    raw_slug = payload.get("slug")
    slug = slugify(str(raw_slug)) if raw_slug and str(raw_slug).strip() else slugify(label)
    params = {
        "slug": slug,
        "label": label,
        "kind": payload.get("kind") or "category",
        "description": payload.get("description"),
        "status": payload.get("status") or "published",
        "sort_order": int(payload.get("sort_order") or 0),
    }
    row = _upsert_row(
        db,
        """
        INSERT INTO archive_video_tags (
            slug, label, kind, description, status, sort_order, created_at, updated_at
        ) VALUES (
            :slug, :label, :kind, :description, :status, :sort_order, now(), now()
        )
        RETURNING *
        """,
        params,
        f"Archive tag slug '{slug}' already exists",
    )
    return dict(_normalize_tag_row(row) or {})


def update_tag(db, slug: str, payload: dict) -> dict | None:
    current = _extract_existing_row(
        db,
        "SELECT * FROM archive_video_tags WHERE slug = :slug",
        {"slug": slug},
    )
    if current is None:
        return None

    updates: list[str] = []
    params: dict[str, Any] = {"slug": slug}
    for field in ("label", "kind", "description", "status", "sort_order"):
        if field in payload and payload[field] is not None:
            updates.append(f"{field} = :{field}")
            params[field] = payload[field]
    if not updates:
        return dict(_normalize_tag_row(current) or {})
    updates.append("updated_at = now()")
    row = _upsert_row(
        db,
        f"""
        UPDATE archive_video_tags
        SET {', '.join(updates)}
        WHERE slug = :slug
        RETURNING *
        """,
        params,
        f"Archive tag slug '{params.get('slug', slug)}' already exists",
    )
    return dict(_normalize_tag_row(row) or {})


def list_tags_admin(
    db,
    q: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    where_parts: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if q:
        where_parts.append("(t.label ILIKE :q OR t.slug ILIKE :q OR t.description ILIKE :q)")
        params["q"] = f"%{q}%"
    if status:
        where_parts.append("t.status = :status")
        params["status"] = status
    if kind:
        where_parts.append("t.kind = :kind")
        params["kind"] = kind
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    rows = db.execute(
        text(
            f"""
            SELECT t.*
            FROM archive_video_tags t
            {where_sql}
            ORDER BY t.sort_order ASC, t.label ASC, t.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    return [dict(_normalize_tag_row(row) or {}) for row in rows]


def set_video_metadata(db, video_id, people: list[dict], tags: list[dict]) -> dict:
    video_row = db.execute(
        text("SELECT id FROM videos WHERE id = :video_id FOR UPDATE"),
        {"video_id": video_id},
    ).mappings().first()
    if video_row is None:
        raise ValidationError("video_id not found", field="video_id")

    video_id_str = str(video_id)
    people_by_slug = {
        str(item.get("slug") or "").strip(): item
        for item in people
        if (item.get("slug") or "").strip()
    }
    tag_by_input_slug = {
        str(item.get("slug") or "").strip(): item
        for item in tags
        if (item.get("slug") or "").strip()
    }
    people_slugs = list(people_by_slug.keys())
    tag_slugs = list(tag_by_input_slug.keys())

    person_rows = []
    if people_slugs:
        clause, params = _in_clause("slug", list(dict.fromkeys(people_slugs)))
        person_rows = db.execute(
            text(
                f"""
                SELECT id, slug, display_name, aliases, description, status, sort_order
                FROM archive_people
                WHERE slug IN ({clause})
                """
            ),
            params,
        ).mappings().all()
    tag_rows = []
    if tag_slugs:
        clause, params = _in_clause("slug", list(dict.fromkeys(tag_slugs)))
        tag_rows = db.execute(
            text(
                f"""
                SELECT id, slug, label, kind, description, status, sort_order
                FROM archive_video_tags
                WHERE slug IN ({clause})
                """
            ),
            params,
        ).mappings().all()

    person_by_slug = {row["slug"]: row for row in person_rows}
    tag_by_slug = {row["slug"]: row for row in tag_rows}
    missing_people = [slug for slug in dict.fromkeys(people_slugs) if slug not in person_by_slug]
    missing_tags = [slug for slug in dict.fromkeys(tag_slugs) if slug not in tag_by_slug]
    if missing_people or missing_tags:
        missing = ", ".join([*(f"person:{slug}" for slug in missing_people), *(f"tag:{slug}" for slug in missing_tags)])
        raise ValidationError(f"Unknown metadata slug(s): {missing}", field="slug")

    db.execute(text("DELETE FROM archive_video_people WHERE video_id = :video_id"), {"video_id": video_id_str})
    db.execute(text("DELETE FROM archive_video_taggings WHERE video_id = :video_id"), {"video_id": video_id_str})

    for slug, item in people_by_slug.items():
        person = person_by_slug[slug]
        db.execute(
            text(
                """
                INSERT INTO archive_video_people (
                    video_id, person_id, role, confidence, notes, created_at
                ) VALUES (
                    :video_id, :person_id, :role, :confidence, :notes, now()
                )
                """
            ),
            {
                "video_id": video_id_str,
                "person_id": person["id"],
                "role": item.get("role") or "guest",
                "confidence": item.get("confidence") or "admin",
                "notes": item.get("notes"),
            },
        )

    for slug, item in tag_by_input_slug.items():
        tag = tag_by_slug[slug]
        db.execute(
            text(
                """
                INSERT INTO archive_video_taggings (
                    video_id, tag_id, confidence, notes, created_at
                ) VALUES (
                    :video_id, :tag_id, :confidence, :notes, now()
                )
                """
            ),
            {
                "video_id": video_id_str,
                "tag_id": tag["id"],
                "confidence": item.get("confidence") or "admin",
                "notes": item.get("notes"),
            },
        )

    return {"video_id": video_id_str, "people": len(people_by_slug), "tags": len(tag_by_input_slug)}


def _get_video_metadata_map(db, video_ids: list, published_only: bool) -> dict[str, dict[str, list[dict]]]:
    result: dict[str, dict[str, list[dict]]] = {
        str(video_id): {"people": [], "tags": []} for video_id in video_ids
    }
    if not video_ids:
        return result

    video_id_values = [str(video_id) for video_id in video_ids]
    clause, params = _in_clause("video_id", video_id_values)

    people_rows = db.execute(
        text(
            f"""
            SELECT
                vp.video_id,
                p.slug,
                p.display_name,
                p.aliases,
                p.description,
                vp.role,
                vp.confidence,
                vp.notes,
                p.sort_order
            FROM archive_video_people vp
            JOIN archive_people p ON p.id = vp.person_id
            WHERE vp.video_id IN ({clause})
              {"AND p.status = 'published'" if published_only else ""}
            ORDER BY p.sort_order ASC, p.display_name ASC, vp.created_at ASC
            """
        ),
        params,
    ).mappings().all()
    for row in people_rows:
        video_key = str(row["video_id"])
        bucket = result.setdefault(video_key, {"people": [], "tags": []})
        bucket["people"].append(
            {
                "slug": row["slug"],
                "display_name": row["display_name"],
                "aliases": _string_list(row.get("aliases")),
                "description": row.get("description"),
                "role": row.get("role"),
                "sort_order": int(row.get("sort_order") or 0),
            }
        )

    tag_rows = db.execute(
        text(
            f"""
            SELECT
                vt.video_id,
                t.slug,
                t.label,
                t.kind,
                t.description,
                vt.confidence,
                vt.notes,
                t.sort_order
            FROM archive_video_taggings vt
            JOIN archive_video_tags t ON t.id = vt.tag_id
            WHERE vt.video_id IN ({clause})
              {"AND t.status = 'published'" if published_only else ""}
            ORDER BY t.sort_order ASC, t.label ASC, vt.created_at ASC
            """
        ),
        params,
    ).mappings().all()
    for row in tag_rows:
        video_key = str(row["video_id"])
        bucket = result.setdefault(video_key, {"people": [], "tags": []})
        bucket["tags"].append(
            {
                "slug": row["slug"],
                "label": row["label"],
                "kind": row["kind"],
                "description": row.get("description"),
                "sort_order": int(row.get("sort_order") or 0),
            }
        )

    return result


def get_video_metadata_map(db, video_ids: list, published_only: bool = True) -> dict[str, dict[str, list[dict]]]:
    return _get_video_metadata_map(db, video_ids, published_only=published_only)


def get_video_metadata_admin_map(db, video_ids: list) -> dict[str, dict[str, list[dict]]]:
    return _get_video_metadata_map(db, video_ids, published_only=False)


def search_videos_for_admin(db, q: str | None = None, limit: int = 50) -> list[dict]:
    params: dict[str, Any] = {"limit": limit}
    where_sql = ""
    if q:
        where_sql = "WHERE (v.title ILIKE :q OR v.youtube_id ILIKE :q OR v.channel_name ILIKE :q)"
        params["q"] = f"%{q}%"
    rows = db.execute(
        text(
            f"""
            SELECT
                v.id,
                v.youtube_id,
                v.title,
                v.duration_seconds,
                v.state,
                v.uploaded_at,
                v.created_at,
                v.updated_at,
                v.channel_name,
                v.language,
                v.category,
                EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id) AS has_whisper_transcript,
                EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript
            FROM videos v
            {where_sql}
            ORDER BY v.uploaded_at DESC NULLS LAST, v.created_at DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    video_ids = [row["id"] for row in rows]
    metadata_map = _get_video_metadata_map(db, video_ids, published_only=False)
    results: list[dict] = []
    for row in rows:
        video = dict(row)
        video_id = str(video["id"])
        video["people"] = metadata_map.get(video_id, {"people": [], "tags": []}).get("people", [])
        video["tags"] = metadata_map.get(video_id, {"people": [], "tags": []}).get("tags", [])
        results.append(video)
    return results
