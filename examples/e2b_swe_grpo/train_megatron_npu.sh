#!/usr/bin/env bash
# Compatibility entry point; model/backend setup lives outside the E2B recipe.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$root/scripts/training/train_megatron_npu.sh" "$@"
