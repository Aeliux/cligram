"""
Native device detection module using high-performance C implementation.

This module provides a drop-in replacement for the pure Python device detection
with significantly better performance using compile-time platform detection and
native system APIs.

Usage:
    from cligram.utils._device import get_device_info

    device = get_device_info()
    print(device.platform)
    print(device.name, device.version)
"""

from cligram.utils.device import Architecture, DeviceInfo, Environment, Platform

try:
    from cligram.utils._device_native import get_device_info as _native_get_device_info

    _NATIVE_AVAILABLE = True
except ImportError:
    _NATIVE_AVAILABLE = False

_device_cache: "DeviceInfo | None" = None


def _parse_native_result(result: dict) -> DeviceInfo:
    """Convert native C extension result to DeviceInfo object.

    Args:
        result: Dictionary returned from C extension with keys:
            platform, architecture, name, version, model, environments

    Returns:
        DeviceInfo object with all fields populated.
    """
    # Map string values to enum types
    platform_map = {
        "Windows": Platform.WINDOWS,
        "Linux": Platform.LINUX,
        "Android": Platform.ANDROID,
        "macOS": Platform.MACOS,
        "Unknown": Platform.UNKNOWN,
    }

    arch_map = {
        "x64": Architecture.X64,
        "x86": Architecture.X86,
        "arm64": Architecture.ARM64,
        "arm": Architecture.ARM,
        "unknown": Architecture.UNKNOWN,
    }

    env_map = {
        "Local": Environment.LOCAL,
        "Docker": Environment.DOCKER,
        "GitHub Actions": Environment.ACTIONS,
        "Github Codespaces": Environment.CODESPACES,
        "Virtual Machine": Environment.VIRTUAL_MACHINE,
        "WSL": Environment.WSL,
        "Termux": Environment.TERMUX,
    }

    platform = platform_map.get(result["platform"], Platform.UNKNOWN)
    architecture = arch_map.get(result["architecture"], Architecture.UNKNOWN)
    environments = [env_map.get(e, Environment.LOCAL) for e in result["environments"]]

    return DeviceInfo(
        platform=platform,
        architecture=architecture,
        name=result["name"],
        version=result["version"],
        model=result["model"],
        environments=environments,
    )


def get_device_info(no_cache: bool = False) -> DeviceInfo:
    """Get comprehensive device information using native C implementation.

    This function uses a high-performance C extension that leverages:
    - Compile-time platform detection (no runtime overhead)
    - Native system APIs (Windows Registry, sysctl, Android properties, etc.)
    - Minimal runtime checks for environment detection

    Performance benefits over pure Python:
    - ~10-50x faster execution time
    - No subprocess calls
    - No file parsing overhead for most operations
    - Direct system API access

    Args:
        no_cache: If True, bypass cache and perform fresh detection.
                 Default is False (use cached result).

    Returns:
        DeviceInfo: Complete device information including platform, architecture,
                   OS version, device model, and runtime environments.

    Raises:
        RuntimeError: If native extension is not available and couldn't be loaded.

    Example:
        >>> device = get_device_info()
        >>> print(f"Running on {device.platform.value}")
        Running on Windows
        >>> print(f"Architecture: {device.architecture.value}")
        Architecture: x64
        >>> print(f"OS: {device.name} {device.version}")
        OS: Windows 10.0
        >>> print(f"Device: {device.model}")
        Device: ASUS TUF Gaming
    """
    global _device_cache

    if not _NATIVE_AVAILABLE:
        raise RuntimeError(
            "Native device detection module not available. "
            "Please build the C extension by running: python scripts/build_native.py"
        )

    # Return cached result if available and caching is enabled
    if not no_cache and isinstance(_device_cache, DeviceInfo):
        return _device_cache

    # Call native C extension
    result = _native_get_device_info()

    # Convert to DeviceInfo object
    device = _parse_native_result(result)

    # Cache the result
    if not no_cache:
        _device_cache = device

    return device


def is_available() -> bool:
    """Check if native device detection is available.

    Returns:
        bool: True if the native C extension is loaded and available, False otherwise.
    """
    return _NATIVE_AVAILABLE


__all__ = ["get_device_info", "is_available", "DeviceInfo"]
