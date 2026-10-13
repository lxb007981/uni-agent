"""Offline preflight: inspect dependencies and bound data without importing torch or calling services."""
import argparse
import importlib.metadata
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
import yaml

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--data-dir", required=True)
parser.add_argument("--runtime-env", required=True)
parser.add_argument("--model-path", required=True)
parser.add_argument("--allow-smoke", action="store_true")
args = parser.parse_args()
errors = []
root = Path(__file__).resolve().parents[2]
info = json.loads((Path(args.data_dir) / "dataset_info.json").read_text())
if info["smoke_only"] and not args.allow_smoke:
    errors.append("Smoke-mode data requires --allow-smoke; it is not held-out evaluation")
ids = {}
for split in ("train", "validation"):
    rows = pq.read_table(Path(args.data_dir) / f"{split}.parquet").to_pylist()
    ids[split] = set()
    for row in rows:
        task = row["extra_info"]["tools_kwargs"]["task"]
        iid = task["metadata"]["instance_id"]
        binding = task["sandbox"]["sandbox_kwargs"]
        if task["name"] != "swe_bench" or task["sandbox"]["provider"] != "e2b":
            errors.append(f"{split}: incorrect task/provider for {iid}")
        if binding.get("expected_instance_id") != iid or not binding.get("template"):
            errors.append(f"{split}: invalid template binding for {iid}")
        ids[split].add(iid)
    if not rows and split == "train":
        errors.append("train is empty")
if ids["train"] & ids["validation"] and not info["smoke_only"]:
    errors.append("Train/validation instance overlap")
runtime = json.loads(Path(args.runtime_env).read_text())
env = runtime.get("env_vars", {})
for name in ("E2B_API_KEY", "E2B_API_URL", "PYTHONPATH"):
    if not env.get(name):
        errors.append(f"Runtime missing {name}")
if env.get("E2B_DEBUG", "false").lower() == "true":
    errors.append("E2B_DEBUG must be disabled")
if Path(runtime.get("working_dir", "")).resolve() != root:
    errors.append("Runtime working_dir must be this checkout")
model = Path(args.model_path)
if not (model / "config.json").is_file():
    errors.append("Model config.json missing")
if not any((model / name).is_file() for name in ("tokenizer.json", "tokenizer.model")):
    errors.append("Model tokenizer missing")
config = yaml.safe_load((root / "examples/e2b_swe_grpo/task_config.yaml").read_text())[0]
if config["sandbox"]["runtime_timeout"] <= config["agent"]["run_timeout"] + config["eval_timeout"]:
    errors.append("Sandbox TTL must include agent, evaluator and startup overhead")
for package in ("uni-agent", "verl", "e2b", "swebench", "ray", "torch", "torch-npu", "megatron-core", "megatron-bridge", "mindspeed", "mindspeed-bridge", "megatron_adaptor", "vllm", "vllm-ascend", "TransferQueue"):
    try:
        print(f"{package}: {importlib.metadata.version(package)}")
    except importlib.metadata.PackageNotFoundError:
        errors.append(f"Missing installed distribution: {package}")
print("Offline checks only: no service connectivity, NPU initialization, or sandbox execution.")
for error in errors:
    print(f"ERROR: {error}", file=sys.stderr)
raise SystemExit(bool(errors))
