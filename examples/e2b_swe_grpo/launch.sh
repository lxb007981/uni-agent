#!/usr/bin/env bash
# Default is command rendering only. --submit is required to contact Ray.
set -euo pipefail
mode=${1:---dry-run}
case "$mode" in --dry-run|--submit) shift "$(( $# > 0 ? 1 : 0 ))";; *) echo "Use --dry-run or --submit" >&2; exit 2;; esac
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"
export MODEL_PROFILE="${MODEL_PROFILE:-$root/configs/models/qwen3_5_35b_a3b.sh}"
source "$MODEL_PROFILE"
: "${MODEL_PATH:?Set the policy model path}"
: "${RUNTIME_ENV:?Generate a private runtime JSON first}"
: "${TRAIN_FILE:?Prepare bound training data}"
: "${TEST_FILE:?Set the required validation file path (it may be empty)}"
: "${NNODES:?Set training node count}"
: "${NGPUS_PER_NODE:?Set NPUs per node}"
export TP=${TP:-1} PP=${PP:-1} CP=${CP:-1} ETP=${ETP:-1}
: "${EP:?Set supported expert parallel size}"
: "${GEN_TP:?Set rollout tensor parallel size}"
[[ -f "$RUNTIME_ENV" && -f "$TRAIN_FILE" && -f "$TEST_FILE" ]] || { echo "Missing runtime/data files" >&2; exit 2; }
for name in NNODES NGPUS_PER_NODE TP PP CP EP ETP GEN_TP; do
    [[ "${!name}" =~ ^[1-9][0-9]*$ ]] || { echo "$name must be a positive integer" >&2; exit 2; }
done
world=$((NNODES * NGPUS_PER_NODE))
(( world % (TP * PP * CP) == 0 && world % (ETP * EP * PP) == 0 && world % GEN_TP == 0 )) || {
    echo "NPU count must be divisible by TP*PP*CP, ETP*EP*PP, and GEN_TP" >&2; exit 2;
}
if (( TP > 1 )); then
    export SEQUENCE_PARALLEL=${SEQUENCE_PARALLEL:-True}
else
    export SEQUENCE_PARALLEL=False
fi
export TASK_CONFIG="${TASK_CONFIG:-$root/examples/e2b_swe_grpo/task_config.yaml}"
export ADV_ESTIMATOR=grpo LOSS_MODE=vanilla CLIP_RATIO_LOW=0.2 CLIP_RATIO_HIGH=0.2
export CONCURRENCY=${CONCURRENCY:-4} GATEWAY_COUNT=${GATEWAY_COUNT:-1}
export TRAIN_PROMPT_BSZ=${TRAIN_PROMPT_BSZ:-1} PPO_MINI_BATCH_SIZE=${PPO_MINI_BATCH_SIZE:-1}
dp=$((world / (TP * PP * CP)))
default_responses=$(((4 + dp - 1) / dp * dp))
export N_RESP_PER_PROMPT=${N_RESP_PER_PROMPT:-$default_responses}
export MAX_PROMPT_LENGTH=${MAX_PROMPT_LENGTH:-16384} MAX_RESPONSE_LENGTH=${MAX_RESPONSE_LENGTH:-16384}
export PROJECT_NAME=${PROJECT_NAME:-E2B-Claude-GRPO-Megatron-NPU}
export RAY_DATA_HOME=${RAY_DATA_HOME:-"$root/.artifacts"}
for name in TRAIN_PROMPT_BSZ PPO_MINI_BATCH_SIZE N_RESP_PER_PROMPT; do
    [[ "${!name}" =~ ^[1-9][0-9]*$ ]] || { echo "$name must be a positive integer" >&2; exit 2; }
done
[[ "$N_RESP_PER_PROMPT" -ge 2 ]] || { echo "GRPO needs multiple samples per prompt" >&2; exit 2; }
(( TRAIN_PROMPT_BSZ % PPO_MINI_BATCH_SIZE == 0 &&
   (PPO_MINI_BATCH_SIZE * N_RESP_PER_PROMPT) % dp == 0 )) || {
    echo "Prompt batch must divide into PPO minibatches; minibatch trajectories must divide across $dp data-parallel ranks" >&2
    exit 2
}
if [[ "$mode" == --dry-run ]]; then
    ray() { printf '%q ' ray "$@"; printf '\n'; }
    export -f ray
fi
exec bash "${TRAIN_SCRIPT:-$root/scripts/training/train_megatron_npu.sh}" \
    ++actor_rollout_ref.rollout.custom.agent_framework.agent_runners.task.trajectory_selection=longest \
    ++actor_rollout_ref.rollout.custom.agent_framework.agent_runners.task.session_timeout_seconds=7500 \
    ++actor_rollout_ref.rollout.custom.agent_framework.mask_unfinished_episode=False \
    trainer.logger='[console]' \
    "$@"
