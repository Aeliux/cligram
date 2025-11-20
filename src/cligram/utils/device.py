import os
import platform
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Callable

_device_cache: "DeviceInfo | None" = None


class Platform(Enum):
    UNKNOWN = "Unknown"
    WINDOWS = "Windows"
    LINUX = "Linux"
    ANDROID = "Android"
    MACOS = "macOS"


class Environment(Enum):
    LOCAL = "Local"
    DOCKER = "Docker"
    ACTIONS = "GitHub Actions"
    CODESPACES = "Github Codespaces"
    VIRTUAL_MACHINE = "Virtual Machine"
    WSL = "WSL"
    TERMUX = "Termux"


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

    @property
    def is_virtual(self) -> bool:
        """Check if running in a virtual environment."""
        virtual_envs = {
            Environment.DOCKER,
            Environment.VIRTUAL_MACHINE,
            Environment.WSL,
        }
        return any(env in virtual_envs for env in self.environments)

    @property
    def is_ci(self) -> bool:
        """Check if running in a CI environment."""
        ci_envs = {Environment.ACTIONS, Environment.CODESPACES}
        return any(env in ci_envs for env in self.environments)


def _read_file_safe(filepath: str, strip_null: bool = False) -> str | None:
    """Safely read a file and return its content."""
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
                if strip_null:
                    content = content.rstrip("\x00")
                return content if content else None
    except Exception:
        pass
    return None


def _read_file_lines(filepath: str) -> list[str]:
    """Safely read a file and return its lines."""
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return [line.strip() for line in f.readlines()]
    except Exception:
        pass
    return []


