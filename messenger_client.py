import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request


logger = logging.getLogger(__name__)


def send_text_message(recipient_id: str, text: str) -> bool:
    page_access_token = os.getenv("MESSENGER_PAGE_ACCESS_TOKEN", "")
    api_version = os.getenv("MESSENGER_API_VERSION", "v20.0")

    if not page_access_token:
        logger.error("Messenger Page Access Token is not configured")
        return False

    url = (
        f"https://graph.facebook.com/{api_version}/me/messages?"
        f"{urllib.parse.urlencode({'access_token': page_access_token})}"
    )
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if 200 <= response.status < 300:
                return True
            logger.error("Messenger Send API returned status=%s", response.status)
            return False
    except urllib.error.HTTPError as exc:
        logger.error("Messenger Send API HTTP error status=%s", exc.code)
    except Exception:
        logger.exception("Messenger Send API request failed")

    return False
