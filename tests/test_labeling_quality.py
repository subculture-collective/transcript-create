from app.archive.labeling.policy import classify_candidate
from app.archive.labeling.quality import assess_label_quality, canonical_hint_for_label


def test_assess_label_quality_marks_incomplete_phrase_noise():
    assessment = assess_label_quality("A Bunch Of", source="keyphrase", assignment_count=20, distinct_videos=5)

    assert assessment.action == "mark_noise"
    assert "weak_opener" in assessment.reasons
    assert "weak_closer" in assessment.reasons


def test_assess_label_quality_suggests_context_alias_without_confusing_related_terms():
    assessment = assess_label_quality("About Israel", source="keyphrase", assignment_count=10, distinct_videos=3)

    assert assessment.action == "review"
    assert assessment.canonical_hint == "Israel"
    assert assessment.needs_llm_review is True


def test_assess_label_quality_maps_vaccinated_phrase_to_vaccination_review():
    assessment = assess_label_quality("Get Vaccinated", source="keyphrase", assignment_count=10, distinct_videos=3)

    assert assessment.action == "review"
    assert assessment.canonical_hint == "Vaccination"


def test_canonical_hint_for_label_prefers_known_entity():
    assert canonical_hint_for_label("About Gaza") == "Gaza"


def test_canonical_hint_does_not_strip_to_incomplete_phrase():
    assert canonical_hint_for_label("A Woman And") is None


def test_policy_demotes_auto_publish_for_bad_phrase_when_label_present():
    candidate = {
        "label": "A Bunch Of",
        "source": "keyphrase",
        "confidence_score": 0.98,
        "evidence_count": 10,
        "distinct_videos": 3,
    }
    policy = {
        "min_publish_score": 0.90,
        "min_review_score": 0.65,
        "min_evidence_count": 1,
        "min_distinct_videos": 1,
        "require_existing_canonical": False,
        "auto_publish_enabled": True,
    }

    assert classify_candidate(candidate, policy, existing_canonical=False) == ("shadow", "shadow")
