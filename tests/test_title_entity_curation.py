import json

import pytest

from app.archive.title_entity_curation import import_title_entity_curation_rows, normalize_curation_row, parse_aliases
from app.exceptions import ValidationError


class _FakeResult:
    def __init__(self, first=None):
        self._first = first

    def mappings(self):
        return self

    def first(self):
        return self._first


class _FakeCurationDb:
    def __init__(self):
        self.people = {}
        self.tags = {}
        self.labels = {}
        self.label_aliases = []
        self.calls = []

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.calls.append((sql, params))

        if sql.strip().startswith("SELECT * FROM archive_people"):
            return _FakeResult(first=self.people.get(params["slug"]))
        if sql.strip().startswith("SELECT * FROM archive_video_tags"):
            return _FakeResult(first=self.tags.get(params["slug"]))

        if "INSERT INTO archive_people" in sql:
            self.people[params["slug"]] = {
                "slug": params["slug"],
                "display_name": params["display_name"],
                "aliases": json.loads(params["aliases"]),
                "description": params.get("description"),
                "default_role": params.get("default_role"),
                "status": "published",
            }
            return _FakeResult()
        if "UPDATE archive_people" in sql:
            current = self.people[params["slug"]]
            current.update(
                {
                    "display_name": params["display_name"],
                    "aliases": json.loads(params["aliases"]),
                    "description": current.get("description") or params.get("description"),
                    "default_role": params.get("default_role") or current.get("default_role"),
                    "status": "published",
                }
            )
            return _FakeResult()

        if "INSERT INTO archive_video_tags" in sql:
            self.tags[params["slug"]] = {
                "slug": params["slug"],
                "label": params["label"],
                "kind": params["kind"],
                "description": params.get("description"),
                "status": "published",
            }
            return _FakeResult()

        if "INSERT INTO archive_labels" in sql:
            row = self.labels.get(params["slug"]) or {"id": f"label-{params['slug']}", "slug": params["slug"]}
            row.update({"label": params["label"], "kind": params["kind"], "description": params.get("description")})
            self.labels[params["slug"]] = row
            return _FakeResult(first=row)
        if "INSERT INTO archive_label_aliases" in sql:
            key = (params["label_id"], params["normalized_alias"])
            if not any((row["label_id"], row["normalized_alias"]) == key for row in self.label_aliases):
                self.label_aliases.append(
                    {
                        "label_id": params["label_id"],
                        "alias": params["alias"],
                        "normalized_alias": params["normalized_alias"],
                    }
                )
            return _FakeResult()
        if "UPDATE archive_video_tags" in sql:
            current = self.tags[params["slug"]]
            current.update(
                {
                    "label": params["label"],
                    "kind": params["kind"],
                    "description": current.get("description") or params.get("description"),
                    "status": "published",
                }
            )
            return _FakeResult()

        return _FakeResult()


def test_parse_aliases_splits_pipe_and_dedupes():
    assert parse_aliases("Austin|AustinShow| Austin ") == ["Austin", "AustinShow"]


def test_normalize_curation_row_requires_approved_canonical_and_type():
    row = normalize_curation_row(
        {
            "candidate": "Austin",
            "decision": "approve",
            "entity_type": "person",
            "canonical": "AustinShow",
            "aliases": "Austin|AustinShow",
        }
    )

    assert row == {
        "candidate": "Austin",
        "entity_type": "person",
        "canonical": "AustinShow",
        "aliases": ["Austin", "AustinShow"],
        "person_role": None,
        "notes": None,
    }


def test_normalize_curation_row_skips_empty_or_skip_decisions():
    assert normalize_curation_row({"candidate": "Austin"}) is None
    assert normalize_curation_row({"candidate": "Austin", "decision": "skip"}) is None


def test_normalize_curation_row_rejects_bad_entity_type():
    with pytest.raises(ValidationError):
        normalize_curation_row(
            {"candidate": "Austin", "decision": "approve", "entity_type": "bad", "canonical": "Austin"}
        )


def test_import_merges_duplicate_person_candidates_into_one_alias_set():
    db = _FakeCurationDb()

    result = import_title_entity_curation_rows(
        db,
        [
            {
                "candidate": "Austin",
                "decision": "approve",
                "entity_type": "person",
                "canonical": "AustinShow",
                "aliases": "Austin",
            },
            {
                "candidate": "AustinShow",
                "decision": "approve",
                "entity_type": "person",
                "canonical": "AustinShow",
                "aliases": "austinshow",
            },
        ],
    )

    assert result == {"rows": 2, "people": 1, "tags": 0, "aliases": 3}
    assert db.people["austinshow"]["display_name"] == "AustinShow"
    assert db.people["austinshow"]["aliases"] == ["Austin", "AustinShow"]
    assert {row["alias"] for row in db.label_aliases} == {"austinshow", "Austin"}


def test_import_person_role_sets_default_role():
    db = _FakeCurationDb()

    result = import_title_entity_curation_rows(
        db,
        [
            {
                "candidate": "Will",
                "decision": "approve",
                "entity_type": "person",
                "person_role": "guest",
                "canonical": "Will Neff",
                "aliases": "Will|Will Neff",
            },
        ],
    )

    assert result["people"] == 1
    assert db.people["will-neff"]["default_role"] == "guest"


def test_person_role_only_allowed_for_person_rows():
    with pytest.raises(ValidationError):
        normalize_curation_row(
            {
                "candidate": "New Jersey",
                "decision": "approve",
                "entity_type": "place",
                "person_role": "guest",
                "canonical": "New Jersey",
            }
        )


def test_import_splits_composite_candidate_into_two_people():
    db = _FakeCurationDb()

    result = import_title_entity_curation_rows(
        db,
        [
            {
                "candidate": "Johnny Depp Amber Heard",
                "decision": "approve",
                "entity_type": "person",
                "canonical": "Johnny Depp",
                "aliases": "Johnny Depp",
            },
            {
                "candidate": "Johnny Depp Amber Heard",
                "decision": "approve",
                "entity_type": "person",
                "canonical": "Amber Heard",
                "aliases": "Amber Heard",
            },
        ],
    )

    assert result["people"] == 2
    assert "johnny-depp" in db.people
    assert "amber-heard" in db.people


def test_import_non_person_rows_create_tags_and_thing_becomes_topic():
    db = _FakeCurationDb()

    result = import_title_entity_curation_rows(
        db,
        [
            {
                "candidate": "Elden Ring",
                "decision": "approve",
                "entity_type": "game",
                "canonical": "Elden Ring",
                "aliases": "",
            },
            {
                "candidate": "Ceasefire Deal",
                "decision": "approve",
                "entity_type": "thing",
                "canonical": "Ceasefire Deal",
                "aliases": "",
            },
        ],
    )

    assert result == {"rows": 2, "people": 0, "tags": 2, "aliases": 2}
    assert db.tags["elden-ring"]["kind"] == "game"
    assert db.tags["ceasefire-deal"]["kind"] == "topic"
    assert db.labels["elden-ring"]["kind"] == "game"
    assert db.labels["ceasefire-deal"]["kind"] == "topic"


def test_import_place_rows_create_place_tags_and_labels():
    db = _FakeCurationDb()

    result = import_title_entity_curation_rows(
        db,
        [
            {
                "candidate": "NJ",
                "decision": "approve",
                "entity_type": "place",
                "canonical": "New Jersey",
                "aliases": "NJ|New Jersey",
            },
        ],
    )

    assert result == {"rows": 1, "people": 0, "tags": 1, "aliases": 2}
    assert db.tags["new-jersey"]["kind"] == "place"
    assert db.labels["new-jersey"]["kind"] == "place"
