"""Run inside the new image: edge-tts version, a short synthesis, and the HELIOS CLI imports."""
import asyncio
import importlib.metadata as m
import subprocess

import edge_tts

assert m.version("edge_tts") == "7.3.1", m.version("edge_tts")


async def synth() -> int:
    n = 0
    async for ch in edge_tts.Communicate("Signed receipts prove delivery, not quality.", "en-US-AndrewNeural").stream():
        if ch["type"] == "audio":
            n += len(ch["data"])
    return n


n = asyncio.run(synth())
assert n > 1000, n
out = subprocess.run(["helios", "--help"], capture_output=True, text=True, timeout=60)
assert out.returncode == 0 and "worker" in out.stdout, out.stderr[-300:]
print("smoke ok: edge-tts 7.3.1, audio bytes", n, "| helios CLI ok")
