"""Tests for archive video metadata repository."""

import json
import uuid

from app.archive.video_metadata_repository import (
    create_person,
    create_tag,
    get_video_metadata_map,
    list_people_admin,
    list_tags_admin,
    seed_default_tags,
    search_videos_for_admin,
    set_video_metadata,
    slugify,
    update_person,
    update_tag,
)
from app.exceptions import ValidationError


class _FakeResult:
    def __init__(self, *, first=None, rows=None):
        self._first = first
        self._rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._rows


class _FakeMetadataDb:
    def __init__(self):
        self.calls = []
        self.rollback_count = 0
        self.people: dict[str, dict] = {}
        self.tags: dict[str, dict] = {}
        self.video_people: list[dict] = []
        self.video_taggings: list[dict] = []
        self.videos: dict[str, dict] = {}

    def rollback(self):
        self.rollback_count += 1

    def add_video(self, *, video_id: str | uuid.UUID, title: str, youtube_id: str = "yt-1", channel_name: str = "HasanAbi"):
        self.videos[str(video_id)] = {
            "id": video_id,
            "youtube_id": youtube_id,
            "title": title,
            "duration_seconds": 120,
            "state": "completed",
            "uploaded_at": None,
            "created_at": None,
            "updated_at": None,
            "channel_name": channel_name,
            "language": "en",
            "category": None,
        }

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.calls.append((sql, params))

        if "INSERT INTO archive_people" in sql:
            row = {
                "id": uuid.uuid4(),
                "slug": params["slug"],
                "display_name": params["display_name"],
                "aliases": json.loads(params["aliases"]),
                "description": params.get("description"),
                "status": params.get("status", "published"),
                "sort_order": params.get("sort_order", 0),
            }
            self.people[row["slug"]] = row
            return _FakeResult(first=row)

        if sql.strip().startswith("SELECT * FROM archive_people WHERE slug = :slug"):
            return _FakeResult(first=self.people.get(params["slug"]))

        if "UPDATE archive_people" in sql:
            current = self.people[params["slug"]].copy()
            for key in ("slug", "display_name", "description", "status", "sort_order"):
                if key in params:
                    current[key] = params[key]
            if "aliases" in params:
                current["aliases"] = json.loads(params["aliases"])
            self.people.pop(params["slug"])
            self.people[current["slug"]] = current
            return _FakeResult(first=current)

        if sql.strip().startswith("SELECT p.*") and "FROM archive_people p" in sql:
            rows = list(self.people.values())
            if params.get("status"):
                rows = [row for row in rows if row["status"] == params["status"]]
            if params.get("q"):
                q = params["q"].strip("%").lower()
                rows = [
                    row
                    for row in rows
                    if q in row["display_name"].lower()
                    or q in row["slug"].lower()
                    or q in (row.get("description") or "").lower()
                    or q in json.dumps(row.get("aliases", [])).lower()
                ]
            rows.sort(key=lambda row: (row["sort_order"], row["display_name"].lower()))
            return _FakeResult(rows=rows[params["offset"] : params["offset"] + params["limit"]])

        if "INSERT INTO archive_video_tags" in sql:
            row = {
                "id": uuid.uuid4(),
                "slug": params["slug"],
                "label": params["label"],
                "kind": params.get("kind", "category"),
                "description": params.get("description"),
                "status": params.get("status", "published"),
                "sort_order": params.get("sort_order", 0),
            }
            self.tags[row["slug"]] = row
            return _FakeResult(first=row)

        if sql.strip().startswith("SELECT * FROM archive_video_tags WHERE slug = :slug"):
            return _FakeResult(first=self.tags.get(params["slug"]))

        if "UPDATE archive_video_tags" in sql:
            current = self.tags[params["slug"]].copy()
            for key in ("slug", "label", "kind", "description", "status", "sort_order"):
                if key in params:
                    current[key] = params[key]
            self.tags.pop(params["slug"])
            self.tags[current["slug"]] = current
            return _FakeResult(first=current)

        if sql.strip().startswith("SELECT t.*") and "FROM archive_video_tags t" in sql:
            rows = list(self.tags.values())
            if params.get("status"):
                rows = [row for row in rows if row["status"] == params["status"]]
            if params.get("kind"):
                rows = [row for row in rows if row["kind"] == params["kind"]]
            if params.get("q"):
                q = params["q"].strip("%").lower()
                rows = [
                    row
                    for row in rows
                    if q in row["label"].lower()
                    or q in row["slug"].lower()
                    or q in (row.get("description") or "").lower()
                ]
            rows.sort(key=lambda row: (row["sort_order"], row["label"].lower()))
            return _FakeResult(rows=rows[params["offset"] : params["offset"] + params["limit"]])

        if "INSERT INTO archive_video_people" in sql and "RETURNING" not in sql:
            self.video_people.append(params)
            return _FakeResult()

        if "INSERT INTO archive_video_taggings" in sql and "RETURNING" not in sql:
            self.video_taggings.append(params)
            return _FakeResult()

        if sql.strip().startswith("DELETE FROM archive_video_people"):
            self.video_people = [row for row in self.video_people if row["video_id"] != params["video_id"]]
            return _FakeResult()

        if sql.strip().startswith("DELETE FROM archive_video_taggings"):
            self.video_taggings = [row for row in self.video_taggings if row["video_id"] != params["video_id"]]
            return _FakeResult()

        if "FROM archive_video_people vp" in sql:
            video_ids = {value for key, value in params.items() if key.startswith("video_id_")}
            published_only = "p.status = 'published'" in sql
            rows = []
            for join in self.video_people:
                if join["video_id"] not in video_ids:
                    continue
                person = next(
                    (
                        row
                        for row in self.people.values()
                        if row["id"] == join["person_id"] and (not published_only or row["status"] == "published")
                    ),
                    None,
                )
                if not person:
                    continue
                rows.append(
                    {
                        "video_id": join["video_id"],
                        "slug": person["slug"],
                        "display_name": person["display_name"],
                        "aliases": person["aliases"],
                        "description": person.get("description"),
                        "role": join.get("role"),
                        "confidence": join.get("confidence"),
                        "notes": join.get("notes"),
                        "sort_order": person.get("sort_order", 0),
                    }
                )
            rows.sort(key=lambda row: (row["sort_order"], row["display_name"].lower()))
            return _FakeResult(rows=rows)

        if "FROM archive_video_taggings vt" in sql:
            video_ids = {value for key, value in params.items() if key.startswith("video_id_")}
            published_only = "t.status = 'published'" in sql
            rows = []
            for join in self.video_taggings:
                if join["video_id"] not in video_ids:
                    continue
                tag = next(
                    (
                        row
                        for row in self.tags.values()
                        if row["id"] == join["tag_id"] and (not published_only or row["status"] == "published")
                    ),
                    None,
                )
                if not tag:
                    continue
                rows.append(
                    {
                        "video_id": join["video_id"],
                        "slug": tag["slug"],
                        "label": tag["label"],
                        "kind": tag["kind"],
                        "description": tag.get("description"),
                        "confidence": join.get("confidence"),
                        "notes": join.get("notes"),
                        "sort_order": tag.get("sort_order", 0),
                    }
                )
            rows.sort(key=lambda row: (row["sort_order"], row["label"].lower()))
            return _FakeResult(rows=rows)

        if "FROM videos v" in sql:
            rows = list(self.videos.values())
            if params.get("q"):
                q = params["q"].strip("%").lower()
                rows = [
                    row
                    for row in rows
                    if q in row["title"].lower()
                    or q in row["youtube_id"].lower()
                    or q in row["channel_name"].lower()
                ]
            rows.sort(key=lambda row: (row["created_at"] is None, row["created_at"]))
            return _FakeResult(rows=rows[: params["limit"]])

        if sql.strip().startswith("SELECT id FROM videos WHERE id = :video_id FOR UPDATE"):
            row = self.videos.get(str(params["video_id"]))
            return _FakeResult(first={"id": row["id"]} if row else None)

        if sql.strip().startswith("SELECT") and "FROM archive_people" in sql and "WHERE slug IN" in sql:
            slugs = {value for key, value in params.items() if key.startswith("slug_")}
            return _FakeResult(rows=[self.people[slug] for slug in slugs if slug in self.people])

        if sql.strip().startswith("SELECT") and "FROM archive_video_tags" in sql and "WHERE slug IN" in sql:
            slugs = {value for key, value in params.items() if key.startswith("slug_")}
            return _FakeResult(rows=[self.tags[slug] for slug in slugs if slug in self.tags])

        if "INSERT INTO archive_video_tags" in sql and "ON CONFLICT" in sql:
            existing = self.tags.get(params["slug"])
            if existing:
                existing.update({"label": params["label"], "kind": "category", "status": "published"})
            else:
                self.tags[params["slug"]] = {
                    "id": uuid.uuid4(),
                    "slug": params["slug"],
                    "label": params["label"],
                    "kind": "category",
                    "description": None,
                    "status": "published",
                    "sort_order": 0,
                }
            return _FakeResult()

        raise AssertionError(f"Unexpected query: {sql}")


