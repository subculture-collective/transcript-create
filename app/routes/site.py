"""Explicit public configuration: never serialize the Settings object."""

from fastapi import APIRouter
from pydantic import BaseModel

from ..settings import settings

router = APIRouter(tags=["Site"])


class SiteConfig(BaseModel):
    name: str
    description: str
    creator_name: str
    public_passages_enabled: bool
    atproto_enabled: bool
    community_enabled: bool


@router.get("/site", response_model=SiteConfig)
def site_config():
    return SiteConfig(
        name=settings.SITE_NAME,
        description=settings.SITE_DESCRIPTION,
        creator_name=settings.SITE_CREATOR_NAME,
        public_passages_enabled=settings.PUBLIC_PASSAGES_ENABLED,
        community_enabled=settings.COMMUNITY_ENABLED,
        atproto_enabled=settings.ATPROTO_ENABLED,
    )
