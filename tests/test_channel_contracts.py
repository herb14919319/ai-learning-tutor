"""R2 contract tests for the LINE, Messenger and Web Chat channels.

Written against the pre-R2 code (channels inside main.py) and kept unchanged
afterwards, except for the three module locations below. Every outbound LINE or
Meta call is intercepted; tests/__init__.py also blocks any real network access.
"""

import base64
import hashlib
import hmac
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import linebot.v3.messaging as line_messaging

import main
import runtime_telemetry
from app.channels import line as line_channel
from app.channels import messenger as messenger_channel
from app.channels import web_chat as web_chat_channel

LINE_CH = line_channel  # module owning LINE transport state (main.py before R2)
MESSENGER_CH = messenger_channel  # (main.messenger_webhook before R2)
WEB_CH = web_chat_channel  # (main.py before R2)

LINE_SECRET = os.environ["LINE_CHANNEL_SECRET"]
MESSENGER_SECRET = os.environ["MESSENGER_APP_SECRET"]
VERIFY_TOKEN = os.environ["MESSENGER_VERIFY_TOKEN"]


class ImmediateExecutor:
    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


def line_body(text="什麼是 RAG？", *, event_id="01HTESTEVENT", message_id="m-1", user_id="U-test-user"):
    return json.dumps({
        "destination": "U-bot",
        "events": [{
            "type": "message",
            "mode": "active",
            "timestamp": 1700000000000,
            "source": {"type": "user", "userId": user_id},
            "webhookEventId": event_id,
            "deliveryContext": {"isRedelivery": False},
            "replyToken": "reply-token-1",
            "message": {"id": message_id, "type": "text", "text": text, "quoteToken": "q-1"},
        }],
    }, ensure_ascii=False)


def line_signature(body, secret=LINE_SECRET):
    return base64.b64encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()).decode()


def messenger_signature(body: bytes, secret=MESSENGER_SECRET):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TelemetryCapture:
    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "telemetry.jsonl"
        self._patch = patch.object(runtime_telemetry, "TELEMETRY_PATH", self.path)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        self._dir.cleanup()

    def events(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]


class RouteContractTest(unittest.TestCase):
    def test_channel_routes_endpoints_and_methods_are_unchanged(self):
        rules = {(r.rule, r.endpoint): sorted(r.methods) for r in main.app.url_map.iter_rules()}
        self.assertEqual(rules[("/callback", "callback")], ["OPTIONS", "POST"])
        self.assertEqual(rules[("/web-chat", "web_chat")], ["OPTIONS", "POST"])
        self.assertEqual(rules[("/webhook/messenger", "messenger_verify")], ["GET", "HEAD", "OPTIONS"])
        self.assertEqual(rules[("/webhook/messenger", "messenger_callback")], ["OPTIONS", "POST"])
        self.assertEqual(len(rules), 23)

    def test_line_handler_registers_only_text_message_events(self):
        self.assertEqual(list(main.handler._handlers), ["MessageEvent_TextMessageContent"])
        self.assertIs(main.handler, LINE_CH.handler)

    def test_channel_methods_not_allowed(self):
        client = main.app.test_client()
        self.assertEqual(client.get("/callback").status_code, 405)
        self.assertEqual(client.get("/web-chat").status_code, 405)
        with patch.dict(os.environ, {"MESSENGER_ENABLED": "true"}):
            self.assertEqual(client.put("/webhook/messenger").status_code, 405)


