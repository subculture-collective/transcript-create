"""Tests for billing routes."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import text


class TestBillingRoutes:
    """Tests for /billing endpoints."""

    @patch("app.settings.settings.STRIPE_API_KEY", None)
    def test_checkout_session_stripe_not_configured(self, client: TestClient):
        """Test checkout session when Stripe is not configured."""
        response = client.post("/billing/checkout-session", json={})
        assert response.status_code == 501
        assert "Stripe not configured" in response.json()["detail"]

    def test_checkout_session_unauthenticated(self, client: TestClient):
        """Test checkout session without authentication."""
        with patch("app.settings.settings.STRIPE_API_KEY", "sk_test_fake"):
            response = client.post("/billing/checkout-session", json={})
            assert response.status_code == 401

    def test_checkout_session_authenticated(self, client: TestClient, db_session):
        """Test checkout session with authenticated user."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject) "
                "VALUES (:id, :email, 'google', 'test123')"
            ),
            {"id": str(user_id), "email": "billing@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        with patch("app.settings.settings.STRIPE_API_KEY", "sk_test_fake"):
            with patch("stripe.Customer.create") as mock_customer:
                with patch("stripe.checkout.Session.create") as mock_session:
                    # Mock Stripe responses
                    mock_customer.return_value = MagicMock(id="cus_test123")
                    mock_session.return_value = MagicMock(
                        id="cs_test123", url="https://checkout.stripe.com/pay/cs_test"
                    )

                    response = client.post(
                        "/billing/checkout-session", json={"period": "monthly"}, cookies={"tc_session": session_token}
                    )
                    assert response.status_code == 200
                    data = response.json()
                    assert "id" in data
                    assert "url" in data

    def test_checkout_session_yearly_period(self, client: TestClient, db_session):
        """Test checkout session with yearly period."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject) "
                "VALUES (:id, :email, 'google', 'test123')"
            ),
            {"id": str(user_id), "email": "yearly@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        with patch("app.settings.settings.STRIPE_API_KEY", "sk_test_fake"):
            with patch("app.settings.settings.STRIPE_PRICE_PRO_YEARLY", "price_yearly"):
                with patch("stripe.Customer.create") as mock_customer:
                    with patch("stripe.checkout.Session.create") as mock_session:
                        mock_customer.return_value = MagicMock(id="cus_test")
                        mock_session.return_value = MagicMock(id="cs_test", url="https://checkout.stripe.com")

                        response = client.post(
                            "/billing/checkout-session",
                            json={"period": "yearly"},
                            cookies={"tc_session": session_token},
                        )
                        assert response.status_code == 200

    @patch("app.settings.settings.STRIPE_API_KEY", None)
    def test_billing_portal_stripe_not_configured(self, client: TestClient):
        """Test billing portal when Stripe is not configured."""
        response = client.get("/billing/portal")
        assert response.status_code == 501

    def test_billing_portal_unauthenticated(self, client: TestClient):
        """Test billing portal without authentication."""
        with patch("app.settings.settings.STRIPE_API_KEY", "sk_test_fake"):
            response = client.get("/billing/portal")
            assert response.status_code == 401

    def test_billing_portal_no_customer(self, client: TestClient, db_session):
        """Test billing portal for user without Stripe customer."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject) "
                "VALUES (:id, :email, 'google', 'test123')"
            ),
            {"id": str(user_id), "email": "nocustomer@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        with patch("app.settings.settings.STRIPE_API_KEY", "sk_test_fake"):
            response = client.get("/billing/portal", cookies={"tc_session": session_token})
            assert response.status_code == 400
            assert "No Stripe customer" in response.json()["detail"]

    def test_billing_portal_with_customer(self, client: TestClient, db_session):
        """Test billing portal for user with Stripe customer."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, stripe_customer_id) "
                "VALUES (:id, :email, 'google', 'test123', :cust_id)"
            ),
            {"id": str(user_id), "email": "customer@example.com", "cust_id": "cus_test123"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        with patch("app.settings.settings.STRIPE_API_KEY", "sk_test_fake"):
            with patch("stripe.billing_portal.Session.create") as mock_portal:
                mock_portal.return_value = MagicMock(url="https://billing.stripe.com/session/test")

                response = client.get("/billing/portal", cookies={"tc_session": session_token})
                assert response.status_code == 200
                data = response.json()
                assert "url" in data

    @patch("app.settings.settings.STRIPE_API_KEY", None)
    def test_stripe_webhook_not_configured(self, client: TestClient):
        """Test Stripe webhook when Stripe is not configured."""
        response = client.post("/stripe/webhook", json={})
        assert response.status_code == 501

    def test_stripe_webhook_checkout_completed(self, client: TestClient, db_session):
        """Test Stripe webhook for checkout session completed."""
        import uuid

        user_id = uuid.uuid4()
        customer_id = "cus_test123"

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, stripe_customer_id) "
                "VALUES (:id, :email, 'google', 'test', :cust_id)"
            ),
            {"id": str(user_id), "email": "webhook@example.com", "cust_id": customer_id},
        )
        db_session.commit()

        with patch("app.settings.settings.STRIPE_API_KEY", "sk_test_fake"):
            with patch("app.settings.settings.STRIPE_WEBHOOK_SECRET", None):
                with patch("stripe.Event.construct_from") as mock_event:
                    mock_event.return_value = {
                        "type": "checkout.session.completed",
                        "data": {"object": {"customer": customer_id, "status": "active"}},
                    }

                    response = client.post(
                        "/stripe/webhook", json={"type": "checkout.session.completed", "data": {"object": {}}}
                    )
                    assert response.status_code == 200
                    assert response.json()["received"] is True

    def test_stripe_webhook_subscription_updated(self, client: TestClient, db_session):
        """Test Stripe webhook for subscription updated."""
        import uuid

        user_id = uuid.uuid4()
        customer_id = "cus_test456"

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, stripe_customer_id) "
                "VALUES (:id, :email, 'google', 'test', :cust_id)"
            ),
            {"id": str(user_id), "email": "subupdate@example.com", "cust_id": customer_id},
        )
        db_session.commit()

        with patch("app.settings.settings.STRIPE_API_KEY", "sk_test_fake"):
            with patch("app.settings.settings.STRIPE_WEBHOOK_SECRET", None):
                with patch("stripe.Event.construct_from") as mock_event:
                    mock_event.return_value = {
                        "type": "customer.subscription.updated",
                        "data": {"object": {"customer": customer_id, "status": "active"}},
                    }

                    response = client.post("/stripe/webhook", json={"type": "customer.subscription.updated"})
                    assert response.status_code == 200

    def test_stripe_webhook_subscription_deleted(self, client: TestClient, db_session):
        """Test Stripe webhook for subscription deleted."""
        import uuid

        user_id = uuid.uuid4()
        customer_id = "cus_test789"

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, stripe_customer_id, plan) "
                "VALUES (:id, :email, 'google', 'test', :cust_id, 'pro')"
            ),
            {"id": str(user_id), "email": "subdelete@example.com", "cust_id": customer_id},
        )
        db_session.commit()

        with patch("app.settings.settings.STRIPE_API_KEY", "sk_test_fake"):
            with patch("app.settings.settings.STRIPE_WEBHOOK_SECRET", None):
                with patch("stripe.Event.construct_from") as mock_event:
                    mock_event.return_value = {
                        "type": "customer.subscription.deleted",
                        "data": {"object": {"customer": customer_id}},
                    }

                    response = client.post("/stripe/webhook", json={"type": "customer.subscription.deleted"})
                    assert response.status_code == 200

                    # Verify plan was downgraded to free
                    user = (
                        db_session.execute(text("SELECT plan FROM users WHERE id = :id"), {"id": str(user_id)})
                        .mappings()
                        .first()
                    )
                    assert user["plan"] == "free"

    def test_stripe_webhook_invalid_signature(self, client: TestClient):
        """Test Stripe webhook with invalid signature."""
        with patch("app.settings.settings.STRIPE_API_KEY", "sk_test_fake"):
            with patch("app.settings.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"):
                with patch("stripe.Webhook.construct_event") as mock_construct:
                    mock_construct.side_effect = Exception("Invalid signature")

                    response = client.post(
                        "/stripe/webhook",
                        json={"type": "test"},
                        headers={"stripe-signature": "invalid"},
                    )
                    assert response.status_code == 400
                    assert "Webhook error" in response.json()["detail"]
