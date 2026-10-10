# Sandbox

A Sandbox is the execution boundary of an agent episode. It owns the runtime lifecycle and provides a common data plane for commands, files, uploads, downloads, and optional port exposure.

Tools depend on the narrow `SandboxBackend` protocol. Tasks and Agents receive the full `Sandbox` object, but the Task remains responsible for starting and stopping it.

## Configuration

`SandboxConfig` selects the provider and carries common lifecycle settings:

```python
from uni_agent.sandbox import SandboxConfig, build_sandbox

config = SandboxConfig(
    provider="modal",
    image="python:3.12",
    runtime_timeout=3600,
    sandbox_kwargs={"app_name": "agent-sandbox"},
)

sandbox = build_sandbox(config)
```

The standard fields are:

- `provider`: registered backend name.
- `image`: container image used by image-backed providers such as Docker and Modal.
- `image_map`: optional rewrite from the dataset image name to the image your cluster can pull (see below).
- `image_mounts`: optional runtime images mounted into the task sandbox.
- `executable_paths`: command names mapped to executables supplied by the task or mounted images.
- `runtime_timeout`: maximum sandbox lifetime.
- `sandbox_kwargs`: provider-specific constructor arguments.

Unknown fields are rejected. Put provider-specific options inside `sandbox_kwargs`.

### `image_map`

SWE-Bench samples ship with public image names such as `swebench/sweb.eval.x86_64.astropy_1776_astropy-13033`. If your cluster cannot pull those names (private registry, mirror, or a local tag), add `image_map` under `sandbox` in Task Config. Do not edit the parquet.

```yaml
sandbox:
  provider: vefaas
  image_map:
    - from: "swebench/**:latest"
      to: "<your-registry>/swe-bench-verified/**:v2"
    - from: "swerebench/**:latest"
      to: "<your-registry>/swe-rebench/**:latest"
```

`**` copies the instance-specific path, so `swebench/sweb.eval.x86_64.astropy_1776_astropy-13033` becomes `<your-registry>/swe-bench-verified/sweb.eval.x86_64.astropy_1776_astropy-13033:v2`.

List as many rules as you need; the first matching `from` is used. Images that match none of the rules are left unchanged.

### Runtime images

Black-box agent harnesses can be packaged separately from task images and attached with:

```yaml
sandbox:
  provider: modal
  image: swebench/sweb.eval.x86_64.example
  image_mounts:
    - image: docker.io/example/claude-code-runtime:1.0
      mount_path: /opt/agent-runtime
  executable_paths:
    claude: /opt/agent-runtime/bin/claude
```

Docker, Modal, and OpenYuanRong support `image_mounts`. `image_map` rewrites only the task `image`, so mounted image references must already be complete and pullable. `executable_paths` exposes selected mounted commands after startup; Local, veFaaS, and E2B reject it.

### KASandbox / E2B

The optional `e2b` provider creates one new sandbox per instance from an existing
KASandbox template ID or alias. For development, install the SDK from a sibling
KASandbox checkout, running this command from the Uni-Agent repository:

```console
python -m pip install -e ../KASandbox/py-sdk
```

The initial compatibility reference is KASandbox revision `c497053` (SDK package
version `2.19.0`). An arbitrary public `e2b` release is not guaranteed to have the
same self-hosted routing behavior. E2B is imported only when used and is not a
mandatory Uni-Agent dependency.

```yaml
sandbox:
  provider: e2b
  runtime_timeout: 7200
  sandbox_kwargs:
    template: "<existing-template-id-or-alias>"
    api_url: "http://<kasandbox-api-host>:3000"
    domain: "<configured-sandbox-domain>"
    # sandbox_url: "http://<sandbox-command-and-file-endpoint>"
    request_timeout: 60
    health_timeout: 10
    cleanup_timeout: 30
```

Supply credentials through the SDK's environment configuration, such as
`E2B_API_KEY`. Explicit per-instance `api_key`, `api_url`, `domain`, and
`sandbox_url` options are supported without changing process-wide environment
variables. Omitted connection options use SDK defaults/environment settings.
The optional `user` applies to both commands and files; omitting it uses the
template/SDK default user. Unknown options are rejected. `E2B_DEBUG=true` is
rejected because that SDK mode skips real allocation and deletion.

`template` must be nonempty. The provider neither builds templates nor interprets
`image` as a template ID. The explicit template is authoritative even when a
dataset row supplies an `image` (including one rewritten by `image_map`). Use only
tasks matching that template; heterogeneous datasets require a future
image-to-template mapping. Prepare required executables in the template:
nonempty `image_mounts` and `executable_paths` are rejected.

There are two required network paths:

1. Uni-Agent workers must reach the KASandbox API and sandbox command/file
   endpoints. Configure `sandbox_url` if required by the deployment's routing.
2. The sandbox must reach the session-specific Uni-Agent gateway address and
   port injected by the task runner. The provider supplies no reverse tunnel;
   `proxy_port` is rejected and `expose_port()` is unsupported.

Install the same compatible SDK and supply credentials and connection settings
in every relevant Ray worker environment. The provider remains agent-agnostic;
the existing Claude Code agent launches Claude and supplies its gateway
environment.

Lifecycle and operation semantics:

- `runtime_timeout` is a finite positive sandbox lifetime, rounded **up** to
  integer seconds. There is no automatic renewal, attach, pooling, or pause.
  Repeated `start()` does not allocate again; after successful `stop()`, a new
  `start()` creates a fresh sandbox.
- `request_timeout` bounds API requests and command launch (default 60 seconds).
  `health_timeout` bounds readiness/health probes (10 seconds), and
  `cleanup_timeout` bounds deletion (30 seconds). All must be finite and positive.
  The base startup concurrency, timeout, retries, and failed-start cleanup apply.
