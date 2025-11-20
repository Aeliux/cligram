from typing import Dict

def get_device_info() -> Dict[str, str]:
    """
    Retrieves detailed information about the current device and operating system.

    Returns:
        Dict[str, str]: A dictionary containing device information with keys:
        - platform (str): The operating system platform (Windows, Linux, macOS, etc.)
        - architecture (str): CPU architecture (x64, x86, arm64, arm)
        - name (str): Operating system name or distribution name
        - version (str): Operating system version
        - model (str): Device model or computer name
    """
