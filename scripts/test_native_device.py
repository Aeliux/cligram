#!/usr/bin/env python3
"""
Simple example demonstrating the native device detection module.

This script shows how to use the native device detection and compares
it with the pure Python implementation.

Usage:
    python scripts/test_native_device.py
"""

import sys
from pathlib import Path

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

    # Get device info
    print("🔍 Detecting device information...")
    try:
        device = get_device_info()
    except Exception as e:
        print(f"❌ Error getting device info: {e}")
        return 1

    print()
    print("📱 Device Information:")
    print("-" * 70)
    print(f"Platform:        {device.platform.value}")
    print(f"Architecture:    {device.architecture.value}")
    print(f"OS Name:         {device.name}")
    print(f"OS Version:      {device.version}")
    print(f"Device Model:    {device.model}")
    print(f"Title:           {device.title}")
    print()
    print(f"Environments:    {', '.join(e.value for e in device.environments)}")
    print()
    print(f"Is Virtual:      {'Yes' if device.is_virtual else 'No'}")
    print(f"Is CI:           {'Yes' if device.is_ci else 'No'}")
    print("-" * 70)
    print()

    # Compare with Python implementation
    print("⚖️  Comparing with pure Python implementation...")
    try:
        import time

        from cligram.utils.device import get_device_info as get_device_info_python

        # Time Python implementation
        start = time.perf_counter()
        device_py = get_device_info_python(no_cache=True)
        python_time = time.perf_counter() - start

        # Time native implementation
        start = time.perf_counter()
        device_native = get_device_info(no_cache=True)
        native_time = time.perf_counter() - start

        print()
        print("Performance Comparison:")
        print(f"  Python: {python_time * 1000:.2f} ms")
        print(f"  Native: {native_time * 1000:.2f} ms")
        print(f"  Speedup: {python_time / native_time:.1f}x")
        print()

        # Check consistency
        if (
            device_py.platform == device_native.platform
            and device_py.architecture == device_native.architecture
        ):
            print("✅ Results are consistent between implementations")
        else:
            print("⚠️  Results differ between implementations:")
            print(
                f"  Platform: {device_py.platform.value} vs {device_native.platform.value}"
            )
            print(
                f"  Architecture: {device_py.architecture.value} vs {device_native.architecture.value}"
            )

    except ImportError:
        print("⚠️  Could not import Python implementation for comparison")

    print()
    print("=" * 70)
    print("✅ Test completed successfully!")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
