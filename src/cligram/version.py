"""Version information for cligram package."""

__version__ = "0.0.0"
__version_tuple__ = (0, 0, 0)

if __version__ == "0.0.0":
    try:
        from ._gen_version import (  # type: ignore  # noqa: F401
            __version__,
            __version_tuple__,
        )
    except ImportError:
        pass
