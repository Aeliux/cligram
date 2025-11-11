from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .. import Proxy


def validate_proxy(proxy: "Proxy") -> bool:
    """Validate if the given proxy is valid"""
    from .. import Proxy
    from ..proxy_manager import ProxyType

    if not proxy or not isinstance(proxy, Proxy):
        return False
    if proxy.type not in ProxyType:
        return False
    if not proxy.is_direct and (not proxy.host or not proxy.port):
        return False
    return True
