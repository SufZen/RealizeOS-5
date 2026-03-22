"""
Stripe integration — invoicing, payment links, payment status.

Configure in .env:
  STRIPE_API_KEY=sk_...

All financial actions are governance-gated (trust ladder: financial_action).
"""
import logging
import os

logger = logging.getLogger(__name__)


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
                headers=headers,
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
                return {"error": f"Failed to create invoice: {invoice.get('error', {}).get('message', '')}"}

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
