# Launching from fresh platform containers

Use the shared checkout `/efs_rl/l50066035/uniagent-kasandbox` on each platform
worker. The reference container `kasandbox_uniagent_runner_003` is only useful
for inspecting the installed stack; no launcher command enters it.

## Existing Qwen3.5 command

The command from the successful experiment remains valid:

```bash
cd /efs_rl/l50066035/uniagent-kasandbox/
USE_MINDSPEED_BRIDGE=True USE_REMOVE_PADDING=True \
  bash launch_uniagent_kasandbox.sh \
  '+actor_rollout_ref.rollout.engine_kwargs.vllm.additional_config={weight_nz_mode:0}'
```

The platform supplies `VC_WORKER_HOSTS` and `VC_TASK_INDEX` in every fresh
container. The head starts Ray and submits the experiment; other workers set up
sandbox access, join Ray, and remain alive. Each node runs its own sandbox
setup before Ray starts, so actor processes inherit the required environment.
The parent shell stays alive until submission ends, then closes the SSH
connections it created, including the head callback tunnel. A failure exit
status from submission is preserved.

The default profile is `configs/models/qwen3_5_35b_a3b.sh`, using 16 NPUs,
TP=2, PP=1, CP=4, EP=8, ETP=1 and rollout TP=4. The experiment defaults to one
step, four responses, no checkpoint saving and resume disabled. Environment
variables override defaults; Hydra arguments supplied on the command line
are appended last.

## Shared sandbox setup

`configs/sandbox/kasandbox.sh` holds deployment settings shared by all policies:
API and command/file proxy endpoints, SSH relay, callback ports/URL, and the
Claude executable path and hash. No model or optimizer settings belong there.

Authentication comes from platform-injected `E2B_API_KEY` and optionally
`KASANDBOX_SSH_PASSWORD`; SSH keys are used when the password is unset/empty.
For this existing shared deployment, the previous inline credentials were
moved to `.runtime/kasandbox.env` with mode 0600, preserving the existing command.
That file is ignored by Git and excluded from Ray uploads. Its assignments
preserve platform-injected values. Fresh containers must mount the shared
checkout, or inject credentials through the platform.

Set `SANDBOX_ENV_FILE=/absolute/private/file` for a different secrets file;
set it to an empty string to disable file loading. An explicitly requested
missing file is an error. `CALLBACK_SSH_PASSWORD` can override callback-only
authentication. SSH passwords are not included in the Ray runtime JSON.

Default networking retains the existing deployment:

- Per-node loopback 9191 forwards through the relay to the E2B API.
- Per-node loopback 9192 forwards through the relay to the command/file proxy.
- The head callback forwards relay 9193 to gateway port 9195.
- The advertised callback base URL is `http://141.4.152.50:9193`; the existing
  bridge forwarding must already be available. Session paths remain intact.

Local and remote API/proxy ports can be configured separately using
`KASANDBOX_API_PORT`, `KASANDBOX_PROXY_PORT`, `KASANDBOX_REMOTE_API_PORT`, and
`KASANDBOX_REMOTE_PROXY_PORT`. The current callback routing supports
`NNODES=1` and `GATEWAY_COUNT=1`; the script retains this guard because gateways
otherwise need explicit routing/placement. Fixed default ports allow one run
per network namespace/relay binding; allocate distinct ports and bridge routes
before running concurrent experiments.

For endpoints reachable directly from every worker, use
`KASANDBOX_TUNNEL_MODE=direct`, `E2B_API_URL`, and `E2B_SANDBOX_URL`.
If sandboxes can directly reach the gateway actors, also set
`CALLBACK_TUNNEL_ENABLED=false`; the framework then uses its native gateway
addresses. Direct API access alone does not imply callback reachability.

Sandbox setup can be reused without training:

```bash
source scripts/sandbox/setup.sh
trap stop_sandbox EXIT
setup_sandbox
# Run the desired sandbox client/agent process here.
```

The callback helper is optional and requires the gateway host/ports plus its
single-node/single-gateway constraints. The reusable sandbox scripts never
start Ray, load a model, or submit training.

## Another model or experiment

Create a profile using the interface described in [README.md](README.md), then:

```bash
MODEL_PROFILE=/shared/configs/my_model.sh \
  bash launch_uniagent_kasandbox.sh trainer.total_training_steps=100
```

The model profile owns model path, parser, parallelism and `MODEL_ARGS`.
The same sandbox configuration, Claude binary and dataset bindings are reused.
Profiles must match the installed training backend and available resources;
selecting a file does not install support for a new architecture.

Use `EXPERIMENT_CONFIG` for another dataset/batching recipe and
`TRAINING_ENV_CONFIG` for another accelerator environment. Keep E2B settings in
`SANDBOX_CONFIG` (defaults to the shared KASandbox profile).

## Fresh image requirements

The platform image must already contain compatible Python, Ray, Uni-Agent,
verl, torch-npu, CANN/HCCL, Megatron, MindSpeed/MindSpeed-Bridge, vLLM-Ascend,
TransferQueue, SWE-Bench dependencies and the KASandbox-compatible E2B SDK.
The launcher does not install packages or rely on manual edits in the reference
container. It uses `/verl` by default; override `VERL_SOURCE` when needed.
The generated runtime prepends this checkout and verl to `PYTHONPATH`, so an
editable install pointing to another checkout does not select the wrong source.

The shared filesystem must expose datasets, model weights, Claude binary and
output paths at identical locations on relevant workers. The Claude binary is
validated on every worker; set `CLAUDE_CODE_LOCAL_BINARY` empty only when the
sandbox's existing binary or normal agent installation path should be used.

The head generates a unique `.runtime/ray.*.json` with mode 0600, containing
E2B/Claude worker variables and the Python source paths. `RUNTIME_ENV` can select
an explicit output path; it is regenerated for the launch. The runtime excludes
`.git`, `.runtime`, `.artifacts` and logs from upload, and uses installed image
dependencies. It does not create another container.

## Offline command rendering

This path does not set up tunnels, start Ray or contact sandbox services:

```bash
export ROOT="$PWD"
export MODEL_PROFILE="$ROOT/configs/models/qwen3_5_35b_a3b.sh"
source "$MODEL_PROFILE"
source examples/e2b_swe_grpo/experiment.sh
# Inject E2B_API_KEY and E2B_API_URL before generating the private runtime.
python examples/e2b_swe_grpo/prepare_runtime.py \
  --verl-source /verl --output .runtime/offline.json
export RUNTIME_ENV="$ROOT/.runtime/offline.json"
bash examples/e2b_swe_grpo/launch.sh --dry-run \
  "${EXPERIMENT_ARGS[@]}" \
  '+actor_rollout_ref.rollout.engine_kwargs.vllm.additional_config={weight_nz_mode:0}'
```

Inspect model/parser/topology, task configuration and user overrides in the
rendered command. Template provisioning and dataset preparation are independent
of model selection. This refactor preserves the existing task timeout values;
review their relationship separately before extending agent/evaluator budgets.
