import json
from datetime import date
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from .. import crud
from ..cache import invalidate_cache, invalidate_cache_pattern
from ..archive.labeling.normalization import slugify_label
from ..archive.labeling.pipeline import extract_labels_for_video
from ..archive.repository import archive_repository
from ..archive.intelligence import get_archive_intelligence, get_archive_period_options
from ..archive.video_metadata_repository import (
    create_person,
    create_tag,
    get_video_metadata_map,
    list_people_admin,
    list_tags_admin,
    search_videos_for_admin,
    seed_default_tags,
    set_video_metadata,
    update_person,
    update_tag,
)
from ..archive.intelligence_repository import (
    create_named_period,
    list_named_periods_admin,
    refresh_named_period_stats,
    refresh_named_period_stats_for_slug,
    seed_named_periods,
    update_named_period,
)
from ..db import get_db
from ..exceptions import NotFoundError, ValidationError
from ..schemas import (
    ArchiveIntelligenceResponse,
    ArchiveLabelAssignmentListResponse,
    ArchiveLabelAssignmentResponse,
    ArchiveLabelExtractionResponse,
    ArchiveLabelListResponse,
    ArchiveLabelReviewAction,
    ArchiveLabelResponse,
    ArchivePersonAdmin,
    ArchivePersonAdminListResponse,
    ArchivePersonCreate,
    ArchivePersonUpdate,
    ArchiveNamedPeriodAdminListResponse,
    ArchiveNamedPeriodAdminResponse,
    ArchiveNamedPeriodCreate,
    ArchiveNamedPeriodUpdate,
    ArchivePeriodOptionsResponse,
    ArchiveSummary,
    ArchiveTimelineResponse,
    ArchiveVideoMetadataAdminListResponse,
    ArchiveVideoMetadataAdminVideo,
    ArchiveVideoMetadataUpdate,
    ArchiveVideoTagAdmin,
    ArchiveVideoTagAdminListResponse,
    ArchiveVideoTagCreate,
    ArchiveVideoTagUpdate,
)
from ..security import ROLE_ADMIN, require_role

router = APIRouter(prefix="", tags=["Archive"])


def _admin_video_metadata_response(db, video_id: uuid.UUID) -> ArchiveVideoMetadataAdminVideo | None:
    video = crud.get_video(db, video_id)
    if not video:
        return None
    try:
        metadata_map = get_video_metadata_map(db, [video_id], published_only=False)
    except (OperationalError, ProgrammingError):
        db.rollback()
        metadata_map = {str(video_id): {"people": [], "tags": []}}
    payload = dict(video)
    metadata = metadata_map.get(str(video_id), {"people": [], "tags": []})
    payload["people"] = metadata.get("people", [])
    payload["tags"] = metadata.get("tags", [])
    return ArchiveVideoMetadataAdminVideo(**payload)


def _fetch_all_rows(result: Any) -> list[dict[str, Any]]:
    if hasattr(result, "mappings"):
        return [dict(row) for row in result.mappings().all()]
    if hasattr(result, "all"):
        return [dict(row) for row in result.all()]
    first = result.first() if hasattr(result, "first") else None
    return [] if first is None else [dict(first)]


def _fetch_first_row(result: Any) -> dict[str, Any] | None:
    rows = _fetch_all_rows(result)
    return rows[0] if rows else None


def _user_id_value(user: Any) -> str | None:
    if user is None:
        return None
    if isinstance(user, dict):
        value = user.get("id")
    elif hasattr(user, "get"):
        value = user.get("id")
    else:
        value = getattr(user, "id", None)
    return None if value is None else str(value)


def _label_response_from_row(row: dict[str, Any]) -> ArchiveLabelResponse:
    return ArchiveLabelResponse(**row)


