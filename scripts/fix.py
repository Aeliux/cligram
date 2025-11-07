#! /usr/bin/env python3

# fix.py
# This script automatically fixes code formatting and linting issues.

import sys

from common import TARGETS, print_summary, run_command


def fix_isort() -> bool:
    """Fix import sorting with isort."""
    return run_command(["isort", *TARGETS], "isort import sorting")


def fix_black() -> bool:
    """Fix code formatting with black."""
    return run_command(["black", *TARGETS], "Black code formatting")


def fix_ruff() -> bool:
    """Fix linting issues with ruff."""
    return run_command(["ruff", "check", "--fix", *TARGETS], "Ruff auto-fix")


def main():
    """Run all auto-fixes or specific fixes based on arguments."""
    import argparse

    parser = argparse.ArgumentParser(description="Auto-fix code issues")
    parser.add_argument("--black", action="store_true", help="Run black formatter")
    parser.add_argument("--isort", action="store_true", help="Run isort")
    parser.add_argument("--ruff", action="store_true", help="Run ruff auto-fix")
    parser.add_argument("--all", action="store_true", help="Run all fixes (default)")

    args = parser.parse_args()

    # If no specific fix is requested, run all
    run_all = args.all or not any([args.black, args.isort, args.ruff])

    results = {}

    # Run in order: isort first, then black, then ruff
    if run_all or args.isort:
        results["isort"] = fix_isort()

    if run_all or args.black:
        results["black"] = fix_black()

    if run_all or args.ruff:
        results["ruff"] = fix_ruff()

    print_summary(results, success_msg="COMPLETED", fail_msg="FAILED")

    # Exit with error if any fix failed
    if not all(results.values()):
        print("Some fixes failed. Please review the output above.")
        sys.exit(1)

    print("All fixes applied successfully! 🎉")
    print("Run 'python scripts/check.py' to verify the changes.")
    sys.exit(0)


if __name__ == "__main__":
    main()
