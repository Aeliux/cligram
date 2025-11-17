from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import ujson as json

    from .. import Proxy
else:
    try:
        import ujson as json
    except ImportError:
        import json

__all__ = ["json"]  # just to get rid of stupid linter warning


def validate_proxy(proxy: "Proxy") -> bool:
    """Validate if the given proxy is valid."""
    from .. import Proxy
    from ..proxy_manager import ProxyType

    if not proxy or not isinstance(proxy, Proxy):
        return False
    if proxy.type not in ProxyType:
        return False
    if not proxy.is_direct and (not proxy.host or not proxy.port):
        return False
    return True


def shorten_path(path: str | Path) -> str:
    """Shorten a file path for display purposes."""
    p = Path(path)
    str_path = str(p)

    # replace home directory with ~
    home = str(Path.home())
    if str_path.startswith(home):
        str_path = "~" + str_path[len(home) :]

    return str_path
