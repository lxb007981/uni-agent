# E2B SWE-Bench training

The platform entry point is `launch_uniagent_kasandbox.sh` at the repository
root. It runs inside every fresh platform container using the shared checkout.
`kasandbox_uniagent_runner_003` is a reference environment, not a container that
the launcher starts or depends on.

## Configuration boundaries

| Location | Responsibility |
| --- | --- |
| `configs/sandbox/kasandbox.sh` | Shared E2B endpoints, relay ports, callback URL and Claude binary |
| `scripts/sandbox/setup.sh` | Per-node API/proxy tunnels, health check and cleanup |
| `scripts/sandbox/callback_tunnel.sh` | Gateway callback tunnel lifecycle |
| `scripts/sandbox/environment.py` | Sandbox/Claude environment forwarded to Ray workers |
| `configs/models/qwen3_5_35b_a3b.sh` | Model path, parser, parallelism and Qwen-specific Hydra options |
| `scripts/training/ascend.sh` | Ascend/HCCL/vLLM process environment before Ray starts |
| `scripts/training/train_megatron_npu.sh` | Megatron GRPO submission and Uni-Agent integration |
| `scripts/training/prepare_runtime.py` | Private Ray runtime JSON composed with sandbox environment |
| `examples/e2b_swe_grpo/experiment.sh` | Dataset paths, batch sizes, output paths and one-step smoke defaults |
| `examples/e2b_swe_grpo/launch.sh` | SWE recipe validation and submit/dry-run handoff |
| `examples/e2b_swe_grpo/task_config.yaml` | Agent/task timeouts, prompt and sandbox provider |
| `examples/e2b_swe_grpo/templates.json` | Task-to-sandbox-template bindings, independent of the policy |

To incorporate another model on the same backend, create a model profile and
set `MODEL_PROFILE=/absolute/path/to/profile.sh`. The profile exports model path,
parser and topology, and defines a Bash `MODEL_ARGS` array (empty is valid).
Do not source the Qwen profile for an unrelated model: it carries Qwen-specific
transformer and vLLM options. Explicit user Hydra arguments are appended last.
Sandbox settings and task/template bindings do not need changes.

A different training backend can select `TRAIN_SCRIPT`; a different platform
runtime can select `TRAINING_ENV_CONFIG`. Different task/experiment setups can
select `TASK_CONFIG`, `EXPERIMENT_CONFIG` and `EXPERIMENT_LAUNCHER`. All config
paths should be absolute. Shell profiles are trusted code, not dotenv files.
`EXPERIMENT_CONFIG` defines an `EXPERIMENT_ARGS` array. `TRAIN_SCRIPT` receives
Hydra arguments, while `EXPERIMENT_LAUNCHER` receives `--submit` followed by those
arguments. The provided SWE launcher still performs Megatron topology checks;
a backend with different constraints should provide its own experiment launcher.

The example-local `prepare_runtime.py`, `train_megatron_npu.sh` and
`callback_tunnel.sh` remain compatibility entry points.

See [LAUNCH_INSTRUCTIONS.md](LAUNCH_INSTRUCTIONS.md) for platform usage,
networking, secrets, validation, and the known-good launch command.

## Dataset and task behavior

`templates.json` binds 33 supplied templates to SWE-Bench instances. Prepare
training data independently of model choice:

```bash
python examples/e2b_swe_grpo/prepare_data.py \
  --source /efs_rl/l50066035/data/swe_agent/swe_bench_verified_modified_yuanrong.parquet \
  --output-dir .artifacts/e2b-django
```

Each row owns its template binding; there is no global template fallback.
Missing or duplicate instances and reused templates are rejected. All selected
rows are training data; the emitted validation parquet is empty. The default
smoke experiment reuses training data for the trainer's required validation
loader. It is not held-out evaluation.

The task verifies binding identity, repository HEAD and a clean tree before
agent execution. Templates provide `/testbed`, original dependencies and the
`testbed` conda environment. Claude is the agent harness; the served policy is
the model being trained. The shared Claude binary is uploaded into each new
sandbox, independent of the model profile.

Known agent wall-time exhaustion receives zero reward without evaluating the
deleted sandbox. Transport failures remain failed sessions. This refactor does
not change provider, agent, reward, template, or task timeout behavior.

## Validation record

The original 2026-10-14 run completed one training step and Ray reported job
`raysubmit_ShHNzM9FXpk2U842` succeeded. Its log also contains a subsequent shell
input-file error; Ray success alone does not establish a clean launcher exit.

The refactor was checked using Bash syntax, Python AST parsing, whitespace
validation, an exact argument multiset/effective-value comparison against the
original recipe, and stubbed platform head/worker flows in the reference
container. Checks covered success/failure cleanup, direct networking, private
runtime generation, and selecting a different model profile. No new training
or sandbox job was launched to validate the refactor.
