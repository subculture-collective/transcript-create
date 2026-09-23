"""Versioned public presentation contract. No secrets or executable CSS/HTML."""

import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

COLOR_TOKENS = frozenset(
    "canvas surface surface-muted surface-raised border border-strong ink muted subtle "
    "accent accent-hover accent-soft accent-contrast accent-2 accent-3 player-accent cta "
    "success success-soft "
    "warning warning-soft danger danger-soft".split()
)


class BrandTheme(BaseModel):
    """Optional overrides of the default design. Unset fields keep the stylesheet's values."""

    model_config = ConfigDict(extra="forbid")
    font: Literal["system", "editorial", "mono"] | None = None
    dark: dict[str, str] = Field(default_factory=dict)
    light: dict[str, str] = Field(default_factory=dict)

    @field_validator("dark", "light")
    @classmethod
    def safe_colors(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) - COLOR_TOKENS or any(not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in value.values()):
            raise ValueError("Theme colors require known tokens and six-digit hex colors")
        return value


class BrandProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    schema_version: Literal[1] = 1
    name: str = Field(default="Transcript Archive", min_length=1, max_length=80)
    description: str = Field(default="Search the archive, share a passage, and keep its context.", max_length=300)
    creator_name: str = Field(default="the creators", min_length=1, max_length=100)
    tagline: str = Field(default="Broadcast archive", max_length=100)
    operator_name: str = Field(default="Archive team", min_length=1, max_length=100)
    operator_url: str = ""
    project_notice: str = Field(
        default="Source recordings and trademarks belong to their respective owners.", max_length=500
    )
    logo_url: str = "/icon.svg"
    favicon_url: str = "/icon.svg"
    social_image_url: str = "/social-card.svg"
    theme: BrandTheme = Field(default_factory=BrandTheme)

    @field_validator("operator_url", "logo_url", "favicon_url", "social_image_url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        if not value:
            return value
        if any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
            raise ValueError("Brand URLs must not contain whitespace or backslashes")
        parsed = urlsplit(value)
        if value.startswith("/") and not value.startswith("//"):
            return value
        if parsed.scheme == "https" and parsed.netloc and not parsed.username and not parsed.password:
            return value
        raise ValueError("Brand URLs must be same-origin absolute paths or https URLs")


def load_brand_profile(path: str) -> BrandProfile:
    if not path:
        return BrandProfile()
    source = Path(path)
    if source.stat().st_size > 65536:
        raise ValueError("Brand profile exceeds 64 KiB")
    return BrandProfile.model_validate_json(source.read_text(encoding="utf-8"))