class LineChannelTest(unittest.TestCase):
    def setUp(self):
        LINE_CH.processed_events.clear()
        self.addCleanup(LINE_CH.processed_events.clear)
        self.client = main.app.test_client()
        self.replies, self.pushes = [], []
        for name, sink in (("reply_message", self.replies), ("push_message", self.pushes)):
            patcher = patch.object(line_messaging.MessagingApi, name,
                                   lambda api, request, sink=sink: sink.append(request))
            patcher.start()
            self.addCleanup(patcher.stop)

    def post(self, body, signature=None):
        return self.client.post("/callback", data=body.encode("utf-8"), content_type="application/json",
                                headers={"X-Line-Signature": line_signature(body) if signature is None else signature})

    def test_bad_or_missing_signature_is_400_and_dispatches_nothing(self):
        body = line_body()
        with patch.object(main.tutor_agent, "answer") as answer:
            self.assertEqual(self.post(body, signature="bad").status_code, 400)
            self.assertEqual(self.client.post("/callback", data=body).status_code, 400)
            self.assertEqual(self.post(body, signature=line_signature(body, "other-secret")).status_code, 400)
        answer.assert_not_called()
        self.assertEqual((self.replies, self.pushes), ([], []))

    def test_signed_text_event_replies_processing_then_pushes_tutor_answer(self):
        body = line_body()
        with TelemetryCapture() as telemetry, patch.object(LINE_CH, "webhook_executor", ImmediateExecutor()), \
             patch.object(main.tutor_agent, "answer", return_value="RAG 會先檢索再生成。") as answer:
            response = self.post(body)
            events = telemetry.events()

        self.assertEqual((response.status_code, response.get_data(as_text=True)), (200, "OK"))
        answer.assert_called_once_with("什麼是 RAG？", user_id="U-test-user")
        self.assertEqual([(r.reply_token, [m.text for m in r.messages]) for r in self.replies],
                         [("reply-token-1", ["助教正在努力思考中..."])])
        self.assertEqual([(p.to, [m.text for m in p.messages]) for p in self.pushes],
                         [("U-test-user", ["RAG 會先檢索再生成。"])])
        self.assertEqual({e["entrypoint"] for e in events}, {"line"})
        self.assertEqual({e["user_scope"] for e in events if e["event"] == "request_received"}, {"channel_user"})
        self.assertEqual(events[-1]["event"], "request_completed")

    def test_duplicate_event_is_processed_once_and_still_acknowledged(self):
        body = line_body(event_id="01HDUPLICATE")
        with patch.object(LINE_CH, "webhook_executor", ImmediateExecutor()), \
             patch.object(main.tutor_agent, "answer", return_value="answer") as answer:
            responses = [self.post(body).status_code for _ in range(2)]
        self.assertEqual(responses, [200, 200])
        answer.assert_called_once()
        self.assertEqual((len(self.replies), len(self.pushes)), (1, 1))

    def test_dedupe_key_order_and_ttl(self):
        event = lambda **kw: type("E", (), {
            "webhook_event_id": kw.get("event_id"), "reply_token": "rt",
            "message": type("M", (), {"id": kw.get("message_id")})()})()
        self.assertEqual(LINE_CH.event_deduplication_key(event(event_id="e", message_id="m")), "event:e")
        self.assertEqual(LINE_CH.event_deduplication_key(event(message_id="m")), "message:m")
        self.assertEqual(LINE_CH.event_deduplication_key(event()), "reply:rt")
        self.assertTrue(LINE_CH.mark_event_if_new(event(event_id="ttl")))
        self.assertFalse(LINE_CH.mark_event_if_new(event(event_id="ttl")))
        LINE_CH.processed_events["event:ttl"] -= LINE_CH.PROCESSED_EVENT_TTL_SECONDS + 1
        self.assertTrue(LINE_CH.mark_event_if_new(event(event_id="ttl")))
        self.assertEqual(LINE_CH.PROCESSED_EVENT_TTL_SECONDS, 600)

    def test_tutor_failure_pushes_error_fallback(self):
        with patch.object(LINE_CH, "webhook_executor", ImmediateExecutor()), \
             patch.object(main.tutor_agent, "answer", side_effect=RuntimeError("boom")):
            self.assertEqual(self.post(line_body()).status_code, 200)
        self.assertEqual([m.text for m in self.pushes[0].messages], [main.ERROR_FALLBACK_RESPONSE])

    def test_help_command_pushes_help_without_tutor(self):
        with patch.object(LINE_CH, "webhook_executor", ImmediateExecutor()), \
             patch.object(main.tutor_agent, "answer") as answer:
            self.post(line_body(text="/help"))
        answer.assert_not_called()
        self.assertIn("AI Learning 助教", self.pushes[0].messages[0].text)

    def test_preserved_exit_command_over_line(self):
        with patch.object(LINE_CH, "webhook_executor", ImmediateExecutor()):
            self.post(line_body(text="/離開"))
        self.assertEqual([m.text for m in self.pushes[0].messages], [main.LEGACY_EXIT_MESSAGE])

    def test_long_answers_are_truncated_for_line(self):
        with patch.object(LINE_CH, "webhook_executor", ImmediateExecutor()), \
             patch.object(main.tutor_agent, "answer", return_value="字" * 5000):
            self.post(line_body())
        text = self.pushes[0].messages[0].text
        self.assertTrue(text.startswith("字" * 4500))
        self.assertTrue(text.endswith("（回覆已因 LINE 單則訊息長度限制截斷）"))

    def test_rich_menu_command_replies_without_push_or_tutor(self):
        with patch.object(LINE_CH, "webhook_executor", ImmediateExecutor()), \
             patch.object(main.tutor_agent, "answer") as answer:
            self.post(line_body(text="我要問問題"))
        answer.assert_not_called()
        self.assertEqual(self.pushes, [])
        self.assertEqual(len(self.replies), 1)
        self.assertIn("歡迎直接問我 AI 相關問題", self.replies[0].messages[-1].text)

    def test_line_reply_runs_on_background_executor(self):
        seen = []
        done = threading.Event()

        def answer(text, user_id=None):
            seen.append(threading.current_thread() is threading.main_thread())
            done.set()
            return "answer"

        with patch.object(main.tutor_agent, "answer", side_effect=answer):
            self.post(line_body(event_id="01HBACKGROUND"))
            self.assertTrue(done.wait(5))
            deadline = time.monotonic() + 5
            while not self.pushes and time.monotonic() < deadline:  # let the background push finish
                time.sleep(0.01)
        self.assertEqual(seen, [False])
        self.assertEqual([m.text for m in self.pushes[0].messages], ["answer"])


