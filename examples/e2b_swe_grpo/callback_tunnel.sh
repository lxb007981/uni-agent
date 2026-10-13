#!/usr/bin/env bash
# Compatibility wrapper for callers that rely on callback cleanup traps.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)/scripts/sandbox/callback_tunnel.sh"
trap stop_callback_tunnel EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
