"""Capture observable Knowledge Pack behaviour (module API + HTTP) as a comparable snapshot.

Run `python -m tests.knowledge_pack_snapshot` to regenerate
tests/fixtures/knowledge_pack_snapshot.json. It was first generated on the
pre-R4 code; tests compare the current behaviour against it.
"""

import hashlib
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "knowledge_pack_snapshot.json"

PACKS = {
    "ipas_ai_application_planner": ("/ipas", "/api/ipas/answer"),
    "ipas_net_zero_planner": ("/ipas/net-zero-planner", "/api/ipas/net-zero-planner/answer"),
    "ipas_cybersecurity": ("/ipas/cybersecurity", "/api/ipas/cybersecurity/answer"),
}


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _modules():
    import main

    return {
        "ipas_ai_application_planner": main.ipas_ai_skill,
        "ipas_net_zero_planner": main.ipas_net_zero_skill,
        "ipas_cybersecurity": main.ipas_cyber_skill,
    }


def public_questions(pack_id, module):
    if pack_id == "ipas_cybersecurity":
        return [q for chapter in module.get_chapters() for q in module.get_questions(chapter["chapter_id"])]
    return module.get_questions()


def capture() -> dict:
    import main

    client = main.app.test_client()
    snapshot = {}
    for pack_id, module in _modules().items():
        page_url, answer_url = PACKS[pack_id]
        chapters = module.get_chapters()
        questions = public_questions(pack_id, module)
        grading = {
            q["question_id"]: {option: module.submit_answer(q["question_id"], option) for option in "ABCD"}
            for q in questions
        }
        http_grading = {
            q["question_id"]: {
                option: (lambda r: [r.status_code, r.get_json()])(
                    client.post(answer_url, json={"question_id": q["question_id"], "answer": option}))
                for option in "ABCD"
            }
            for q in questions
        }
        first_id = questions[0]["question_id"]
        validation_cases = {
            "not_json": dict(data="x", content_type="text/plain"),
            "json_list": dict(json=["x"]),
            "missing_question_id": dict(json={"answer": "A"}),
            "blank_question_id": dict(json={"question_id": "  ", "answer": "A"}),
            "missing_answer": dict(json={"question_id": first_id}),
            "invalid_answer": dict(json={"question_id": first_id, "answer": "E"}),
            "numeric_answer": dict(json={"question_id": first_id, "answer": 1}),
            "unknown_question": dict(json={"question_id": "NO-SUCH-Q999", "answer": "A"}),
            "lowercase_and_spaces": dict(json={"question_id": f"  {first_id.lower()} ", "answer": " b "}),
        }
        validation = {}
        for name, kwargs in validation_cases.items():
            response = client.post(answer_url, **kwargs)
            validation[name] = [response.status_code, response.get_json()]
        page = client.get(page_url)
        snapshot[pack_id] = {
            "course_info": module.get_course_info(),
            "chapter_ids": [c["chapter_id"] for c in chapters],
            "chapters_digest": _digest(chapters),
            "chapter_detail_digests": {c["chapter_id"]: _digest(module.get_chapter(c["chapter_id"])) for c in chapters},
            "question_ids": [q["question_id"] for q in questions],
            "public_questions_digest": _digest(questions),
            "grading_digest": _digest(grading),
            "http_grading_digest": _digest(http_grading),
            "http_validation": validation,
            "sources_digest": _digest(module.get_sources()),
            "page": [page.status_code, hashlib.sha256(page.data).hexdigest()],
        }
    return snapshot


if __name__ == "__main__":
    import tests  # noqa: F401  (test isolation and network guard)

    FIXTURE.parent.mkdir(exist_ok=True)
    FIXTURE.write_text(json.dumps(capture(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE}")
