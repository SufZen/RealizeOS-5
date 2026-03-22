"""
Social media posting — LinkedIn + Twitter/X API integration.

Governance-gated by default (requires approval via trust ladder).
Configure API tokens in .env:
  LINKEDIN_TOKEN=...
  TWITTER_BEARER_TOKEN=...
"""
import logging
import os

logger = logging.getLogger(__name__)


def is_linkedin_available() -> bool:
    """Check if LinkedIn posting is configured."""
    return bool(os.getenv("LINKEDIN_TOKEN", ""))


def is_twitter_available() -> bool:
    """Check if Twitter/X posting is configured."""
    return bool(os.getenv("TWITTER_BEARER_TOKEN", ""))


async def post_to_linkedin(content: str, title: str = "") -> dict:
    """
    Post content to LinkedIn.

    Requires LINKEDIN_TOKEN environment variable.

    Returns:
        {posted: bool, post_id: str, error: str}
    """
    token = os.getenv("LINKEDIN_TOKEN", "")
    if not token:
        return {"posted": False, "error": "LINKEDIN_TOKEN not configured"}

    try:
        import httpx
        # LinkedIn API v2 - UGC Post
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        # Get user profile URN
        async with httpx.AsyncClient(timeout=30) as client:
            profile_resp = await client.get(
                "https://api.linkedin.com/v2/userinfo",
                headers=headers,
            )
            if profile_resp.status_code != 200:
                return {"posted": False, "error": f"LinkedIn auth failed: {profile_resp.status_code}"}

            user_sub = profile_resp.json().get("sub", "")
            if not user_sub:
                return {"posted": False, "error": "Could not get LinkedIn user ID"}

            # Create post
            post_data = {
                "author": f"urn:li:person:{user_sub}",
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": content},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                },
            }

            resp = await client.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers=headers,
                json=post_data,
            )

            if resp.status_code in (200, 201):
                post_id = resp.headers.get("x-restli-id", resp.json().get("id", ""))
                return {"posted": True, "platform": "linkedin", "post_id": post_id}
            else:
                return {"posted": False, "error": f"LinkedIn API error: {resp.status_code} {resp.text[:200]}"}

    except ImportError:
        return {"posted": False, "error": "httpx not installed"}
    except Exception as e:
        return {"posted": False, "error": str(e)[:200]}


async def post_to_twitter(content: str) -> dict:
    """
    Post a tweet to Twitter/X.

    Requires TWITTER_BEARER_TOKEN environment variable.

    Returns:
        {posted: bool, tweet_id: str, error: str}
    """
    bearer = os.getenv("TWITTER_BEARER_TOKEN", "")
    if not bearer:
        return {"posted": False, "error": "TWITTER_BEARER_TOKEN not configured"}

    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.twitter.com/2/tweets",
                headers=headers,
                json={"text": content[:280]},  # Twitter character limit
            )

            if resp.status_code in (200, 201):
                tweet_id = resp.json().get("data", {}).get("id", "")
                return {"posted": True, "platform": "twitter", "tweet_id": tweet_id}
            else:
                return {"posted": False, "error": f"Twitter API error: {resp.status_code} {resp.text[:200]}"}

    except ImportError:
        return {"posted": False, "error": "httpx not installed"}
    except Exception as e:
        return {"posted": False, "error": str(e)[:200]}


def get_social_status() -> dict:
    """Get status of social media integrations."""
    return {
        "linkedin": {
            "configured": is_linkedin_available(),
            "description": "LinkedIn posts and articles",
        },
        "twitter": {
            "configured": is_twitter_available(),
            "description": "Twitter/X posts",
        },
    }
