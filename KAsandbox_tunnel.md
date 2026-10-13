## 2026-10-14: Claude callback directly through the PC

The callback is now configured separately from E2B_API_URL and E2B_SANDBOX_URL.
The platform still starts a fresh training container for each run. The reference
container kasandbox_uniagent_runner_001 is not a callback destination.

Request direction:

```text
Claude in KASandbox
  -> PC 141.4.152.50:9193 (user-created SSH local forward)
  -> 7.150.8.255 127.0.0.1:9193 (training-created SSH remote forward)
  -> current training container <HEAD_HOST>:9195 (uni-agent gateway)
  -> rollout backend
```

### PC command — run manually

Keep the existing API (9191) and client-proxy (9192) tunnels running.
Stop BOTH previous callback commands with Ctrl+C in their terminals: the local
forward bound to 127.0.0.1:9193 and the remote forward on 141.61.85.96:9194.
Then run this single replacement command and leave it running:

```powershell
ssh -g -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 141.4.152.50:9193:127.0.0.1:9193 root@7.150.8.255
```

A disposable sandbox reached a temporary PC listener at 141.4.152.50 and received
a unique response. Its connection to the PC's 100.105.236.137 address timed out.
The explicit PC bind address is required; loopback is unreachable from sandboxes.
No callback service or sshd/firewall changes are needed on the KASandbox server.
PC sleep, restart, or SSH disconnect breaks the bridge. If the PC address changes,
update the bind address and CALLBACK_ADVERTISED_BASE_URL together.

### If the PC address changes

The PC address is not guaranteed to stay at 141.4.152.50. Reconnecting the VPN,
changing networks, or restarting the PC may assign a different address.

1. Find the current IPv4 addresses in PowerShell:

   ```powershell
   Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias,IPAddress
   ```

   Choose the interface reachable from KASandbox. The verified address was on
   `usg0`; do not assume every listed address is reachable. Exclude loopback and
   `169.254.*` addresses. The previously tested `100.105.236.137` was unreachable.

2. Stop the old callback SSH command with Ctrl+C. Replace `NEW_PC_IP` below with
   the new address, then run this replacement command and leave it running:

   ```powershell
   ssh -g -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L NEW_PC_IP:9193:127.0.0.1:9193 root@7.150.8.255
   ```

3. In the platform's training launch command, set the matching callback origin.
   Replace `NEW_PC_IP` with the same address used above:

   ```bash
   cd /efs_rl/l50066035/uniagent-kasandbox/ && CALLBACK_ADVERTISED_BASE_URL=http://NEW_PC_IP:9193 USE_MINDSPEED_BRIDGE=True bash launch_uniagent_kasandbox.sh '+actor_rollout_ref.rollout.engine_kwargs.vllm.additional_config={weight_nz_mode:0}'
   ```

   Set this variable in the platform job, not just in your PC terminal. The
   launcher's built-in default remains the old address unless you also update
   its `CALLBACK_ADVERTISED_BASE_URL` default in the shared launch script.
   Existing jobs retain their old session URLs; start a new training run.

4. Verify that a sandbox can reach `NEW_PC_IP:9193` with the SSH command running.
   After the training gateway starts, run from inside a sandbox:

   ```bash
   curl --noproxy '*' --connect-timeout 5 --max-time 10 -i http://NEW_PC_IP:9193/
   ```

   HTTP 404 at `/` confirms that the gateway is reachable. A PC-side curl alone
   does not verify sandbox-to-PC connectivity. Before gateway startup the full
   HTTP check cannot succeed; a timeout afterward means the new address, tunnel,
   or network path needs checking.

Keep the API/client-proxy tunnels on 9191/9192 running, restarting them if the
network change disconnected SSH. Their commands and the callback ports remain
unchanged. No sandbox-server changes are needed for a PC address change.

### Training launch

Use the same platform command for a new run. Existing jobs retain the old URL:

```bash
cd /efs_rl/l50066035/uniagent-kasandbox/ && USE_MINDSPEED_BRIDGE=True bash launch_uniagent_kasandbox.sh '+actor_rollout_ref.rollout.engine_kwargs.vllm.additional_config={weight_nz_mode:0}'
```

The launcher starts a reverse forward through 7.150.8.255:22222:
relay 127.0.0.1:9193 -> this job's HEAD_HOST:9195.
It waits for SSH forwarding confirmation, fails if the relay port is occupied,
and closes its own SSH control connection when the launcher exits. The gateway
binds its Ray node address on port 9195. Its session URLs advertise
http://141.4.152.50:9193/sessions/<session-id>/v1.
Claude receives ANTHROPIC_BASE_URL without the trailing /v1 and requests
/sessions/<session-id>/v1/messages.

This route supports one active training job, one Ray CPU node and one gateway.
The manager rejects an advertised route with multiple gateways or CPU nodes.
Do not override gateway_listen_port independently of CALLBACK_GATEWAY_PORT.
Additional jobs require separate relay ports, PC forwards, and callback listeners.

Launcher settings, if a coordinated port change is needed:

- CALLBACK_GATEWAY_PORT=9195: training gateway bind port.
- CALLBACK_RELAY_PORT=9193: loopback port reserved on 7.150.8.255.
- CALLBACK_ADVERTISED_BASE_URL=http://141.4.152.50:9193: sandbox-facing PC origin.
- CALLBACK_RELAY_SSH_TARGET=root@7.150.8.255 and CALLBACK_RELAY_SSH_PORT=22222.
- CALLBACK_SSH_PASSWORD: defaults to the launcher's existing relay credential;
  set it to an empty string to use SSH keys instead.

