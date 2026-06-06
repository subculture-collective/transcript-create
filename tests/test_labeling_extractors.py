from app.archive.intelligence_repository import alias_matches_text
from app.archive.labeling.extractors import extract_alias_candidates, extract_keyphrase_candidates, extract_title_alias_candidates, suggest_person_names_from_title, suggest_person_names_from_titles
from app.archive.labeling.normalization import is_junk_phrase, normalize_label, normalized_alias, slugify_label


def test_keyphrase_extractor_finds_repeated_domain_phrase_and_filters_single_video_phrase():
    windows = [
        {"id": "w1", "video_id": "v1", "text": "okbuddy starts the segment and okbuddy is the joke", "start_ms": 0, "end_ms": 60000},
        {"id": "w2", "video_id": "v2", "text": "people keep saying okbuddy during this stream", "start_ms": 0, "end_ms": 60000},
        {"id": "w3", "video_id": "v3", "text": "chadvice call segment and chadvice question", "start_ms": 0, "end_ms": 60000},
    ]

    candidates = extract_keyphrase_candidates(windows, min_distinct_videos=2, min_occurrences=2)
    labels = {candidate.label for candidate in candidates}

    assert "Okbuddy" in labels
    assert "Chadvice" not in labels

    candidate = next(item for item in candidates if item.label == "Okbuddy")
    assert candidate.aliases == ("okbuddy",)
    assert candidate.component_scores["occurrences"] >= 2
    assert candidate.evidence[0]["extractor"] == "keyphrase"


def test_alias_extractor_uses_matching_alias_evidence_and_ignores_non_matches():
    windows = [
        {"id": "w1", "video_id": "v1", "text": "Trump and Gaza were discussed", "start_ms": 1000, "end_ms": 5000},
        {"id": "w2", "video_id": "v2", "text": "nothing relevant here", "start_ms": 6000, "end_ms": 9000},
    ]
    aliases = [
        {"label_id": "topic-gaza", "label": "Gaza", "alias": "gaza", "kind": "topic", "status": "active"},
    ]

    candidates = extract_alias_candidates(windows, aliases)

    assert [candidate.label for candidate in candidates] == ["Gaza"]
    assert candidates[0].evidence[0]["window_id"] == "w1"
    assert candidates[0].evidence[0]["matched_alias"] == "gaza"
    assert candidates[0].evidence[0]["extractor"] == "alias"


def test_ambiguous_and_inactive_aliases_do_not_produce_candidates():
    windows = [{"id": "w1", "video_id": "v1", "text": "ICE raid in the news", "start_ms": 0, "end_ms": 1000}]
    aliases = [
        {"label_id": "topic-ice", "label": "ICE", "alias": "ice", "kind": "topic", "status": "inactive"},
        {"label_id": "topic-ice-2", "label": "ICE", "alias": "ice", "kind": "topic", "status": "active", "is_ambiguous": True},
    ]

    assert extract_alias_candidates(windows, aliases) == []


def test_normalization_rejects_junk_phrases_and_slugifies_labels():
    assert is_junk_phrase("")
    assert is_junk_phrase("yeah")
    assert is_junk_phrase("12345")
    assert is_junk_phrase("stream vod chat")
    assert is_junk_phrase("About")
    assert is_junk_phrase("About This")
    assert is_junk_phrase("About The")
    assert is_junk_phrase("Able To")
    assert is_junk_phrase("10 Years")
    assert not is_junk_phrase("okbuddy")
    assert not is_junk_phrase("New Jersey")
    assert not is_junk_phrase("The Majority Report")
    assert not is_junk_phrase("Call of Duty")

    assert normalize_label("  new jersey  ") == "New Jersey"
    assert normalize_label("ICE") == "ICE"
    assert normalized_alias("ICE Raid!!") == "ice raid"
    assert slugify_label("New Jersey") == "new-jersey"
    assert slugify_label("   ") == "label"


def test_alias_matching_respects_boundaries():
    assert not alias_matches_text("ice", "nice")
    assert alias_matches_text("ice", "ICE raid")


def test_extractors_sort_deterministically():
    windows = [
        {"id": "w1", "video_id": "v1", "text": "alpha beta alpha beta", "start_ms": 0, "end_ms": 1000},
        {"id": "w2", "video_id": "v2", "text": "alpha beta alpha beta", "start_ms": 1000, "end_ms": 2000},
    ]

    candidates = extract_keyphrase_candidates(windows, min_distinct_videos=2, min_occurrences=2)
    assert [candidate.label for candidate in candidates] == sorted(candidate.label for candidate in candidates)


def test_title_alias_extractor_emits_title_source_candidates():
    aliases = [
        {"label_id": "tag-chadvice", "label": "Chadvice", "alias": "chadvice", "kind": "category", "status": "active", "is_ambiguous": False},
        {"label_id": "tag-gaming", "label": "Gaming", "alias": "gaming", "kind": "category", "status": "active", "is_ambiguous": True},
    ]

    candidates = extract_title_alias_candidates({"id": "video-1", "title": "HasanAbi April 23, 2026 – hanging out after Chadvice"}, aliases)

    assert [candidate.label for candidate in candidates] == ["Chadvice"]
    assert candidates[0].kind == "category"
    assert candidates[0].evidence[0]["extractor"] == "title"
    assert candidates[0].evidence[0]["matched_alias"] == "chadvice"


def test_title_person_suggester_finds_names_and_filters_hasan_noise():
    names = suggest_person_names_from_title("HasanAbi May 27, 2026 – back in LA, Senate candidate Julie Gonzales visits")

    assert "Julie Gonzales" in names
    assert "HasanAbi" not in names


def test_title_person_suggester_groups_examples():
    suggestions = suggest_person_names_from_titles(
        [
            {"id": "v1", "title": "HasanAbi – Julie Gonzales visits"},
            {"id": "v2", "title": "HasanAbi – talking with Julie Gonzales"},
        ]
    )

    julie = next(item for item in suggestions if item["name"] == "Julie Gonzales")
    assert julie["count"] == 2
    assert julie["titles"][0]["video_id"] == "v1"
