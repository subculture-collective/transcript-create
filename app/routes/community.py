"""Local public community. Session identity is never inferred from external handles."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from ..audit import write_audit_from_request
from ..db import get_db
from ..security import has_role, require_auth
from ..settings import settings


def enabled():
    if not settings.COMMUNITY_ENABLED:
        raise HTTPException(404, "Community is not enabled")


router = APIRouter(prefix="/community", tags=["Community"], dependencies=[Depends(enabled)])


class PostInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["update", "discussion", "reply"]
    body: str = Field(min_length=1, max_length=5000)
    publish: bool = False
    parent_id: UUID | None = None
    video_id: UUID | None = None
    start_ms: int | None = Field(default=None, ge=0, le=2147483647, strict=True)
    end_ms: int | None = Field(default=None, ge=1, le=2147483647, strict=True)

    @model_validator(mode="after")
    def validate_links(self):
        if (self.kind == "reply") != (self.parent_id is not None):
            raise ValueError("Only replies require a parent")
        values = (self.video_id, self.start_ms, self.end_ms)
        if any(v is not None for v in values):
            if any(v is None for v in values) or self.end_ms <= self.start_ms:
                raise ValueError("A passage needs a video and a valid start/end range")
        if self.kind == "discussion" and self.video_id is None:
            raise ValueError("Start a discussion from an archive passage")
        if self.kind == "reply" and self.video_id is not None:
            raise ValueError("Replies inherit their parent's passage")
        return self


class Post(BaseModel):
    id: UUID
    author_id: UUID
    author_name: str
    parent_id: UUID | None
    kind: str
    body: str
    status: str
    video_id: UUID | None
    video_title: str | None
    start_ms: int | None
    end_ms: int | None
    pinned: bool
    created_at: datetime
    updated_at: datetime


class PostPage(BaseModel):
    items: list[Post]
    next_offset: int | None


class PostEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=5000)
    if_match: datetime


class ArchiveAddition(BaseModel):
    id: UUID
    title: str | None


class PostActivity(BaseModel):
    kind: Literal["post"]
    at: datetime
    post: Post


class ArchiveActivity(BaseModel):
    kind: Literal["archive"]
    at: datetime
    video: ArchiveAddition


class CommunityTimeline(BaseModel):
    items: list[PostActivity | ArchiveActivity]
    next_offset: int | None


class Reason(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=1000)


class Moderation(Reason):
    action: Literal["hide", "restore", "pin", "unpin"]


SELECT_POST = """SELECT p.*, COALESCE(u.name, 'Member') AS author_name, v.title AS video_title
FROM community_posts p JOIN users u ON u.id=p.author_id LEFT JOIN videos v ON v.id=p.video_id """


def read_post(db, post_id):
    row = db.execute(text(SELECT_POST + "WHERE p.id=:id"), {"id": post_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Post not found")
    return dict(row)


def public_parent(db, parent_id):
    parent = read_post(db, parent_id)
    if parent["status"] != "published" or parent["parent_id"] is not None:
        raise HTTPException(404, "Discussion not found")
    return parent


def audit(db, request, user, action, post_id, details=None):
    write_audit_from_request(
        db,
        request,
        f"community.{action}",
        user_id=user["id"],
        resource_type="community_post",
        resource_id=str(post_id),
        details=details,
    )


def moderate_user(user=Depends(require_auth)):
    if not has_role(user, "moderator"):
        raise HTTPException(403, "Moderator access required")
    return user


@router.get("/posts", response_model=PostPage)
def list_posts(
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(20, ge=1, le=100),
    parent_id: UUID | None = None,
    video_id: UUID | None = None,
    db=Depends(get_db),
):
    if parent_id:
        public_parent(db, parent_id)
    where = "p.parent_id=:parent" if parent_id else "p.parent_id IS NULL"
    if video_id:
        where += " AND p.video_id=:video"
    rows = (
        db.execute(
            text(SELECT_POST + f"""WHERE p.status='published' AND {where}
        ORDER BY p.pinned DESC, p.created_at DESC, p.id DESC LIMIT :limit OFFSET :offset"""),
            {"parent": parent_id, "video": video_id, "limit": limit + 1, "offset": offset},
        )
        .mappings()
        .all()
    )
    return {"items": rows[:limit], "next_offset": offset + limit if len(rows) > limit else None}


@router.get("/timeline", response_model=CommunityTimeline)
def community_timeline(
    offset: int = Query(0, ge=0, le=100000), limit: int = Query(20, ge=1, le=100), db=Depends(get_db)
):
    rows = (
        db.execute(
            text("""
        SELECT * FROM (
            SELECT p.id, 'post' AS kind, p.created_at AS at,
                to_jsonb(p) || jsonb_build_object('author_name', COALESCE(u.name, 'Member'), 'video_title', v.title) AS post,
                NULL::jsonb AS video
            FROM community_posts p JOIN users u ON u.id=p.author_id LEFT JOIN videos v ON v.id=p.video_id
            WHERE p.status='published' AND p.parent_id IS NULL
            UNION ALL
            SELECT v.id, 'archive' AS kind, v.created_at AS at, NULL::jsonb AS post,
                jsonb_build_object('id', v.id, 'title', v.title) AS video
            FROM videos v WHERE v.state='completed' AND
                (EXISTS(SELECT 1 FROM segments s WHERE s.video_id=v.id)
                 OR EXISTS(SELECT 1 FROM youtube_transcripts yt JOIN youtube_segments ys ON ys.youtube_transcript_id=yt.id WHERE yt.video_id=v.id))
        ) activity ORDER BY at DESC, kind, id DESC LIMIT :limit OFFSET :offset
    """),
            {"limit": limit + 1, "offset": offset},
        )
        .mappings()
        .all()
    )
    return {"items": rows[:limit], "next_offset": offset + limit if len(rows) > limit else None}


@router.get("/hidden", response_model=PostPage)
def hidden_posts(offset: int = Query(0, ge=0, le=100000), user=Depends(moderate_user), db=Depends(get_db)):
    rows = (
        db.execute(
            text(
                SELECT_POST + "WHERE p.status='hidden' ORDER BY p.updated_at DESC, p.id DESC LIMIT 101 OFFSET :offset"
            ),
            {"offset": offset},
        )
        .mappings()
        .all()
    )
    return {"items": rows[:100], "next_offset": offset + 100 if len(rows) > 100 else None}


@router.get("/mine", response_model=PostPage)
def mine(offset: int = Query(0, ge=0, le=100000), user=Depends(require_auth), db=Depends(get_db)):
    rows = (
        db.execute(
            text(
                SELECT_POST + "WHERE p.author_id=:user ORDER BY p.created_at DESC, p.id DESC LIMIT 101 OFFSET :offset"
            ),
            {"user": user["id"], "offset": offset},
        )
        .mappings()
        .all()
    )
    return {"items": rows[:100], "next_offset": offset + 100 if len(rows) > 100 else None}


@router.get("/export", response_model=PostPage)
def export_posts(offset: int = Query(0, ge=0, le=100000), user=Depends(require_auth), db=Depends(get_db)):
    """Paginated own-content portability, including drafts and moderated content."""
    return mine(offset, user, db)


@router.post("/posts", response_model=Post, status_code=201)
def create_post(payload: PostInput, request: Request, user=Depends(require_auth), db=Depends(get_db)):
    if payload.kind == "update" and not has_role(user, "admin"):
        raise HTTPException(403, "Only the creator administrator can publish updates")
    # Serialize per-account submissions, including concurrent requests.
    db.execute(text("SELECT id FROM users WHERE id=:id FOR UPDATE"), {"id": user["id"]})
    count = db.execute(
        text("SELECT count(*) FROM community_posts WHERE author_id=:id AND created_at > now()-interval '1 minute'"),
        {"id": user["id"]},
    ).scalar()
    if count >= 10:
        raise HTTPException(429, "Please wait a minute before posting again")
    if payload.parent_id:
        db.execute(text("SELECT id FROM community_posts WHERE id=:id FOR UPDATE"), {"id": payload.parent_id})
        public_parent(db, payload.parent_id)
    if payload.video_id:
        video = (
            db.execute(text("SELECT duration_seconds FROM videos WHERE id=:id FOR KEY SHARE"), {"id": payload.video_id})
            .mappings()
            .first()
        )
        if not video:
            raise HTTPException(404, "Source video not found")
        if video["duration_seconds"] and payload.end_ms > video["duration_seconds"] * 1000:
            raise HTTPException(422, "Passage ends after the source video")
    post_id = uuid4()
    params = payload.model_dump(exclude={"publish"}) | {
        "id": post_id,
        "author": user["id"],
        "status": "published" if payload.publish else "draft",
    }
    db.execute(
        text("""INSERT INTO community_posts(id,author_id,parent_id,kind,body,status,video_id,start_ms,end_ms)
        VALUES (:id,:author,:parent_id,:kind,:body,:status,:video_id,:start_ms,:end_ms)"""),
        params,
    )
    audit(db, request, user, "create", post_id, {"status": params["status"]})
    result = read_post(db, post_id)
    db.commit()
    return result


@router.patch("/posts/{post_id}", response_model=Post)
def edit_post(post_id: UUID, payload: PostEdit, request: Request, user=Depends(require_auth), db=Depends(get_db)):
    db.execute(text("SELECT id FROM community_posts WHERE id=:id FOR UPDATE"), {"id": post_id})
    post = read_post(db, post_id)
    if str(post["author_id"]) != str(user["id"]):
        raise HTTPException(403, "Only the author can edit this post")
    if post["status"] == "hidden":
        raise HTTPException(409, "A moderator must review this hidden post before it can be edited")
    if post["kind"] == "update" and not has_role(user, "admin"):
        raise HTTPException(403, "Creator access required")
    if post["updated_at"] != payload.if_match:
        raise HTTPException(409, "This post changed. Reload it before saving another edit")
    if post["parent_id"]:
        public_parent(db, post["parent_id"])
    # clock_timestamp changes even inside a caller's longer transaction.
    db.execute(
        text("UPDATE community_posts SET body=:body,updated_at=clock_timestamp() WHERE id=:id"),
        {"id": post_id, "body": payload.body},
    )
    audit(db, request, user, "edit", post_id, {"status": post["status"]})
    result = read_post(db, post_id)
    db.commit()
    return result


@router.post("/posts/{post_id}/publish", response_model=Post)
def publish_post(post_id: UUID, request: Request, user=Depends(require_auth), db=Depends(get_db)):
    db.execute(text("SELECT id FROM community_posts WHERE id=:id FOR UPDATE"), {"id": post_id})
    post = read_post(db, post_id)
    if str(post["author_id"]) != str(user["id"]):
        raise HTTPException(403, "Only the author can publish this draft")
    if post["kind"] == "update" and not has_role(user, "admin"):
        raise HTTPException(403, "Creator access required")
    if post["status"] != "draft":
        raise HTTPException(409, "Only drafts can be published")
    if post["parent_id"]:
        public_parent(db, post["parent_id"])
    db.execute(text("UPDATE community_posts SET status='published',updated_at=now() WHERE id=:id"), {"id": post_id})
    audit(db, request, user, "publish", post_id)
    result = read_post(db, post_id)
    db.commit()
    return result


@router.delete("/posts/{post_id}", status_code=204)
def delete_post(post_id: UUID, request: Request, user=Depends(require_auth), db=Depends(get_db)):
    # Deleting a root also removes its replies; communicate this explicitly in the UI.
    result = db.execute(
        text("DELETE FROM community_posts WHERE id=:id AND author_id=:author RETURNING id"),
        {"id": post_id, "author": user["id"]},
    ).first()
    if not result:
        raise HTTPException(404, "Post not found or not owned by you")
    audit(db, request, user, "delete", post_id)
    db.commit()


@router.post("/posts/{post_id}/report", status_code=204)
def report_post(post_id: UUID, payload: Reason, request: Request, user=Depends(require_auth), db=Depends(get_db)):
    post = read_post(db, post_id)
    if post["status"] != "published":
        raise HTTPException(404, "Post not found")
    if post["parent_id"]:
        public_parent(db, post["parent_id"])
    db.execute(
        text("""INSERT INTO community_reports(post_id,reporter_id,reason) VALUES (:id,:user,:reason)
        ON CONFLICT(post_id,reporter_id) DO NOTHING"""),
        {"id": post_id, "user": user["id"], "reason": payload.reason},
    )
    audit(db, request, user, "report", post_id)
    db.commit()


@router.get("/reports")
def reports(offset: int = Query(0, ge=0, le=100000), user=Depends(moderate_user), db=Depends(get_db)):
    rows = (
        db.execute(
            text("""SELECT r.id, r.post_id, r.reason, r.created_at, p.body, p.status AS post_status
        FROM community_reports r JOIN community_posts p ON p.id=r.post_id
        WHERE r.status='open' ORDER BY r.created_at,r.id LIMIT 101 OFFSET :offset"""),
            {"offset": offset},
        )
        .mappings()
        .all()
    )
    return {"items": rows[:100], "next_offset": offset + 100 if len(rows) > 100 else None}


@router.post("/reports/{report_id}/resolve", status_code=204)
def resolve_report(report_id: UUID, payload: Reason, request: Request, user=Depends(moderate_user), db=Depends(get_db)):
    post_id = db.execute(
        text("UPDATE community_reports SET status='resolved' WHERE id=:id RETURNING post_id"), {"id": report_id}
    ).scalar()
    if not post_id:
        raise HTTPException(404, "Report not found")
    audit(db, request, user, "resolve_report", post_id, {"report_id": str(report_id), "reason": payload.reason})
    db.commit()


@router.post("/posts/{post_id}/moderate", response_model=Post)
def moderate_post(
    post_id: UUID, payload: Moderation, request: Request, user=Depends(moderate_user), db=Depends(get_db)
):
    db.execute(text("SELECT id FROM community_posts WHERE id=:id FOR UPDATE"), {"id": post_id})
    post = read_post(db, post_id)
    if post["status"] == "draft":
        raise HTTPException(409, "Moderation cannot publish an author's draft")
    if payload.action in ("pin", "unpin"):
        if not has_role(user, "admin") or post["parent_id"]:
            raise HTTPException(403, "Only creator administrators can pin root posts")
        db.execute(
            text("UPDATE community_posts SET pinned=:pinned,updated_at=now() WHERE id=:id"),
            {"id": post_id, "pinned": payload.action == "pin"},
        )
    else:
        status = "hidden" if payload.action == "hide" else "published"
        db.execute(
            text("UPDATE community_posts SET status=:status,updated_at=now() WHERE id=:id"),
            {"id": post_id, "status": status},
        )
    audit(db, request, user, payload.action, post_id, {"reason": payload.reason})
    result = read_post(db, post_id)
    db.commit()
    return result
