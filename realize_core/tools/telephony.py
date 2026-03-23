"""
Telephony — outbound phone calls via Twilio.

Governance-gated: requires trust level 3+ (phone_call action).

Configure in .env:
  TWILIO_ACCOUNT_SID=AC...
  TWILIO_AUTH_TOKEN=...
  TWILIO_PHONE_NUMBER=+1...
"""

import logging
import os

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """Check if telephony is configured."""
    return all(
        [
            os.getenv("TWILIO_ACCOUNT_SID", ""),
            os.getenv("TWILIO_AUTH_TOKEN", ""),
            os.getenv("TWILIO_PHONE_NUMBER", ""),
        ]
    )


async def make_call(
    to_number: str,
    message: str = "",
    twiml_url: str = "",
) -> dict:
    """
    Initiate an outbound phone call via Twilio.

    Args:
        to_number: Phone number to call (E.164 format: +1234567890)
        message: Text message to speak (uses TTS)
        twiml_url: URL to TwiML instructions (alternative to message)

    Returns:
        {call_sid, status, error}
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_PHONE_NUMBER", "")

    if not all([account_sid, auth_token, from_number]):
        return {"error": "Twilio not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)"}

    if not to_number.startswith("+"):
        return {"error": "Phone number must be in E.164 format (e.g., +1234567890)"}

    try:
        from base64 import b64encode

        import httpx

        auth = b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}

        data = {
            "To": to_number,
            "From": from_number,
        }

        if twiml_url:
            data["Url"] = twiml_url
        elif message:
            # Use Twilio's TTS via TwiML
            twiml = f'<Response><Say voice="alice">{message}</Say></Response>'
            data["Twiml"] = twiml
        else:
            return {"error": "Provide either 'message' or 'twiml_url'"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json",
                headers=headers,
                data=data,
            )

            call_data = resp.json()
            if resp.status_code in (200, 201):
                return {
                    "call_sid": call_data.get("sid", ""),
                    "status": call_data.get("status", ""),
                    "to": to_number,
                }
            else:
                return {"error": call_data.get("message", f"Twilio error: {resp.status_code}")}

    except ImportError:
        return {"error": "httpx not installed"}
    except Exception as e:
        return {"error": str(e)[:200]}


def get_telephony_status() -> dict:
    return {
        "configured": is_available(),
        "provider": "twilio",
        "description": "Outbound phone calls",
    }
