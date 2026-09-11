"""Tests for core.events.EventBus — async pub/sub with per-subscriber queues.

All async test bodies are wrapped via `asyncio.run()` so pytest runs them
natively without requiring pytest-asyncio.
"""

import asyncio
import logging

import pytest

from core.events import (
    EventBus,
    PipelineEvent,
    TaskCompleted,
    ProductStateChanged,
    LLMCallLogged,
    get_event_bus,
    reset_event_bus_for_tests,
)


def run_async(coro):
    """Utility wrapper — runs an async test body synchronously via asyncio.run()."""
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_bus():
    reset_event_bus_for_tests(None)
    yield
    reset_event_bus_for_tests(None)


# ── Subscribe ──────────────────────────────────────────────────────────────


class TestEventBusSubscribe:
    def test_subscribe_returns_id_and_registers(self):
        bus = EventBus()

        async def handler(event: PipelineEvent) -> None:
            pass

        sid = bus.subscribe("TaskCompleted", handler)
        assert sid
        assert len(sid) == 8
        assert "TaskCompleted" in bus._subscribers
        assert any(s[0] == sid for s in bus._subscribers["TaskCompleted"])

    def test_multiple_event_types_isolated(self):
        bus = EventBus()

        async def on_tc(e): pass
        async def on_ps(e): pass

        bus.subscribe("TaskCompleted", on_tc)
        bus.subscribe("ProductStateChanged", on_ps)

        assert len(bus._subscribers["TaskCompleted"]) == 1
        assert len(bus._subscribers["ProductStateChanged"]) == 1


# ── Publish ────────────────────────────────────────────────────────────────


class TestEventBusPublish:
    def test_publish_delivers_to_subscriber(self):
        async def _body():
            bus = EventBus()
            received = []

            async def handler(event):
                received.append(event)

            bus.subscribe("TaskCompleted", handler)
            await bus.publish(TaskCompleted(
                task_id="t1", product_id="p1", agent_type="dev", status="completed",
            ))
            await asyncio.sleep(0.05)
            assert len(received) == 1
            assert received[0].task_id == "t1"

        run_async(_body())

    def test_publish_to_multiple_subscribers(self):
        async def _body():
            bus = EventBus()
            r1, r2 = [], []

            async def h1(e): r1.append(e)
            async def h2(e): r2.append(e)

            bus.subscribe("TaskCompleted", h1)
            bus.subscribe("TaskCompleted", h2)
            await bus.publish(TaskCompleted(
                task_id="t1", product_id="p1", agent_type="dev", status="completed",
            ))
            await asyncio.sleep(0.05)
            assert len(r1) == 1
            assert len(r2) == 1

        run_async(_body())

    def test_publish_wrong_type_not_delivered(self):
        async def _body():
            bus = EventBus()
            received = []

            async def handler(e): received.append(e)
            bus.subscribe("TaskCompleted", handler)
            await bus.publish(ProductStateChanged(product_id="p1", new_state="done"))
            await asyncio.sleep(0.05)
            assert len(received) == 0

        run_async(_body())

    def test_publish_no_subscribers_no_error(self):
        async def _body():
            bus = EventBus()
            await bus.publish(TaskCompleted(
                task_id="t1", product_id="p1", agent_type="dev", status="completed",
            ))

        run_async(_body())


# ── Queue Overflow (DROPs) ─────────────────────────────────────────────────


