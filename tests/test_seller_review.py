"""The seller-review gate (scripts/seller_review.py): YuTao sees our numbers about Insight and PriorSeal
before they are public (alexar76/aimarket-hub#23, 2026-11-13). What these tests defend: a passage with
his numbers never passes without his answer, and a check that cannot ask him blocks instead of passing."""

import importlib.util
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("seller_review", ROOT / "scripts" / "seller_review.py")
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)

REG = sr.load_registry()
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
YUTAO = REG["sellers"]["yutao"]


def test_the_id_matches_the_review_service():
    # Same vector as okx-a2mcp/test/review.test.js: change both or neither.
    assert sr.review_id("yutao", "Insight: 19 of 20.") == "927c321a8244292a36da"


def test_only_paragraphs_that_name_the_seller_and_hold_a_number_are_filed():
    text = """# Who pays for x402

Insight answered 19 of its 20 routes with a 402.

PriorSeal has four GET routes and no request body.

PriorSeal: 4 of 4 listed on   modelmarket.dev.

We counted 134,025 price quotes in total.

The insight here is that nobody pays.
"""
    [(seller, excerpt)] = sr.find(text, REG)
    assert seller["id"] == "yutao"
    assert excerpt == ("Insight answered 19 of its 20 routes with a 402.\n\n"
                       "PriorSeal: 4 of 4 listed on modelmarket.dev.")


def test_a_text_without_his_names_files_nothing():
    assert sr.find("We counted 134,025 price quotes and 82 paid calls.", REG) == []


class FakeService:
    def __init__(self, decision=None, fail=False):
        self.records, self.decision, self.fail, self.calls = {}, decision, fail, []

    def __call__(self, method, url, body=None):
        self.calls.append((method, url, body))
        if self.fail:
            raise OSError("connection refused")
        if method == "GET":
            rid = url.rsplit("/", 1)[1]
            return (200, self.records[rid]) if rid in self.records else (404, {})
        rid = sr.review_id(body["seller"], body["excerpt"])
        self.records[rid] = {"id": rid, "created_at": sr.iso(NOW), "not_before": body["not_before"],
                             "decision": self.decision, "decided_at": None, "note": ""}
        return 201, self.records[rid]


ITEMS = [(YUTAO, "Insight answered 19 of its 20 routes with a 402.")]


def run(svc, now=NOW, items=ITEMS):
    out = io.StringIO()
    code = sr.review("blog/post", "Post", items, REG, http=svc, now=now, out=out)
    return code, out.getvalue()


def test_a_new_passage_is_filed_with_his_window_and_blocks():
    svc = FakeService()
    code, out = run(svc)
    assert code == 2 and "BLOCKED" in out and "waiting for YuTao" in out
    method, url, body = svc.calls[-1]
    assert method == "POST" and url.endswith("/requests")
    assert body["not_before"] == sr.iso(NOW + timedelta(hours=72))
    assert body["seller"] == "yutao" and body["source"] == "blog/post"


def test_his_ok_lets_it_through_and_his_objection_does_not():
    assert run(FakeService(decision="ok"))[0] == 0
    code, out = run(FakeService(decision="object"))
    assert code == 2 and "objected" in out


def test_silence_is_not_consent_unless_he_agreed():
    svc = FakeService()
    run(svc)
    later = NOW + timedelta(hours=73)
    assert run(svc, now=later)[0] == 2
    agreed = {**YUTAO, "silence_is_consent": True}
    assert run(svc, now=later, items=[(agreed, ITEMS[0][1])])[0] == 0


def test_a_changed_number_is_a_new_request():
    svc = FakeService(decision="ok")
    run(svc)
    code, _ = run(FakeService(), items=[(YUTAO, "Insight answered 18 of its 20 routes with a 402.")])
    assert code == 2


def test_an_unreachable_service_blocks():
    code, out = run(FakeService(fail=True))
    assert code == 3 and "not publishing" in out


def test_a_service_that_answers_with_another_record_blocks():
    def wrong(method, url, body=None):
        return 200, {"id": "0" * 20, "decision": "ok"}
    assert run(wrong)[0] == 3


def test_blog_live_only_skips_posts_scheduled_for_later(tmp_path):
    for slug, until in (("now", None), ("later", "2026-12-01T00:00:00Z")):
        d = tmp_path / slug
        d.mkdir()
        (d / "body.md").write_text("Insight answered 19 of 20.")
        meta = {"title": slug} | ({"embargo_until": until} if until else {})
        (d / "meta.json").write_text(json.dumps(meta))
    live = sr._blog_posts(tmp_path, None, True, NOW)
    assert [s for s, _, _ in live] == ["blog/now"]
    assert [s for s, _, _ in sr._blog_posts(tmp_path, "later", False, NOW)] == ["blog/later"]


def test_scan_reports_without_contacting_anyone(tmp_path, capsys, monkeypatch):
    f = tmp_path / "draft.md"
    f.write_text("PriorSeal: 4 of 4 listed.")
    monkeypatch.setattr(sr, "_http", lambda *a, **k: pytest.fail("scan must not call the service"))
    assert sr.main(["scan", str(f)]) == 2
    assert "YuTao" in capsys.readouterr().out
