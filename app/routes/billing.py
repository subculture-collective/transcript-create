import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text

from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..db import get_db
from ..settings import settings

router = APIRouter()
stripe.api_key = settings.STRIPE_API_KEY or None


@router.post("/billing/checkout-session")
def create_checkout_session(payload: dict, request: Request, db=Depends(get_db)):
    if not settings.STRIPE_API_KEY:
        raise HTTPException(501, "Stripe not configured")
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise HTTPException(401)
    period = (payload.get("period") or "").lower()
    price_id = payload.get("price_id") or (
        settings.STRIPE_PRICE_PRO_YEARLY
        if period == "yearly" and settings.STRIPE_PRICE_PRO_YEARLY
        else settings.STRIPE_PRICE_PRO_MONTHLY
    )
    origin = settings.FRONTEND_ORIGIN.rstrip("/")
    success_url_t = (settings.STRIPE_SUCCESS_URL or f"{origin}/pricing?success=1").replace("{origin}", origin)
    cancel_url_t = (settings.STRIPE_CANCEL_URL or f"{origin}/pricing?canceled=1").replace("{origin}", origin)
    customer_id = user.get("stripe_customer_id")
    if not customer_id:
        user_email = user.get("email")
        metadata = {"user_id": str(user["id"])}
        if user_email:
            cust = stripe.Customer.create(email=str(user_email), metadata=metadata)
        else:
            cust = stripe.Customer.create(metadata=metadata)
        customer_id = cust.id
        db.execute(
            text("UPDATE users SET stripe_customer_id=:c, updated_at=now() WHERE id=:i"),
            {"c": customer_id, "i": str(user["id"])},
        )
        db.commit()
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url_t,
        cancel_url=cancel_url_t,
        allow_promotion_codes=True,
        metadata={"user_id": str(user["id"])},
    )
    return {"id": session.id, "url": session.url}


@router.get("/billing/portal")
def billing_portal(request: Request, db=Depends(get_db)):
    if not settings.STRIPE_API_KEY:
        raise HTTPException(501, "Stripe not configured")
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise HTTPException(401)
    if not user.get("stripe_customer_id"):
        raise HTTPException(400, "No Stripe customer")
    origin = settings.FRONTEND_ORIGIN.rstrip("/")
    portal = stripe.billing_portal.Session.create(customer=user["stripe_customer_id"], return_url=f"{origin}/pricing")
    return {"url": portal.url}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db=Depends(get_db)):
    if not settings.STRIPE_API_KEY:
        raise HTTPException(501, "Stripe not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        if settings.STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
        else:
            event_data = await request.json()
            event = stripe.Event.construct_from(event_data, stripe.api_key)
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {e}")
    t = event.get("type")
    data = event.get("data", {}).get("object", {})

    def set_plan_by_customer(customer_id: str, plan: str | None, sub_status: str | None):
        row = (
            db.execute(text("SELECT id FROM users WHERE stripe_customer_id=:c"), {"c": customer_id}).mappings().first()
        )
        if not row:
            return
        if plan:
            db.execute(
                text("UPDATE users SET plan=:p, stripe_subscription_status=:s, updated_at=now() WHERE id=:i"),
                {"p": plan, "s": sub_status, "i": str(row["id"])},
            )
        else:
            db.execute(
                text("UPDATE users SET stripe_subscription_status=:s, updated_at=now() WHERE id=:i"),
                {"s": sub_status, "i": str(row["id"])},
            )
        db.commit()

    if t in ("checkout.session.completed", "customer.subscription.created", "customer.subscription.updated"):
        customer_id = data.get("customer") or data.get("customer_id")
        status = (data.get("status") or "").lower()
        plan = settings.PRO_PLAN_NAME if status in ("active", "trialing") else None
        if customer_id:
            set_plan_by_customer(customer_id, plan, status)
    elif t in ("customer.subscription.deleted",):
        customer_id = data.get("customer")
        if customer_id:
            set_plan_by_customer(customer_id, "free", "canceled")
    return {"received": True}
