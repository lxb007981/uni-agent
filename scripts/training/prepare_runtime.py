"""Write a private Ray runtime JSON using an already installed training environment."""
import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", required=True)
parser.add_argument("--verl-source", required=True, help="Absolute path to compatible installed/shared verl source")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
verl = Path(args.verl_source).resolve()
if not (verl / "verl" / "trainer" / "main_ppo.py").is_file():
    raise SystemExit("verl source is missing; initialize the pinned submodule or specify a validated checkout")
import sys

sys.path.insert(0, str(root / "scripts" / "sandbox"))
from environment import worker_environment

env = worker_environment()
env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(root), str(verl), os.environ.get("PYTHONPATH"))))
runtime = {"working_dir": str(root), "excludes": ["/.git/", "/.runtime/", "/.artifacts/", "/logs/"],
           "env_vars": env}
out = Path(args.output).resolve()
out.parent.mkdir(parents=True, exist_ok=True)
fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd, "w") as stream:
    json.dump(runtime, stream, indent=2)
    stream.write("\n")
print(f"Wrote private runtime configuration: {out}")
