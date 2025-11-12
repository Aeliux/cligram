#! /usr/bin/env python3

# cov.py
# This script runs test coverage analysis using pytest-cov.


import sys

from common import PROJECT_ROOT, print_summary, run_command


def run_coverage(
    html: bool = False, xml: bool = False, junit: bool = False, term: bool = True
) -> bool:
    """Run pytest with coverage."""
    cmd = ["pytest", "--cov=cligram", "--cov-report=term-missing"]

    if html:
        cmd.append("--cov-report=html")

    if xml:
        cmd.append("--cov-report=xml")

    if junit:
        cmd.extend(["--junitxml=junit.xml", "-o", "junit_family=legacy"])

    if not term:
        # Remove term-missing if terminal output is disabled
        cmd = [c for c in cmd if not c.startswith("--cov-report=term")]

    return run_command(cmd, "pytest coverage analysis")


def main():
    """Run coverage analysis with specified report formats."""
    import argparse

    parser = argparse.ArgumentParser(description="Run test coverage analysis")
    parser.add_argument(
        "--html", action="store_true", help="Generate HTML coverage report"
    )
    parser.add_argument(
        "--xml", action="store_true", help="Generate XML coverage report"
    )
    parser.add_argument(
        "--junit", action="store_true", help="Generate JUnit coverage report"
    )
    parser.add_argument(
        "--no-term", action="store_true", help="Disable terminal output"
    )
    parser.add_argument(
        "--all", action="store_true", help="Generate all report formats"
    )

    args = parser.parse_args()

    # Determine which reports to generate
    html = args.all or args.html
    xml = args.all or args.xml
    junit = args.all or args.junit
    term = not args.no_term

    results = {}
    results["coverage"] = run_coverage(html=html, xml=xml, junit=junit, term=term)

    print_summary(results, success_msg="COMPLETED", fail_msg="FAILED")

    # Exit with error if coverage failed
    if not all(results.values()):
        print("Coverage analysis failed. Please review the output above.")
        sys.exit(1)

    print("Coverage analysis completed successfully! 🎉")

    if html:
        html_path = PROJECT_ROOT / "htmlcov" / "index.html"
        print(f"HTML report: {html_path}")

    if xml:
        xml_path = PROJECT_ROOT / "coverage.xml"
        print(f"XML report: {xml_path}")

    sys.exit(0)


if __name__ == "__main__":
    main()