def _run_command(command: list[str], timeout: int = 2) -> str | None:
    """Run a command and return its output safely."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            return output if output else None
    except Exception:
        pass
    return None


class WindowsDetector:
    """Windows platform detection and information gathering."""

    @staticmethod
    def detect() -> tuple[Platform, str, str, str]:
        """Detect Windows-specific information."""
        name = "Windows"
        version = platform.win32_ver()[0] or platform.release()
        model = WindowsDetector.get_model() or platform.node()
        return Platform.WINDOWS, name, version, model

    @staticmethod
    def get_model() -> str | None:
        """Get Windows motherboard/system model from registry."""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS"
            )
            value, _ = winreg.QueryValueEx(key, "SystemProductName")
            winreg.CloseKey(key)
            return value
        except Exception:
            pass

        # Fallback to WMIC
        return _run_command(["wmic", "computersystem", "get", "model"])


class LinuxDetector:
    """Linux platform detection and information gathering."""

    @staticmethod
    def detect() -> tuple[Platform, str, str, str]:
        """Detect Linux-specific information."""
        name, version = LinuxDetector.get_distro_info()
        model = LinuxDetector.get_device_model() or platform.node()
        return Platform.LINUX, name, version, model

    @staticmethod
    def get_distro_info() -> tuple[str, str]:
        """Get Linux distribution name and version."""
        distro_name = "Linux"
        distro_version = platform.release()

        lines = _read_file_lines("/etc/os-release")
        name_value = None
        version_value = None

        for line in lines:
            if line.startswith("NAME="):
                name_value = line.split("=", 1)[1].strip('"')
            elif line.startswith("VERSION_ID="):
                version_value = line.split("=", 1)[1].strip('"')
            elif line.startswith("VERSION=") and not version_value:
                version_value = line.split("=", 1)[1].strip('"')

        if name_value:
            distro_name = name_value
        if version_value:
            distro_version = version_value

        return distro_name, distro_version

    @staticmethod
    def get_device_model() -> str | None:
        """Get Linux device/motherboard model."""
        # Try DMI information (x86/x64 systems)
        dmi_paths = [
            "/sys/class/dmi/id/product_name",
            "/sys/class/dmi/id/board_name",
            "/sys/devices/virtual/dmi/id/product_name",
            "/sys/devices/virtual/dmi/id/board_name",
        ]

        for path in dmi_paths:
            model = _read_file_safe(path)
            if model and model.lower() not in (
                "to be filled by o.e.m.",
                "default string",
                "system product name",
            ):
                return model

        # Try device tree (ARM systems like Raspberry Pi)
        device_tree_paths = [
            "/proc/device-tree/model",
            "/sys/firmware/devicetree/base/model",
        ]

        for path in device_tree_paths:
            model = _read_file_safe(path, strip_null=True)
            if model:
                return model

        return None


class AndroidDetector:
    """Android platform detection and information gathering."""

    @staticmethod
    def is_android() -> bool:
        """Check if running on Android system."""
        android_indicators = [
            "/system/build.prop",
            "/system/bin/app_process",
            "/system/framework/framework-res.apk",
        ]

        if any(os.path.exists(path) for path in android_indicators):
            return True

        if os.getenv("ANDROID_ROOT") or os.getenv("ANDROID_DATA"):
            return True

        return False

    @staticmethod
    def detect() -> tuple[Platform, str, str, str]:
        """Detect Android-specific information."""
        name = "Android"
        version = AndroidDetector.get_version() or platform.release()
        model = AndroidDetector.get_device_model() or platform.node()
        return Platform.ANDROID, name, version, model

    @staticmethod
    def get_property(property_name: str) -> str | None:
        """Get Android system property using getprop command."""
        return _run_command(["getprop", property_name])

    @staticmethod
    def get_version() -> str | None:
        """Get Android version from system properties."""
        version = AndroidDetector.get_property("ro.build.version.release")

        if version:
            sdk_version = AndroidDetector.get_property("ro.build.version.sdk")
            if sdk_version:
                return f"{version} (API {sdk_version})"

        return version

    @staticmethod
    def get_device_model() -> str | None:
        """Get Android device model and manufacturer."""
        manufacturer = AndroidDetector.get_property("ro.product.manufacturer")
        model = AndroidDetector.get_property(
            "ro.product.marketname"
        ) or AndroidDetector.get_property("ro.product.model")

        if manufacturer and model:
            # Avoid duplication if model already contains manufacturer
            if model.lower().startswith(manufacturer.lower()):
                return model
            return f"{manufacturer} {model}"

        return model or manufacturer


class MacOSDetector:
    """macOS platform detection and information gathering."""

    @staticmethod
    def detect() -> tuple[Platform, str, str, str]:
        """Detect macOS-specific information."""
        name = "macOS"
        version = platform.mac_ver()[0] or platform.release()
        model = MacOSDetector.get_model() or platform.node()
        return Platform.MACOS, name, version, model

    @staticmethod
    def get_model() -> str | None:
        """Get macOS device model."""
        # Try system_profiler
        output = _run_command(["system_profiler", "SPHardwareDataType"], timeout=5)

        if output:
            for line in output.split("\n"):
                if "Model Name:" in line:
                    return line.split(":", 1)[1].strip()
                elif "Model Identifier:" in line:
                    return line.split(":", 1)[1].strip()

        # Fallback to sysctl
        return _run_command(["sysctl", "-n", "hw.model"])


def get_device_info(no_cache=False) -> DeviceInfo:
    """Get comprehensive device information across all supported platforms.

    Returns:
        DeviceInfo: Complete device information including platform, architecture, and environment.
    """
    global _device_cache
    if not no_cache and isinstance(_device_cache, DeviceInfo):
        return _device_cache

    system = platform.system()
    architecture = get_architecture()
    environments = _detect_environments()

    # Platform-specific detection
    if system == "Windows":
        plat, name, version, model = WindowsDetector.detect()
    elif system == "Linux":
        if AndroidDetector.is_android():
            plat, name, version, model = AndroidDetector.detect()
        else:
            plat, name, version, model = LinuxDetector.detect()
    elif system == "Darwin":
        plat, name, version, model = MacOSDetector.detect()
    elif system == "Android":
        plat, name, version, model = AndroidDetector.detect()
    else:
        plat = Platform.UNKNOWN
        name = system
        version = platform.release()
        model = platform.node()

    # Validate and fallback for model
    model = _validate_model(model, environments)

    device = DeviceInfo(
        platform=plat,
        architecture=architecture,
        name=name,
        version=version,
        model=model,
        environments=environments,
    )

    if not no_cache:
        _device_cache = device

    return device


def get_architecture() -> Architecture:
    """Detect system architecture."""
    machine = platform.machine().lower()

    architecture_map = {
        ("amd64", "x86_64", "x64"): Architecture.X64,
        ("arm64", "aarch64", "armv8", "armv8l", "aarch64_be"): Architecture.ARM64,
        ("i386", "i686", "x86", "i86pc"): Architecture.X86,
    }

    for machines, arch in architecture_map.items():
        if machine in machines:
            return arch

    # ARM 32-bit (check with startswith)
    if machine.startswith("arm") or machine in ("armv7l", "armv6l", "armv5l"):
        return Architecture.ARM

    return Architecture.UNKNOWN


def _detect_environments() -> list[Environment]:
    """Detect all active environments."""
    environments: list[Environment] = []

    # Environment detection rules
    env_checks: list[tuple[Callable[[], bool], Environment]] = [
        (lambda: os.getenv("CODESPACES") == "true", Environment.CODESPACES),
        (lambda: os.getenv("GITHUB_ACTIONS") == "true", Environment.ACTIONS),
        (
            lambda: os.path.exists("/.dockerenv") or os.path.exists("/.containerenv"),
            Environment.DOCKER,
        ),
        (lambda: os.getenv("WSL_DISTRO_NAME") is not None, Environment.WSL),
        (lambda: os.getenv("TERMUX_VERSION") is not None, Environment.TERMUX),
    ]

    for check, env in env_checks:
        try:
            if check():
                environments.append(env)
        except Exception:
            continue

    return environments if environments else [Environment.LOCAL]


def _validate_model(model: str, environments: list[Environment]) -> str:
    """Validate and clean up model name."""
    invalid_models = {
        "",
        "unknown",
        "virtual machine",
        "none",
        "to be filled by o.e.m.",
        "default string",
        "system product name",
    }

    if not model or model.strip().lower() in invalid_models:
        if Environment.VIRTUAL_MACHINE not in environments:
            environments.append(Environment.VIRTUAL_MACHINE)
        return platform.node()

    return model
