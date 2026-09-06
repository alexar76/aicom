"""Regressions for the findings of the 2026-08-29 external code review.

Three were real and are fixed here; a fourth (a Redis wake feedback loop) was found while
checking the third. Each test pins the *behaviour*, not the shape of the fix.
"""

from __future__ import annotations

import asyncio
import threading

import pytest


# ---------------------------------------------------------- sandbox: argv, never a shell


def test_sandbox_command_rejects_a_shell_string():
    from security.docker_sandbox import append_image_and_command

    base = ["docker", "run", "--rm"]
    with pytest.raises(TypeError):
        append_image_and_command(base, "python:3.12-slim", "echo hi; rm -rf /")


def test_sandbox_command_keeps_argv_verbatim_without_a_shell():
    from security.docker_sandbox import append_image_and_command

    argv = ["python3", "-c", "print('a; b')"]
    out = append_image_and_command(["docker", "run"], "img", argv)
    assert out == ["docker", "run", "img", "python3", "-c", "print('a; b')"]
    # No shell anywhere: a metacharacter in an argument is data, not syntax.
    assert "sh" not in out and "-lc" not in out


def test_every_in_repo_caller_passes_argv():
    """The string branch was removed; this fails loudly if someone reintroduces a caller."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    # Our own source only: rglob over the repo root walks node_modules and every venv.
    scanned = [
        f for d in ("security", "web", "orchestrator", "agents", "core", "director")
        for f in (root / d).rglob("*.py")
    ]
    for path in scanned:
        if "worktrees" in path.parts or "node_modules" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name != "append_image_and_command" or len(node.args) < 3:
                continue
            if isinstance(node.args[2], ast.Constant) and isinstance(node.args[2].value, str):
                offenders.append(f"{path}:{node.lineno}")
    assert offenders == []
    assert scanned, "nothing scanned — the source layout moved"


# --------------------------------------------------- analyst: a failed search is not data


def test_failed_search_is_a_status_not_a_result():
    import agents.analyst as analyst

    def _explode(*a, **kw):
        raise RuntimeError("ratelimited by duckduckgo")

    orig = analyst._duckduckgo_search.__globals__.get("DDGS")  # noqa: F841 - documented below
    # The import happens inside the function, so patch the module it imports from.
    import sys
    import types

    fake = types.ModuleType("duckduckgo_search")
    fake.DDGS = _explode
    sys.modules["duckduckgo_search"] = fake
    try:
        outcome = analyst._duckduckgo_search("market size widgets")
    finally:
        sys.modules.pop("duckduckgo_search", None)

    assert outcome.ok is False
    assert outcome.results == []
    # The failure text must never sit where a search hit sits.
    assert "ratelimited" in outcome.error


def test_a_total_search_failure_tells_the_model_it_has_no_evidence(monkeypatch):
    import agents.analyst as analyst

    monkeypatch.setattr(
        analyst,
        "_duckduckgo_search",
        lambda q, max_results=3: analyst.SearchOutcome(ok=False, results=[], error="offline"),
    )
    evidence = analyst._market_search("widget CRM")
    assert evidence.grounding == "none"
    assert evidence.queries_ok == 0
    assert len(evidence.errors) == evidence.queries

    block = analyst._evidence_block(evidence)
    assert "NONE RETRIEVED" in block
    # The old prompt said "use the results above as factual basis" no matter what came back.
    assert "factual basis" not in block.lower()
    assert "unverified estimate" in block
    # And the error text is not smuggled into the prompt as something to reason from.
    assert "offline" not in block


def test_partial_search_failure_is_reported_not_hidden(monkeypatch):
    import agents.analyst as analyst

    calls = {"n": 0}

    def _flaky(q, max_results=3):
        calls["n"] += 1
        if calls["n"] % 2:
            return analyst.SearchOutcome(
                ok=True,
                results=[{"title": "T", "body": "B", "href": "https://example.com/a"}],
            )
        return analyst.SearchOutcome(ok=False, results=[], error="timeout")

    monkeypatch.setattr(analyst, "_duckduckgo_search", _flaky)
    evidence = analyst._market_search("widget CRM")
    assert evidence.grounding == "partial"
    assert evidence.sources == ["https://example.com/a"] * evidence.queries_ok
    assert "did not run" in analyst._evidence_block(evidence)


def test_grounded_search_asks_for_citations():
    import agents.analyst as analyst

    evidence = analyst.MarketEvidence(
        text="--- Search: x ---\nTitle: T\nSnippet: S\nURL: https://example.com/a\n",
        queries=4,
        queries_ok=4,
        sources=["https://example.com/a"],
        errors=[],
    )
    assert evidence.grounding == "full"
    block = analyst._evidence_block(evidence)
    assert "cite" in block.lower()
    assert "did not run" not in block


# ------------------------------------------------- worker wake: threads and feedback loops


@pytest.mark.asyncio
async def test_wake_from_another_thread_actually_wakes_the_worker():
    from pipeline_worker import PipelineWorker

    worker = PipelineWorker()
    worker._loop = asyncio.get_running_loop()

    def _from_thread():
        worker.wake_local()

    t = threading.Thread(target=_from_thread)
    waiter = asyncio.create_task(worker._wake_event.wait())
    await asyncio.sleep(0)
    t.start()
    # If wake_local touched the Event directly from the thread the waiter could be missed.
    await asyncio.wait_for(waiter, timeout=2.0)
    t.join()
    assert worker._wake_event.is_set()


@pytest.mark.asyncio
async def test_wake_local_does_not_publish_to_redis(monkeypatch):
    """The Redis listener is wired to wake_local; if it published, it would feed itself."""
    import orchestrator.redis_wake as redis_wake
    from pipeline_worker import PipelineWorker

    published = []
    monkeypatch.setattr(redis_wake, "publish_wake", lambda reason="": published.append(reason))

    worker = PipelineWorker()
    worker._loop = asyncio.get_running_loop()
    worker.wake_local()
    assert published == []
    assert worker._wake_event.is_set()


def test_redis_listener_is_wired_to_the_non_publishing_wake(monkeypatch):
    import orchestrator.queue_backend as qb
    import orchestrator.redis_wake as redis_wake
    from pipeline_worker import PipelineWorker

    captured = {}

    class _Listener:
        def __init__(self, on_wake, **kw):
            captured["on_wake"] = on_wake

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(qb, "pipeline_queue_backend", lambda: "redis")
    monkeypatch.setattr(redis_wake, "RedisWakeListener", _Listener)

    worker = PipelineWorker()
    worker._start_redis_wake_listener()
    assert captured.get("started") is True
    # Wired to signal_new_work, every popped wake published a new one onto the same key.
    assert captured["on_wake"] == worker.wake_local


@pytest.mark.asyncio
async def test_signal_new_work_does_not_block_the_loop_on_a_slow_redis(monkeypatch):
    import orchestrator.redis_wake as redis_wake
    from pipeline_worker import PipelineWorker

    entered = threading.Event()
    release = threading.Event()

    def _slow_publish(reason=""):
        entered.set()
        release.wait(5)

    monkeypatch.setattr(redis_wake, "publish_wake", _slow_publish)

    worker = PipelineWorker()
    worker._loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(asyncio.to_thread(lambda: None), timeout=1)  # warm the pool
        worker.signal_new_work()
        # The loop must still be responsive while the publish is in flight.
        await asyncio.wait_for(asyncio.sleep(0), timeout=1.0)
        assert worker._wake_event.is_set()
        assert entered.wait(2.0), "publish never ran"
    finally:
        release.set()


# ── the two ways the first analyst fix was still incomplete ──────────────────────


def test_the_system_prompt_does_not_promise_evidence_that_may_not_exist():
    """The evidence block can say NONE RETRIEVED while the prompt above it says otherwise.

    The block was fixed and the system prompt was not, so a total search failure produced a
    prompt that both asserted live results and denied them — and the assertion came first.
    """
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1]
            / "agents" / "prompts" / "analyst_research_prompt.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "you have access to real-time web search results" not in lowered
    assert "use these results as factual input" not in lowered
    # It must still tell the model where to look, or the evidence block is orphaned.
    assert "search" in lowered


def test_a_search_failure_never_reaches_the_stored_research_artifact():
    """market_research.json is read back into the PM, architect and developer prompts.

    Storing the exception text there moved the same bug into a longer pipe: out of one
    prompt and into four.
    """
    import agents.analyst as analyst

    evidence = analyst.MarketEvidence(
        text="", queries=4, queries_ok=0, sources=[],
        errors=["market size widgets: RatelimitException(secret-ish detail)"],
    )
    # The shape the agent stores.
    stored = {
        "grounding": evidence.grounding,
        "queries": evidence.queries,
        "queries_succeeded": evidence.queries_ok,
        "results_found": evidence.results_found,
        "sources": evidence.sources,
        "failed_queries": len(evidence.errors),
    }
    blob = repr(stored)
    assert "RatelimitException" not in blob
    assert "secret-ish detail" not in blob
    # The fact of failure survives — only the text is dropped.
    assert stored["failed_queries"] == 1
    assert stored["grounding"] == "none"


def test_the_agent_stores_counts_not_exception_text():
    """Pins the actual construction in agents/analyst.py, not a copy of it in this test."""
    import inspect

    import agents.analyst as analyst

    src = inspect.getsource(analyst.MarketResearchAgent._run_research)
    assert '"failed_queries": len(evidence.errors)' in src
    assert '"search_errors": evidence.errors' not in src


# ── a truncated reply must not be cached, and an agent must be able to see it ────
# Found by sweeping the ecosystem for the shape that produced a half-written file: the
# router cached the cut-off answer and served it on the next call BEFORE any provider ran,
# so finish_reason was never set and the truncation guard had nothing to guard. Three
# "attempts" were three cache hits.


def test_a_truncated_reply_is_never_cached():
    import inspect

    import llm.router as router

    src = inspect.getsource(router.LLMRouter.generate)
    idx = src.index("_cache_set(cache_key, result)")
    guard = src[max(0, idx - 900):idx]
    assert "was_truncated" in guard, "the cache write is not guarded by the truncation flag"


def test_a_cache_hit_says_it_came_from_cache():
    """A hit runs no provider, so nothing else would set the field. "" would read as
    "the provider did not say" — which is exactly what the guard treats as fine."""
    import inspect

    import llm.router as router

    src = inspect.getsource(router.LLMRouter.generate)
    hit = src[src.index("LLM cache hit"):]
    hit = hit[: hit.index("return cached") + len("return cached")]
    assert 'finish_reason = "cache"' in hit


@pytest.mark.asyncio
async def test_an_agent_can_see_that_its_reply_was_cut_off():
    """`replace()` builds a NEW config and the provider writes the flag onto that copy.

    Without copying it back, every agent in the factory is structurally blind to a reply
    that stopped mid-sentence — and _extract_json will close the braces and hand back
    something that reads like a complete object with every field after the cut missing.
    """
    from agents.base_agent import BaseAgent

    class _Router:
        async def generate(self, prompt, task_type=None, config=None):
            config.finish_reason = "length"
            return '{"partial": true'

    class _Agent(BaseAgent):
        async def execute(self, agent_input):  # pragma: no cover - not exercised
            return None

    agent = _Agent(agent_type="tester", llm_router=_Router(), task_type="t")
    assert agent.last_reply_was_truncated is False
    await agent._generate("hello")
    assert agent.last_reply_was_truncated is True


@pytest.mark.asyncio
async def test_a_complete_reply_does_not_look_truncated():
    from agents.base_agent import BaseAgent

    class _Router:
        async def generate(self, prompt, task_type=None, config=None):
            config.finish_reason = "stop"
            return "{}"

    class _Agent(BaseAgent):
        async def execute(self, agent_input):  # pragma: no cover
            return None

    agent = _Agent(agent_type="tester", llm_router=_Router(), task_type="t")
    await agent._generate("hello")
    assert agent.last_reply_was_truncated is False


# ── the rest of the sweep: streams, empty answers, and one retry that asks for less ──


def test_the_openai_stream_reads_the_terminal_finish_reason():
    import inspect

    import llm.openai_compatible as oc

    src = inspect.getsource(oc.OpenAICompatibleProvider.stream)
    assert 'choice.get("finish_reason")' in src
    assert "cfg.finish_reason" in src


def test_a_null_content_is_named_not_returned_as_none():
    import inspect

    import llm.openai_compatible as oc

    src = inspect.getsource(oc.OpenAICompatibleProvider.generate)
    assert "if response_text is None:" in src
    assert '"no_content"' in src


def test_the_anthropic_stream_reads_message_delta_and_error_frames():
    import inspect

    import llm.anthropic_provider as ap

    src = inspect.getsource(ap.AnthropicProvider.stream)
    assert '"message_delta"' in src and "stop_reason" in src
    assert '"error"' in src


def test_an_anthropic_answer_with_no_text_says_why():
    from llm.anthropic_provider import AnthropicProvider

    assert AnthropicProvider._no_text_reason({"content": [{"type": "refusal"}]}) == "refusal"
    assert AnthropicProvider._no_text_reason(
        {"content": [{"type": "tool_use"}]}).startswith("no_text")
    assert AnthropicProvider._no_text_reason({"content": []}) == "no_content"
    assert AnthropicProvider._no_text_reason(None) == "no_content"


def test_ollama_reports_its_done_reason_on_both_paths():
    import inspect

    import llm.local_ollama as lo

    gen = inspect.getsource(lo.LocalOllamaProvider.generate)
    stream = inspect.getsource(lo.LocalOllamaProvider.stream)
    assert "done_reason" in gen and "done_reason" in stream


def test_produced_no_text_recognises_every_shape():
    from llm.provider import GenerationConfig

    cfg = GenerationConfig()
    assert cfg.produced_no_text is False
    for reason in ("refusal", "no_content", "content_filter", "no_text:tool_use"):
        cfg.finish_reason = reason
        assert cfg.produced_no_text is True, reason
    cfg.finish_reason = "stop"
    assert cfg.produced_no_text is False


@pytest.mark.asyncio
async def test_a_truncated_reply_is_retried_once_asking_for_less():
    from agents.base_agent import TRUNCATION_RETRY_NOTE, BaseAgent

    calls = []

    class _Router:
        async def generate(self, prompt, task_type=None, config=None):
            calls.append(prompt)
            if len(calls) == 1:
                config.finish_reason = "length"
                return '{"cut": '
            config.finish_reason = "stop"
            return '{"complete": true}'

    class _Agent(BaseAgent):
        async def execute(self, agent_input):  # pragma: no cover
            return None

    agent = _Agent(agent_type="tester", llm_router=_Router(), task_type="t")
    out = await agent._generate("do the thing")
    assert out == '{"complete": true}'
    assert len(calls) == 2, "a cut-off reply must be retried"
    assert TRUNCATION_RETRY_NOTE in calls[1]
    assert "do the thing" in calls[1], "the retry must still carry the actual task"


@pytest.mark.asyncio
async def test_it_retries_only_once():
    """A second truncation means the request does not fit; another round will not change it."""
    from agents.base_agent import BaseAgent

    calls = []

    class _Router:
        async def generate(self, prompt, task_type=None, config=None):
            calls.append(prompt)
            config.finish_reason = "length"
            return "cut"

    class _Agent(BaseAgent):
        async def execute(self, agent_input):  # pragma: no cover
            return None

    agent = _Agent(agent_type="tester", llm_router=_Router(), task_type="t")
    await agent._generate("x")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_a_complete_reply_is_not_retried():
    from agents.base_agent import BaseAgent

    calls = []

    class _Router:
        async def generate(self, prompt, task_type=None, config=None):
            calls.append(prompt)
            config.finish_reason = "stop"
            return "{}"

    class _Agent(BaseAgent):
        async def execute(self, agent_input):  # pragma: no cover
            return None

    agent = _Agent(agent_type="tester", llm_router=_Router(), task_type="t")
    await agent._generate("x")
    assert len(calls) == 1
