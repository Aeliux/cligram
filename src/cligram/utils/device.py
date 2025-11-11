import os
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
    version: str
    model: str
    environments: list[Environment]

    @property
    def title(self) -> str:
        return f"{self.platform.value} {self.version} {self.architecture.value}"


def get_device_info() -> DeviceInfo:
    import platform

    plat = Platform.UNKNOWN
    system = platform.system()
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
        if "android" in platform.platform().lower():
            plat = Platform.ANDROID
        else:
            plat = Platform.LINUX

    if not environments:
        environments.append(Environment.LOCAL)

    return DeviceInfo(
        platform=plat,
        architecture=architecture,
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
