#!/usr/bin/env bash
# Model-independent deployment defaults. Inject secrets via platform environment
# or a private SANDBOX_ENV_FILE on the shared filesystem.
export KASANDBOX_TUNNEL_MODE="${KASANDBOX_TUNNEL_MODE:-ssh}"
export KASANDBOX_SSH_TARGET="${KASANDBOX_SSH_TARGET:-root@7.150.8.255}"
export KASANDBOX_SSH_PORT="${KASANDBOX_SSH_PORT:-22222}"
export KASANDBOX_API_PORT="${KASANDBOX_API_PORT:-9191}"
export KASANDBOX_PROXY_PORT="${KASANDBOX_PROXY_PORT:-9192}"
export KASANDBOX_REMOTE_API_PORT="${KASANDBOX_REMOTE_API_PORT:-9191}"
export KASANDBOX_REMOTE_PROXY_PORT="${KASANDBOX_REMOTE_PROXY_PORT:-9192}"
export E2B_API_URL="${E2B_API_URL:-http://127.0.0.1:$KASANDBOX_API_PORT}"
export E2B_SANDBOX_URL="${E2B_SANDBOX_URL:-http://127.0.0.1:$KASANDBOX_PROXY_PORT}"
export E2B_DOMAIN="${E2B_DOMAIN:-e2b.app}"
export CALLBACK_TUNNEL_ENABLED="${CALLBACK_TUNNEL_ENABLED:-true}"
export CALLBACK_RELAY_PORT="${CALLBACK_RELAY_PORT:-9193}"
export CALLBACK_GATEWAY_PORT="${CALLBACK_GATEWAY_PORT:-9195}"
export CALLBACK_ADVERTISED_BASE_URL="${CALLBACK_ADVERTISED_BASE_URL:-http://141.4.152.50:9193}"
export CALLBACK_RELAY_SSH_TARGET="${CALLBACK_RELAY_SSH_TARGET:-$KASANDBOX_SSH_TARGET}"
export CALLBACK_RELAY_SSH_PORT="${CALLBACK_RELAY_SSH_PORT:-$KASANDBOX_SSH_PORT}"
# Every fresh training container reads this shared binary; the agent uploads it
# through the sandbox Files API before launching Claude in each new sandbox.
export CLAUDE_CODE_LOCAL_BINARY="${CLAUDE_CODE_LOCAL_BINARY-/efs_rl/l00870118/claude_clade_binary/claude}"
if [[ "$CLAUDE_CODE_LOCAL_BINARY" == /efs_rl/l00870118/claude_clade_binary/claude ]]; then
    export CLAUDE_CODE_LOCAL_BINARY_SHA256="${CLAUDE_CODE_LOCAL_BINARY_SHA256:-e4daf793d1e74fb0d9874dd09e98690bbfd7be515f78a87fd05b9e2b4bb33b03}"
fi
if [[ -n "${CLAUDE_CODE_LOCAL_BINARY:-}" ]]; then
    [[ "$CLAUDE_CODE_LOCAL_BINARY" = /* && -f "$CLAUDE_CODE_LOCAL_BINARY" && -r "$CLAUDE_CODE_LOCAL_BINARY" ]] || {
        echo "CLAUDE_CODE_LOCAL_BINARY must be an absolute readable file on this worker" >&2
        exit 2
    }
    export CLAUDE_CODE_LOCAL_BINARY
fi