The launcher supplies gateway_listen_port and gateway_advertised_base_url through
Hydra. No callback credentials or extra environment variables need to be copied
into the Ray runtime JSON.

### Removed KASandbox host component

The previous uniagent-callback service was stopped and disabled. Its unit at
/etc/systemd/system/uniagent-callback.service, enablement symlink, and
/opt/uniagent-callback directory were removed. Unused relay source and service
files were also removed from the training repository. Historical journal entries
may remain. No KASandbox application, firewall, or sshd configuration was changed.
The user-owned SSH remote forward on 9194 remains until stopped in its terminal.

After the job's gateway has started, this PC-side check exercises the callback chain:

```powershell
curl.exe --noproxy "*" --max-time 10 -i http://141.4.152.50:9193/
```

An HTTP 404 at / is expected: the gateway uses session routes. A connection reset
or timeout means a forwarding hop is missing; before gateway startup this check
cannot succeed. The job logs the listening address and advertised origin.
The PC tunnels are intentionally started by the user, not by the training code.



# 试运行记录

## 2026-10-14：修复 Sandbox readiness probe 失败

原有 `9191 -> 3000` 链路只转发 KASandbox API。SDK 的健康检查、命令执行和文件操作还需要访问 client-proxy。

已验证本机可访问 `141.61.85.96:3002`。未提供 sandbox 路由信息时，该端口返回 `400 Invalid host`，表示 HTTP 服务可达，并不代表某个 sandbox 已就绪。

新增链路：

```text
云上训练容器 127.0.0.1:9192
  -> SSH 7.150.8.255:22222
  -> 7.150.8.255 127.0.0.1:9192
  -> 本机 PC 的 reverse SSH tunnel
  -> 141.61.85.96:3002 (client-proxy)
```

在本机 PC 保持以下命令运行（可在 PowerShell 中运行）：

```bash
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 127.0.0.1:9192:141.61.85.96:3002 root@7.150.8.255
```

验证时启动的 PC 后台隧道已停止，改由用户在前台终端运行上述命令，使用 Ctrl+C 停止。PC 休眠、重启或 SSH 断开后需要重新启动；启动前确认旧隧道已退出，避免端口冲突。原有 API 隧道仍需保持运行。

远端 `/efs_rl/l50066035/uniagent-kasandbox/launch_uniagent_kasandbox.sh` 已增加训练容器到 relay 的 `9192` 转发，并在 `prepare_runtime.py` 前设置：

```bash
export E2B_SANDBOX_URL=http://127.0.0.1:9192
```

`prepare_runtime.py` 会将该变量写入 Ray runtime 环境。原 launcher 备份为 `launch_uniagent_kasandbox.sh.bak.proxy-9192`。

验证结果：在参考容器中使用模板 `zd8n9j50mzyi43lpfa0h`，通过 PC 隧道以及额外经过 SSH `22222` 的完整转发路径，均成功创建 sandbox、通过 `is_running()`、执行简单命令并删除 sandbox。launcher 通过 `bash -n`。尚未重新运行云端训练任务。

此链路修复的是训练端到 sandbox 的访问。sandbox 内 Claude Code 到训练 gateway 的模型请求是另一方向，仍需单独验证。

## 本地中转

**日期 2026-10-13**

### 链路设计

云上机器:9191
| （不能用22端口）
7.150.8.255:9191
|
PC:141.61.85.96:3000

### PC 可达性验证

curl -sS --noproxy '*' --max-time 30  'http://141.61.85.96:3000/templates' -H "X-API-Key: e2b_6435cfe54f276adb9d692d5b29c4c9645f7e077a" | python3 -m json.tool

### 操作记录

**PC中转：PC本地运行**

```bash
ssh -N -R 9191:141.61.85.96:3000 root@7.150.8.255 # 7.150.8.255:9191 -> PC:141.61.85.96:3000
```

**操作结果**

7.150.8.255 能够通过 127.0.0.1:9191 访问沙箱服务器

之后修改

```bash
export E2B_API_URL=http://127.0.0.1:9191
```

**云上机器到 7.150 机器**

- 需要手动在 7.150.8.255 非 22 端口上启动 sshd 服务

    ```bash
    /usr/sbin/sshd -p 22222 # 在 22222 端口上启动 sshd 服务
    ss -tlnp | grep ssh # 检查 sshd 服务是否被正确启动

    # ss: socket statistics; 用于查看 Linux 网络 socket 状态
    # -t: TCP
    # -l: listening
    # -n: 不解析名字，直接显示端口
    # -p: 显示对应进程
    ```


- 云上机器 发起 ssh 连接
    ```bash
    sshpass -p 'CodeAgent123' ssh -o StrictHostKeyChecking=no -p 22222 -f -N -L 127.0.0.1:9191:127.0.0.1:9191 root@7.150.8.255 &
    ```

之后在云上机器上通过 127.0.0.1:9191 访问沙箱

## 其他修改

/efs_rl/l50066035/uniagent-kasandbox/examples/e2b_swe_grpo/train_megatron_npu.sh
L87：移除了 --no-wait 参数

根据 /efs_rl/l50066035/uniagent-kasandbox/examples/e2b_swe_grpo/LAUNCH_INSTRUCTIONS.md，修改了部分参数，将多个步骤的代码块整合为 /efs_rl/l50066035/uniagent-kasandbox/launch_uniagent_kasandbox.sh 文件

### 运行命令

cd /efs_rl/l50066035/uniagent-kasandbox/ && bash launch_uniagent_kasandbox.sh |& tee "./logs/uniagent_kasandbox_$(date -u -d '+8 hours' +'%Y%m%d_%H%M%S').log"
