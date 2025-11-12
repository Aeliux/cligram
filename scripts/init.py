#! /usr/bin/env python3

"""init.py
This script initializes the development environment by installing necessary dependencies.
It ensures Poetry is installed, installs project dependencies, and sets up pre-commit hooks.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def get_poetry_paths():
    """Get potential Poetry installation paths based on OS."""
    home = Path.home()
    system = platform.system()

    paths = []

    if system == "Windows":
        # Standard Poetry installation paths on Windows
        paths.extend(
            [
                home / "AppData" / "Roaming" / "Python" / "Scripts" / "poetry.exe",
                home
                / "AppData"
                / "Roaming"
                / "pypoetry"
                / "venv"
                / "Scripts"
                / "poetry.exe",
                home / ".poetry" / "bin" / "poetry.exe",
                Path(os.environ.get("APPDATA", ""))
                / "Python"
                / "Scripts"
                / "poetry.exe",
            ]
        )
    else:
        # Standard Poetry installation paths on Unix-like systems
        paths.extend(
            [
                home / ".local" / "bin" / "poetry",
                home / ".poetry" / "bin" / "poetry",
                Path("/usr/local/bin/poetry"),
                Path("/usr/bin/poetry"),
            ]
        )

    return [p for p in paths if p.exists()]


def get_poetry_executable():
    """Find the Poetry executable in the system."""
    # First, try to find poetry in PATH using shutil.which (most reliable)
    poetry_in_path = shutil.which("poetry")
    if poetry_in_path:
        try:
            result = subprocess.run(
                [poetry_in_path, "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return poetry_in_path
        except (subprocess.TimeoutExpired, Exception):
            pass

    # If not in PATH, search common installation locations
    for poetry_path in get_poetry_paths():
        try:
            result = subprocess.run(
                [str(poetry_path), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return str(poetry_path)
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
            continue

    return None


def add_poetry_to_path():
    """Add Poetry binary directory to PATH for current session."""
    home = Path.home()
    system = platform.system()

    if system == "Windows":
        poetry_bins = [
            home / "AppData" / "Roaming" / "Python" / "Scripts",
            home / "AppData" / "Roaming" / "pypoetry" / "venv" / "Scripts",
        ]
    else:
        poetry_bins = [
            home / ".local" / "bin",
            home / ".poetry" / "bin",
        ]

    for poetry_bin in poetry_bins:
        if poetry_bin.exists():
            bin_str = str(poetry_bin)
            if bin_str not in os.environ["PATH"]:
                os.environ["PATH"] = f"{bin_str}{os.pathsep}{os.environ['PATH']}"


def verify_poetry_installation():
    """Verify that Poetry is properly installed and working."""
    poetry = get_poetry_executable()

    if poetry is None:
        return False

    try:
        result = subprocess.run(
            [poetry, "--version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and "Poetry" in result.stdout:
            return True
    except Exception:
        pass

    return False


def install_poetry():
    """Install Poetry based on the operating system."""
    print("Poetry not found. Installing Poetry...")

    system = platform.system()

    # Check if we already have Poetry but PATH is not updated
    add_poetry_to_path()
    if verify_poetry_installation():
        print("✓ Poetry found after updating PATH!")
        return get_poetry_executable()

    try:
        install_script_url = "https://install.python-poetry.org"

        if system == "Windows":
            # Try multiple Python launchers on Windows
            python_commands = ["py", "python", "python3"]
            install_success = False

            for py_cmd in python_commands:
                try:
                    subprocess.run(
                        [
                            "powershell",
                            "-Command",
                            f"(Invoke-WebRequest -Uri {install_script_url} -UseBasicParsing).Content | {py_cmd} -",
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    install_success = True
                    break
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue

            if not install_success:
                raise Exception(
                    "Failed to install Poetry. No suitable Python interpreter found."
                )
        else:
            # Unix-like systems
            python_commands = ["python3", "python"]
            install_success = False

            for py_cmd in python_commands:
                try:
                    subprocess.run(
                        ["sh", "-c", f"curl -sSL {install_script_url} | {py_cmd} -"],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    install_success = True
                    break
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue

            if not install_success:
                raise Exception(
                    "Failed to install Poetry. Ensure curl and Python are available."
                )

        print("✓ Poetry installation completed!")

        # Update PATH for current session
        add_poetry_to_path()

        # Verify installation with retries
        import time

        for attempt in range(3):
            time.sleep(1)  # Give system a moment to update

            if verify_poetry_installation():
                poetry = get_poetry_executable()
                print(f"✓ Poetry verified at: {poetry}")
                return poetry

            # Try updating PATH again
            add_poetry_to_path()

        # Last resort: try to find Poetry by path
        poetry_paths = get_poetry_paths()
        if poetry_paths:
            poetry = str(poetry_paths[0])
            print(f"✓ Poetry found at: {poetry}")
            print(
                "⚠ Note: You may need to restart your terminal for Poetry to be available in PATH"
            )
            return poetry

        raise Exception(
            "Poetry was installed but cannot be verified. "
            "Please restart your terminal and run this script again, "
            "or manually add Poetry to your PATH."
        )

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if hasattr(e, "stderr") and e.stderr else str(e)
        print(f"✗ Failed to install Poetry: {error_msg}", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(
            "✗ Poetry installation timed out. Please check your internet connection.",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def ensure_poetry():
    """Ensure Poetry is installed and return the executable path."""
    # First check: Look for Poetry
    poetry = get_poetry_executable()

    if poetry is None:
        # Second check: Try updating PATH and look again
        add_poetry_to_path()
        poetry = get_poetry_executable()

    if poetry is None:
        # Third check: Install Poetry
        poetry = install_poetry()
    else:
        # Verify the found Poetry actually works
        try:
            result = subprocess.run(
                [poetry, "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                print(f"⚠ Found Poetry at {poetry} but it's not working properly")
                print("Attempting to reinstall...")
                poetry = install_poetry()
            else:
                print(f"✓ Poetry found: {poetry}")
                version = result.stdout.strip()
                if version:
                    print(f"  Version: {version}")
        except Exception as e:
            print(f"⚠ Error checking Poetry: {e}")
            print("Attempting to reinstall...")
            poetry = install_poetry()

    return poetry


def install_dependencies(poetry):
    """Install project dependencies using Poetry."""
    print("\nInstalling project dependencies...")

    # Get project root (parent of scripts directory)
    project_root = Path(__file__).parent.parent

    # Check if pyproject.toml exists
    pyproject_file = project_root / "pyproject.toml"
    if not pyproject_file.exists():
        print(f"⚠ No pyproject.toml found at {project_root}")
        print("  Skipping dependency installation")
        return

    try:
        result = subprocess.run(
            [poetry, "install"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
        print("✓ Dependencies installed successfully!")
        if result.stdout:
            # Show last few lines of output
            lines = result.stdout.strip().split("\n")
            for line in lines[-3:]:
                if line.strip():
                    print(f"  {line}")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install dependencies: {e}", file=sys.stderr)
        if e.stderr:
            print(f"  Error details: {e.stderr}", file=sys.stderr)
        sys.exit(1)


def setup_precommit_hooks(poetry):
    """Setup pre-commit hooks."""
    print("\nSetting up pre-commit hooks...")

    project_root = Path(__file__).parent.parent

    # Check if .pre-commit-config.yaml exists
    precommit_config = project_root / ".pre-commit-config.yaml"
    if not precommit_config.exists():
        print("  No .pre-commit-config.yaml found, skipping pre-commit setup")
        return

    try:
        # First check if pre-commit is installed
        subprocess.run(
            [poetry, "run", "pre-commit", "--version"],
            cwd=project_root,
            check=True,
            capture_output=True,
            timeout=10,
        )

        # Install pre-commit hooks
        subprocess.run(
            [poetry, "run", "pre-commit", "install"],
            cwd=project_root,
            check=True,
            capture_output=True,
            timeout=30,
        )
        print("✓ Pre-commit hooks installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"⚠ Failed to install pre-commit hooks: {e}", file=sys.stderr)
        print("  (This is optional - continuing anyway)")
        print("  You may need to install pre-commit: poetry add --group dev pre-commit")
    except subprocess.TimeoutExpired:
        print("⚠ Pre-commit installation timed out")
        print("  (This is optional - continuing anyway)")


def main():
    """Main function to initialize the development environment."""
    print("=" * 60)
    print("Initializing development environment...")
    print("=" * 60)

    # Ensure Poetry is installed
    poetry = ensure_poetry()

    # Install dependencies
    install_dependencies(poetry)

    # Setup pre-commit hooks
    setup_precommit_hooks(poetry)

    print("\n" + "=" * 60)
    print("✓ Development environment initialized successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
