#!/usr/bin/env python3

# check.py
# This script is used to perform various checks on the project.

import sys

from common import TARGETS, print_summary, run_command


def check_black() -> bool:
    """Run black code formatter check."""
    return run_command(["black", "--check", *TARGETS], "Black code formatting check")


def check_isort() -> bool:
    """Run isort import sorting check."""
    return run_command(
        ["isort", "--check-only", *TARGETS], "isort import sorting check"
    )


def check_ruff() -> bool:
    """Run ruff linter."""
    return run_command(["ruff", "check", *TARGETS], "Ruff linter check")


def check_mypy() -> bool:
    """Run mypy type checker."""
    return run_command(["mypy", "src", "--pretty"], "MyPy type checking")


def check_bandit() -> bool:
    """Run bandit security checker."""
    return run_command(["bandit", "-r", "src", "-ll"], "Bandit security check")


def check_pip_audit() -> bool:
    """Run pip-audit for dependency vulnerabilities."""
    return run_command(["pip-audit"], "Pip-audit dependency vulnerability check")


def check_pydocstyle() -> bool:
    """Run pydocstyle for docstring style checking."""
    return run_command(
        ["pydocstyle", "src/cligram"], "Pydocstyle docstring style check"
    )


def check_pytest() -> bool:
    """Run pytest test suite."""
    return run_command(["pytest", "tests", "-v"], "Pytest test suite")


def main():
    """Run all checks or specific checks based on arguments."""
    import argparse

    parser = argparse.ArgumentParser(description="Run project checks")
    parser.add_argument("--black", action="store_true", help="Run black check")
    parser.add_argument("--isort", action="store_true", help="Run isort check")
    parser.add_argument("--ruff", action="store_true", help="Run ruff check")
    parser.add_argument("--mypy", action="store_true", help="Run mypy check")
    parser.add_argument("--bandit", action="store_true", help="Run bandit check")
    parser.add_argument("--audit", action="store_true", help="Run pip-audit check")
    # parser.add_argument(
    #     "--pydocstyle", action="store_true", help="Run pydocstyle check"
    # )
    parser.add_argument("--test", action="store_true", help="Run pytest")
    parser.add_argument("--all", action="store_true", help="Run all checks (default)")

    args = parser.parse_args()

    # If no specific check is requested, run all
    run_all = args.all or not any(
        [
            args.black,
            args.isort,
            args.ruff,
            args.mypy,
            args.bandit,
            args.audit,
            # args.pydocstyle,
            args.test,
        ]
    )

    results = {}

    if run_all or args.black:
        results["black"] = check_black()

    if run_all or args.isort:
        results["isort"] = check_isort()

    if run_all or args.ruff:
        results["ruff"] = check_ruff()

    if run_all or args.mypy:
        results["mypy"] = check_mypy()

    if run_all or args.bandit:
        results["bandit"] = check_bandit()

    if run_all or args.audit:
        results["audit"] = check_pip_audit()

    # if run_all or args.pydocstyle:
    #     results["pydocstyle"] = check_pydocstyle()

    if run_all or args.test:
        results["test"] = check_pytest()

    print_summary(results, success_msg="PASSED", fail_msg="FAILED")

    # Exit with error if any check failed
    if not all(results.values()):
        sys.exit(1)

    print("All checks passed! 🎉")
    sys.exit(0)


if __name__ == "__main__":
    main()
