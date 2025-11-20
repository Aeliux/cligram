#!/usr/bin/env python3
"""
Simple example demonstrating the native device detection module.

This script shows how to use the native device detection and compares
it with the pure Python implementation.

Usage:
    python scripts/test_native_device.py
"""

import sys
import time
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cligram.utils import _device, device
from cligram.utils.device import _NATIVE_AVAILABLE, get_device_info


def main():
    print("=" * 70)
    print("Native Device Detection Test")
    print("=" * 70)
    print()

    if not _NATIVE_AVAILABLE:
        print("❌ Native extension not available!")
        print("\nBuild it first")
        return 1

    print("✅ Native extension is available!")
    print()

    # Time Python implementation
    device._NATIVE_AVAILABLE = False  # Force using Python implementation
    start = time.perf_counter()
    device_py = get_device_info(no_cache=True)
    python_time = time.perf_counter() - start

    # Time native implementation
    device._NATIVE_AVAILABLE = True  # Force using native implementation
    start = time.perf_counter()
    device_native = get_device_info(no_cache=True)
    native_time = time.perf_counter() - start

    # Time raw native implementation
    start = time.perf_counter()
    _ = _device.get_device_info()
    raw_native_time = time.perf_counter() - start

    print()
    print("📱 Device Information: (native/python)")
    print("-" * 70)
    print(f"Platform:        {device_native.platform.value}/{device_py.platform.value}")
    print(
        f"Architecture:    {device_native.architecture.value}/{device_py.architecture.value}"
    )
    print(f"OS Name:         {device_native.name}/{device_py.name}")
    print(f"OS Version:      {device_native.version}/{device_py.version}")
    print(f"Device Model:    {device_native.model}/{device_py.model}")
    print(f"Title:           {device_native.title}/{device_py.title}")
    print()
    print(
        f"Environments:    {', '.join(e.value for e in device_native.environments)}/{', '.join(e.value for e in device_py.environments)}"
    )
    print("-" * 70)
    print()

    # Compare with Python implementation
    print("⚖️  Comparing with pure Python implementation...")

    print()
    print("Performance Comparison:")
    print(f"  Python: {python_time * 1000:.2f} ms")
    print(f"  Native: {native_time * 1000:.2f} ms")
    print(f"  Speedup: {python_time / native_time:.1f}x")
    print(f"  Raw Native: {raw_native_time * 1000:.2f} ms")
    print()

    # Check consistency
    if device_py == device_native:
        print("✅ Results are consistent between implementations")
    else:
        print("⚠️  Results differ between implementations")

    print()
    print("=" * 70)
    print("✅ Test completed successfully!")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
