from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.archive.video_metadata_repository import slugify
from app.exceptions import ValidationError

VALID_ENTITY_TYPES = {"person", "game", "event", "topic", "place", "org", "meme", "category", "series", "thing"}
TAG_ENTITY_TYPES = VALID_ENTITY_TYPES - {"person"}
PERSON_ROLES = {"guest", "host", "caller", "subject", "mentioned"}


def _normalized_alias(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def parse_aliases(value: str | None) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for raw in str(value or "").split("|"):
        alias = raw.strip()
        normalized = _normalized_alias(alias)
        if not alias or not normalized or normalized in seen:
            continue
        aliases.append(alias)
        seen.add(normalized)
    return aliases


def _merge_aliases(*alias_groups: Iterable[str]) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for group in alias_groups:
        for raw in group:
            alias = str(raw or "").strip()
            normalized = _normalized_alias(alias)
            if not alias or not normalized or normalized in seen:
                continue
            aliases.append(alias)
            seen.add(normalized)
    return aliases


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item or "").strip()]
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value.strip() else []
        if isinstance(loaded, list):
            return [str(item) for item in loaded if str(item or "").strip()]
        return [str(loaded)] if str(loaded or "").strip() else []
    return [str(value)] if str(value or "").strip() else []


def normalize_curation_row(row: dict[str, str]) -> dict[str, object] | None:
    decision = str(row.get("decision") or "").strip().lower()
    if not decision or decision == "skip":
        return None
    if decision != "approve":
        raise ValidationError(f"Unsupported curation decision '{decision}'", field="decision")

    entity_type = str(row.get("entity_type") or "").strip().lower()
    canonical = str(row.get("canonical") or "").strip()
    candidate = str(row.get("candidate") or row.get("name") or "").strip()
    if entity_type not in VALID_ENTITY_TYPES:
        raise ValidationError(f"Unsupported entity_type '{entity_type}'", field="entity_type")
    if not canonical:
        raise ValidationError("canonical is required for approved curation rows", field="canonical")
    person_role = str(row.get("person_role") or "").strip().lower() or None
    if person_role and person_role not in PERSON_ROLES:
        raise ValidationError(f"Unsupported person_role '{person_role}'", field="person_role")
    if person_role and entity_type != "person":
        raise ValidationError("person_role can only be set for person rows", field="person_role")

    aliases = _merge_aliases([candidate, canonical], parse_aliases(row.get("aliases")))
    return {
        "candidate": candidate,
        "entity_type": entity_type,
        "canonical": canonical,
        "aliases": aliases,
        "person_role": person_role,
        "notes": str(row.get("notes") or "").strip() or None,
    }


def read_curation_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _upsert_person(db, *, canonical: str, aliases: list[str], notes: str | None, default_role: str | None) -> str:
    slug = slugify(canonical)
    current = db.execute(text("SELECT * FROM archive_people WHERE slug = :slug"), {"slug": slug}).mappings().first()
    merged_aliases = _merge_aliases(_json_list(current.get("aliases") if current else None), aliases)
    if current is None:
        db.execute(
            text(
                """
                INSERT INTO archive_people (
                    slug, display_name, aliases, description, default_role, status, sort_order, created_at, updated_at
                ) VALUES (
                    :slug,
                    :display_name,
                    CAST(:aliases AS JSONB),
                    :description,
                    :default_role,
                    'published',
                    0,
                    now(),
                    now()
                )
                """
            ),
            {
                "slug": slug,
                "display_name": canonical,
                "aliases": json.dumps(merged_aliases),
                "description": notes,
                "default_role": default_role,
            },
        )
        return slug
    db.execute(
        text(
            """
            UPDATE archive_people
            SET display_name = :display_name,
                aliases = CAST(:aliases AS JSONB),
                description = COALESCE(description, :description),
                default_role = COALESCE(:default_role, default_role),
                status = CASE WHEN status = 'hidden' THEN status ELSE 'published' END,
                updated_at = now()
            WHERE slug = :slug
            """
        ),
        {
            "slug": slug,
            "display_name": canonical,
            "aliases": json.dumps(merged_aliases),
            "description": notes,
            "default_role": default_role,
        },
    )
    return slug


def _tag_kind(entity_type: str) -> str:
    if entity_type == "thing":
        return "topic"
    return entity_type


