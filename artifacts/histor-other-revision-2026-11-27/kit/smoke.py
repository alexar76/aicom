"""Inside the candidate image, no network: the build knows migration 027, applies every migration to a fresh
SQLite store, the store reads and writes a handshake reading, and the reader has the handshake-only read."""
import inspect, os, sys, tempfile

os.environ["HISTOR_DATA_DIR"] = tempfile.mkdtemp()
os.environ.pop("HISTOR_DATABASE_URL", None)
import histor
# The application runs from /app; the image also holds an installed copy of the package it was built from.
assert histor.__file__ == "/app/histor/__init__.py", histor.__file__
from histor import check, crawler, migrations
from histor.config import load_settings
from histor.mcpclient import McpReader
from histor.service import build

assert (27, "027_revision_readings") in [(v, n) for v, n, _ in migrations.MIGRATIONS]
assert "handshake_only" in inspect.signature(McpReader.list_tools).parameters
assert "same-other-revision" in check.NOTES and hasattr(crawler, "OtherRevision")
settings = load_settings()
assert settings.revision_reads_per_day == 1500 and settings.revision_reread_days == 7
services = build(settings)
try:
    store = services.store
    store.put_revision_reading("t1", beside_toolset="sha256-a", protocol="2025-06-18", toolset="sha256-b", tool_count=3,
                               status="ok", read_at="2026-11-27T00:00:00Z")
    store.put_revision_reading("t1", beside_toolset="sha256-c", protocol="2025-06-18", toolset="sha256-b", tool_count=3,
                               status="ok", read_at="2026-11-27T01:00:00Z")
    assert store.revision_reading("t1")["beside_toolset"] == "sha256-c"
    assert store.revision_reading_index() == {"t1": ("sha256-c", "2026-11-27T01:00:00Z")}
    assert store.last_protocol("t1") == ""
finally:
    services.close()
print("smoke ok: migration 27, store, reader")