def _assignment_response_from_row(row: dict[str, Any]) -> ArchiveLabelAssignmentResponse:
    label = {
        "id": row["label_id"],
        "slug": row["label_slug"],
        "label": row["label_label"],
        "kind": row["label_kind"],
        "status": row["label_status"],
        "source": row["label_source"],
        "publish_tier": row["label_publish_tier"],
        "confidence_score": float(row["label_confidence_score"]),
        "description": row.get("label_description"),
    }
    return ArchiveLabelAssignmentResponse(
        id=row["id"],
        label=ArchiveLabelResponse(**label),
        video_id=row["video_id"],
        unit_type=row["unit_type"],
        start_ms=row.get("start_ms"),
        end_ms=row.get("end_ms"),
        status=row["status"],
        publish_tier=row["publish_tier"],
        confidence_score=float(row["confidence_score"]),
        evidence_count=int(row.get("evidence_count") or 0),
        evidence=list(row.get("evidence") or []),
    )


def _load_label_row(db, label_id: uuid.UUID | str) -> dict[str, Any] | None:
    return _fetch_first_row(
        db.execute(
            text(
                """
                SELECT id, slug, label, kind, status, source, publish_tier, confidence_score, description, canonical_id
                FROM archive_labels
                WHERE id = :label_id
                """
            ),
            {"label_id": str(label_id)},
        )
    )


def _load_assignment_row(db, assignment_id: uuid.UUID | str) -> dict[str, Any] | None:
    return _fetch_first_row(
        db.execute(
            text(
                """
                SELECT
                    a.id,
                    a.video_id,
                    a.unit_type,
                    a.start_ms,
                    a.end_ms,
                    a.status,
                    a.publish_tier,
                    a.confidence_score,
                    a.evidence_count,
                    a.evidence,
                    l.id AS label_id,
                    l.slug AS label_slug,
                    l.label AS label_label,
                    l.kind AS label_kind,
                    l.status AS label_status,
                    l.source AS label_source,
                    l.publish_tier AS label_publish_tier,
                    l.confidence_score AS label_confidence_score,
                    l.description AS label_description
                FROM archive_label_assignments AS a
                JOIN archive_labels AS l ON l.id = a.label_id
                WHERE a.id = :assignment_id
                """
            ),
            {"assignment_id": str(assignment_id)},
        )
    )


