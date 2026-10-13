#!/usr/bin/env bash
# Source on the gateway node. Caller owns cleanup and must remain alive.
# Authentication uses CALLBACK_SSH_PASSWORD if supplied, otherwise SSH keys.
start_callback_tunnel() {
    [[ "${NNODES}" == 1 && "${GATEWAY_COUNT}" == 1 ]] || {
        echo "The callback relay requires NNODES=1 and GATEWAY_COUNT=1" >&2
        return 2
    }
    for port in "$CALLBACK_RELAY_PORT" "$CALLBACK_GATEWAY_PORT"; do
        [[ "$port" =~ ^[0-9]+$ ]] && (( port > 0 && port < 65536 )) || {
            echo "Invalid callback port: $port" >&2
            return 2
        }
    done
    CALLBACK_CONTROL_DIR=$(mktemp -d /tmp/uniagent-callback.XXXXXX)
    CALLBACK_CONTROL_SOCKET="$CALLBACK_CONTROL_DIR/ssh"
    local -a auth=()
    if [[ -n "${CALLBACK_SSH_PASSWORD:-}" ]]; then
        auth=(sshpass -e)
    fi
    SSHPASS="${CALLBACK_SSH_PASSWORD:-}" "${auth[@]}" ssh \
        -o StrictHostKeyChecking=no -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
        -o ConnectTimeout=15 -o ControlPersist=no \
        -M -S "$CALLBACK_CONTROL_SOCKET" -f -N -T \
        -p "${CALLBACK_RELAY_SSH_PORT:-22222}" \
        -R "127.0.0.1:${CALLBACK_RELAY_PORT}:${HEAD_HOST}:${CALLBACK_GATEWAY_PORT}" \
        "${CALLBACK_RELAY_SSH_TARGET:-root@7.150.8.255}"
    # -f plus ExitOnForwardFailure waits for remote forwarding confirmation.
    ssh -S "$CALLBACK_CONTROL_SOCKET" -O check \
        "${CALLBACK_RELAY_SSH_TARGET:-root@7.150.8.255}"
    echo "Callback relay 127.0.0.1:$CALLBACK_RELAY_PORT -> $HEAD_HOST:$CALLBACK_GATEWAY_PORT"
}

stop_callback_tunnel() {
    if [[ -n "${CALLBACK_CONTROL_SOCKET:-}" ]]; then
        ssh -S "$CALLBACK_CONTROL_SOCKET" -O exit \
            "${CALLBACK_RELAY_SSH_TARGET:-root@7.150.8.255}" 2>/dev/null || true
        rm -f -- "$CALLBACK_CONTROL_SOCKET"
        rmdir -- "$CALLBACK_CONTROL_DIR" 2>/dev/null || true
    fi
}
