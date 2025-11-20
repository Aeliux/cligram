#!/usr/bin/env python3
"""
Benchmark script to compare native vs pure Python device detection.

This script measures performance and validates that both implementations
return equivalent results.

Usage:
    python scripts/benchmark_device.py
    python scripts/benchmark_device.py --iterations 1000
"""

import argparse
import sys
import time
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def format_time(seconds: float) -> str:
    """Format time in appropriate units."""
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.1f} µs"
    elif seconds < 1:
        return f"{seconds * 1_000:.2f} ms"
    else:
        return f"{seconds:.3f} s"


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark native vs Python device detection"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Number of iterations for benchmark (default: 100)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching for more accurate timing",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("🔬 Device Detection Benchmark")
    print("=" * 80)
    print()

    # Import modules
    try:
        from cligram.utils._device import get_device_info as get_device_info_native
        from cligram.utils._device import (
            is_available,
        )
        from cligram.utils.device import get_device_info as get_device_info_python
    except ImportError as e:
        print(f"❌ Error importing modules: {e}")
        print("\nMake sure you've built the native extension:")
        print("  python scripts/build_native.py --inplace")
        return 1

    # Check native availability
    if not is_available():
        print("❌ Native extension not available!")
        print("\nBuild it first:")
        print("  python scripts/build_native.py --inplace")
        return 1

    print("✅ Native extension is available")
    print()

    # First, get results from both implementations
    print("📊 Collecting device information...")
    print()

    device_py = get_device_info_python(no_cache=True)
    device_native = get_device_info_native(no_cache=True)

    # Display results
    print("Python Implementation Result:")
    print(f"  Platform:     {device_py.platform.value}")
    print(f"  Architecture: {device_py.architecture.value}")
    print(f"  Name:         {device_py.name}")
    print(f"  Version:      {device_py.version}")
    print(f"  Model:        {device_py.model}")
    print(f"  Environments: {', '.join(e.value for e in device_py.environments)}")
    print()

    print("Native Implementation Result:")
    print(f"  Platform:     {device_native.platform.value}")
    print(f"  Architecture: {device_native.architecture.value}")
    print(f"  Name:         {device_native.name}")
    print(f"  Version:      {device_native.version}")
    print(f"  Model:        {device_native.model}")
    print(f"  Environments: {', '.join(e.value for e in device_native.environments)}")
    print()

    # Validate consistency
    print("🔍 Validating consistency...")
    issues = []

    if device_py.platform != device_native.platform:
        issues.append(
            f"Platform mismatch: {device_py.platform.value} vs {device_native.platform.value}"
        )

    if device_py.architecture != device_native.architecture:
        issues.append(
            f"Architecture mismatch: {device_py.architecture.value} vs {device_native.architecture.value}"
        )

    if issues:
        print("⚠️  Found inconsistencies:")
        for issue in issues:
            print(f"  - {issue}")
        print()
    else:
        print("✅ Both implementations return consistent results")
        print()

    # Benchmark
    print(f"⏱️  Running benchmark ({args.iterations} iterations)...")
    print()

    # Warmup
    for _ in range(10):
        get_device_info_python(no_cache=args.no_cache)
        get_device_info_native(no_cache=args.no_cache)

    # Benchmark Python implementation
    python_times = []
    for _ in range(args.iterations):
        start = time.perf_counter()
        get_device_info_python(no_cache=args.no_cache)
        python_times.append(time.perf_counter() - start)

    # Benchmark native implementation
    native_times = []
    for _ in range(args.iterations):
        start = time.perf_counter()
        get_device_info_native(no_cache=args.no_cache)
        native_times.append(time.perf_counter() - start)

    # Calculate statistics
    py_avg = sum(python_times) / len(python_times)
    py_min = min(python_times)
    py_max = max(python_times)

    native_avg = sum(native_times) / len(native_times)
    native_min = min(native_times)
    native_max = max(native_times)

    speedup = py_avg / native_avg

    # Display results
    print("Results:")
    print()
    print("Python Implementation:")
    print(f"  Average: {format_time(py_avg)}")
    print(f"  Min:     {format_time(py_min)}")
    print(f"  Max:     {format_time(py_max)}")
    print()

    print("Native Implementation:")
    print(f"  Average: {format_time(native_avg)}")
    print(f"  Min:     {format_time(native_min)}")
    print(f"  Max:     {format_time(native_max)}")
    print()

    print("Performance:")
    print(f"  🚀 Speedup: {speedup:.1f}x faster")
    print(f"  ⚡ Time saved: {format_time(py_avg - native_avg)} per call")
    print()

    # Summary
    if speedup > 10:
        emoji = "🏆"
        message = "Excellent performance improvement!"
    elif speedup > 5:
        emoji = "✨"
        message = "Great performance improvement!"
    elif speedup > 2:
        emoji = "👍"
        message = "Good performance improvement!"
    else:
        emoji = "📊"
        message = "Modest performance improvement."

    print("=" * 80)
    print(f"{emoji} {message}")
    print(f"Native implementation is {speedup:.1f}x faster than Python")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