def _insert_label_feedback(
    db,
    *,
    label_id: uuid.UUID | str | None,
    assignment_id: uuid.UUID | str | None,
    action: str,
    old_value: dict[str, Any],
    new_value: dict[str, Any],
    reason: str | None,
    user: Any,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO archive_label_feedback (
                label_id, assignment_id, action, old_value, new_value, reason, user_id, created_at
            ) VALUES (
                :label_id, :assignment_id, :action, CAST(:old_value AS jsonb), CAST(:new_value AS jsonb), :reason, :user_id, now()
            )
            """
        ),
        {
            "label_id": None if label_id is None else str(label_id),
            "assignment_id": None if assignment_id is None else str(assignment_id),
            "action": action,
            "old_value": json.dumps(old_value or {}),
            "new_value": json.dumps(new_value or {}),
            "reason": reason,
            "user_id": _user_id_value(user),
        },
    )


def _review_label_action(db, label_id: uuid.UUID, payload: ArchiveLabelReviewAction, user: Any) -> ArchiveLabelResponse:
    label = _load_label_row(db, label_id)
    if label is None:
        raise NotFoundError(f"Label {label_id} not found", resource_type="archive_label")

    action = payload.action
    old_value = {
        "id": str(label["id"]),
        "slug": label["slug"],
        "label": label["label"],
        "status": label["status"],
        "canonical_id": None if label.get("canonical_id") is None else str(label["canonical_id"]),
    }

    if action in {"approve", "publish"}:
        new_status = "published"
        db.execute(
            text("UPDATE archive_labels SET status = :status, updated_at = now() WHERE id = :label_id"),
            {"status": new_status, "label_id": str(label_id)},
        )
        new_value = {**old_value, "status": new_status}
    elif action == "hide":
        new_status = "hidden"
        db.execute(
            text("UPDATE archive_labels SET status = :status, updated_at = now() WHERE id = :label_id"),
            {"status": new_status, "label_id": str(label_id)},
        )
        new_value = {**old_value, "status": new_status}
    elif action == "reject":
        new_status = "rejected"
        db.execute(
            text("UPDATE archive_labels SET status = :status, updated_at = now() WHERE id = :label_id"),
            {"status": new_status, "label_id": str(label_id)},
        )
        new_value = {**old_value, "status": new_status}
    elif action == "rename":
        if not payload.label:
            raise ValidationError("label is required for rename actions", field="label")
        new_slug = slugify_label(payload.label)
        slug_conflict = _fetch_first_row(
            db.execute(
                text("SELECT id FROM archive_labels WHERE slug = :slug AND id <> :label_id LIMIT 1"),
                {"slug": new_slug, "label_id": str(label_id)},
            )
        )
        if slug_conflict is not None:
            raise ValidationError(f"Archive label slug '{new_slug}' already exists", field="label")
        db.execute(
            text("UPDATE archive_labels SET label = :label, slug = :slug, updated_at = now() WHERE id = :label_id"),
            {"label": payload.label, "slug": new_slug, "label_id": str(label_id)},
        )
        new_value = {**old_value, "label": payload.label, "slug": new_slug}
    elif action == "merge":
        if payload.target_label_id is None:
            raise ValidationError("target_label_id is required for merge actions", field="target_label_id")
        if str(payload.target_label_id) == str(label_id):
            raise ValidationError("target_label_id must be different from the source label", field="target_label_id")
        target = _load_label_row(db, payload.target_label_id)
        if target is None:
            raise NotFoundError(f"Label {payload.target_label_id} not found", resource_type="archive_label")
        db.execute(
            text("UPDATE archive_labels SET status = 'merged', canonical_id = :target_label_id, updated_at = now() WHERE id = :label_id"),
            {"target_label_id": str(payload.target_label_id), "label_id": str(label_id)},
        )
        new_value = {**old_value, "status": "merged", "canonical_id": str(payload.target_label_id)}
    else:
        raise ValidationError(f"Unsupported review action: {action}", field="action")

    _insert_label_feedback(
        db,
        label_id=label_id,
        assignment_id=None,
        action=action,
        old_value=old_value,
        new_value=new_value,
        reason=payload.reason,
        user=user,
    )

    updated = _load_label_row(db, label_id)
    if updated is None:
        raise NotFoundError(f"Label {label_id} not found", resource_type="archive_label")
    return _label_response_from_row(updated)


def _review_assignment_action(db, assignment_id: uuid.UUID, payload: ArchiveLabelReviewAction, user: Any) -> ArchiveLabelAssignmentResponse:
    assignment = _load_assignment_row(db, assignment_id)
    if assignment is None:
        raise NotFoundError(f"Assignment {assignment_id} not found", resource_type="archive_label_assignment")

    action = payload.action
    label_id = assignment["label_id"]
    old_value = {
        "id": str(assignment["id"]),
        "status": assignment["status"],
        "label_status": assignment["label_status"],
        "label_id": str(label_id),
    }

    if action == "approve":
        db.execute(
            text("UPDATE archive_label_assignments SET status = 'admin_approved', updated_at = now() WHERE id = :assignment_id"),
            {"assignment_id": str(assignment_id)},
        )
        db.execute(
            text("UPDATE archive_labels SET status = 'published', updated_at = now() WHERE id = :label_id"),
            {"label_id": str(label_id)},
        )
        new_value = {**old_value, "status": "admin_approved", "label_status": "published"}
    elif action == "reject":
        db.execute(
            text("UPDATE archive_label_assignments SET status = 'rejected', updated_at = now() WHERE id = :assignment_id"),
            {"assignment_id": str(assignment_id)},
        )
        new_value = {**old_value, "status": "rejected"}
    elif action == "publish":
        db.execute(
            text("UPDATE archive_label_assignments SET status = 'auto_published', updated_at = now() WHERE id = :assignment_id"),
            {"assignment_id": str(assignment_id)},
        )
        db.execute(
            text("UPDATE archive_labels SET status = 'published', updated_at = now() WHERE id = :label_id"),
            {"label_id": str(label_id)},
        )
        new_value = {**old_value, "status": "auto_published", "label_status": "published"}
    elif action == "hide":
        db.execute(
            text("UPDATE archive_label_assignments SET status = 'shadow', updated_at = now() WHERE id = :assignment_id"),
            {"assignment_id": str(assignment_id)},
        )
        new_value = {**old_value, "status": "shadow"}
    elif action in {"rename", "merge"}:
        raise ValidationError("Assignment review actions do not support rename or merge", field="action")
    else:
        raise ValidationError(f"Unsupported review action: {action}", field="action")

    _insert_label_feedback(
        db,
        label_id=label_id,
        assignment_id=assignment_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        reason=payload.reason,
        user=user,
    )

    updated = _load_assignment_row(db, assignment_id)
    if updated is None:
        raise NotFoundError(f"Assignment {assignment_id} not found", resource_type="archive_label_assignment")
    return _assignment_response_from_row(updated)


@router.get(
    "/archive/summary",
    response_model=ArchiveSummary,
    summary="Get archive summary",
    description="Summary statistics for HasanAra based on real VOD and transcript data.",
)
def archive_summary(
    recent_limit: int = Query(6, ge=0, le=20, description="Number of recent videos to include"),
    popular_limit: int = Query(8, ge=0, le=20, description="Number of popular searches to include"),
    db=Depends(get_db),
):
    return archive_repository.get_summary(db, recent_limit=recent_limit, popular_limit=popular_limit)


@router.get(
    "/archive/timeline",
    response_model=ArchiveTimelineResponse,
    summary="Get archive timeline",
    description="Chronological archive timeline grouped by month or year from real uploaded videos.",
)
def archive_timeline(
    granularity: str = Query("month", pattern="^(month|year)$", description="Bucket videos by month or year"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of videos to include"),
    db=Depends(get_db),
):
    return crud.get_archive_timeline(db, limit=limit, granularity=granularity)


@router.get(
    "/archive/intelligence",
    response_model=ArchiveIntelligenceResponse,
    summary="Get archive intelligence",
    description="Composed archive exploration response with timeline, topics, trending searches, and cited evidence.",
)
def archive_intelligence(
    topic_limit: int = Query(8, ge=1, le=20, description="Maximum number of topic cards to include"),
    period_limit: int = Query(24, ge=1, le=120, description="Maximum number of periods to include"),
    granularity: str = Query("month", pattern="^(month|week)$", description="Period granularity for cached intelligence"),
    date_from: date | None = Query(None, description="Lower bound for cached intelligence periods"),
    date_to: date | None = Query(None, description="Upper bound for cached intelligence periods"),
    period: str | None = Query(None, description="Predefined archive period slug"),
    db=Depends(get_db),
):
    return get_archive_intelligence(
        db,
        topic_limit=topic_limit,
        period_limit=period_limit,
        granularity=granularity,
        date_from=date_from,
        date_to=date_to,
        period=period,
    )


@router.get(
    "/archive/intelligence/periods",
    response_model=ArchivePeriodOptionsResponse,
    summary="List archive intelligence periods",
    description="Return predefined archive periods and cached counts for the archive intelligence UI.",
)
def archive_intelligence_periods(
    kind: str | None = Query(None, description="Optional period kind filter"),
    limit: int = Query(120, ge=1, le=500, description="Maximum number of periods to include"),
    db=Depends(get_db),
):
    return get_archive_period_options(db, kind=kind, limit=limit)


@router.get(
    "/admin/archive/periods",
    response_model=ArchiveNamedPeriodAdminListResponse,
    summary="List archive periods (Admin)",
    description="List all predefined archive intelligence periods, including hidden drafts.",
)
def admin_archive_periods(
    kind: str | None = Query(None, description="Optional period kind filter"),
    status: str | None = Query(None, description="Optional period status filter"),
    q: str | None = Query(None, description="Search slug, label, or description"),
    limit: int = Query(200, ge=1, le=500, description="Maximum number of periods to include"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    return list_named_periods_admin(db, kind=kind, status=status, q=q, limit=limit, offset=offset)


@router.post(
    "/admin/archive/periods",
    response_model=ArchiveNamedPeriodAdminResponse,
    summary="Create archive period (Admin)",
    description="Create a predefined archive intelligence period.",
)
def admin_create_archive_period(
    payload: ArchiveNamedPeriodCreate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    period = create_named_period(db, payload)
    if period is None:
        raise NotFoundError("Archive period could not be created", resource_type="archive_named_period")
    db.commit()
    refreshed = refresh_named_period_stats_for_slug(db, period.slug)
    db.commit()
    return refreshed or period


@router.patch(
    "/admin/archive/periods/{slug}",
    response_model=ArchiveNamedPeriodAdminResponse,
    summary="Update archive period (Admin)",
    description="Update a predefined archive intelligence period.",
)
def admin_update_archive_period(
    slug: str,
    payload: ArchiveNamedPeriodUpdate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    period = update_named_period(db, slug, payload)
    if period is None:
        raise NotFoundError(f"Archive period {slug} not found", resource_type="archive_named_period")
    db.commit()
    refreshed = refresh_named_period_stats_for_slug(db, slug)
    db.commit()
    return refreshed or period


@router.post(
    "/admin/archive/periods/{slug}/refresh",
    response_model=ArchiveNamedPeriodAdminResponse,
    summary="Refresh archive period stats (Admin)",
    description="Recalculate cached stats for a predefined archive intelligence period.",
)
def admin_refresh_archive_period(
    slug: str,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    refreshed = refresh_named_period_stats_for_slug(db, slug)
    if refreshed is None:
        raise NotFoundError(f"Archive period {slug} not found", resource_type="archive_named_period")
    db.commit()
    return refreshed


@router.post(
    "/admin/archive/periods/seed",
    summary="Seed archive periods (Admin)",
    description="Seed curated archive periods and refresh cached stats.",
)
def admin_seed_archive_periods(
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    seeded = seed_named_periods(db)
    db.commit()
    refreshed = refresh_named_period_stats(db)
    db.commit()
    return {"seeded": seeded.get("periods", 0), "refreshed": refreshed.get("rows", 0)}


@router.get(
    "/admin/archive/metadata/people",
    response_model=ArchivePersonAdminListResponse,
    summary="List archive people (Admin)",
)
def admin_list_archive_people(
    q: str | None = Query(None, description="Search slug, display name, aliases, or description"),
    status: str | None = Query(None, description="Optional person status filter"),
    limit: int = Query(200, ge=1, le=500, description="Maximum number of people to include"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    return ArchivePersonAdminListResponse(items=list_people_admin(db, q=q, status=status, limit=limit, offset=offset))


@router.post(
    "/admin/archive/metadata/people",
    response_model=ArchivePersonAdmin,
    summary="Create archive person (Admin)",
)
def admin_create_archive_person(
    payload: ArchivePersonCreate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    person = create_person(db, payload.model_dump(exclude_none=True))
    db.commit()
    return ArchivePersonAdmin(**person)


@router.patch(
    "/admin/archive/metadata/people/{slug}",
    response_model=ArchivePersonAdmin,
    summary="Update archive person (Admin)",
)
def admin_update_archive_person(
    slug: str,
    payload: ArchivePersonUpdate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    person = update_person(db, slug, payload.model_dump(exclude_none=True))
    if person is None:
        raise NotFoundError(f"Archive person {slug} not found", resource_type="archive_person")
    db.commit()
    invalidate_cache_pattern("video:*")
    return ArchivePersonAdmin(**person)


@router.get(
    "/admin/archive/metadata/tags",
    response_model=ArchiveVideoTagAdminListResponse,
    summary="List archive tags (Admin)",
)
def admin_list_archive_tags(
    q: str | None = Query(None, description="Search slug, label, or description"),
    status: str | None = Query(None, description="Optional tag status filter"),
    kind: str | None = Query(None, description="Optional tag kind filter"),
    limit: int = Query(200, ge=1, le=500, description="Maximum number of tags to include"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    return ArchiveVideoTagAdminListResponse(items=list_tags_admin(db, q=q, status=status, kind=kind, limit=limit, offset=offset))


@router.post(
    "/admin/archive/metadata/tags",
    response_model=ArchiveVideoTagAdmin,
    summary="Create archive tag (Admin)",
)
def admin_create_archive_tag(
    payload: ArchiveVideoTagCreate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    tag = create_tag(db, payload.model_dump(exclude_none=True))
    db.commit()
    return ArchiveVideoTagAdmin(**tag)


@router.patch(
    "/admin/archive/metadata/tags/{slug}",
    response_model=ArchiveVideoTagAdmin,
    summary="Update archive tag (Admin)",
)
def admin_update_archive_tag(
    slug: str,
    payload: ArchiveVideoTagUpdate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    tag = update_tag(db, slug, payload.model_dump(exclude_none=True))
    if tag is None:
        raise NotFoundError(f"Archive tag {slug} not found", resource_type="archive_video_tag")
    db.commit()
    invalidate_cache_pattern("video:*")
    return ArchiveVideoTagAdmin(**tag)


@router.get(
    "/admin/archive/metadata/videos",
    response_model=ArchiveVideoMetadataAdminListResponse,
    summary="Search archive videos with metadata (Admin)",
)
def admin_search_archive_videos_with_metadata(
    q: str | None = Query(None, description="Search title, YouTube ID, or channel name"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of videos to include"),
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    return ArchiveVideoMetadataAdminListResponse(items=[ArchiveVideoMetadataAdminVideo(**dict(row)) for row in search_videos_for_admin(db, q=q, limit=limit)])


@router.get(
    "/admin/archive/metadata/videos/{video_id}",
    response_model=ArchiveVideoMetadataAdminVideo,
    summary="Get archive video metadata (Admin)",
)
def admin_get_archive_video_metadata(
    video_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    video = _admin_video_metadata_response(db, video_id)
    if video is None:
        raise NotFoundError(f"Video {video_id} not found", resource_type="video")
    return video


@router.put(
    "/admin/archive/metadata/videos/{video_id}",
    response_model=ArchiveVideoMetadataAdminVideo,
    summary="Set archive video metadata (Admin)",
)
def admin_set_archive_video_metadata(
    video_id: uuid.UUID,
    payload: ArchiveVideoMetadataUpdate,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    set_video_metadata(
        db,
        video_id,
        people=[item.model_dump(exclude_none=True) for item in payload.people],
        tags=[item.model_dump(exclude_none=True) for item in payload.tags],
    )
    db.commit()
    invalidate_cache("video", video_id)
    video = _admin_video_metadata_response(db, video_id)
    if video is None:
        raise NotFoundError(f"Video {video_id} not found", resource_type="video")
    return video


@router.post(
    "/admin/archive/metadata/seed-tags",
    summary="Seed archive metadata tags (Admin)",
)
def admin_seed_archive_metadata_tags(
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    seeded = seed_default_tags(db)
    db.commit()
    invalidate_cache_pattern("video:*")
    return seeded


@router.get(
    "/admin/archive/labels",
    response_model=ArchiveLabelListResponse,
    summary="List archive labels (Admin)",
    description="List extracted labels for review, moderation, and publication.",
)
def admin_list_archive_labels(
    status: str | None = Query(None, description="Optional label status filter"),
    kind: str | None = Query(None, description="Optional label kind filter"),
    q: str | None = Query(None, description="Search slug, label, or description"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of labels to include"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    clauses = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status:
        clauses.append("status = :status")
        params["status"] = status
    if kind:
        clauses.append("kind = :kind")
        params["kind"] = kind
    if q:
        clauses.append("(slug ILIKE :q OR label ILIKE :q OR COALESCE(description, '') ILIKE :q)")
        params["q"] = f"%{q}%"
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _fetch_all_rows(
        db.execute(
            text(
                f"""
                SELECT id, slug, label, kind, status, source, publish_tier, confidence_score, description
                FROM archive_labels
                {where_sql}
                ORDER BY updated_at DESC, confidence_score DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    )
    return ArchiveLabelListResponse(items=[_label_response_from_row(row) for row in rows])


