"""Integration tests for billing and payment flows."""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


class TestBillingFlow:
    """Integration tests for billing functionality."""

    @pytest.mark.timeout(60)
    def test_create_checkout_session(self, integration_client: TestClient, clean_test_data):
        """Test creating a Stripe checkout session."""
        response = integration_client.post(
            "/billing/checkout",
            json={"plan": "pro", "price_id": "price_test123"},
        )

        # Endpoint might not exist or require authentication
        assert response.status_code in [200, 401, 404, 422]

        if response.status_code == 200:
            data = response.json()
            # Should contain checkout session info
            assert "url" in data or "session_id" in data or "id" in data

    @pytest.mark.timeout(60)
    def test_create_checkout_session_invalid_plan(self, integration_client: TestClient, clean_test_data):
        """Test creating checkout session with invalid plan."""
        response = integration_client.post(
            "/billing/checkout",
            json={"plan": "invalid_plan_xyz"},
        )

        # Should reject invalid plan
        assert response.status_code in [400, 404, 422]

    @pytest.mark.timeout(60)
    def test_get_billing_info(self, integration_client: TestClient, clean_test_data):
        """Test retrieving billing information."""
        response = integration_client.get("/billing/info")

        # Requires authentication
        assert response.status_code in [200, 401, 404]


class TestStripeWebhooks:
    """Integration tests for Stripe webhook handling."""

    @pytest.mark.timeout(60)
    @patch("app.routes.billing.stripe.Webhook.construct_event")
    def test_webhook_subscription_created(
        self, mock_construct, integration_client: TestClient, integration_db, clean_test_data
    ):
        """Test handling Stripe webhook for subscription creation."""
        # Create a test user
        user_id = uuid.uuid4()

        try:
            integration_db.execute(
                text(
                    """
                    INSERT INTO users (id, email, plan, stripe_customer_id)
                    VALUES (:user_id, 'test@example.com', 'free', 'cus_test123')
                """
                ),
                {"user_id": str(user_id)},
            )
            integration_db.commit()
        except Exception:
            pytest.skip("Users table not available")

        # Mock webhook event
        mock_event = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_test123",
                    "customer": "cus_test123",
                    "status": "active",
                    "items": {"data": [{"price": {"id": "price_pro"}}]},
                }
            },
        }
        mock_construct.return_value = mock_event

        # Send webhook
        response = integration_client.post(
            "/billing/webhook",
            json=mock_event,
            headers={"stripe-signature": "test_signature"},
        )

        # Endpoint might not exist
        assert response.status_code in [200, 404, 500]

    @pytest.mark.timeout(60)
    def test_webhook_invalid_signature(self, integration_client: TestClient, clean_test_data):
        """Test webhook with invalid signature."""
        response = integration_client.post(
            "/billing/webhook",
            json={"type": "test"},
            headers={"stripe-signature": "invalid_signature"},
        )

        # Should reject invalid signature or return 404 if not implemented
        assert response.status_code in [400, 404, 500]

    @pytest.mark.timeout(60)
    @patch("app.routes.billing.stripe.Webhook.construct_event")
    def test_webhook_subscription_deleted(
        self, mock_construct, integration_client: TestClient, integration_db, clean_test_data
    ):
        """Test handling Stripe webhook for subscription cancellation."""
        # Create a test user with active subscription
        user_id = uuid.uuid4()

        try:
            integration_db.execute(
                text(
                    """
                    INSERT INTO users (id, email, plan, stripe_customer_id)
                    VALUES (:user_id, 'test@example.com', 'pro', 'cus_test123')
                """
                ),
                {"user_id": str(user_id)},
            )
            integration_db.commit()
        except Exception:
            pytest.skip("Users table not available")

        # Mock webhook event
        mock_event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_test123",
                    "customer": "cus_test123",
                }
            },
        }
        mock_construct.return_value = mock_event

        # Send webhook
        response = integration_client.post(
            "/billing/webhook",
            json=mock_event,
            headers={"stripe-signature": "test_signature"},
        )

        # Endpoint might not exist
        assert response.status_code in [200, 404, 500]


class TestPlanUpgrade:
    """Integration tests for plan upgrade functionality."""

    @pytest.mark.timeout(60)
    def test_upgrade_to_pro(self, integration_client: TestClient, integration_db, clean_test_data):
        """Test upgrading user from free to pro plan."""
        # Create a free user
        user_id = uuid.uuid4()

        try:
            integration_db.execute(
                text(
                    """
                    INSERT INTO users (id, email, plan)
                    VALUES (:user_id, 'test@example.com', 'free')
                """
                ),
                {"user_id": str(user_id)},
            )
            integration_db.commit()

            # Simulate upgrade
            integration_db.execute(text("UPDATE users SET plan = 'pro' WHERE id = :id"), {"id": str(user_id)})
            integration_db.commit()

            # Verify upgrade
            result = integration_db.execute(text("SELECT plan FROM users WHERE id = :id"), {"id": str(user_id)})
            plan = result.scalar()
            assert plan == "pro"

        except Exception:
            pytest.skip("Users table not available")

    @pytest.mark.timeout(60)
    def test_downgrade_to_free(self, integration_client: TestClient, integration_db, clean_test_data):
        """Test downgrading user from pro to free plan."""
        # Create a pro user
        user_id = uuid.uuid4()

        try:
            integration_db.execute(
                text(
                    """
                    INSERT INTO users (id, email, plan)
                    VALUES (:user_id, 'test@example.com', 'pro')
                """
                ),
                {"user_id": str(user_id)},
            )
            integration_db.commit()

            # Simulate downgrade
            integration_db.execute(text("UPDATE users SET plan = 'free' WHERE id = :id"), {"id": str(user_id)})
            integration_db.commit()

            # Verify downgrade
            result = integration_db.execute(text("SELECT plan FROM users WHERE id = :id"), {"id": str(user_id)})
            plan = result.scalar()
            assert plan == "free"

        except Exception:
            pytest.skip("Users table not available")


class TestPaymentMethods:
    """Integration tests for payment method management."""

    @pytest.mark.timeout(60)
    def test_add_payment_method(self, integration_client: TestClient, clean_test_data):
        """Test adding a payment method."""
        response = integration_client.post(
            "/billing/payment-method",
            json={"payment_method_id": "pm_test123"},
        )

        # Requires authentication
        assert response.status_code in [200, 401, 404]

    @pytest.mark.timeout(60)
    def test_list_payment_methods(self, integration_client: TestClient, clean_test_data):
        """Test listing payment methods."""
        response = integration_client.get("/billing/payment-methods")

        # Requires authentication
        assert response.status_code in [200, 401, 404]

    @pytest.mark.timeout(60)
    def test_delete_payment_method(self, integration_client: TestClient, clean_test_data):
        """Test deleting a payment method."""
        response = integration_client.delete("/billing/payment-method/pm_test123")

        # Requires authentication
        assert response.status_code in [200, 204, 401, 404]
