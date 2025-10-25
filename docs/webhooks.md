# Stripe Webhook Integration Guide

This guide explains how to integrate and handle Stripe webhooks for subscription management in Transcript Create.

## Overview

Transcript Create uses Stripe webhooks to automatically update user subscription status when:
- A user completes checkout
- A subscription is created or updated
- A subscription is canceled or expires

## Webhook Endpoint

```
POST /stripe/webhook
```

This endpoint receives and processes webhook events from Stripe.

## Setup

### 1. Configure Stripe

In your Stripe Dashboard:

1. Go to **Developers** → **Webhooks**
2. Click **Add endpoint**
3. Enter your webhook URL: `https://api.example.com/stripe/webhook`
4. Select events to listen for:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
5. Copy the webhook signing secret

### 2. Environment Variables

Add these to your `.env` file:

```bash
# Stripe API configuration
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Price IDs from Stripe Dashboard
STRIPE_PRICE_PRO_MONTHLY=price_...
STRIPE_PRICE_PRO_YEARLY=price_...

# Checkout URLs
STRIPE_SUCCESS_URL=https://app.example.com/pricing?success=1
STRIPE_CANCEL_URL=https://app.example.com/pricing?canceled=1

# Plan configuration
PRO_PLAN_NAME=pro
```

## Webhook Events

### checkout.session.completed

Triggered when a user successfully completes checkout.

**What it does:**
1. Identifies the customer by Stripe customer ID
2. Updates user's plan to "pro"
3. Sets subscription status to "active"

### customer.subscription.created

Triggered when a new subscription is created.

**What it does:**
- Sets user plan based on subscription status
- Active or trialing subscriptions → "pro" plan
- Other statuses → no plan change

### customer.subscription.updated

Triggered when subscription status changes (e.g., payment updated, plan changed).

**What it does:**
- Updates user plan based on new subscription status
- Handles transitions between active/inactive states

### customer.subscription.deleted

Triggered when a subscription is canceled or expires.

**What it does:**
1. Sets user plan back to "free"
2. Sets subscription status to "canceled"

## Event Processing

### Webhook Signature Verification

Stripe signs all webhook events. The API automatically verifies signatures:

```python
if settings.STRIPE_WEBHOOK_SECRET:
    event = stripe.Webhook.construct_event(
        payload, 
        signature_header, 
        settings.STRIPE_WEBHOOK_SECRET
    )
```

If verification fails, returns `400 Bad Request`.

### Database Updates

When processing events, the API:

1. Extracts customer ID from the event
2. Queries the database for user with matching `stripe_customer_id`
3. Updates the user record:
   - `plan` field (free/pro)
   - `stripe_subscription_status` field
   - `updated_at` timestamp

### Response Format

All webhook requests return:

```json
{
  "received": true
}
```

This acknowledges receipt to Stripe, even if processing fails (to avoid retries).

## Testing Webhooks

### Local Development with Stripe CLI

Install the [Stripe CLI](https://stripe.com/docs/stripe-cli):

```bash
# Login to Stripe
stripe login

# Forward webhooks to local server
stripe listen --forward-to http://localhost:8000/stripe/webhook

# Trigger test events
stripe trigger checkout.session.completed
stripe trigger customer.subscription.updated
stripe trigger customer.subscription.deleted
```

The CLI displays the webhook signing secret - add it to your `.env`:

```bash
STRIPE_WEBHOOK_SECRET=whsec_test_...
```

### Test Events

Use Stripe Dashboard to send test webhooks:

1. Go to **Developers** → **Webhooks**
2. Click on your endpoint
3. Click **Send test webhook**
4. Select event type and send

### Manual Testing

Send a test webhook with curl:

```bash
# Get a sample event from Stripe CLI or docs
curl -X POST https://api.example.com/stripe/webhook \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: t=timestamp,v1=signature" \
  -d @test_event.json
```

## Subscription Flow

### Creating a Subscription

1. User clicks "Upgrade to Pro" on frontend
2. Frontend calls `POST /billing/checkout-session`
3. API creates Stripe checkout session
4. User redirects to Stripe checkout page
5. User completes payment
6. Stripe sends `checkout.session.completed` webhook
7. API updates user plan to "pro"
8. User redirects back to success page

### Canceling a Subscription

1. User accesses billing portal via `GET /billing/portal`
2. User cancels subscription in Stripe portal
3. Stripe sends `customer.subscription.deleted` webhook
4. API updates user plan back to "free"

## Error Handling

### Webhook Validation Errors

**400 Bad Request** - Invalid signature
```json
{
  "error": "validation_error",
  "message": "Invalid webhook signature: ...",
  "details": {}
}
```

**400 Bad Request** - Malformed event
```json
{
  "error": "validation_error",
  "message": "Webhook error: ...",
  "details": {}
}
```

### Configuration Errors

**503 Service Unavailable** - Stripe not configured
```json
{
  "error": "external_service_error",
  "message": "Stripe billing is not configured",
  "details": {
    "service": "Stripe"
  }
}
```

## Monitoring

### Stripe Dashboard

Monitor webhook deliveries in Stripe Dashboard:

1. Go to **Developers** → **Webhooks**
2. Click on your endpoint
3. View delivery history and status
4. Retry failed deliveries if needed

### Application Logs

The API logs all webhook events:

```json
{
  "level": "info",
  "message": "Stripe webhook received",
  "event_type": "customer.subscription.updated",
  "customer_id": "cus_...",
  "timestamp": "2025-10-25T10:30:00Z"
}
```

### Failed Deliveries

If webhook processing fails:

1. Stripe automatically retries with exponential backoff
2. Check application logs for errors
3. Fix the issue
4. Use Stripe Dashboard to retry failed events

## Security Best Practices

### Webhook Signing

**Always verify webhook signatures** to ensure events come from Stripe:

```python
# ✅ Good - Verifies signature
event = stripe.Webhook.construct_event(
    payload, signature, webhook_secret
)

# ❌ Bad - Trusts unverified data
event = json.loads(payload)
```

### Idempotency

Webhook handlers should be idempotent (safe to run multiple times):

- Use `UPDATE` instead of `INSERT` where possible
- Check existing state before making changes
- Handle duplicate events gracefully

### Endpoint Security

- Use HTTPS in production
- Don't expose webhook secret in logs or errors
- Rate limit webhook endpoint if needed
- Monitor for suspicious activity

## Common Issues

### Signature Verification Fails

**Cause:** Webhook secret mismatch

**Solution:** 
1. Copy correct secret from Stripe Dashboard
2. Update `STRIPE_WEBHOOK_SECRET` in `.env`
3. Restart API server

### User Not Found

**Cause:** Webhook references customer not in database

**Solution:** Ensure customer ID is set when creating Stripe customers:

```python
customer = stripe.Customer.create(
    email=user_email,
    metadata={"user_id": str(user_id)}
)
```

### Plan Not Updating

**Cause:** Event not handled or database transaction failed

**Solution:**
1. Check application logs for errors
2. Verify event type is in handled list
3. Check database connection
4. Retry failed event from Stripe Dashboard

## Related Endpoints

### Create Checkout Session

```
POST /billing/checkout-session
```

Creates a Stripe checkout session for Pro subscription.

### Billing Portal

```
GET /billing/portal
```

Returns URL to Stripe customer portal for managing subscriptions.

## Related Documentation

- [Getting Started](getting-started.md) - Basic API usage
- [Authentication](authentication.md) - OAuth and session management
- [API Reference](api-reference.md) - Complete endpoint documentation
- [Stripe Webhooks Documentation](https://stripe.com/docs/webhooks)
