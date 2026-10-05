"""R6: learner-state and telemetry persistence boundaries.

The behaviour-pinning tests at the top were written and passing against the
pre-R6 code (module-level dictionaries in memory/conversation_context.py and
the inline JSONL writer in runtime_telemetry.py) before the extraction.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import runtime_telemetry
import tests
from memory.conversation_context import (
    MAX_CONTEXT_TURNS,
    add_message,
    add_turn,
    build_contextual_prompt,
    build_user_prompt,
    clear_active_skill,
    clear_context,
    format_recent_context,
    get_active_skill,
    get_recent_context,
    set_active_skill,
)

ROOT = Path(__file__).resolve().parents[1]


class LearnerStateSemanticsTest(unittest.TestCase):
    def setUp(self):
        clear_context()
        self.addCleanup(clear_context)

    def test_missing_identity_is_never_stored(self):
        for user_id in (None, ""):
            add_turn(user_id, "q", "a")
            set_active_skill(user_id, "hungyi_lee")
            self.assertEqual(get_recent_context(user_id), [])
            self.assertIsNone(get_active_skill(user_id))
            clear_active_skill(user_id)  # no error
        self.assertEqual(build_contextual_prompt("prompt", None), "prompt")

    def test_messages_are_filtered_stripped_and_trimmed(self):
        add_message("u", "system", "ignored")
        add_message("u", "user", "   ")
        add_message("u", "user", None)
        add_message("u", "user", "  question  ")
        self.assertEqual(get_recent_context("u"), [{"role": "user", "content": "question"}])
        for index in range(MAX_CONTEXT_TURNS * 3):
            add_message("u", "assistant", f"m{index}")
        context = get_recent_context("u")
        self.assertEqual(MAX_CONTEXT_TURNS, 6)
        self.assertEqual(len(context), 12)
        self.assertEqual(context[0]["content"], f"m{MAX_CONTEXT_TURNS * 3 - 12}")

    def test_reads_return_copies(self):
        add_turn("u", "q", "a")
        context = get_recent_context("u")
        context[0]["content"] = "mutated"
        context.append({"role": "user", "content": "extra"})
        self.assertEqual(get_recent_context("u"), [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}])

    def test_state_is_isolated_per_learner_and_cleared_per_learner(self):
        add_turn("a", "qa", "aa")
        add_turn("b", "qb", "ab")
        set_active_skill("a", "skill_a")
        set_active_skill("b", "skill_b")
        set_active_skill("b", "")  # empty skill is ignored
        self.assertEqual((get_active_skill("a"), get_active_skill("b")), ("skill_a", "skill_b"))
        clear_context("a")
        self.assertEqual((get_recent_context("a"), get_active_skill("a")), ([], None))
        self.assertEqual((len(get_recent_context("b")), get_active_skill("b")), (2, "skill_b"))
        clear_active_skill("b")
        self.assertEqual((len(get_recent_context("b")), get_active_skill("b")), (2, None))
        clear_context()
        self.assertEqual(get_recent_context("b"), [])

    def test_contextual_prompt_format_is_unchanged(self):
        add_turn("u", "What is Skill?", "Skill is an SOP.")
        self.assertEqual(
            build_user_prompt("And MCP?", "u"),
            "最近對話：\nUser: What is Skill?\nAssistant: Skill is an SOP.\n\n"
            "請把最近對話只當作短期上下文，用來理解學生是否在承接上一輪。"
            "不要把它當成永久記憶，也不要因此改變工具或 Skill 的選擇。\n\n"
            "學生問題：And MCP?",
        )
        self.assertEqual(format_recent_context([]), "")

    def test_tutor_records_turns_and_honours_active_skill(self):
        with patch.object(main.tutor_agent, "_general_teaching_answer", return_value="general"):
            main.tutor_agent.answer("今天天氣如何", user_id="learner-1")
        self.assertEqual(get_recent_context("learner-1"),
                         [{"role": "user", "content": "今天天氣如何"}, {"role": "assistant", "content": "general"}])
        set_active_skill("learner-1", "ipas_cybersecurity")
        reply = main.tutor_agent.answer("隨便一句話", user_id="learner-1")
        self.assertIn("目前支援", reply)  # routed by the active skill, not by keywords
        self.assertEqual(main.generate_tutor_answer("/離開", user_id="learner-1"), main.LEGACY_EXIT_MESSAGE)
        self.assertIsNone(get_active_skill("learner-1"))


class TelemetryCompatibilityTest(unittest.TestCase):
    def test_jsonl_bytes_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "telemetry.jsonl"
            runtime_telemetry.write_runtime_telemetry(
                {"timestamp": "2026-10-05T00:00:00Z", "event": "e1", "entrypoint": "line", "unknown": "dropped",
                 "provider": "openai", "input_tokens": 3, "route": "路由"},
                path=path,
            )
            with patch.object(runtime_telemetry, "utc_timestamp", return_value="2026-10-05T00:00:01Z"):
                runtime_telemetry.write_runtime_telemetry({"event": "e2"}, path=path)
            data = path.read_bytes()
        fields = runtime_telemetry.TELEMETRY_FIELDS
        first = {field: None for field in fields}
        first.update(timestamp="2026-10-05T00:00:00Z", event="e1", entrypoint="line", provider="openai",
                     input_tokens=3, route="路由")
        second = {field: None for field in fields}
        second.update(timestamp="2026-10-05T00:00:01Z", event="e2")
        expected = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in (first, second))
        # The file is opened in text mode, so lines end with the platform separator (CRLF on
        # Windows, LF on Linux/Render). Pre-R6 behaviour, preserved deliberately.
        self.assertEqual(data, expected.replace("\n", os.linesep).encode("utf-8"))
        self.assertIn('"route":"路由"'.encode("utf-8"), data)

    def test_correlated_events_keep_order_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "t.jsonl"
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path):
                context = runtime_telemetry.create_request_context("web_chat", user_scope="anonymous",
                                                                   question_length=5, request_id="req-1")
                runtime_telemetry.record_request_received(context, route="/web-chat")
                context = runtime_telemetry.record_request_validation(context, status="success")
                with runtime_telemetry.activate_request_context(context):
                    runtime_telemetry.emit_runtime_event("guard_evaluated", status="success", guard_reason="learning")
                runtime_telemetry.record_request_terminal(context, status="success")
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["event"] for e in events],
                         ["request_received", "request_validated", "guard_evaluated", "request_completed"])
        self.assertEqual({(e["request_id"], e["entrypoint"], e["user_scope"], e["schema_version"]) for e in events},
                         {("req-1", "web_chat", "anonymous", 2)})
        self.assertEqual(events[0]["route"], "/web-chat")

    def test_write_failures_are_logged_and_swallowed(self):
        with tempfile.TemporaryDirectory() as directory:
            blocked = Path(directory) / "file"
            blocked.write_text("x", encoding="utf-8")
            with self.assertLogs("runtime_telemetry", level="ERROR") as logs:
                runtime_telemetry.write_runtime_telemetry({"event": "e"}, path=blocked / "t.jsonl")
        self.assertIn("Runtime telemetry write failed", logs.output[0])

    def test_path_comes_from_environment_with_unchanged_default(self):
        script = "import runtime_telemetry as t; print(t.TELEMETRY_PATH.as_posix()); print(t.DEFAULT_TELEMETRY_PATH.as_posix())"
        for env_value, expected in (("custom/telemetry.jsonl", "custom/telemetry.jsonl"), ("", "data/runtime_telemetry.jsonl")):
            env = {**os.environ, "RUNTIME_TELEMETRY_PATH": env_value}
            output = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True,
                                    text=True, check=True).stdout.split()
            self.assertEqual(output, [expected, "data/runtime_telemetry.jsonl"])

    def test_suite_isolation_points_at_a_temporary_file(self):
        self.assertNotEqual(Path(runtime_telemetry.TELEMETRY_PATH).resolve(),
                            (ROOT / runtime_telemetry.DEFAULT_TELEMETRY_PATH).resolve())

    def test_dashboard_aggregation_reads_the_jsonl_file(self):
        records = [
            {"schema_version": 2, "timestamp": "2026-10-01T00:00:00Z", "request_id": "r1", "event": "request_received",
             "entrypoint": "web_chat", "status": "received"},
            {"schema_version": 2, "timestamp": "2026-10-01T00:00:01Z", "request_id": "r1", "event": "provider_attempted",
             "entrypoint": "web_chat", "provider": "openai", "status": "success", "total_tokens": 7},
            {"schema_version": 2, "timestamp": "2026-10-01T00:00:02Z", "request_id": "r1", "event": "request_completed",
             "entrypoint": "web_chat", "status": "success", "latency_ms": 12},
            {"timestamp": "2026-09-30T00:00:00Z", "entrypoint": "line", "provider": "openai", "status": "success"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "t.jsonl"
            path.write_text("".join(json.dumps(r) + "\n" for r in records) + "not json\n", encoding="utf-8")
            summary = runtime_telemetry.aggregate_runtime_telemetry("2026-10", path=path)
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path), \
                 patch.dict(os.environ, {"DASHBOARD_API_KEY": "dash-key"}):
                response = main.app.test_client().get("/api/runtime/telemetry?month=2026-10",
                                                      headers={"X-Dashboard-Key": "dash-key"})
        self.assertEqual((summary["month"], summary["total_requests"], summary["success"], summary["total_tokens"]),
                         ("2026-10", 1, 1, 7))
        self.assertEqual((response.status_code, response.get_json()), (200, summary))


class LearnerStateStoreInterfaceTest(unittest.TestCase):
    def test_interface_is_limited_to_existing_operations(self):
        from memory.learner_state import LearnerStateStore

        methods = {name for name in vars(LearnerStateStore) if not name.startswith("_")}
        self.assertEqual(methods, {"get_recent_messages", "append_message", "get_active_skill",
                                   "set_active_skill", "clear_active_skill", "clear"})

    def test_in_memory_store_matches_the_module_semantics(self):
        from memory.learner_state import InMemoryLearnerStateStore, LearnerStateStore

        store = InMemoryLearnerStateStore()
        self.assertIsInstance(store, LearnerStateStore)
        for user_id in (None, ""):
            store.append_message(user_id, "user", "q")
            store.set_active_skill(user_id, "s")
            self.assertEqual((store.get_recent_messages(user_id), store.get_active_skill(user_id)), ([], None))
        store.append_message("u", "system", "ignored")
        store.append_message("u", "user", "  q  ")
        for index in range(20):
            store.append_message("u", "assistant", f"a{index}")
        messages = store.get_recent_messages("u")
        self.assertEqual((len(messages), messages[0]["content"], messages[-1]["content"]), (12, "a8", "a19"))
        messages[0]["content"] = "mutated"
        self.assertEqual(store.get_recent_messages("u")[0]["content"], "a8")
        store.set_active_skill("u", "skill")
        store.set_active_skill("v", "other")
        store.clear("u")
        self.assertEqual((store.get_recent_messages("u"), store.get_active_skill("u"), store.get_active_skill("v")),
                         ([], None, "other"))
        store.clear()
        self.assertIsNone(store.get_active_skill("v"))

    def test_stores_are_independent_and_the_tutor_uses_the_one_it_is_given(self):
        from agents.tutor_agent import TutorAgent
        from memory.learner_state import InMemoryLearnerStateStore, get_learner_state_store

        clear_context()
        self.addCleanup(clear_context)
        isolated = InMemoryLearnerStateStore()
        agent = TutorAgent(lambda system, user: "answer", skill_runtime=main.tutor_agent.skill_runtime,
                           learner_state=isolated)
        agent.answer("今天天氣如何", user_id="learner-x")
        self.assertEqual(len(isolated.get_recent_messages("learner-x")), 2)
        self.assertEqual(get_recent_context("learner-x"), [])
        self.assertIs(main.tutor_agent.learner_state, get_learner_state_store())

    def test_only_learner_state_lives_in_the_store(self):
        from memory.learner_state import InMemoryLearnerStateStore

        self.assertEqual(set(vars(InMemoryLearnerStateStore())),
                         {"max_context_turns", "_conversation_context", "_active_skills", "_lock"})


class ModuleLevelStateInventoryTest(unittest.TestCase):
    """Every module-level mutable container in production code, classified (R6).

    A new one fails this test until it is classified here. Learner state (A) may only
    live in memory/learner_state.py.
    """

    INVENTORY = {
        ("app/channels/line.py", "processed_events"): "B channel: LINE dedupe",
        ("app/channels/messenger.py", "_processed_message_ids"): "B channel: Messenger dedupe",
        ("app/channels/web_chat.py", "web_chat_rate_limits"): "B channel: Web Chat rate limit",
        ("llm/gateway.py", "model_clients"): "B infrastructure: provider client cache",
    }
    MUTABLE_CALLS = {"dict", "list", "set", "defaultdict", "OrderedDict", "deque"}
    EXCLUDED_DIRS = {"tests", "venv", ".venv", "tmp", "hung-yi-lee-skill", "__pycache__", ".git"}

    def module_level_containers(self):
        import ast

        found = set()
        for path in ROOT.rglob("*.py"):
            relative = path.relative_to(ROOT)
            if set(relative.parts) & self.EXCLUDED_DIRS:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                targets, value = [], None
                if isinstance(node, ast.Assign):
                    targets, value = node.targets, node.value
                elif isinstance(node, ast.AnnAssign) and node.value is not None:
                    targets, value = [node.target], node.value
                is_container = isinstance(value, (ast.Dict, ast.List, ast.Set, ast.DictComp, ast.ListComp, ast.SetComp)) or (
                    isinstance(value, ast.Call) and getattr(value.func, "id", getattr(value.func, "attr", None)) in self.MUTABLE_CALLS)
                for target in targets:
                    # UPPER_CASE names are constants by convention; dunders (__all__) are not state.
                    if (is_container and isinstance(target, ast.Name) and not target.id.isupper()
                            and not target.id.startswith("__")):
                        found.add((relative.as_posix(), target.id))
        return found

    def test_no_unclassified_module_level_state(self):
        self.assertEqual(self.module_level_containers(), set(self.INVENTORY))

    def test_conversation_module_holds_no_state(self):
        import memory.conversation_context as module

        self.assertFalse({"_conversation_context", "_active_skills", "_context_lock"} & set(vars(module)))


class TelemetrySinkTest(unittest.TestCase):
    def test_default_sink_is_the_jsonl_file_at_the_configured_path(self):
        sink = runtime_telemetry.get_telemetry_sink()
        self.assertIsInstance(sink, runtime_telemetry.JsonlTelemetrySink)
        self.assertIsInstance(sink, runtime_telemetry.TelemetrySink)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "t.jsonl"
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path):
                self.assertEqual(sink.path, path)
                runtime_telemetry.write_runtime_telemetry({"timestamp": "2026-10-05T00:00:00Z", "event": "e"})
                self.assertEqual([r["event"] for r in sink.read_records()], ["e"])

    def test_sink_can_be_replaced_without_changing_record_shape(self):
        class MemorySink:
            def __init__(self):
                self.records = []

            def write(self, record):
                self.records.append(record)

        memory_sink = MemorySink()
        previous = runtime_telemetry.set_telemetry_sink(memory_sink)
        try:
            context = runtime_telemetry.create_request_context("line", user_scope="channel_user", request_id="r-9")
            runtime_telemetry.record_request_received(context)
        finally:
            self.assertIs(runtime_telemetry.set_telemetry_sink(previous), memory_sink)
        (record,) = memory_sink.records
        self.assertEqual((record["event"], record["request_id"], record["entrypoint"], record["schema_version"]),
                         ("request_received", "r-9", "line", 2))
        self.assertIs(runtime_telemetry.get_telemetry_sink(), previous)

    def test_no_external_network_attempts(self):
        before = list(tests.BLOCKED_NETWORK_ATTEMPTS)
        main.generate_tutor_answer("今天天氣如何", user_id="r6-network")
        runtime_telemetry.aggregate_runtime_telemetry("2026-10")
        self.assertEqual(tests.BLOCKED_NETWORK_ATTEMPTS, before)


if __name__ == "__main__":
    unittest.main()
