"""SWE-bench task: one problem family, solved by whichever agent you configure."""

from __future__ import annotations

import json
import logging

from pydantic import Field

from ..base import Task, TaskConfig, TaskResult
from ..registry import register_task

logger = logging.getLogger(__name__)


class SWEBenchTaskConfig(TaskConfig):
    name: str = "swe_bench"
    run_oracle_solution: bool = Field(
        default=False,
        description="Oracle mode: skip the agent and score the dataset's gold patch directly.",
    )
    score_agent_timeout: bool = Field(
        default=False,
        description="Score an E2B agent wall-time budget exhaustion as zero without evaluating a deleted sandbox.",
    )
    eval_timeout: float = Field(
        default=600.0,
        description="Per-sample reward-eval timeout (s) inside the sandbox.",
    )


@register_task("swe_bench")
class SWEBenchTask(Task):
    name = "swe_bench"
    config_model = SWEBenchTaskConfig

    async def run(self) -> TaskResult:
        cfg: SWEBenchTaskConfig = self.config  # type: ignore[assignment]
        sample = cfg.metadata  # the dataset sample is carried on the task config

        instance_id = sample.get("instance_id", "?") if isinstance(sample, dict) else "?"
        task_config_dump = cfg.model_dump(mode="json", exclude={"metadata", "prompt"})
        logger.info(
            f"starting swe_bench task (instance_id={instance_id}, run_oracle_solution={cfg.run_oracle_solution})\n"
            f"task config: {json.dumps(task_config_dump, indent=2)}"
        )
        sandbox_instance = self.build_sandbox()
        if sandbox_instance.provider == "e2b":
            expected = getattr(sandbox_instance, "expected_instance_id", None)
            if expected != instance_id:
                raise ValueError(f"E2B template binding mismatch: expected {expected!r}, sample {instance_id!r}")
        async with sandbox_instance as sandbox:
            if sandbox.provider == "e2b":
                base_commit = sample.get("base_commit")
                if not isinstance(base_commit, str) or not base_commit.strip():
                    raise ValueError("E2B SWE task requires base_commit")
                # Preserve the template's setup commits while discarding changes
                # left in its working tree. Keep ignored build/dependency files.
                for argv in (
                    ["git", "config", "--global", "--add", "safe.directory", "/testbed"],
                    # Imported templates may contain root-owned nested directories.
                    ["sh", "-c", 'sudo -n chown -R -- "$(id -u):$(id -g)" /testbed'],
                    ["git", "reset", "--hard", "HEAD"],
                    ["git", "clean", "-fd"],
                ):
                    result = await sandbox.exec(argv, workdir="/testbed", timeout=30)
                    if result.exit_code != 0:
                        raise RuntimeError(
                            f"Template repository preparation failed ({' '.join(argv)}): "
                            f"exit_code={result.exit_code}, stderr={result.stderr.strip()!r}"
                        )
                clean = await sandbox.exec(
                    ["git", "status", "--porcelain", "--untracked-files=all"],
                    workdir="/testbed", timeout=30,
                )
                if clean.exit_code != 0 or clean.stdout.strip():
                    raise RuntimeError(
                        "Template repository cleanup failed: "
                        f"exit_code={clean.exit_code}, stdout={clean.stdout.strip()!r}, "
                        f"stderr={clean.stderr.strip()!r}"
                    )
            agent_error = None
            if cfg.run_oracle_solution:
                logger.info("applying gold patch to /testbed")
                await sandbox.write_file("/tmp/gold_patch.patch", sample["patch"])
                applied = await sandbox.exec(
                    ["git", "apply", "--whitespace=fix", "/tmp/gold_patch.patch"], workdir="/testbed",
                )
                if applied.exit_code != 0:
                    raise RuntimeError("Oracle patch failed to apply")
                finished = True
            else:
                agent = self.build_agent()
                messages = cfg.prompt
                # The endpoint the agent calls lives on cfg.agent.model (the agent validates it).
                agent_result = await agent.run(
                    sandbox=sandbox,
                    messages=messages,
                    workdir="/testbed",
                )
                finished = agent_result.finished
                agent_error = agent_result.info.get("error")
                if (
                    cfg.score_agent_timeout
                    and not finished
                    and getattr(sandbox, "command_budget_exhausted", False)
                ):
                    return TaskResult(
                        reward=0.0, accuracy=0.0, finished=False,
                        extra_info={"agent_budget_exhausted": True, "eval_completed": False},
                    )

            from .reward import compute_reward

            result = await compute_reward(sample, sandbox, eval_timeout=cfg.eval_timeout)
            if isinstance(agent_error, str) and agent_error.strip():
                result = {**result, "agent_error": agent_error}

            logger.info(f"task done: resolved={result['resolved']}")
            return TaskResult(
                reward=float(result["resolved"]),
                accuracy=float(result["resolved"]),
                finished=finished,
                extra_info=result,
            )
