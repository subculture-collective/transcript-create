from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


def test_support_config_is_public_and_disabled_without_payment_link(monkeypatch):
    monkeypatch.setattr(settings, "DONATION_PAYMENT_LINK_URL", "")

    response = TestClient(app).get("/support")

    assert response.status_code == 200
    assert response.json() == {"donations_enabled": False, "payment_url": None}


def test_support_config_returns_validated_stripe_payment_link(monkeypatch):
    payment_url = "https://buy.stripe.com/test_example"
    monkeypatch.setattr(settings, "DONATION_PAYMENT_LINK_URL", payment_url)

    response = TestClient(app).get("/support")

    assert response.status_code == 200
    assert response.json() == {"donations_enabled": True, "payment_url": payment_url}
