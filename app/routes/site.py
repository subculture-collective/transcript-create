"""Explicit public configuration: never serialize the Settings object."""

from typing import Literal, cast

from fastapi import APIRouter
from pydantic import ConfigDict, Field
from pydantic.json_schema import JsonDict

from .. import branding
from ..branding import BrandProfile
from ..settings import settings

router = APIRouter(tags=["Site"])

# Rekolekt core is headless: each archive frontend owns its styling. The theme
# is still validated and served at /site so existing frontends keep working,
# but the response schema marks it deprecated. The profile's theme.dark tokens
# still colour the server-rendered passage pages and cards, so the profile
# model in app.branding is deliberately left unmarked.
# json_schema_extra is used instead of Field(deprecated=True) so that reading
# these fields never emits runtime warnings.
_DEPRECATED: JsonDict = {"deprecated": True}
_THEME_DEPRECATION = "Deprecated: frontends own their styling. Still served so existing frontends keep working."


class BrandTheme(branding.BrandTheme):
    """Deprecated visual overrides from the site profile: font choice and colour tokens.

    Still served so existing frontends keep working. New frontends should own their styling.
    """

    model_config = ConfigDict(json_schema_extra=_DEPRECATED)
    font: Literal["system", "editorial", "mono"] | None = Field(
        default=None, description=_THEME_DEPRECATION, json_schema_extra=_DEPRECATED
    )
    dark: dict[str, str] = Field(default_factory=dict, description=_THEME_DEPRECATION, json_schema_extra=_DEPRECATED)
    light: dict[str, str] = Field(default_factory=dict, description=_THEME_DEPRECATION, json_schema_extra=_DEPRECATED)


def _mark_theme_deprecated(schema: JsonDict) -> None:
    # Pydantic drops sibling keywords other than description next to a $ref.
    properties = cast(JsonDict, schema["properties"])
    cast(JsonDict, properties["theme"])["deprecated"] = True


class SiteConfig(BrandProfile):
    model_config = ConfigDict(json_schema_extra=_mark_theme_deprecated)
    name: str
    description: str
    creator_name: str
    theme: BrandTheme = Field(default_factory=BrandTheme, description=_THEME_DEPRECATION)
    public_passages_enabled: bool
    clip_exports_enabled: bool
    atproto_enabled: bool
    community_enabled: bool


@router.get("/site", response_model=SiteConfig)
def site_config():
    profile = settings.SITE_BRANDING.model_dump(exclude={"name", "description", "creator_name"})
    return SiteConfig(
        **profile,
        name=settings.SITE_NAME,
        description=settings.SITE_DESCRIPTION,
        creator_name=settings.SITE_CREATOR_NAME,
        public_passages_enabled=settings.PUBLIC_PASSAGES_ENABLED,
        community_enabled=settings.COMMUNITY_ENABLED,
        atproto_enabled=settings.ATPROTO_ENABLED,
        clip_exports_enabled=settings.CLIP_EXPORTS_ENABLED,
    )