- The command `timeout` is a separate deadline covering launch and execution.
  `None` removes the command deadline, including the SDK's default 60-second
  connection limit; sandbox lifetime still applies. Nonzero exits preserve the
  actual exit code, stdout, and stderr. Arguments are POSIX-quoted; `workdir` and
  the command environment are forwarded to the SDK.
- A command timeout or cancellation attempts bounded deletion of the **entire
  sandbox**, since the SDK's process kill does not guarantee child termination.
  Subsequent evaluation cannot use a destroyed sandbox. Timeouts follow the base
  policy (`exit_code=-1`); cancellation propagates after cleanup. Failed deletion
  retains ownership for a later `stop()` and reports the failure in the timeout
  result or cancellation log. The instance refuses further operations until
  deletion succeeds. An already-deleted sandbox counts as successful cleanup.
- Startup cancellation shields allocation for the remainder of its bounded
  request, retains any returned handle, and attempts deletion before propagating
  cancellation. A lost create response or SDK failure after allocation can still
  leave an unknown sandbox ID. Its finite lifetime is the final cleanup bound;
  immediate deletion cannot be guaranteed in this window. Keep
  `SANDBOX_STOP_TIMEOUT` large enough for the configured deletion bound.
- Absolute file paths use native binary reads and writes (strings are encoded as
  UTF-8); reads return `bytes`, missing reads raise, and writes create parents and
  overwrite existing files. Relative paths use the base command implementation
  so they share command working-directory semantics. Upload/download reuse these
  methods; directory transfer also requires `bash`, `tar`, and `gzip` in the
  template (relative file operations require `base64`). Native persistent shells
  are unsupported; `exec_shell()` uses the standard `bash -c` wrapper.
- The reference SDK shares HTTP transports per event loop and exposes no public
  sandbox transport-close operation. The provider does not close private clients
  that other instances may still use. Per-instance proxy configuration is not
  exposed because that shared transport would not isolate different proxies.

Live deployment validation remains necessary: lifecycle and double-stop,
nonzero commands, literal arguments, environment/cwd forwarding, text/binary and
directory transfers, command timeout/cancellation, failed/cancelled startup,
deleted-sandbox errors, and isolation between two instances. A live Claude Code
episode and RL training are separate integration milestones.

## Lifecycle

Use a Sandbox as an async context manager:

```python
async with sandbox:
    result = await sandbox.exec_shell("python --version")
```

Entering the context starts the backend with retry, timeout, and global startup-concurrency controls. Exiting the context calls `stop()` even when the episode raises.

The shared lifecycle uses:

- `SANDBOX_STARTUP_TIMEOUT`: startup timeout, 600 seconds by default.
- `SANDBOX_STARTUP_CONCURRENCY`: process-wide startup limit, 64 by default.
- `SANDBOX_STOP_TIMEOUT`: timeout for the cleanup `stop()` after a failed or cancelled start, 120 seconds by default. Cancellation waits for this cleanup, so the bound keeps a hung provider from blocking it forever.

Remote providers should implement `is_alive()` as a non-throwing health probe.

## Data Plane

`SandboxBackend` exposes:

```python
await sandbox.exec(argv, timeout=..., workdir=..., env=...)
await sandbox.exec_shell(script, timeout=..., workdir=..., env=...)
await sandbox.read_file(path)
await sandbox.write_file(path, content)
await sandbox.upload(local_path, remote_path)
await sandbox.download(remote_path, local_path)
await sandbox.expose_port(port)
```

The base class provides portable command, file, and directory-transfer implementations. Providers may override file methods when they have a native data plane. For example, Local uses the host filesystem directly, Docker uses `docker cp`, and Modal uses its filesystem API for absolute paths.

## Error Policy

All providers share the public `Sandbox.exec()` error policy:

- A timeout becomes `ExecResult(exit_code=-1)`.
- A normal command/provider error while the sandbox is alive becomes `exit_code=127`.
- An infrastructure error after the sandbox has died is re-raised.

This policy prevents one bad agent command from crashing an otherwise healthy episode while still surfacing backend failures.

!!! warning "Do not override `exec()`"
    Custom providers implement `_exec()`. The public `exec()` wrapper owns the cross-provider error policy and is enforced by tests.

## Custom Backend

A minimal backend implements `start()`, `stop()`, and `_exec()`:

```python
from uni_agent.sandbox.base import ExecResult, Sandbox
from uni_agent.sandbox.registry import register_sandbox


@register_sandbox("my_backend")
class MySandbox(Sandbox):
    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    async def _exec(
        self,
        argv: list[str],
        *,
        timeout: float | None = None,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        ...
```

If the backend needs custom configuration mapping, override `from_config()`:

```python
@classmethod
def from_config(cls, config: SandboxConfig):
    return cls(
        image=config.image,
        runtime_timeout=config.runtime_timeout,
        image_mounts=config.image_mounts,
        executable_paths=config.executable_paths,
        **config.sandbox_kwargs,
    )
```

Register the lazy module in `SANDBOX_MODULES`:

```python
SANDBOX_MODULES["my_backend"] = "my_package.sandbox"
```

The module is imported only when the provider is selected, so optional SDKs do not affect other backends.

## Implementation Rules

- Implement `_exec()`, not `exec()`.
- Make `start()` and `stop()` safe to call during partial failures.
- Override `is_alive()` for remote providers.
- Extend `_is_timeout_error()` when the provider SDK uses custom timeout exceptions.
- Preserve `stdout`, `stderr`, and exit codes in `ExecResult`.
- Prefer native file APIs when available; otherwise inherit the base transfer implementation.
- Add tests for lifecycle cleanup, timeout classification, dead-backend errors, environment forwarding, and binary file transfer.
