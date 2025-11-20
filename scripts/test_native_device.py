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

from cligram.utils.device import get_device_info as get_device_info_python

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main():
    print("=" * 70)
    print("Native Device Detection Test")
    print("=" * 70)
    print()

    # Check if native extension is available
    try:
        from cligram.utils._device import get_device_info, is_available
    except ImportError as e:
        print(f"❌ Failed to import native module: {e}")
        print("\nMake sure to build the extension first:")
        print("  python scripts/build_native.py --inplace")
        return 1

    if not is_available():
        print("❌ Native extension not available!")
        print("\nBuild it first:")
        print("  python scripts/build_native.py --inplace")
        return 1

    print("✅ Native extension is available!")
    print()

    # Time Python implementation
    start = time.perf_counter()
    device_py = get_device_info_python(no_cache=True)
    python_time = time.perf_counter() - start

    # Time native implementation
    start = time.perf_counter()
    device_native = get_device_info(no_cache=True)
    native_time = time.perf_counter() - start

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
