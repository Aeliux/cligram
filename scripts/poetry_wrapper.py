#! /usr/bin/env python3

"""poetry_wrapper.py
A reusable wrapper that ensures Poetry is available and forwards commands to it.
This can be used by other scripts to run commands in the Poetry environment.
"""

import subprocess
import sys
from pathlib import Path

# Import the ensure_poetry function from init.py
sys.path.insert(0, str(Path(__file__).parent))
from init import ensure_poetry, get_poetry_executable


def run_in_poetry_env(command_args, check=True):
    """Run a command in the Poetry virtual environment.

    Args:
        command_args: List of command arguments (e.g., ["pytest", "-v"])
        check: Whether to raise exception on non-zero exit code

    Returns:
        subprocess.CompletedProcess result
    """
    poetry = get_poetry_executable()

    if poetry is None:
        print(
            "Poetry not found. Run 'python scripts/init.py' first to set up the environment."
        )
        sys.exit(1)

    project_root = Path(__file__).parent.parent

    # Run the command through Poetry
    result = subprocess.run(
        [poetry, "run"] + command_args, cwd=project_root, check=check
    )

    return result


def main():
    """Main function that forwards all arguments to Poetry run.
    Usage: python poetry_wrapper.py <command> [args...]
    Example: python poetry_wrapper.py pytest -v
    """
    if len(sys.argv) < 2:
        print("Usage: python poetry_wrapper.py <command> [args...]")
        print("Example: python poetry_wrapper.py pytest -v")
        sys.exit(1)

    # Ensure Poetry is available
    ensure_poetry()

    # Forward all arguments to Poetry run
    command_args = sys.argv[1:]
    result = run_in_poetry_env(command_args, check=False)

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
