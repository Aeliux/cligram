import os
import platform
from dataclasses import dataclass
from enum import Enum


class Platform(Enum):
    UNKNOWN = "Unknown"
    WINDOWS = "Windows"
    LINUX = "Linux"
    ANDROID = "Android"


class Environment(Enum):
    LOCAL = "Local"
    DOCKER = "Docker"
    ACTIONS = "GitHub Actions"
    CODESPACES = "Github Codespaces"
    VIRTUAL_MACHINE = "Virtual Machine"


class Architecture(Enum):
    UNKNOWN = "unknown"
    X86 = "x86"
    X64 = "x64"
    ARM = "arm"
    ARM64 = "arm64"


@dataclass
class DeviceInfo:
    platform: Platform
    architecture: Architecture
    name: str
    version: str
    model: str
    environments: list[Environment]

    @property
    def title(self) -> str:
        return f"{self.name} {self.version}"


def get_device_info() -> DeviceInfo:
    plat = Platform.UNKNOWN
    system = platform.system()
    name = system
    architecture = get_architecture()
    model = platform.node()
    version = platform.release()
    environments: list[Environment] = []

    # Detect github codespaces
    if os.getenv("CODESPACES") == "true":
        environments.append(Environment.CODESPACES)

    # Detect github actions
    if os.getenv("GITHUB_ACTIONS") == "true":
        environments.append(Environment.ACTIONS)

    # Detect docker
    if os.path.exists("/.dockerenv") or os.path.exists("/.containerenv"):
        environments.append(Environment.DOCKER)

    if system == "Windows":
        plat = Platform.WINDOWS
        mb_model = _windows_get_motherboard_model_registry()
        if mb_model:
            model = mb_model
        version = platform.win32_ver()[0]
    elif system == "Linux":
        if _is_android():
            plat = Platform.ANDROID
            name = "Android"
            # Get Android version and device model
            android_version = _android_get_version()
            if android_version:
                version = android_version
            android_model = _android_get_device_model()
            if android_model:
                model = android_model
        else:
            plat = Platform.LINUX
            # Get Linux distro info
            name, version = _linux_get_distro_info()
            # Get device/motherboard model
            device_model = _linux_get_device_model()
            if device_model:
                model = device_model

    if (
        not model
        or model.strip() == ""
        or model.lower() == "unknown"
        or model.lower() == "virtual machine"
        or model.lower() == "none"
    ):
        environments.append(Environment.VIRTUAL_MACHINE)
        model = platform.node()

    if not environments:
        environments.append(Environment.LOCAL)

    return DeviceInfo(
        platform=plat,
        architecture=architecture,
        name=name,
        version=version,
        model=model,
        environments=environments,
    )


def get_architecture() -> Architecture:
    import platform

    machine = platform.machine().lower()

    # x64/AMD64
    if machine in ("amd64", "x86_64", "x64"):
        return Architecture.X64
    # ARM64
    elif machine in ("arm64", "aarch64", "armv8", "armv8l", "aarch64_be"):
        return Architecture.ARM64
    # ARM (32-bit)
    elif machine.startswith("arm") or machine in ("armv7l", "armv6l", "armv5l"):
        return Architecture.ARM
    # x86
    elif machine in ("i386", "i686", "x86", "i86pc"):
        return Architecture.X86
    else:
        return Architecture.UNKNOWN


def _windows_get_motherboard_model_registry() -> str | None:
    import winreg

    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS"
        )
        value, _ = winreg.QueryValueEx(key, "SystemProductName")
        winreg.CloseKey(key)
        return value
    except Exception:
        return None


def _linux_get_distro_info() -> tuple[str, str]:
    """Get Linux distribution name and version from /etc/os-release."""
    distro_name = "Linux"
    distro_version = platform.release()

    try:
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release", "r") as f:
                lines = f.readlines()
                name = None
                version = None
                for line in lines:
                    line = line.strip()
                    if line.startswith("NAME="):
                        name = line.split("=", 1)[1].strip('"')
                    elif line.startswith("VERSION_ID="):
                        version = line.split("=", 1)[1].strip('"')
                    elif line.startswith("VERSION=") and not version:
                        version = line.split("=", 1)[1].strip('"')

                if name:
                    distro_name = name
                if version:
                    distro_version = version
    except Exception:
        pass

    return distro_name, distro_version


def _linux_get_device_model() -> str | None:
    """Get Linux device/motherboard model from various sources."""
    # Try DMI information (works on most x86/x64 systems)
    dmi_paths = [
        "/sys/class/dmi/id/product_name",
        "/sys/class/dmi/id/board_name",
        "/sys/devices/virtual/dmi/id/product_name",
        "/sys/devices/virtual/dmi/id/board_name",
    ]

    for path in dmi_paths:
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    model = f.read().strip()
                    if model and model.lower() not in (
                        "",
                        "to be filled by o.e.m.",
                        "default string",
                        "system product name",
                    ):
                        return model
        except Exception:
            continue

    # Try device tree (works on ARM systems like Raspberry Pi)
    device_tree_paths = [
        "/proc/device-tree/model",
        "/sys/firmware/devicetree/base/model",
    ]

    for path in device_tree_paths:
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    model = f.read().strip().rstrip("\x00")
                    if model:
                        return model
        except Exception:
            continue

    return None


def _is_android() -> bool:
    """Check if running on Android system."""
    # Check for Android-specific paths
    android_indicators = [
        "/system/build.prop",
        "/system/bin/app_process",
        "/system/framework/framework-res.apk",
    ]

    for path in android_indicators:
        if os.path.exists(path):
            return True

    # Check environment variables
    if os.getenv("ANDROID_ROOT") or os.getenv("ANDROID_DATA"):
        return True

    return False


def _android_getprop(property_name: str) -> str | None:
    """Get Android system property using getprop command."""
    try:
        import subprocess

        result = subprocess.run(
            ["getprop", property_name],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            return value if value else None
    except Exception:
        pass

    return None


def _android_get_version() -> str | None:
    """Get Android version from system properties."""
    version = _android_getprop("ro.build.version.release")

    # Try to get SDK version for more detail
    if version:
        sdk_version = _android_get_sdk_version()
        if sdk_version:
            return f"{version} (API {sdk_version})"

    return version


def _android_get_sdk_version() -> str | None:
    """Get Android SDK/API level."""
    return _android_getprop("ro.build.version.sdk")


def _android_get_device_model() -> str | None:
    """Get Android device model and manufacturer."""
    manufacturer = _android_getprop("ro.product.manufacturer")
    model = _android_getprop("ro.product.model")

    # Format the device string
    if manufacturer and model:
        # Avoid duplication if model already starts with manufacturer
        if model.lower().startswith(manufacturer.lower()):
            return model
        else:
            return f"{manufacturer} {model}"
    elif model:
        return model
    elif manufacturer:
        return manufacturer

    return None
