from __future__ import annotations

import asyncio
import os
import socket
import sys
from pathlib import Path


def _runtime_pid_file() -> Path:
    return Path(__file__).resolve().parents[1] / "deploy" / "no_docker" / "runtime_logs" / "pids" / "localhost_ipv6_proxy.pid"


async def _forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _handle(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    target_host: str,
    target_port: int,
) -> None:
    upstream_reader: asyncio.StreamReader | None = None
    upstream_writer: asyncio.StreamWriter | None = None
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(
            target_host,
            target_port,
            family=socket.AF_INET,
        )
        await asyncio.gather(
            _forward(client_reader, upstream_writer),
            _forward(upstream_reader, client_writer),
        )
    finally:
        for writer in (client_writer, upstream_writer):
            if writer is None:
                continue
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


async def _serve() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8767
    target_host = "127.0.0.1"
    server = await asyncio.start_server(
        lambda r, w: _handle(r, w, target_host, port),
        host="::1",
        port=port,
        family=socket.AF_INET6,
    )
    pid_file = _runtime_pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))
    try:
        async with server:
            await server.serve_forever()
    finally:
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    asyncio.run(_serve())
