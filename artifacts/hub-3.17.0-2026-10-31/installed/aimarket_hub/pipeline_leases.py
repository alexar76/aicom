"""Fence stale pipeline workers before resuming a durable seller operation."""
from contextvars import ContextVar

current = ContextVar("pipeline_lease", default=None)
TTL = 180


class LeaseLost(RuntimeError):
    pass


def check(conn, run_id):
    lease = current.get()
    if lease and lease[0] == run_id:
        row = conn.execute("SELECT lease_token FROM studio_pipeline_invocations WHERE run_id = ?", (run_id,)).fetchone()
        if not row or row['lease_token'] != lease[1]:
            raise LeaseLost("Pipeline execution transferred to another worker")