class MessengerChannelTest(unittest.TestCase):
    def setUp(self):
        MESSENGER_CH._processed_message_ids.clear()
        self.addCleanup(MESSENGER_CH._processed_message_ids.clear)
        self.client = main.app.test_client()
        self.sent = []
        original = (MESSENGER_CH._reply_generator, MESSENGER_CH._background_executor)
        self.addCleanup(lambda: MESSENGER_CH.configure_messenger_handler(
            reply_generator=original[0], executor=original[1]))
        MESSENGER_CH.configure_messenger_handler(reply_generator=original[0], executor=ImmediateExecutor())

        def fake_urlopen(request, timeout=None):
            self.sent.append((request.full_url, json.loads(request.data.decode("utf-8")), timeout))
            return type("R", (), {"status": 200, "__enter__": lambda s: s, "__exit__": lambda s, *a: False})()

        for patcher in (patch("urllib.request.urlopen", fake_urlopen),
                        patch.dict(os.environ, {"MESSENGER_ENABLED": "true", "MESSENGER_PAGE_ACCESS_TOKEN": "fake-page-token"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def post(self, payload, signature=None):
        body = json.dumps(payload).encode("utf-8")
        return self.client.post("/webhook/messenger", data=body, content_type="application/json",
                                headers={"X-Hub-Signature-256": messenger_signature(body) if signature is None else signature})

    @staticmethod
    def payload(text="What is RAG?", mid="mid-1", sender="psid-1"):
        message = {"text": text}
        if mid is not None:
            message["mid"] = mid
        return {"object": "page", "entry": [{"messaging": [{"sender": {"id": sender}, "message": message}]}]}

    def texts(self):
        return [(body["recipient"]["id"], body["message"]["text"]) for _, body, _ in self.sent]

    def test_verification_contract(self):
        ok = self.client.get(f"/webhook/messenger?hub.mode=subscribe&hub.verify_token={VERIFY_TOKEN}&hub.challenge=c-1")
        self.assertEqual((ok.status_code, ok.get_data(as_text=True)), (200, "c-1"))
        for query in (f"hub.mode=unsubscribe&hub.verify_token={VERIFY_TOKEN}&hub.challenge=c",
                      "hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=c", ""):
            with self.subTest(query=query):
                response = self.client.get(f"/webhook/messenger?{query}")
                self.assertEqual((response.status_code, response.get_data(as_text=True)), (403, "Forbidden"))

    def test_disabled_channel_is_404_for_both_methods(self):
        with patch.dict(os.environ, {"MESSENGER_ENABLED": "false"}):
            self.assertEqual(self.client.get("/webhook/messenger").status_code, 404)
            self.assertEqual(self.post(self.payload()).status_code, 404)
        self.assertEqual(self.sent, [])

    def test_bad_signature_is_403_and_sends_nothing(self):
        with patch.object(main.tutor_agent, "answer") as answer:
            self.assertEqual(self.post(self.payload(), signature="sha256=bad").status_code, 403)
            self.assertEqual(self.post(self.payload(), signature="").status_code, 403)
        answer.assert_not_called()
        self.assertEqual(self.sent, [])

    def test_signed_text_sends_processing_then_tutor_answer(self):
        with TelemetryCapture() as telemetry, \
             patch.object(main.tutor_agent, "answer", return_value="RAG answer") as answer:
            response = self.post(self.payload())
            events = telemetry.events()
        self.assertEqual((response.status_code, response.get_data(as_text=True)), (200, "OK"))
        answer.assert_called_once_with("What is RAG?", user_id="messenger:psid-1")
        self.assertEqual(self.texts(), [("psid-1", "助教正在努力思考中..."), ("psid-1", "RAG answer")])
        self.assertTrue(all(url.startswith("https://graph.facebook.com/v20.0/me/messages?") for url, _, _ in self.sent))
        self.assertEqual({timeout for _, _, timeout in self.sent}, {20})
        self.assertEqual({e["entrypoint"] for e in events}, {"messenger"})

    def test_duplicate_mid_is_processed_once_and_missing_mid_is_never_deduped(self):
        with patch.object(main.tutor_agent, "answer", return_value="answer") as answer:
            self.post(self.payload(mid="dup"))
            self.post(self.payload(mid="dup"))
            self.assertEqual(answer.call_count, 1)
            self.post(self.payload(mid=None))
            self.post(self.payload(mid=None))
            self.assertEqual(answer.call_count, 3)
        self.assertEqual(MESSENGER_CH.MESSAGE_DEDUPLICATION_TTL_SECONDS, 600)

    def test_non_text_events_are_acknowledged_without_sending(self):
        payload = {"object": "page", "entry": [{"messaging": [
            {"sender": {"id": "psid-1"}, "message": {"text": "echo", "is_echo": True}},
            {"sender": {"id": "psid-1"}, "message": {"attachments": [{"type": "image"}]}},
            {"sender": {"id": "psid-1"}, "read": {"watermark": 1}},
        ]}]}
        self.assertEqual(self.post(payload).status_code, 200)
        self.assertEqual(self.post({"object": "user"}).status_code, 200)
        self.assertEqual(self.sent, [])

    def test_tutor_failure_and_long_answers(self):
        with patch.object(main.tutor_agent, "answer", side_effect=RuntimeError("boom")):
            self.post(self.payload(mid="err"))
        self.assertEqual(self.texts()[-1], ("psid-1", main.ERROR_FALLBACK_RESPONSE))
        with patch.object(main.tutor_agent, "answer", return_value="字" * 5000):
            self.post(self.payload(mid="long"))
        self.assertTrue(self.texts()[-1][1].endswith("（回覆已因 LINE 單則訊息長度限制截斷）"))

    def test_handler_exception_is_still_acknowledged(self):
        with patch.object(MESSENGER_CH, "handle_messenger_event", side_effect=RuntimeError("boom")):
            response = self.post(self.payload())
        self.assertEqual((response.status_code, response.get_data(as_text=True)), (200, "OK"))


class WebChatChannelTest(unittest.TestCase):
    def setUp(self):
        WEB_CH.web_chat_rate_limits.clear()
        self.addCleanup(WEB_CH.web_chat_rate_limits.clear)
        self.client = main.app.test_client()

    def chat(self, payload=None, **kwargs):
        return self.client.post("/web-chat", json=payload, **kwargs)

    def test_validation_contract(self):
        with patch.object(main.tutor_agent, "answer") as answer:
            cases = [
                (self.chat({"message": "   "}), 400, {"reply": "請先輸入一個想討論的 AI 學習問題。"}),
                (self.chat({"message": 3}), 400, {"reply": "請先輸入一個想討論的 AI 學習問題。"}),
                (self.chat(["not", "a", "dict"]), 400, {"reply": "請先輸入一個想討論的 AI 學習問題。"}),
                (self.client.post("/web-chat", data="x", content_type="text/plain"), 400,
                 {"reply": "請先輸入一個想討論的 AI 學習問題。"}),
                (self.chat({"message": "A" * 3001}), 400, {"reply": "問題內容過長，請縮短後再試。"}),
                (self.chat({"message": "What is RAG?", "skill_id": ""}), 400, {"error": "unsupported_skill"}),
            ]
            for response, status, body in cases:
                with self.subTest(body=body):
                    self.assertEqual((response.status_code, response.json), (status, body))
        answer.assert_not_called()

    def test_success_is_untruncated_and_stateless(self):
        with patch.object(main.tutor_agent, "answer", return_value="字" * 5000) as answer:
            response = self.chat({"message": "What is RAG?", "user_id": "spoofed"})
        self.assertEqual((response.status_code, response.json), (200, {"reply": "字" * 5000}))
        answer.assert_called_once_with("What is RAG?", user_id=None)

    def test_tutor_failure_returns_error_fallback_with_200(self):
        with patch.object(main.tutor_agent, "answer", side_effect=RuntimeError("boom")):
            response = self.chat({"message": "What is RAG?"})
        self.assertEqual((response.status_code, response.json), (200, {"reply": main.ERROR_FALLBACK_RESPONSE}))

    def test_rate_limit_is_per_first_forwarded_ip_with_sliding_window(self):
        headers = {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
        with patch.object(main.tutor_agent, "answer", return_value="ok"):
            statuses = [self.chat({"message": "What is RAG?"}, headers=headers).status_code for _ in range(21)]
            other = self.chat({"message": "What is RAG?"}, headers={"X-Forwarded-For": "198.51.100.1"})
        self.assertEqual(statuses, [200] * 20 + [429])
        self.assertEqual(other.status_code, 200)
        self.assertEqual(len(WEB_CH.web_chat_rate_limits["203.0.113.7"]), 20)
        limited = self.chat({"message": "What is RAG?"}, headers=headers)
        self.assertEqual((limited.status_code, limited.json), (429, {"error": "rate_limit_exceeded"}))
        WEB_CH.web_chat_rate_limits["203.0.113.7"] = [time.monotonic() - 61] * 20
        with patch.object(main.tutor_agent, "answer", return_value="ok"):
            self.assertEqual(self.chat({"message": "What is RAG?"}, headers=headers).status_code, 200)
        self.assertEqual((WEB_CH.TUTOR_API_RATE_LIMIT_REQUESTS, WEB_CH.TUTOR_API_RATE_LIMIT_WINDOW_SECONDS,
                          WEB_CH.TUTOR_API_MAX_QUESTION_LENGTH), (20, 60, 3000))

    def test_check_order_validation_then_rate_limit_then_skill(self):
        WEB_CH.web_chat_rate_limits["127.0.0.1"] = [time.monotonic()] * 20
        self.assertEqual(self.chat({"message": ""}).status_code, 400)
        self.assertEqual(self.chat({"message": "A" * 3001}).status_code, 400)
        self.assertEqual(self.chat({"message": "ok", "skill_id": "x"}).status_code, 429)

    def test_telemetry_for_success_and_rejections(self):
        with TelemetryCapture() as telemetry, patch.object(main.tutor_agent, "answer", return_value="ok"):
            self.chat({"message": "What is RAG?"})
            self.chat({"message": ""})
            WEB_CH.web_chat_rate_limits["127.0.0.1"] = [time.monotonic()] * 20
            self.chat({"message": "What is RAG?"})
            events = telemetry.events()
        requests = {}
        for event in events:
            requests.setdefault(event["request_id"], []).append(event)
        success, invalid, limited = requests.values()
        self.assertEqual(success[0]["event"], "request_received")
        self.assertEqual((success[0]["route"], success[0]["user_scope"], success[0]["entrypoint"],
                          success[0]["question_length"]), ("/web-chat", "anonymous", "web_chat", 12))
        self.assertEqual(success[-1]["event"], "request_completed")
        self.assertEqual([(e["event"], e["status"], e["error_category"]) for e in invalid],
                         [("request_received", "received", None), ("request_validated", "error", "validation_error"),
                          ("request_failed", "error", "validation_error")])
        self.assertEqual([e["error_category"] for e in limited[1:]], ["rate_limit_error", "rate_limit_error"])


class GuardCharacterizationStillHoldsTest(unittest.TestCase):
    def test_ipas_question_over_web_chat_is_still_guard_rejected(self):
        with patch.object(main.tutor_agent, "answer") as answer:
            response = main.app.test_client().post("/web-chat", json={"message": "CIA Triad 是什麼"},
                                                   headers={"X-Forwarded-For": "192.0.2.10"})
        self.assertEqual(response.status_code, 200)
        answer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
