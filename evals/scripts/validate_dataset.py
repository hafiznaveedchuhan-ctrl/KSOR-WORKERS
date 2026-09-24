"""CLI wrapper: uv run python scripts/validate_dataset.py [--require-reviewed] [-v]"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "datasets" / "validate.py"), run_name="__main__")
