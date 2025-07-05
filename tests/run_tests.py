#!/usr/bin/env python3
"""
Comprehensive test runner for PostgreSQL integration tests.
Provides different test execution modes and reporting.
"""

import os
import sys
import asyncio
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Any


class TestRunner:
    """Comprehensive test runner for PostgreSQL integration tests."""
    
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.project_root = self.test_dir.parent
        
    def run_integration_tests(self, verbose: bool = False, coverage: bool = False) -> int:
        """Run integration tests."""
        cmd = [
            "python", "-m", "pytest",
            str(self.test_dir / "test_database_integration.py"),
            "-m", "integration",
            "--tb=short"
        ]
        
        if verbose:
            cmd.append("-v")
        
        if coverage:
            cmd.extend(["--cov=backend", "--cov-report=html", "--cov-report=term"])
        
        return subprocess.run(cmd, cwd=self.project_root).returncode
    
    def run_performance_tests(self, benchmark_only: bool = False) -> int:
        """Run performance and benchmark tests."""
        cmd = [
            "python", "-m", "pytest",
            str(self.test_dir / "test_performance_benchmarks.py"),
            "-m", "performance",
            "--tb=short"
        ]
        
        if benchmark_only:
            cmd.append("--benchmark-only")
        else:
            cmd.extend(["--benchmark-save=hokm_benchmarks", "--benchmark-sort=mean"])
        
        return subprocess.run(cmd, cwd=self.project_root).returncode
    
    def run_transaction_tests(self, verbose: bool = False) -> int:
        """Run transaction management tests."""
        cmd = [
            "python", "-m", "pytest",
            str(self.test_dir / "test_transaction_management.py"),
            "-m", "integration",
            "--tb=short"
        ]
        
        if verbose:
            cmd.append("-v")
        
        return subprocess.run(cmd, cwd=self.project_root).returncode
    
    def run_concurrent_tests(self, max_workers: int = 4) -> int:
        """Run concurrent operation tests."""
        cmd = [
            "python", "-m", "pytest",
            str(self.test_dir),
            "-m", "concurrent",
            f"-n={max_workers}",
            "--tb=short"
        ]
        
        return subprocess.run(cmd, cwd=self.project_root).returncode
    
    def run_full_test_suite(self, coverage: bool = True, benchmark: bool = True) -> Dict[str, int]:
        """Run the complete test suite."""
        results = {}
        
        print("🧪 Running PostgreSQL Integration Test Suite...")
        print("=" * 60)
        
        # Integration tests
        print("\n📊 Running Integration Tests...")
        results["integration"] = self.run_integration_tests(verbose=True, coverage=coverage)
        
        # Performance tests
        if benchmark:
            print("\n⚡ Running Performance Tests...")
            results["performance"] = self.run_performance_tests(benchmark_only=False)
        
        # Transaction tests
        print("\n🔄 Running Transaction Tests...")
        results["transaction"] = self.run_transaction_tests(verbose=True)
        
        # Concurrent tests
        print("\n🚀 Running Concurrent Tests...")
        results["concurrent"] = self.run_concurrent_tests(max_workers=4)
        
        # Summary
        print("\n" + "=" * 60)
        print("📈 Test Results Summary:")
        for test_type, exit_code in results.items():
            status = "✅ PASSED" if exit_code == 0 else "❌ FAILED"
            print(f"  {test_type.title()} Tests: {status}")
        
        return results
    
    def setup_test_environment(self) -> bool:
        """Set up the test environment."""
        print("🔧 Setting up test environment...")
        
        # Check if test database URL is set
        test_db_url = os.getenv("TEST_DATABASE_URL")
        if not test_db_url:
            print("⚠️  TEST_DATABASE_URL not set. Using default.")
            os.environ["TEST_DATABASE_URL"] = "postgresql://test_user:test_password@localhost:5432/hokm_test"
        
        # Set test environment flag
        os.environ["DATABASE_ENVIRONMENT"] = "test"
        
        # Install test dependencies
        try:
            subprocess.run([
                "pip", "install", "-r", str(self.project_root / "requirements.txt")
            ], check=True, capture_output=True)
            print("✅ Dependencies installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install dependencies: {e}")
            return False
    
    def create_test_database(self) -> bool:
        """Create test database if it doesn't exist."""
        print("🗄️  Creating test database...")
        
        # This would need to be customized based on your database setup
        try:
            # Example command - adjust based on your setup
            subprocess.run([
                "createdb", "hokm_test"
            ], check=True, capture_output=True)
            print("✅ Test database created successfully")
            return True
        except subprocess.CalledProcessError:
            print("ℹ️  Test database may already exist")
            return True
    
    def cleanup_test_environment(self):
        """Clean up test environment."""
        print("🧹 Cleaning up test environment...")
        
        # Remove test database (optional)
        try:
            subprocess.run([
                "dropdb", "hokm_test"
            ], check=True, capture_output=True)
            print("✅ Test database cleaned up")
        except subprocess.CalledProcessError:
            print("ℹ️  Test database cleanup skipped")


def main():
    """Main entry point for test runner."""
    parser = argparse.ArgumentParser(description="PostgreSQL Integration Test Runner")
    parser.add_argument("--setup", action="store_true", help="Set up test environment")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--performance", action="store_true", help="Run performance tests only")
    parser.add_argument("--transaction", action="store_true", help="Run transaction tests only")
    parser.add_argument("--concurrent", action="store_true", help="Run concurrent tests only")
    parser.add_argument("--full", action="store_true", help="Run full test suite")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmarks")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--cleanup", action="store_true", help="Clean up test environment")
    
    args = parser.parse_args()
    
    runner = TestRunner()
    
    if args.setup:
        if not runner.setup_test_environment():
            return 1
        if not runner.create_test_database():
            return 1
        print("✅ Test environment setup complete!")
        return 0
    
    if args.cleanup:
        runner.cleanup_test_environment()
        return 0
    
    if args.integration:
        return runner.run_integration_tests(verbose=args.verbose, coverage=args.coverage)
    
    if args.performance:
        return runner.run_performance_tests(benchmark_only=args.benchmark)
    
    if args.transaction:
        return runner.run_transaction_tests(verbose=args.verbose)
    
    if args.concurrent:
        return runner.run_concurrent_tests()
    
    if args.full or not any([args.integration, args.performance, args.transaction, args.concurrent]):
        results = runner.run_full_test_suite(coverage=args.coverage, benchmark=args.benchmark)
        return 0 if all(code == 0 for code in results.values()) else 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
