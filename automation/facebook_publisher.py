from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from meta_config import get_meta_api_version


@dataclass(frozen=True)
class PublishResult:
    success: bool
    post_id: str | None = None
    error: str | None = None


def _safe_error_text(value: object, secrets: tuple[str, ...]) -> str:
    text = str(value or "").strip()
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"(?i)(access[_ -]?token|authorization|bearer|api[_ -]?key)(\s*[:=]\s*|\s+)[^\s&,;]+",
        r"\1\2[REDACTED]",
        text,
    )
    return text[:500]


def _meta_error_message(exc: urllib.error.HTTPError, token: str) -> str:
    detail = ""
    try:
        payload = json.loads(exc.read().decode("utf-8", errors="replace"))
        detail = payload.get("error", {}).get("message", "")
    except (AttributeError, json.JSONDecodeError, OSError):
        pass

    safe_detail = _safe_error_text(detail, (token,))
    if exc.code in (400, 401, 403):
        prefix = (
            "Meta Graph API rejected the Page post. Verify that the token is a Page Access "
            "Token for this Page and has pages_manage_posts permission"
        )
    else:
        prefix = f"Meta Graph API returned HTTP {exc.code}"
    return f"{prefix}: {safe_detail}" if safe_detail else prefix


def publish_page_post(
    message: str,
    *,
    page_id: str | None = None,
    page_access_token: str | None = None,
    api_version: str | None = None,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> PublishResult:
    """Publish one text post to a Facebook Page through the Meta Graph API."""
    page_id = (page_id if page_id is not None else os.getenv("MESSENGER_PAGE_ID", "")).strip()
    token = (
        page_access_token
        if page_access_token is not None
        else os.getenv("MESSENGER_PAGE_ACCESS_TOKEN", "")
    ).strip()
    version = (api_version if api_version is not None else get_meta_api_version()).strip()

    if not message.strip():
        return PublishResult(False, error="Facebook post message is empty")
    if not page_id:
        return PublishResult(False, error="MESSENGER_PAGE_ID is not configured")
    if not token:
        return PublishResult(False, error="MESSENGER_PAGE_ACCESS_TOKEN is not configured")
    if not version:
        return PublishResult(False, error="MESSENGER_API_VERSION is not configured")

    safe_page_id = urllib.parse.quote(page_id, safe="")
    safe_version = urllib.parse.quote(version, safe="")
    url = f"https://graph.facebook.com/{safe_version}/{safe_page_id}/feed"
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode({"message": message}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with opener(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            post_id = str(payload.get("id", "")).strip()
            if not post_id:
                return PublishResult(False, error="Meta Graph API response did not contain a post ID")
            return PublishResult(True, post_id=post_id)
    except urllib.error.HTTPError as exc:
        return PublishResult(False, error=_meta_error_message(exc, token))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return PublishResult(False, error="Meta Graph API returned an invalid response")
    except Exception as exc:
        safe_error = _safe_error_text(exc, (token,))
        suffix = f": {safe_error}" if safe_error else ""
        return PublishResult(False, error=f"Meta Graph API request failed{suffix}")
