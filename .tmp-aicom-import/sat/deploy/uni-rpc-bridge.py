"""Expose the bubble's chain to the bubble's containers — and to nobody else.

Anvil listens on 127.0.0.1 only, which is correct: the UNI chain must not be reachable from
outside the host. But a container cannot reach the host's loopback, so the UNI hub could not
talk to its own chain at all.

This forwards 172.17.0.1:8545 (the docker bridge address, not routable from off-host) to
127.0.0.1:8545. Deliberately NOT 0.0.0.0: binding the chain to a public interface would
break the seal from the outside — anyone could then mint the bubble's dollars, and a
simulation anyone can join is not sealed.
"""
from __future__ import annotations

import asyncio
import logging

LISTEN_HOST = "172.17.0.1"
LISTEN_PORT = 8545
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 8545

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


async def pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()


async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    try:
        target_reader, target_writer = await asyncio.open_connection(TARGET_HOST, TARGET_PORT)
    except OSError as exc:
        logging.warning("cannot reach the chain at %s:%s — %s", TARGET_HOST, TARGET_PORT, exc)
        client_writer.close()
        return
    await asyncio.gather(
        pump(client_reader, target_writer),
        pump(target_reader, client_writer),
        return_exceptions=True,
    )


async def main() -> None:
    server = await asyncio.start_server(handle, LISTEN_HOST, LISTEN_PORT)
    logging.info(
        "uni rpc bridge: %s:%s -> %s:%s (docker bridge only)",
        LISTEN_HOST, LISTEN_PORT, TARGET_HOST, TARGET_PORT,
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