class TestEventBusQueueOverflow:
    def test_drop_on_full_queue(self, caplog):
        async def _body():
            bus = EventBus(queue_maxsize=2)
            barrier = asyncio.Event()

            async def slow_handler(event):
                await barrier.wait()

            bus.subscribe("TaskCompleted", slow_handler)

            for i in range(5):
                await bus.publish(TaskCompleted(
                    task_id=f"t{i}", product_id="p1", agent_type="dev", status="completed",
                ))

            await asyncio.sleep(0.1)

            stats = bus.stats()
            any_sub_stats = list(stats["queues"].values())[0] if stats["queues"] else {}
            drops = any_sub_stats.get("drops", 0) if any_sub_stats else 0
            assert drops > 0, f"Expected drops when queue overflows, got {drops}"

            drop_logs = [r.message for r in caplog.records if "DROP" in r.message]
            assert len(drop_logs) > 0

            barrier.set()

        run_async(_body())

    def test_drop_throttled_logging(self, caplog):
        """After 10 drops, only powers of two get logged (11-15 are silent, 16 logged)."""
        async def _body():
            caplog.set_level(logging.WARNING)
            bus = EventBus(queue_maxsize=1)
            barrier = asyncio.Event()

            async def slow_handler(event):
                await barrier.wait()

            bus.subscribe("TaskCompleted", slow_handler)

            # Fire 20 events — queue size 1, worker consumes first, 19 drops
            for i in range(20):
                await bus.publish(TaskCompleted(
                    task_id=f"t{i}", product_id="p1", agent_type="dev", status="completed",
                ))
            await asyncio.sleep(0.05)

            drop_logs = [r for r in caplog.records if "DROP" in r.message]
            # Drop 1 logs, then throttled: 1,2,...,10 then 16 only
            # Total logged ~ 12 (1-10 = 10, + 16 = 11, maybe + 0 = 11–12)
            assert len(drop_logs) >= 1, "At least first drop should be logged"

            # After 10 drops, drop #11-15 should NOT be logged
            drop_11_to_15 = [r for r in drop_logs if "drops=11" in r.message
                             or "drops=12" in r.message or "drops=13" in r.message
                             or "drops=14" in r.message or "drops=15" in r.message]
            assert len(drop_11_to_15) == 0, f"Drops 11-15 should be throttled, got {drop_11_to_15}"

            barrier.set()

        run_async(_body())


# ── Isolation between subscribers ───────────────────────────────────────────


class TestEventBusIsolation:
    def test_slow_subscriber_does_not_block_fast(self):
        async def _body():
            bus = EventBus()
            fast_received = []
            slow_barrier = asyncio.Event()

            async def slow_handler(event):
                await slow_barrier.wait()

            async def fast_handler(event):
                fast_received.append(event)

            sid_slow = bus.subscribe("ProductStateChanged", slow_handler)
            bus.subscribe("ProductStateChanged", fast_handler)

            await bus.publish(ProductStateChanged(product_id="p1", new_state="started"))
            await asyncio.sleep(0.1)

            assert len(fast_received) >= 1, "Fast handler should receive despite slow one blocking"

            slow_barrier.set()
            bus.unsubscribe("ProductStateChanged", sid_slow)

        run_async(_body())


# ── Unsubscribe ────────────────────────────────────────────────────────────


class TestEventBusUnsubscribe:
    def test_unsubscribe_stops_delivery(self):
        async def _body():
            bus = EventBus()
            received = []

            async def handler(e): received.append(e)

            sid = bus.subscribe("TaskCompleted", handler)
            assert bus.unsubscribe("TaskCompleted", sid)

            await bus.publish(TaskCompleted(
                task_id="t1", product_id="p1", agent_type="dev", status="completed",
            ))
            await asyncio.sleep(0.05)
            assert len(received) == 0

        run_async(_body())

    def test_unsubscribe_tears_down_worker(self):
        async def _body():
            bus = EventBus()
            barrier = asyncio.Event()

            async def handler(e): await barrier.wait()

            sid = bus.subscribe("TaskCompleted", handler)
            await bus.publish(TaskCompleted(
                task_id="t1", product_id="p1", agent_type="dev", status="completed",
            ))
            await asyncio.sleep(0.02)

            assert sid in bus._tasks
            assert sid in bus._queues

            bus.unsubscribe("TaskCompleted", sid)
            assert sid not in bus._tasks
            assert sid not in bus._queues

            barrier.set()

        run_async(_body())

    def test_unsubscribe_nonexistent_returns_false(self):
        bus = EventBus()
        assert not bus.unsubscribe("TaskCompleted", "nonexistent")


# ── Shutdown ───────────────────────────────────────────────────────────────


