from dataclasses import dataclass
from enum import Enum


class OperationSystem(Enum):
    UNKNOWN = "Unknown"
    WINDOWS = "Windows"
    LINUX = "Linux"
    ANDROID = "Android"


class Architecture(Enum):
    UNKNOWN = "unknown"
    X86 = "x86"
    X64 = "x64"
    ARM = "arm"
    ARM64 = "arm64"


@dataclass
class DeviceInfo:
    os: OperationSystem
    architecture: Architecture
    os_title: str
    version: str
    model: str


def get_device_info() -> DeviceInfo:
    import platform

    system = platform.system()
    architecture = get_architecture()
    model = platform.node()
    version = platform.release()

    if system == "Windows":
        os = OperationSystem.WINDOWS
        mb_model = _windows_get_motherboard_model_registry()
        if mb_model:
            model = mb_model
        version = platform.win32_ver()[0]
    elif system == "Linux":
        if "android" in platform.platform().lower():
            os = OperationSystem.ANDROID
        else:
            os = OperationSystem.LINUX
    else:
        os = OperationSystem.UNKNOWN

    os_title = f"{os.value} {version} {architecture.value}"

    return DeviceInfo(
        os=os,
        architecture=architecture,
        os_title=os_title,
        version=version,
        model=model,
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


def _windows_get_motherboard_model_registry() -> str | None:  # type: ignore
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
