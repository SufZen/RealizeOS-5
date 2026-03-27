"""
Stripe integration — invoicing, payment links, payment status.

Configure in .env:
  STRIPE_API_KEY=sk_...

All financial actions are governance-gated (trust ladder: financial_action).
"""

import hashlib
import hmac
import logging
import os
import time

logger = logging.getLogger(__name__)

# Safety limits
STRIPE_MAX_AMOUNT_CENTS = 99_999_999  # $999,999.99
STRIPE_MIN_AMOUNT_CENTS = 1


def _validate_amount(amount_cents: int) -> str | None:
    """Validate payment amount. Returns error string or None if valid."""
    if not isinstance(amount_cents, int):
        return f"amount_cents must be an integer, got {type(amount_cents).__name__}"
    if amount_cents < STRIPE_MIN_AMOUNT_CENTS:
        return f"amount_cents must be at least {STRIPE_MIN_AMOUNT_CENTS}, got {amount_cents}"
    if amount_cents > STRIPE_MAX_AMOUNT_CENTS:
        return f"amount_cents exceeds max ({STRIPE_MAX_AMOUNT_CENTS}), got {amount_cents}"
    return None


def _make_idempotency_key(*parts: str) -> str:
    """Generate a deterministic idempotency key from component parts."""
    # Use a 1-hour time bucket to allow retries within the same window
    time_bucket = str(int(time.time()) // 3600)
    raw = "|".join([*parts, time_bucket])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _parse_stripe_error(response_json: dict) -> str:
    """Extract human-readable error from Stripe API response."""
    err = response_json.get("error", {})
    code = err.get("code", "")
    decline_code = err.get("decline_code", "")
    message = err.get("message", "Unknown error")
    parts = [message]
    if code:
        parts.append(f"(code: {code})")
    if decline_code:
        parts.append(f"(decline: {decline_code})")
    return " ".join(parts)


def is_available() -> bool:
    """Check if Stripe is configured."""
    return bool(os.getenv("STRIPE_API_KEY", ""))


async def create_invoice(
    customer_email: str,
    items: list[dict],
    currency: str = "usd",
    description: str = "",
) -> dict:
    """
    Create and send a Stripe invoice.

    Args:
        customer_email: Customer's email
        items: List of {description, amount_cents} dicts
        currency: Currency code (default: usd)
        description: Invoice description

    Returns:
        {invoice_id, status, url, error}
    """
    api_key = os.getenv("STRIPE_API_KEY", "")
    if not api_key:
        return {"error": "STRIPE_API_KEY not configured"}

    try:
        import httpx

        headers = {"Authorization": f"Bearer {api_key}"}
        base = "https://api.stripe.com/v1"

        # Validate all item amounts
        for item in items:
            amt = item.get("amount_cents", 0)
            err = _validate_amount(amt)
            if err:
                return {"error": f"Invalid line item amount: {err}"}

        # Idempotency key to prevent duplicate invoices on retry
        items_hash = hashlib.sha256(
            str(sorted((i.get("description", ""), i.get("amount_cents", 0)) for i in items)).encode()
        ).hexdigest()[:16]
        idempotency_key = _make_idempotency_key(customer_email, items_hash)
        idem_headers = {**headers, "Idempotency-Key": idempotency_key}

        async with httpx.AsyncClient(timeout=30) as client:
            # Find or create customer
            cust_resp = await client.get(
                f"{base}/customers/search",
                headers=headers,
                params={"query": f"email:'{customer_email}'"},
            )
            customers = cust_resp.json().get("data", [])

            if customers:
                customer_id = customers[0]["id"]
            else:
                create_resp = await client.post(
                    f"{base}/customers",
                    headers=headers,
                    data={"email": customer_email},
                )
                customer_id = create_resp.json().get("id")
                if not customer_id:
                    return {"error": "Failed to create customer"}

            # Create invoice
            invoice_resp = await client.post(
                f"{base}/invoices",
                headers=idem_headers,
                data={
                    "customer": customer_id,
                    "collection_method": "send_invoice",
                    "days_until_due": 30,
                    "description": description,
                },
            )
            invoice = invoice_resp.json()
            invoice_id = invoice.get("id")
            if not invoice_id:
                return {"error": f"Failed to create invoice: {_parse_stripe_error(invoice)}"}

            # Add line items
            for item in items:
                await client.post(
                    f"{base}/invoiceitems",
                    headers=headers,
                    data={
                        "customer": customer_id,
                        "invoice": invoice_id,
                        "amount": item.get("amount_cents", 0),
                        "currency": currency,
                        "description": item.get("description", ""),
                    },
                )

            # Finalize and send
            await client.post(f"{base}/invoices/{invoice_id}/finalize", headers=headers)
            send_resp = await client.post(f"{base}/invoices/{invoice_id}/send", headers=headers)
            final = send_resp.json()

            return {
                "invoice_id": invoice_id,
                "status": final.get("status", "unknown"),
                "url": final.get("hosted_invoice_url", ""),
                "amount_due": final.get("amount_due", 0),
                "currency": currency,
            }

    except ImportError:
        return {"error": "httpx not installed"}
    except Exception as e:
        return {"error": str(e)[:200]}


async def create_payment_link(
    amount_cents: int,
    currency: str = "usd",
    description: str = "Payment",
) -> dict:
    """
    Create a Stripe payment link.

    Returns:
        {url, payment_link_id, error}
    """
    api_key = os.getenv("STRIPE_API_KEY", "")
    if not api_key:
        return {"error": "STRIPE_API_KEY not configured"}

    try:
        import httpx

        headers = {"Authorization": f"Bearer {api_key}"}
        base = "https://api.stripe.com/v1"

        async with httpx.AsyncClient(timeout=30) as client:
            # Validate amount
            err = _validate_amount(amount_cents)
            if err:
                return {"error": err}

            # Create a price
            price_resp = await client.post(
                f"{base}/prices",
                headers=headers,
                data={
                    "unit_amount": amount_cents,
                    "currency": currency,
                    "product_data[name]": description,
                },
            )
            price_id = price_resp.json().get("id")
            if not price_id:
                return {"error": "Failed to create price"}

            # Create payment link
            link_resp = await client.post(
                f"{base}/payment_links",
                headers=headers,
                data={
                    "line_items[0][price]": price_id,
                    "line_items[0][quantity]": 1,
                },
            )
            link = link_resp.json()

            return {
                "payment_link_id": link.get("id", ""),
                "url": link.get("url", ""),
                "amount_cents": amount_cents,
                "currency": currency,
            }

    except ImportError:
        return {"error": "httpx not installed"}
    except Exception as e:
        return {"error": str(e)[:200]}


async def check_payment_status(invoice_id: str) -> dict:
    """Check the status of a Stripe invoice."""
    api_key = os.getenv("STRIPE_API_KEY", "")
    if not api_key:
        return {"error": "STRIPE_API_KEY not configured"}

    try:
        import httpx

        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://api.stripe.com/v1/invoices/{invoice_id}",
                headers=headers,
            )
            invoice = resp.json()

            return {
                "invoice_id": invoice_id,
                "status": invoice.get("status", "unknown"),
                "amount_due": invoice.get("amount_due", 0),
                "amount_paid": invoice.get("amount_paid", 0),
                "currency": invoice.get("currency", ""),
                "customer_email": invoice.get("customer_email", ""),
            }

    except ImportError:
        return {"error": "httpx not installed"}
    except Exception as e:
        return {"error": str(e)[:200]}


def get_stripe_status() -> dict:
    """Get Stripe integration status."""
    return {
        "configured": is_available(),
        "description": "Invoicing, payment links, payment tracking",
    }


def verify_webhook_signature(
    payload: bytes,
    signature_header: str,
    webhook_secret: str | None = None,
) -> bool:
    """
    Verify a Stripe webhook signature (HMAC-SHA256).

    Args:
        payload: Raw request body bytes
        signature_header: Stripe-Signature header value
        webhook_secret: Webhook signing secret (falls back to env var)

    Returns:
        True if the signature is valid
    """
    secret = webhook_secret or os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning("No STRIPE_WEBHOOK_SECRET configured — cannot verify webhook")
        return False

    try:
        # Parse the Stripe-Signature header
        parts = dict(
            kv.split("=", 1) for kv in signature_header.split(",") if "=" in kv
        )
        timestamp = parts.get("t", "")
        sig_v1 = parts.get("v1", "")

        if not timestamp or not sig_v1:
            return False

        # Build the signed payload
        signed_payload = f"{timestamp}.{payload.decode()}"
        expected = hmac.new(
            secret.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, sig_v1)
    except Exception as e:
        logger.warning("Webhook signature verification failed: %s", e)
        return False