class TestEventBusShutdown:
    def test_shutdown_cancels_workers(self):
        async def _body():
            bus = EventBus()

            async def h1(e): pass
            async def h2(e): pass

            bus.subscribe("TaskCompleted", h1)
            bus.subscribe("ProductStateChanged", h2)

            await bus.publish(TaskCompleted(
                task_id="t1", product_id="p1", agent_type="dev", status="completed",
            ))
            await asyncio.sleep(0.02)
            assert len(bus._tasks) >= 1

            await bus.shutdown()
            assert len(bus._tasks) == 0
            assert len(bus._queues) == 0

        run_async(_body())

    def test_shutdown_clears_drop_counts(self):
        async def _body():
            bus = EventBus(queue_maxsize=1)
            barrier = asyncio.Event()

            async def slow(e): await barrier.wait()
            bus.subscribe("TaskCompleted", slow)

            for _ in range(3):
                await bus.publish(TaskCompleted(
                    task_id="t1", product_id="p1", agent_type="dev", status="completed",
                ))
            await asyncio.sleep(0.02)

            assert any(d > 0 for d in bus._drop_counts.values()), \
                "Should have recorded drops before shutdown"

            barrier.set()
            await bus.shutdown()
            assert len(bus._drop_counts) == 0, \
                "shutdown() must clear _drop_counts"

        run_async(_body())

    def test_shutdown_idempotent(self):
        async def _body():
            bus = EventBus()
            await bus.shutdown()
            await bus.shutdown()  # second call must not raise

        run_async(_body())


# ── publish_background ─────────────────────────────────────────────────────


class TestEventBusBackground:
    def test_publish_background_delivers(self):
        async def _body():
            bus = EventBus()
            received = []

            async def handler(e): received.append(e)

            bus.subscribe("TaskCompleted", handler)
            bus.publish_background(TaskCompleted(
                task_id="t1", product_id="p1", agent_type="dev", status="completed",
            ))
            await asyncio.sleep(0.1)
            assert len(received) == 1

        run_async(_body())


# ── Stats ──────────────────────────────────────────────────────────────────


class TestEventBusStats:
    def test_stats_subscriber_count(self):
        bus = EventBus()

        async def h1(e): pass
        async def h2(e): pass

        bus.subscribe("TaskCompleted", h1)
        bus.subscribe("TaskCompleted", h2)
        bus.subscribe("ProductStateChanged", h1)

        stats = bus.stats()
        assert stats["subscriber_count"] == 3
        assert stats["queue_maxsize"] == 1024

    def test_stats_queue_depths(self):
        async def _body():
            bus = EventBus()

            async def h(e): pass
            bus.subscribe("TaskCompleted", h)
            await bus.publish(TaskCompleted(
                task_id="t1", product_id="p1", agent_type="dev", status="completed",
            ))
            await asyncio.sleep(0.02)

            stats = bus.stats()
            assert len(stats["queues"]) >= 1
            for qinfo in stats["queues"].values():
                assert "depth" in qinfo
                assert "maxsize" in qinfo
                assert "drops" in qinfo

        run_async(_body())


# ── Event Models ───────────────────────────────────────────────────────────


class TestEventBusEvents:
    def test_task_completed_fields(self):
        event = TaskCompleted(
            task_id="task-001", product_id="prod-001",
            agent_type="dev", status="completed", state="CODE_COMMITTED",
        )
        assert event.task_id == "task-001"
        assert event.event_id  # auto-generated UUID

    def test_llm_call_logged_fields(self):
        event = LLMCallLogged(
            provider="deepseek", model="deepseek-chat",
            task_type="code_generation", tokens_used=1500,
            estimated_cost_usd=0.002, duration_ms=1200.0,
        )
        assert event.provider == "deepseek"
        assert event.tokens_used == 1500

    def test_build_artifact_ready(self):
        from core.events import BuildArtifactReady
        event = BuildArtifactReady(
            product_id="p1", artifact_path="/tmp/build",
            artifact_type="frontend", checksum="abc123",
        )
        assert event.artifact_type == "frontend"

    def test_security_scan_completed(self):
        from core.events import SecurityScanCompleted
        event = SecurityScanCompleted(
            product_id="p1", findings_count=5,
            critical_count=1, high_count=2, passed=False,
        )
        assert event.critical_count == 1
        assert not event.passed


# ── Singleton ──────────────────────────────────────────────────────────────


class TestSingleton:
    def test_get_event_bus_same_instance(self):
        reset_event_bus_for_tests(None)
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_reset_event_bus_for_tests(self):
        bus_a = EventBus()
        reset_event_bus_for_tests(bus_a)
        assert get_event_bus() is bus_a

        reset_event_bus_for_tests(None)
        bus_b = get_event_bus()
        assert bus_b is not bus_a
