from __future__ import annotations

from app.archive.labeling.quality import apply_quality_gate


def classify_candidate(candidate: dict, policy: dict, existing_canonical: bool) -> tuple[str, str]:
    score = float(candidate.get("confidence_score") or 0)
    evidence_count = int(candidate.get("evidence_count") or 0)
    distinct_videos = int(candidate.get("distinct_videos") or 0)

    min_publish = float(policy.get("min_publish_score") or 0.90)
    min_review = float(policy.get("min_review_score") or 0.65)
    min_evidence = int(policy.get("min_evidence_count") or 1)
    min_videos = int(policy.get("min_distinct_videos") or 1)
    require_existing = bool(policy.get("require_existing_canonical"))
    auto_publish = bool(policy.get("auto_publish_enabled", True))

    evidence_ok = evidence_count >= min_evidence and distinct_videos >= min_videos
    canonical_ok = existing_canonical or not require_existing

    if score >= min_publish and evidence_ok and canonical_ok:
        publish_tier, assignment_status = "gold", "auto_published" if auto_publish else "candidate"
        if candidate.get("label"):
            publish_tier, assignment_status, _assessment = apply_quality_gate(
                str(candidate.get("label") or ""),
                publish_tier,
                assignment_status,
                source=str(candidate.get("source") or "") or None,
                assignment_count=evidence_count,
                distinct_videos=distinct_videos,
                existing_canonical=existing_canonical,
            )
        return publish_tier, assignment_status

    silver_threshold = max(min_review, min_publish - 0.12)
    if score >= silver_threshold and evidence_ok and existing_canonical:
        publish_tier, assignment_status = "silver", "auto_published" if auto_publish else "candidate"
        if candidate.get("label"):
            publish_tier, assignment_status, _assessment = apply_quality_gate(
                str(candidate.get("label") or ""),
                publish_tier,
                assignment_status,
                source=str(candidate.get("source") or "") or None,
                assignment_count=evidence_count,
                distinct_videos=distinct_videos,
                existing_canonical=existing_canonical,
            )
        return publish_tier, assignment_status

    if score >= min_review and evidence_count > 0:
        return "bronze", "candidate"

    return "shadow", "shadow"
