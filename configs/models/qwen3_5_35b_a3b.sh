#!/usr/bin/env bash
# Qwen3.5-35B-A3B on Megatron/MindSpeed-Bridge + vLLM-Ascend.
# Sourced by orchestration and submission; keep it idempotent.
export MODEL_PATH="${MODEL_PATH:-/efs_rl/c00833002/models/Qwen3.5-35B-A3B}"
export TOOL_PARSER="${TOOL_PARSER:-qwen3_coder}"
export NNODES="${NNODES:-1}" NGPUS_PER_NODE="${NGPUS_PER_NODE:-16}"
export TP="${TP:-2}" PP="${PP:-1}" CP="${CP:-4}"
export EP="${EP:-8}" ETP="${ETP:-1}" GEN_TP="${GEN_TP:-4}"
MODEL_ARGS=(
    ++actor_rollout_ref.actor.megatron.override_transformer_config.moe_token_dispatcher_type=alltoall
    ++actor_rollout_ref.actor.megatron.override_transformer_config.moe_grouped_gemm=True
    ++actor_rollout_ref.actor.megatron.override_transformer_config.recompute_granularity=full
    ++actor_rollout_ref.actor.megatron.override_transformer_config.recompute_method=uniform
    ++actor_rollout_ref.actor.megatron.override_transformer_config.recompute_num_layers=1
    ++actor_rollout_ref.actor.megatron.override_transformer_config.moe_permute_fusion=False
    ++actor_rollout_ref.actor.megatron.override_transformer_config.use_flash_attn=True
    ++actor_rollout_ref.actor.megatron.override_transformer_config.use_naive_l2norm=True
    ++actor_rollout_ref.actor.megatron.override_transformer_config.attention_backend=auto
    ++actor_rollout_ref.actor.megatron.override_transformer_config.context_parallel_algo=megatron_cp_algo
    +actor_rollout_ref.rollout.engine_kwargs.vllm.compilation_config.cudagraph_mode=FULL_DECODE_ONLY
    +actor_rollout_ref.rollout.engine_kwargs.vllm.async_scheduling=False
    +actor_rollout_ref.rollout.engine_kwargs.vllm.no_disable_hybrid_kv_cache_manager=True
)
if [[ "${USE_MINDSPEED_BRIDGE:-True}" == True ]]; then
    MODEL_ARGS+=(
        ++actor_rollout_ref.actor.megatron.override_transformer_config.use_triton_gdn=False
        ++actor_rollout_ref.actor.megatron.override_transformer_config.use_ascend_gdn=True
    )
fi