def test_slugify_and_admin_create_list_people():
    db = _FakeMetadataDb()

    assert slugify("Guest One!!") == "guest-one"

    person = create_person(
        db,
        {"display_name": "Guest One", "slug": "Guest One!!", "aliases": ["G1"], "description": "Guest"},
    )
    assert person["slug"] == "guest-one"
    assert person["aliases"] == ["G1"]

    update_person(db, "guest-one", {"status": "hidden", "sort_order": 3})
    hidden = list_people_admin(db, status="hidden")
    assert hidden[0]["slug"] == "guest-one"

    listed = list_people_admin(db, q="guest", status="hidden")
    assert listed[0]["display_name"] == "Guest One"


def test_create_list_tags_and_seed_default_tags_idempotent():
    db = _FakeMetadataDb()

    tag = create_tag(db, {"label": "Chadvice", "slug": "Chadvice"})
    assert tag["slug"] == "chadvice"

    normalized = create_tag(db, {"label": "Other Tag", "slug": "Other Tag!!"})
    assert normalized["slug"] == "other-tag"

    update_tag(db, "chadvice", {"status": "hidden"})
    assert list_tags_admin(db, status="hidden")[0]["slug"] == "chadvice"

    first = seed_default_tags(db)
    second = seed_default_tags(db)
    assert first["tags"] == second["tags"] == 9
    assert len(db.tags) == 10


