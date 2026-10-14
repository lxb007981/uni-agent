#!/usr/bin/env bash
# Task/data and smoke-experiment defaults; no model or sandbox network settings.
export TRAIN_FILE="${TRAIN_FILE:-$ROOT/.artifacts/e2b-django/train.parquet}"
# A nonempty validation loader is required even with evaluation disabled.
# Reusing training data is smoke validation, not held-out evaluation.
export TEST_FILE="${TEST_FILE:-$TRAIN_FILE}"
export TRAIN_PROMPT_BSZ="${TRAIN_PROMPT_BSZ:-1}"
export PPO_MINI_BATCH_SIZE="${PPO_MINI_BATCH_SIZE:-1}"
export N_RESP_PER_PROMPT="${N_RESP_PER_PROMPT:-4}"
export CONCURRENCY="${CONCURRENCY:-4}" GATEWAY_COUNT="${GATEWAY_COUNT:-1}"
export MAX_PROMPT_LENGTH="${MAX_PROMPT_LENGTH:-24576}"
export MAX_RESPONSE_LENGTH="${MAX_RESPONSE_LENGTH:-65536}"
export EXP_NAME="${EXP_NAME:-e2b_django_megatron_grpo_$(date +%Y%m%d_%H%M%S)}"
export CKPTS_DIR="${CKPTS_DIR:-$ROOT/.artifacts/ckpts/$EXP_NAME}"
export AGENT_LOG_DIR="${AGENT_LOG_DIR:-$ROOT/.artifacts/logs/$EXP_NAME}"
EXPERIMENT_ARGS=(
    trainer.total_training_steps=10
    trainer.save_freq=-1
    trainer.resume_mode=disable
)
