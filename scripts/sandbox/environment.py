"""Environment forwarded to sandbox/agent workers, independent of the policy."""
import os


def worker_environment():
    required = ("E2B_API_KEY", "E2B_API_URL")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise SystemExit(f"Missing environment variables: {missing}")
    env = {key: os.environ[key] for key in (
        *required, "E2B_DOMAIN", "E2B_SANDBOX_URL",
        "CLAUDE_CODE_LOCAL_BINARY", "CLAUDE_CODE_LOCAL_BINARY_SHA256",
    ) if os.environ.get(key)}
    env["E2B_DEBUG"] = "false"
    return env
