#!/usr/bin/env bash
# Platform entry point: run on every node in each fresh training container.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export MODEL_PROFILE="${MODEL_PROFILE:-$ROOT/configs/models/qwen3_5_35b_a3b.sh}"
source "$MODEL_PROFILE"
source "${TRAINING_ENV_CONFIG:-$ROOT/scripts/training/ascend.sh}"
source "${EXPERIMENT_CONFIG:-$ROOT/examples/e2b_swe_grpo/experiment.sh}"
source "$ROOT/scripts/sandbox/setup.sh"
trap stop_sandbox EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

: "${VC_WORKER_HOSTS:?Platform must supply VC_WORKER_HOSTS}"
: "${VC_TASK_INDEX:?Platform must supply VC_TASK_INDEX}"
HEAD_HOST="${VC_WORKER_HOSTS%%,*}"
setup_sandbox

if [[ "$VC_TASK_INDEX" == 0 ]]; then
    # Private per-launch output avoids concurrent writers on the shared mount.
    if [[ -z "${RUNTIME_ENV:-}" ]]; then
        mkdir -p "$ROOT/.runtime"
        RUNTIME_ENV=$(mktemp "$ROOT/.runtime/ray.XXXXXX.json")
    fi
    export RUNTIME_ENV
    python3 "$ROOT/scripts/training/prepare_runtime.py" \
        --verl-source "${VERL_SOURCE:-/verl}" --output "$RUNTIME_ENV"
    ray start --head --port=6379 --dashboard-host=0.0.0.0 --node-ip-address="$HEAD_HOST"
    start_sandbox_callback
    gateway_args=()
    if [[ "$CALLBACK_TUNNEL_ENABLED" == true ]]; then
        gateway_args+=(
            "++actor_rollout_ref.rollout.custom.agent_framework.gateway_listen_port=$CALLBACK_GATEWAY_PORT"
            "++actor_rollout_ref.rollout.custom.agent_framework.gateway_advertised_base_url=$CALLBACK_ADVERTISED_BASE_URL"
        )
    fi
    # Keep this shell alive to own tunnels until the blocking submission ends.
    bash "${EXPERIMENT_LAUNCHER:-$ROOT/examples/e2b_swe_grpo/launch.sh}" --submit \
        "${gateway_args[@]}" "${EXPERIMENT_ARGS[@]}" "$@"
else
    until ray start --address="$HEAD_HOST:6379"; do sleep 5; done
    sleep infinity
fi
