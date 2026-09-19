"""Public-client metadata only. OAuth credentials never enter the Python API."""

from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, HTTPException

from ..settings import settings

router = APIRouter(prefix="/atproto", tags=["AT Protocol"])
SCOPE = "atproto repo:app.bsky.feed.post?action=create"


def metadata():
    if not settings.ATPROTO_ENABLED:
        raise HTTPException(404, "AT account connection is not enabled")
    origin = settings.FRONTEND_ORIGIN.rstrip("/")
    parsed = urlsplit(origin)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise HTTPException(503, "AT client requires a configured public origin")
    redirect = f"{origin}/at.html"
    if parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "::1") and settings.ENVIRONMENT != "production":
        client_id = "http://localhost?" + urlencode({"redirect_uri": redirect, "scope": SCOPE})
    elif parsed.scheme == "https" and parsed.hostname and not parsed.port:
        client_id = f"{origin}/api/atproto/client-metadata.json"
    else:
        raise HTTPException(503, "AT client requires HTTPS without a custom port")
    return {
        "client_id": client_id,
        "client_name": f"{settings.SITE_NAME} public sharing",
        "client_uri": origin,
        "redirect_uris": [redirect],
        "scope": SCOPE,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": "web",
        "dpop_bound_access_tokens": True,
    }


@router.get("/client-metadata.json")
def client_metadata():
    return metadata()


@router.get("/config")
def client_config():
    resolver = urlsplit(settings.ATPROTO_HANDLE_RESOLVER)
    if resolver.scheme != "https" or not resolver.hostname or resolver.username or resolver.password:
        raise HTTPException(503, "AT handle resolver must use HTTPS")
    return {"client_id": metadata()["client_id"], "handle_resolver": settings.ATPROTO_HANDLE_RESOLVER}
