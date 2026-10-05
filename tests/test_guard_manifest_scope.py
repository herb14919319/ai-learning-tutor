"""R3: enabled chat-skill manifests widen the scope guard; nothing else may."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import runtime_telemetry
import tests
from router_guard import (
    BLOCKED_REDIRECT_MESSAGE,
    CLARIFICATION_MESSAGE,
    classify_intent,
    manifest_scope_terms,
    route_learning_boundary,
)
from skills.discovery import DiscoveryResult, discover_skills
from skills.registry import DISCOVERY_RESULT, get_runtime
from skills.runtime import SkillManifest

FLAG_OFF = {"GUARD_USE_MANIFEST_TERMS": "false"}


def manifest_file(directory, **overrides):
    payload = {
        "schema_version": 1,
        "skill_id": directory.name.replace("-", "_"),
        "display_name": "Probe",
        "status": "active",
        "skill_type": "runtime",
        "entrypoint": "skills.r3_probe_missing_module",
        "keywords": ["量子糾纏探針"],
    }
    payload.update(overrides)
    directory.mkdir()
    (directory / "skill.json").write_text(
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def fake_manifest(name, *, keywords=("量子糾纏探針",), enabled=True, status="active", skill_type="runtime"):
    return SkillManifest(name=name, display_name=name, description="", domains=(), keywords=tuple(keywords),
                         capabilities=(), entrypoint=f"skills.{name}", enabled=enabled, status=status,
                         skill_type=skill_type)


class EligibilityRuleTest(unittest.TestCase):
    def test_production_terms_come_only_from_routable_chat_skills(self):
        routable = {m.name for m in DISCOVERY_RESULT.manifests if m.enabled}
        self.assertEqual(routable, {"hungyi_lee", "ipas_ai_application_planner", "ipas_cybersecurity"})
        expected = {t.strip().lower() for m in DISCOVERY_RESULT.manifests if m.name in routable
                    for t in (*m.domains, *m.keywords)}
        self.assertEqual(set(manifest_scope_terms()), expected)
        for web_only in ("ipas_net_zero_planner", "little_tree"):
            manifest = next(m for m in DISCOVERY_RESULT.manifests if m.name == web_only)
            self.assertEqual((manifest.skill_type, manifest.enabled), ("web", False))

    def test_disabled_web_legacy_invalid_and_stray_entries_never_widen_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_file(root / "disabled_probe", status="disabled", keywords=["禁用探針"])
            manifest_file(root / "experimental_probe", status="experimental", keywords=["實驗探針"])
            manifest_file(root / "web_probe", skill_type="web", entrypoint=None, keywords=["網頁探針"])
            manifest_file(root / "legacy_probe", skill_type="legacy", status="disabled", keywords=["遺留探針"])
            manifest_file(root / "unloadable_probe", keywords=["無法載入探針"])
            manifest_file(root / "unknown_field_probe", keywords=["未知欄位探針"], surprise=True)
            manifest_file(root / "bad-id", skill_id="Bad Id", keywords=["錯誤代號探針"])
            (root / "malformed_probe").mkdir()
            (root / "malformed_probe" / "skill.json").write_text("{not json", encoding="utf-8")
            (root / "stray_dir").mkdir()
            (root / "loose.json").write_text(json.dumps({"keywords": ["散落探針"]}), encoding="utf-8")
            result = discover_skills(root)

        self.assertEqual(result.loaded_skills, {})
        self.assertIn("unloadable_probe", result.unavailable)
        self.assertEqual(manifest_scope_terms(result), ())
        for probe in ("禁用探針", "實驗探針", "網頁探針", "遺留探針", "無法載入探針", "未知欄位探針", "錯誤代號探針", "散落探針"):
            with self.subTest(term=probe):
                self.assertEqual(classify_intent(f"請解釋{probe}", scope_terms=manifest_scope_terms(result)), "unknown")

    def test_each_rule_condition_is_required(self):
        loaded = {name: object() for name in ("ok", "disabled", "web", "experimental", "unavailable")}
        result = DiscoveryResult(
            manifests=(
                fake_manifest("ok", keywords=("合格探針", "x", " ")),
                fake_manifest("disabled", keywords=("停用探針",), enabled=False),
                fake_manifest("web", keywords=("網頁探針",), skill_type="web"),
                fake_manifest("experimental", keywords=("實驗探針",), status="experimental"),
                fake_manifest("not_loaded", keywords=("未載入探針",)),
                fake_manifest("unavailable", keywords=("不可用探針",)),
            ),
            loaded_skills=loaded,
            unavailable={"unavailable": "runtime_load_failed"},
            diagnostics=(),
        )
        self.assertEqual(manifest_scope_terms(result), ("合格探針",))  # one-character terms are ignored

    def test_untrusted_metadata_fails_closed_to_static_terms(self):
        class Broken:
            @property
            def manifests(self):
                raise RuntimeError("corrupt discovery state")

        with self.assertLogs("router_guard", level="ERROR"):
            self.assertEqual(manifest_scope_terms(Broken()), ())
        with patch("skills.registry.DISCOVERY_RESULT", Broken()), self.assertLogs("router_guard", level="ERROR"):
            self.assertFalse(route_learning_boundary("CIA Triad 是什麼").allowed)
            self.assertTrue(route_learning_boundary("Transformer 是什麼").allowed)  # static terms still apply


class GuardBehaviourTest(unittest.TestCase):
    def setUp(self):
        self.runtime = get_runtime()

    def route(self, text):
        return self.runtime.route(self.runtime.normalize_request(text))["skill"]

    def test_supported_ipas_cybersecurity_query_reaches_its_skill_end_to_end(self):
        with patch.object(main.tutor_agent, "_general_teaching_answer") as general:
            reply = main.generate_tutor_answer("CIA Triad 是什麼", user_id="r3-user")
        general.assert_not_called()
        self.assertTrue(reply.startswith("CIA 三目標總覽："))  # deterministic skill reply, no LLM
        self.assertIn("審核狀態", reply)
        self.assertIn("iPAS_資訊安全管理概論_PART_I.pdf", reply)

    def test_net_zero_stays_out_of_chat_scope_because_it_is_web_only(self):
        for text in ("淨零排放是什麼", "碳盤查怎麼做"):
            with self.subTest(text=text):
                self.assertEqual(self.route(text), "general")
                self.assertFalse(route_learning_boundary(text).allowed)

    def test_ai_application_planner_follows_its_manifest(self):
        for text in ("L111 考什麼", "HITL 跟 HOTL 差在哪", "AGI 是什麼"):
            with self.subTest(text=text):
                self.assertTrue(route_learning_boundary(text).allowed)
                self.assertEqual(self.route(text), "ipas_ai_application_planner")
        with patch.dict(os.environ, FLAG_OFF):  # all three were rejected before R3
            for text in ("L111 考什麼", "HITL 跟 HOTL 差在哪", "AGI 是什麼"):
                self.assertFalse(route_learning_boundary(text).allowed)

    def test_off_topic_casual_and_tool_misuse_are_still_rejected(self):
        cases = {
            "今天晚餐吃什麼": ("unknown", CLARIFICATION_MESSAGE),
            "你好": ("casual_chat", BLOCKED_REDIRECT_MESSAGE),
            "幫我畫一張 CIA Triad 的海報": ("tool_misuse", BLOCKED_REDIRECT_MESSAGE),
            "用 iPAS 的口吻寫情書": ("tool_misuse", BLOCKED_REDIRECT_MESSAGE),
            "台北明天會下雨嗎": ("unknown", CLARIFICATION_MESSAGE),
        }
        for text, (intent, response) in cases.items():
            with self.subTest(text=text):
                guard = route_learning_boundary(text)
                self.assertEqual((guard.allowed, guard.intent, guard.response), (False, intent, response))

    def test_already_supported_ai_queries_are_unchanged(self):
        queries = ("什麼是 Transformer？", "RAG 跟 fine-tune 差在哪？", "初學者要怎麼學 LLM？",
                   "AI Agent 怎麼設計？", "我想學生成式AI", "how should i learn machine learning")
        for text in queries:
            with self.subTest(text=text):
                on = (route_learning_boundary(text), self.route(text))
                with patch.dict(os.environ, FLAG_OFF):
                    off = (route_learning_boundary(text), self.route(text))
                self.assertEqual(on, off)
                self.assertTrue(on[0].allowed)


class GuardTelemetryTest(unittest.TestCase):
    def events_for(self, text, env=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.jsonl"
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path), patch.dict(os.environ, env or {}):
                main.generate_tutor_answer(text, entrypoint="web_chat")
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_newly_supported_query_no_longer_records_guard_rejection(self):
        before = self.events_for("CIA Triad 是什麼", FLAG_OFF)
        after = self.events_for("CIA Triad 是什麼")
        guard_before = next(e for e in before if e["event"] == "guard_evaluated")
        guard_after = next(e for e in after if e["event"] == "guard_evaluated")
        self.assertEqual((guard_before["status"], guard_before["guard_result"], guard_before["error_category"]),
                         ("rejected", "rejected", "guard_rejected"))
        self.assertEqual((guard_after["status"], guard_after["guard_result"], guard_after["guard_reason"],
                          guard_after["error_category"]), ("success", "allowed", "learning", None))
        self.assertEqual([(e["event"], e["route"], e["skill_id"]) for e in after if e["event"] in ("route_selected", "skill_selected")],
                         [("route_selected", "ipas_cybersecurity", None), ("skill_selected", None, "ipas_cybersecurity")])
        self.assertEqual((before[-1]["status"], before[-1]["error_category"]), ("rejected", "guard_rejected"))
        self.assertEqual((after[-1]["event"], after[-1]["status"]), ("request_completed", "success"))
        for event in before + after:
            self.assertEqual(list(event), list(runtime_telemetry.TELEMETRY_FIELDS))

    def test_off_topic_telemetry_is_identical_with_flag_on_or_off(self):
        strip = lambda events: [{k: v for k, v in e.items() if k not in ("timestamp", "request_id", "latency_ms")}
                                for e in events]
        self.assertEqual(strip(self.events_for("今天晚餐吃什麼")), strip(self.events_for("今天晚餐吃什麼", FLAG_OFF)))


class NoNetworkTest(unittest.TestCase):
    def test_guard_and_skill_path_make_no_external_network_attempts(self):
        before = list(tests.BLOCKED_NETWORK_ATTEMPTS)
        for text in ("CIA Triad 是什麼", "資訊安全三目標", "L111 考什麼"):
            route_learning_boundary(text)
        main.generate_tutor_answer("風險評鑑流程", user_id="r3-network")
        self.assertEqual(tests.BLOCKED_NETWORK_ATTEMPTS, before)


if __name__ == "__main__":
    unittest.main()