def test_video_metadata_assignment_round_trip_and_public_filtering():
    db = _FakeMetadataDb()
    video_id = uuid.uuid4()
    db.add_video(video_id=video_id, title="Metadata VOD", youtube_id="meta1")

    guest = create_person(db, {"display_name": "Guest One", "slug": "guest-one"})
    hidden_guest = create_person(db, {"display_name": "Hidden Guest", "slug": "hidden-guest", "status": "hidden"})
    tag = create_tag(db, {"label": "Chadvice", "slug": "chadvice"})
    hidden_tag = create_tag(db, {"label": "Hidden Tag", "slug": "hidden-tag", "status": "hidden"})

    set_video_metadata(
        db,
        video_id,
        people=[{"slug": guest["slug"], "role": "guest"}, {"slug": hidden_guest["slug"], "role": "guest"}],
        tags=[{"slug": tag["slug"]}, {"slug": hidden_tag["slug"]}],
    )

    metadata = get_video_metadata_map(db, [video_id])
    assert metadata[str(video_id)]["people"] == [
        {"slug": "guest-one", "display_name": "Guest One", "aliases": [], "description": None, "role": "guest"}
    ]
    assert metadata[str(video_id)]["tags"] == [{"slug": "chadvice", "label": "Chadvice", "kind": "category", "description": None}]

    admin = search_videos_for_admin(db, q="Metadata")
    assert {person["slug"] for person in admin[0]["people"]} == {"guest-one", "hidden-guest"}
    assert {tag["slug"] for tag in admin[0]["tags"]} == {"chadvice", "hidden-tag"}


def test_set_video_metadata_rejects_unknown_slugs():
    db = _FakeMetadataDb()
    video_id = uuid.uuid4()
    db.add_video(video_id=video_id, title="Metadata VOD", youtube_id="meta2")

    try:
        set_video_metadata(db, video_id, people=[{"slug": "missing"}], tags=[])
    except Exception as exc:
        assert exc.__class__.__name__ == "ValidationError"
    else:
        raise AssertionError("Expected validation error for missing slug")


def test_set_video_metadata_rejects_missing_video_even_without_metadata():
    db = _FakeMetadataDb()
    missing_video_id = uuid.uuid4()

    try:
        set_video_metadata(db, missing_video_id, people=[], tags=[])
    except ValidationError as exc:
        assert exc.message == "video_id not found"
        assert exc.details["field"] == "video_id"
    else:
        raise AssertionError("Expected validation error for missing video")

    assert any("FOR UPDATE" in sql for sql, _ in db.calls)