def _upsert_tag(db, *, entity_type: str, canonical: str, notes: str | None) -> str:
    slug = slugify(canonical)
    kind = _tag_kind(entity_type)
    current = db.execute(text("SELECT * FROM archive_video_tags WHERE slug = :slug"), {"slug": slug}).mappings().first()
    if current is None:
        db.execute(
            text(
                """
                INSERT INTO archive_video_tags (
                    slug, label, kind, description, status, sort_order, created_at, updated_at
                ) VALUES (
                    :slug, :label, :kind, :description, 'published', 0, now(), now()
                )
                """
            ),
            {"slug": slug, "label": canonical, "kind": kind, "description": notes},
        )
        return slug
    db.execute(
        text(
            """
            UPDATE archive_video_tags
            SET label = :label,
                kind = :kind,
                description = COALESCE(description, :description),
                status = CASE WHEN status = 'hidden' THEN status ELSE 'published' END,
                updated_at = now()
            WHERE slug = :slug
            """
        ),
        {"slug": slug, "label": canonical, "kind": kind, "description": notes},
    )
    return slug


def _label_kind(entity_type: str) -> str:
    if entity_type == "thing":
        return "topic"
    return entity_type


def _upsert_label_aliases(db, *, entity_type: str, canonical: str, aliases: list[str], notes: str | None) -> int:
    slug = slugify(canonical)
    kind = _label_kind(entity_type)
    label_row = db.execute(
        text(
            """
            INSERT INTO archive_labels (
                slug, label, kind, description, status, source, publish_tier, confidence_score, created_at, updated_at
            ) VALUES (
                :slug, :label, :kind, :description, 'published', 'admin', 'gold', 1, now(), now()
            )
            ON CONFLICT (slug) DO UPDATE SET
                label = EXCLUDED.label,
                kind = EXCLUDED.kind,
                description = COALESCE(archive_labels.description, EXCLUDED.description),
                status = CASE
                    WHEN archive_labels.status IN ('rejected', 'merged') THEN archive_labels.status
                    ELSE 'published'
                END,
                publish_tier = 'gold',
                updated_at = now()
            RETURNING id
            """
        ),
        {"slug": slug, "label": canonical, "kind": kind, "description": notes},
    ).mappings().first()
    if label_row is None:
        return 0
    count = 0
    for alias in _merge_aliases([slug.replace("-", " "), canonical], aliases):
        normalized = _normalized_alias(alias)
        if not normalized:
            continue
        db.execute(
            text(
                """
                INSERT INTO archive_label_aliases (
                    label_id, alias, normalized_alias, language, weight, source, status, is_ambiguous, created_at
                ) VALUES (
                    :label_id, :alias, :normalized_alias, 'en', 1, 'admin', 'active', false, now()
                )
                ON CONFLICT (label_id, normalized_alias) DO NOTHING
                """
            ),
            {"label_id": label_row["id"], "alias": alias, "normalized_alias": normalized},
        )
        count += 1
    return count


def import_title_entity_curation_rows(db, rows: list[dict[str, str]], *, seed_aliases: bool = True) -> dict[str, int]:
    people: set[str] = set()
    tags: set[str] = set()
    approved_count = 0
    alias_count = 0
    for raw_row in rows:
        row = normalize_curation_row(raw_row)
        if row is None:
            continue
        approved_count += 1
        canonical = str(row["canonical"])
        raw_aliases = row.get("aliases")
        aliases = [str(alias) for alias in raw_aliases] if isinstance(raw_aliases, list) else []
        raw_notes = row.get("notes")
        notes = raw_notes if isinstance(raw_notes, str) else None
        raw_person_role = row.get("person_role")
        person_role = raw_person_role if isinstance(raw_person_role, str) else None
        entity_type = str(row["entity_type"])
        if entity_type == "person":
            people.add(_upsert_person(db, canonical=canonical, aliases=aliases, notes=notes, default_role=person_role))
        elif entity_type in TAG_ENTITY_TYPES:
            tags.add(_upsert_tag(db, entity_type=entity_type, canonical=canonical, notes=notes))
        if seed_aliases:
            alias_count += _upsert_label_aliases(
                db, entity_type=entity_type, canonical=canonical, aliases=aliases, notes=notes
            )

    return {"rows": approved_count, "people": len(people), "tags": len(tags), "aliases": alias_count}
