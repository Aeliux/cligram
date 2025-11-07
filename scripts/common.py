"""Common utilities for check and fix scripts."""

import subprocess
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Common directories to check/fix
TARGETS = ["src", "scripts", "tests"]


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return True if successful."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"{'='*60}")
    try:
        subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
        print(f"✓ {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed with exit code {e.returncode}")
        return False


def print_summary(
    results: dict[str, bool], success_msg: str = "PASSED", fail_msg: str = "FAILED"
):
    """Print a summary of check/fix results."""
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    for name, passed in results.items():
        status = f"✓ {success_msg}" if passed else f"✗ {fail_msg}"
        print(f"{name:15} {status}")

    print(f"{'='*60}\n")
