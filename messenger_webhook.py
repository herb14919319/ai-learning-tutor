import hmac
import logging
from typing import Callable

from messenger_client import send_text_message


logger = logging.getLogger(__name__)

MESSENGER_PROCESSING_MESSAGE = "\u52a9\u6559\u6b63\u5728\u52aa\u529b\u601d\u8003\u4e2d..."
MESSENGER_ERROR_FALLBACK_RESPONSE = (
    "\u62b1\u6b49\uff0c\u52a9\u6559\u66ab\u6642\u60f3\u4e0d\u51fa"
    "\u7b54\u6848\uff0c\u8acb\u7a0d\u5f8c\u518d\u8a66\u4e00\u6b21\u3002"
)

_reply_generator: Callable[[str, str], str] | None = None
_background_executor = None


def configure_messenger_handler(*, reply_generator: Callable[[str, str], str], executor) -> None:
    global _reply_generator, _background_executor
    _reply_generator = reply_generator
    _background_executor = executor


def handle_verify_request(args, verify_token: str | None = None):
    mode = args.get("hub.mode", "")
    token = args.get("hub.verify_token", "")
    challenge = args.get("hub.challenge", "")

    if mode == "subscribe" and verify_token is not None and hmac.compare_digest(token, verify_token):
        return challenge, 200
    return "Forbidden", 403


def process_messenger_text_async(sender_id: str, user_text: str) -> None:
    reply = MESSENGER_ERROR_FALLBACK_RESPONSE
    try:
        if _reply_generator is None:
            logger.error("Messenger reply generator is not configured")
        else:
            reply = _reply_generator(f"messenger:{sender_id}", user_text)
    except Exception:
        logger.exception("Messenger async text processing failed")

    send_text_message(sender_id, reply or MESSENGER_ERROR_FALLBACK_RESPONSE)


def _is_text_message_event(messaging_event: dict) -> bool:
    message = messaging_event.get("message")
    if not isinstance(message, dict):
        return False
    if message.get("is_echo"):
        return False
    if message.get("attachments"):
        return False
    return isinstance(message.get("text"), str) and bool(message.get("text").strip())


def handle_messenger_event(payload: dict) -> bool:
    if not isinstance(payload, dict) or payload.get("object") != "page":
        return False

    submitted = False
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            continue
        for messaging_event in entry.get("messaging", []):
            if not isinstance(messaging_event, dict):
                continue
            if not _is_text_message_event(messaging_event):
                continue

            sender = messaging_event.get("sender") or {}
            sender_id = sender.get("id")
            if not sender_id:
                logger.warning("Messenger text event has no sender id")
                continue

            user_text = messaging_event["message"]["text"].strip()
            send_text_message(sender_id, MESSENGER_PROCESSING_MESSAGE)
            try:
                if _background_executor is None:
                    logger.error("Messenger background executor is not configured")
                    continue
                _background_executor.submit(process_messenger_text_async, sender_id, user_text)
                submitted = True
            except Exception:
                logger.exception("Failed to submit Messenger async processing task")
                send_text_message(sender_id, MESSENGER_ERROR_FALLBACK_RESPONSE)

    return submitted
