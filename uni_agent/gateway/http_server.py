"""HTTP listener for a gateway exposed through a fixed-port SSH tunnel."""
from __future__ import annotations

import asyncio
import socket

import uvicorn


async def run_fixed_port_server(app, address: str, port: int) -> tuple[int, asyncio.Task]:
    # Bind before spawning uvicorn so a port conflict raises OSError here instead
    # of SystemExit in an asynchronous server task.
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sock = socket.create_server((address, port), family=family)
    sock.setblocking(False)
    server = uvicorn.Server(uvicorn.Config(
        app, host=address, port=port, log_level="warning", timeout_graceful_shutdown=5
    ))

    async def serve():
        try:
            await server.serve(sockets=[sock])
        except asyncio.CancelledError:
            if server.started:
                await server.shutdown(sockets=[sock])
            raise
        finally:
            sock.close()

    task = asyncio.create_task(serve())
    try:
        async with asyncio.timeout(30):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("Gateway HTTP server exited before startup")
                await asyncio.sleep(0.01)
    except BaseException:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        sock.close()
        raise
    return port, task
