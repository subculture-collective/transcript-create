from app.archive.labeling.policy import classify_candidate


def test_policy_auto_publishes_gold_with_enough_evidence():
    candidate = {
        "kind": "topic",
        "unit_type": "window",
        "confidence_score": 0.93,
        "evidence_count": 3,
        "distinct_videos": 2,
    }
    policy = {
        "min_publish_score": 0.90,
        "min_review_score": 0.65,
        "min_evidence_count": 2,
        "min_distinct_videos": 1,
        "require_existing_canonical": False,
        "auto_publish_enabled": True,
    }

    assert classify_candidate(candidate, policy, existing_canonical=False) == ("gold", "auto_published")


def test_policy_sends_weak_candidate_to_shadow():
    candidate = {"kind": "topic", "unit_type": "window", "confidence_score": 0.4, "evidence_count": 1, "distinct_videos": 1}
    policy = {
        "min_publish_score": 0.90,
        "min_review_score": 0.65,
        "min_evidence_count": 2,
        "min_distinct_videos": 1,
        "require_existing_canonical": False,
        "auto_publish_enabled": True,
    }

    assert classify_candidate(candidate, policy, existing_canonical=False) == ("shadow", "shadow")


def test_policy_marks_safe_existing_label_as_silver_auto_publish():
    candidate = {"kind": "topic", "unit_type": "window", "confidence_score": 0.82, "evidence_count": 2, "distinct_videos": 1}
    policy = {
        "min_publish_score": 0.90,
        "min_review_score": 0.65,
        "min_evidence_count": 2,
        "min_distinct_videos": 1,
        "require_existing_canonical": True,
        "auto_publish_enabled": True,
    }

    assert classify_candidate(candidate, policy, existing_canonical=True) == ("silver", "auto_published")


def test_policy_auto_publish_disabled_returns_candidate_tiers_only():
    candidate = {"kind": "topic", "unit_type": "window", "confidence_score": 0.93, "evidence_count": 3, "distinct_videos": 2}
    policy = {
        "min_publish_score": 0.90,
        "min_review_score": 0.65,
        "min_evidence_count": 2,
        "min_distinct_videos": 1,
        "require_existing_canonical": False,
        "auto_publish_enabled": False,
    }

    assert classify_candidate(candidate, policy, existing_canonical=False) == ("gold", "candidate")


def test_policy_require_existing_canonical_blocks_gold_for_non_existing():
    candidate = {"kind": "topic", "unit_type": "window", "confidence_score": 0.95, "evidence_count": 3, "distinct_videos": 2}
    policy = {
        "min_publish_score": 0.90,
        "min_review_score": 0.65,
        "min_evidence_count": 2,
        "min_distinct_videos": 1,
        "require_existing_canonical": True,
        "auto_publish_enabled": True,
    }

    assert classify_candidate(candidate, policy, existing_canonical=False) == ("bronze", "candidate")
