#!/usr/bin/env python3
"""
Demo script showing how to use the PostgreSQL integration testing framework.
Demonstrates test execution, configuration, and analysis capabilities.
"""

import os
import sys
import asyncio
import subprocess
from pathlib import Path


async def main():
    """Demonstrate the testing framework capabilities."""
    
    print("🎮 Hokm Game Server - PostgreSQL Integration Testing Demo")
    print("=" * 60)
    
    # Get the tests directory
    tests_dir = Path(__file__).parent
    
    print("\n1. 🔧 Setting up test environment...")
    setup_result = subprocess.run([
        "python", str(tests_dir / "setup_test_env.py"), "--check"
    ], capture_output=True, text=True)
    
    if setup_result.returncode != 0:
        print("❌ Test environment not ready. Setting up...")
        setup_result = subprocess.run([
            "python", str(tests_dir / "setup_test_env.py"), "--setup"
        ])
        if setup_result.returncode != 0:
            print("❌ Failed to set up test environment")
            return 1
    else:
        print("✅ Test environment is ready")
    
    print("\n2. 🧪 Running quick integration tests...")
    integration_result = subprocess.run([
        "python", "-m", "pytest", 
        str(tests_dir / "test_database_integration.py"),
        "::TestDatabaseIntegration::test_database_connection",
        "-v", "--tb=short"
    ])
    
    if integration_result.returncode == 0:
        print("✅ Integration tests passed")
    else:
        print("❌ Integration tests failed")
    
    print("\n3. ⚡ Running performance benchmark sample...")
    benchmark_result = subprocess.run([
        "python", "-m", "pytest",
        str(tests_dir / "test_performance_benchmarks.py"),
        "::TestPerformanceBenchmarks::test_player_creation_performance",
        "--benchmark-only", "-v"
    ])
    
    if benchmark_result.returncode == 0:
        print("✅ Performance benchmarks completed")
    else:
        print("❌ Performance benchmarks failed")
    
    print("\n4. 🔄 Running transaction safety test...")
    transaction_result = subprocess.run([
        "python", "-m", "pytest",
        str(tests_dir / "test_transaction_management.py"),
        "::TestTransactionManagement::test_basic_transaction_commit",
        "-v", "--tb=short"
    ])
    
    if transaction_result.returncode == 0:
        print("✅ Transaction tests passed")
    else:
        print("❌ Transaction tests failed")
    
    print("\n5. 🚀 Running concurrency test sample...")
    concurrent_result = subprocess.run([
        "python", "-m", "pytest",
        str(tests_dir / "test_concurrent_operations.py"),
        "::TestConcurrentOperations::test_concurrent_player_creation",
        "-v", "--tb=short"
    ])
    
    if concurrent_result.returncode == 0:
        print("✅ Concurrency tests passed")
    else:
        print("❌ Concurrency tests failed")
    
    print("\n6. 📊 Generating test report...")
    report_result = subprocess.run([
        "python", str(tests_dir / "run_tests.py"), "--integration", "--coverage"
    ])
    
    if report_result.returncode == 0:
        print("✅ Test report generated successfully")
    else:
        print("❌ Test report generation failed")
    
    print("\n" + "=" * 60)
    print("🎯 Demo Summary:")
    print("  - Test environment setup and validation")
    print("  - Database integration testing")
    print("  - Performance benchmarking")
    print("  - Transaction safety validation")
    print("  - Concurrency testing")
    print("  - Comprehensive reporting")
    
    print("\n📚 Next Steps:")
    print("  1. Run full test suite: python tests/run_tests.py --full")
    print("  2. View test configuration: python tests/setup_test_env.py --config")
    print("  3. Run specific test categories: python tests/run_tests.py --performance")
    print("  4. Generate HTML reports: pytest tests/ --cov=backend --cov-report=html")
    
    print("\n✨ PostgreSQL Integration Testing Framework is ready!")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
