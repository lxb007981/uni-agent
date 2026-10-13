"""Compatibility entry point for the shared runtime composer."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/training/prepare_runtime.py"), run_name="__main__")
