from __future__ import annotations

import asyncio
import logging
import math
import os
import shlex
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from .base import ExecResult, Sandbox
from .registry import register_sandbox

if TYPE_CHECKING:
    from e2b import AsyncSandbox

    from .base import SandboxConfig

logger = logging.getLogger(__name__)


async def _finish_cleanup(coro) -> None:
    """Finish bounded cleanup through repeated cancellation, then propagate it."""
    task = asyncio.create_task(coro)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    if cancelled:
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.error("E2B cleanup failed during cancellation (%s); ownership retained", type(error).__name__)
        raise asyncio.CancelledError()
    task.result()


@register_sandbox("e2b")
class E2BSandbox(Sandbox):
    """Own one sandbox created from an existing KASandbox template.

    SDK imports are deferred until use. Command timeout/cancellation destroys
    the entire sandbox because process handles do not guarantee child cleanup.
    """

    def __init__(
        self,
        *,
        template: str = "",
        runtime_timeout: float = 3600.0,
        api_url: str | None = None,
        domain: str | None = None,
        sandbox_url: str | None = None,
        api_key: str | None = None,
        user: str | None = None,
        request_timeout: float = 60.0,
        health_timeout: float = 10.0,
        cleanup_timeout: float = 30.0,
    ) -> None:
        if not isinstance(template, str) or not template.strip():
            raise ValueError("E2BSandbox requires a nonempty sandbox_kwargs.template (existing ID or alias)")
        for name, value in (
            ("runtime_timeout", runtime_timeout),
            ("request_timeout", request_timeout),
            ("health_timeout", health_timeout),
            ("cleanup_timeout", cleanup_timeout),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name, value in (
            ("api_url", api_url),
            ("domain", domain),
            ("sandbox_url", sandbox_url),
            ("api_key", api_key),
            ("user", user),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a nonempty string when supplied")
        for name, value in (("api_url", api_url), ("sandbox_url", sandbox_url)):
            if value is not None:
                parsed = urlsplit(value)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                    raise ValueError(f"{name} must be an absolute HTTP(S) URL")
        self.template = template.strip()
        self.runtime_timeout = math.ceil(runtime_timeout)
        self.request_timeout = request_timeout
        self.health_timeout = health_timeout
        self.cleanup_timeout = cleanup_timeout
        self.user = user
        self._connection_options = {
            key: value
            for key, value in dict(api_url=api_url, domain=domain, sandbox_url=sandbox_url, api_key=api_key).items()
            if value is not None
        }
        self._sandbox: AsyncSandbox | None = None
        self._ready = False
        self._lifecycle_lock = asyncio.Lock()

    @classmethod
    def from_config(cls, config: SandboxConfig) -> E2BSandbox:
        if config.image_mounts or config.executable_paths:
            raise ValueError("E2BSandbox does not support image_mounts or executable_paths; prepare the template first")
        if "proxy_port" in config.sandbox_kwargs:
            raise ValueError("E2BSandbox does not support proxy_port or gateway reverse tunnels")
        return cls(runtime_timeout=config.runtime_timeout, **config.sandbox_kwargs)

    async def _allocate(self) -> None:
        from e2b import AsyncSandbox

        # Retain ownership before any readiness probe or other await.
        self._sandbox = await asyncio.wait_for(
            AsyncSandbox.create(
                template=self.template,
                timeout=self.runtime_timeout,
                request_timeout=self.request_timeout,
                **self._connection_options,
            ),
            timeout=self.request_timeout,
        )

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._sandbox is not None:
                if self._ready:
                    return
                raise RuntimeError("E2BSandbox has unfinished cleanup; call stop() before restarting")
            # The reference SDK's debug mode skips both allocation and deletion;
            # it cannot provide the episode ownership guarantees of this provider.
            if os.getenv("E2B_DEBUG", "false").lower() == "true":
                raise ValueError("E2BSandbox requires E2B_DEBUG to be disabled")
            allocation = asyncio.create_task(self._allocate())
            try:
                await asyncio.shield(allocation)
                if not await self._probe():
                    raise RuntimeError("E2BSandbox failed its readiness probe")
                self._ready = True
            except asyncio.CancelledError:
                try:
                    await _finish_cleanup(self._reconcile_allocation(allocation))
                except Exception as exc:
                    logger.error("E2B startup cleanup failed (%s); ownership retained", type(exc).__name__)
                raise

    async def _reconcile_allocation(self, allocation: asyncio.Task) -> None:
        try:
            await allocation
        except Exception:
            # A failed create may not return an ID. Its finite TTL is the final
            # bound in that case; a lost response cannot be reconciled locally.
            pass
        await self._delete_owned()

    async def _delete_owned(self) -> None:
        if self._sandbox is None:
            return
        from e2b.exceptions import SandboxNotFoundException

        self._ready = False
        try:
            await asyncio.wait_for(
                self._sandbox.kill(request_timeout=self.cleanup_timeout), timeout=self.cleanup_timeout
            )
        except SandboxNotFoundException:
            pass
        # kill() also returns False for an already-deleted sandbox. Unexpected
        # failures leave the handle intact, allowing a later stop() to retry.
        self._sandbox = None
        # The reference SDK shares its transport across the event loop and has
        # no public close method. Closing private clients would disrupt peers.

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            await _finish_cleanup(self._delete_owned())

    async def _probe(self) -> bool:
        if self._sandbox is None:
            return False
        try:
            return await asyncio.wait_for(
                self._sandbox.is_running(request_timeout=self.health_timeout), timeout=self.health_timeout
            )
        except Exception:
            return False

    async def is_alive(self) -> bool:
        return self._ready and await self._probe()

    def _require_sandbox(self) -> AsyncSandbox:
        if self._sandbox is None or not self._ready:
            raise RuntimeError("E2BSandbox is not ready; call start() first (or retry pending stop())")
        return self._sandbox

    def _is_timeout_error(self, exc: BaseException) -> bool:
        from e2b.exceptions import TimeoutException
        from httpcore import TimeoutException as CoreTimeoutException
        from httpx import TimeoutException as HTTPTimeoutException

        return super()._is_timeout_error(exc) or isinstance(
            exc, TimeoutException | CoreTimeoutException | HTTPTimeoutException
        )

    async def _abort_command(self, sandbox: AsyncSandbox) -> None:
        async with self._lifecycle_lock:
            if self._sandbox is sandbox:
                await self._delete_owned()

    async def _exec(
        self,
        argv: list[str],
        *,
        timeout: float | None = None,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        from e2b.sandbox.commands.command_handle import CommandExitException

        sandbox = self._require_sandbox()
        handle = None

        async def run() -> ExecResult:
            nonlocal handle
            handle = await asyncio.wait_for(
                sandbox.commands.run(
                    shlex.join(argv),
                    background=True,
                    cwd=workdir,
                    envs=env,
                    user=self.user,
                    timeout=0,
                    request_timeout=self.request_timeout,
                ),
                timeout=self.request_timeout,
            )
            try:
                result = await handle.wait()
            except CommandExitException as exc:
                result = exc
            return ExecResult(exit_code=result.exit_code, stdout=result.stdout, stderr=result.stderr)

        try:
            # timeout=None explicitly has no command deadline, including no SDK
            # default 60-second connection limit. Lifetime still bounds the VM.
            return await asyncio.wait_for(run(), timeout=timeout)
        except asyncio.CancelledError:
            try:
                await _finish_cleanup(self._abort_command(sandbox))
            except Exception as exc:
                logger.error("E2B command cancellation cleanup failed (%s); retry stop()", type(exc).__name__)
            raise
        except Exception as exc:
            if not self._is_timeout_error(exc):
                raise
            try:
                await _finish_cleanup(self._abort_command(sandbox))
            except Exception as cleanup_error:
                raise TimeoutError(
                    "Command timed out; sandbox deletion failed "
                    f"({type(cleanup_error).__name__}); ownership retained, retry stop()"
                ) from exc
            raise
        finally:
            if handle is not None:
                await handle.disconnect()

    async def read_file(self, path: str) -> bytes:
        if not path.startswith("/"):
            return await super().read_file(path)
        from e2b.exceptions import FileNotFoundException

        try:
            data = await self._require_sandbox().files.read(
                path, format="bytes", user=self.user, request_timeout=self.request_timeout
            )
        except FileNotFoundException as exc:
            raise RuntimeError(f"read_file {path!r} failed: file not found") from exc
        return bytes(data)

    async def write_file(self, path: str, content: bytes | str) -> None:
        if not path.startswith("/"):
            return await super().write_file(path, content)
        data = content.encode("utf-8") if isinstance(content, str) else content
        await self._require_sandbox().files.write(path, data, user=self.user, request_timeout=self.request_timeout)