@router.get(
    "/admin/archive/labels/{label_id}/assignments",
    response_model=ArchiveLabelAssignmentListResponse,
    summary="List label assignments (Admin)",
    description="List review assignments for a label.",
)
def admin_list_archive_label_assignments(
    label_id: uuid.UUID,
    status: str | None = Query(None, description="Optional assignment status filter"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of assignments to include"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    clauses = ["a.label_id = :label_id"]
    params: dict[str, Any] = {"label_id": str(label_id), "limit": limit, "offset": offset}
    if status:
        clauses.append("a.status = :status")
        params["status"] = status
    rows = _fetch_all_rows(
        db.execute(
            text(
                f"""
                SELECT
                    a.id,
                    a.video_id,
                    a.unit_type,
                    a.start_ms,
                    a.end_ms,
                    a.status,
                    a.publish_tier,
                    a.confidence_score,
                    a.evidence_count,
                    a.evidence,
                    l.id AS label_id,
                    l.slug AS label_slug,
                    l.label AS label_label,
                    l.kind AS label_kind,
                    l.status AS label_status,
                    l.source AS label_source,
                    l.publish_tier AS label_publish_tier,
                    l.confidence_score AS label_confidence_score,
                    l.description AS label_description
                FROM archive_label_assignments AS a
                JOIN archive_labels AS l ON l.id = a.label_id
                WHERE {' AND '.join(clauses)}
                ORDER BY a.updated_at DESC, a.confidence_score DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    )
    return ArchiveLabelAssignmentListResponse(items=[_assignment_response_from_row(row) for row in rows])


@router.post(
    "/admin/archive/labels/{label_id}/review",
    response_model=ArchiveLabelResponse,
    summary="Review archive label (Admin)",
    description="Approve, reject, publish, hide, rename, or merge a label.",
)
def admin_review_archive_label(
    label_id: uuid.UUID,
    payload: ArchiveLabelReviewAction,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    label = _review_label_action(db, label_id, payload, user)
    db.commit()
    return label


@router.post(
    "/admin/archive/label-assignments/{assignment_id}/review",
    response_model=ArchiveLabelAssignmentResponse,
    summary="Review archive label assignment (Admin)",
    description="Approve, reject, publish, or hide a label assignment.",
)
def admin_review_archive_label_assignment(
    assignment_id: uuid.UUID,
    payload: ArchiveLabelReviewAction,
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    assignment = _review_assignment_action(db, assignment_id, payload, user)
    db.commit()
    return assignment


@router.post(
    "/admin/archive/labels/extract-video/{video_id}",
    response_model=ArchiveLabelExtractionResponse,
    summary="Extract labels for a video (Admin)",
    description="Run the label extraction pipeline for a single video.",
)
def admin_extract_labels_for_video(
    video_id: uuid.UUID,
    extraction_tier: str = Query("cheap", description="Extraction tier to use"),
    db=Depends(get_db),
    user=Depends(require_role(ROLE_ADMIN)),
):
    result = extract_labels_for_video(db, video_id=str(video_id), extraction_tier=extraction_tier)
    db.commit()
    return ArchiveLabelExtractionResponse(**result)
