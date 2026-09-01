from fastapi import APIRouter
from pydantic import BaseModel

from ..settings import settings

router = APIRouter(prefix="", tags=["Support"])


class SupportConfig(BaseModel):
    donations_enabled: bool
    payment_url: str | None


@router.get(
    "/support",
    response_model=SupportConfig,
    summary="Get public donation configuration",
    description="Return the validated Stripe-hosted Payment Link when donations are enabled.",
)
def support_config() -> SupportConfig:
    payment_url = settings.DONATION_PAYMENT_LINK_URL or None
    return SupportConfig(donations_enabled=payment_url is not None, payment_url=payment_url)
