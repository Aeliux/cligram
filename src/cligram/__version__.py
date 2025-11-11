from importlib.metadata import PackageNotFoundError, version

from . import exceptions

try:
    __version__ = version("cligram")
except PackageNotFoundError:
    # Package not installed, try reading from pyproject.toml
    import tomllib
    from pathlib import Path

    try:
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)
        __version__ = pyproject["project"]["version"]
    except (FileNotFoundError, KeyError):
        raise exceptions.VersionError("Cannot determine the version of cligram.")
