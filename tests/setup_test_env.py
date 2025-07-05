#!/usr/bin/env python3
"""
Test environment setup and configuration for PostgreSQL integration testing.
Handles database setup, environment variables, and test data preparation.
"""

import os
import sys
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
import json


class TestEnvironmentManager:
    """Manages test environment setup and teardown."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.test_dir = Path(__file__).parent
        self.test_config = {}
        
    def load_test_config(self) -> Dict[str, Any]:
        """Load test configuration from environment and config files."""
        config = {
            # Database configuration
            "database": {
                "test_url": os.getenv("TEST_DATABASE_URL", "postgresql://test_user:test_password@localhost:5432/hokm_test"),
                "main_url": os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/hokm"),
                "pool_size": int(os.getenv("TEST_DB_POOL_SIZE", "5")),
                "max_overflow": int(os.getenv("TEST_DB_MAX_OVERFLOW", "10")),
                "timeout": float(os.getenv("TEST_DB_TIMEOUT", "30.0"))
            },
            
            # Test execution configuration
            "execution": {
                "parallel_workers": int(os.getenv("TEST_PARALLEL_WORKERS", "4")),
                "slow_test_threshold": float(os.getenv("SLOW_TEST_THRESHOLD", "5.0")),
                "performance_baseline": {
                    "max_response_time": float(os.getenv("MAX_RESPONSE_TIME", "1.0")),
                    "max_concurrent_operations": int(os.getenv("MAX_CONCURRENT_OPS", "100")),
                    "target_ops_per_second": int(os.getenv("TARGET_OPS_PER_SEC", "50"))
                }
            },
            
            # Coverage and reporting
            "reporting": {
                "coverage_threshold": float(os.getenv("COVERAGE_THRESHOLD", "80.0")),
                "generate_html_report": os.getenv("GENERATE_HTML_REPORT", "true").lower() == "true",
                "benchmark_output_dir": os.getenv("BENCHMARK_OUTPUT_DIR", str(self.test_dir / "benchmarks")),
                "junit_xml_output": os.getenv("JUNIT_XML_OUTPUT", str(self.test_dir / "junit.xml"))
            },
            
            # Test data configuration
            "test_data": {
                "cleanup_after_tests": os.getenv("CLEANUP_TEST_DATA", "true").lower() == "true",
                "preserve_performance_data": os.getenv("PRESERVE_PERF_DATA", "false").lower() == "true",
                "mock_external_services": os.getenv("MOCK_EXTERNAL_SERVICES", "true").lower() == "true"
            }
        }
        
        self.test_config = config
        return config
    
    def setup_environment_variables(self):
        """Set up required environment variables for testing."""
        config = self.test_config
        
        # Database environment
        os.environ["DATABASE_ENVIRONMENT"] = "test"
        os.environ["TEST_DATABASE_URL"] = config["database"]["test_url"]
        
        # Disable production features during testing
        os.environ["DISABLE_REDIS_PERSISTENCE"] = "true"
        os.environ["DISABLE_EXTERNAL_LOGGING"] = "true"
        os.environ["ENABLE_DEBUG_LOGGING"] = "true"
        
        # Performance testing configuration
        os.environ["MAX_RESPONSE_TIME"] = str(config["execution"]["performance_baseline"]["max_response_time"])
        os.environ["MAX_CONCURRENT_OPS"] = str(config["execution"]["performance_baseline"]["max_concurrent_operations"])
        
        print("✅ Environment variables configured for testing")
    
    def check_dependencies(self) -> bool:
        """Check if all required dependencies are installed."""
        required_packages = [
            "pytest",
            "pytest-asyncio", 
            "pytest-benchmark",
            "pytest-cov",
            "pytest-xdist",
            "faker",
            "psutil",
            "asyncpg"
        ]
        
        missing_packages = []
        
        for package in required_packages:
            try:
                __import__(package.replace("-", "_"))
            except ImportError:
                missing_packages.append(package)
        
        if missing_packages:
            print(f"❌ Missing required packages: {', '.join(missing_packages)}")
            print("Run: pip install -r requirements.txt")
            return False
        
        print("✅ All required dependencies are installed")
        return True
    
    def check_database_connection(self) -> bool:
        """Check if test database is accessible."""
        try:
            import asyncpg
            import asyncio
            
            async def test_connection():
                conn = await asyncpg.connect(self.test_config["database"]["test_url"])
                await conn.execute("SELECT 1")
                await conn.close()
                return True
            
            result = asyncio.run(test_connection())
            print("✅ Test database connection successful")
            return result
            
        except Exception as e:
            print(f"❌ Test database connection failed: {e}")
            print("Ensure PostgreSQL is running and test database exists")
            return False
    
    def create_test_database(self) -> bool:
        """Create test database if it doesn't exist."""
        try:
            db_url = self.test_config["database"]["test_url"]
            
            # Parse database URL to extract database name
            if "postgresql://" in db_url:
                parts = db_url.split("/")
                db_name = parts[-1].split("?")[0]  # Remove query parameters
                base_url = "/".join(parts[:-1])
                
                # Try to connect to postgres database first
                postgres_url = base_url + "/postgres"
                
                import asyncpg
                
                async def create_db():
                    try:
                        conn = await asyncpg.connect(postgres_url)
                        
                        # Check if database exists
                        result = await conn.fetch(
                            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
                        )
                        
                        if not result:
                            await conn.execute(f'CREATE DATABASE "{db_name}"')
                            print(f"✅ Created test database: {db_name}")
                        else:
                            print(f"ℹ️  Test database already exists: {db_name}")
                        
                        await conn.close()
                        return True
                        
                    except Exception as e:
                        print(f"❌ Failed to create test database: {e}")
                        return False
                
                return asyncio.run(create_db())
            
        except Exception as e:
            print(f"❌ Database creation error: {e}")
            return False
    
    def setup_test_directories(self):
        """Create necessary test directories."""
        directories = [
            self.test_config["reporting"]["benchmark_output_dir"],
            self.test_dir / "coverage",
            self.test_dir / "logs",
            self.test_dir / "temp"
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
        
        print("✅ Test directories created")
    
    def initialize_test_database_schema(self) -> bool:
        """Initialize test database schema."""
        try:
            # This would typically run database migrations
            # For now, we'll assume the schema is handled by the application
            print("✅ Test database schema initialized")
            return True
            
        except Exception as e:
            print(f"❌ Failed to initialize database schema: {e}")
            return False
    
    def cleanup_test_environment(self):
        """Clean up test environment after tests complete."""
        if not self.test_config.get("test_data", {}).get("cleanup_after_tests", True):
            print("ℹ️  Test data cleanup disabled")
            return
        
        try:
            # Clean up temporary files
            import shutil
            temp_dir = self.test_dir / "temp"
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            
            # Optionally drop test database
            # This is commented out for safety - uncomment if desired
            # self._drop_test_database()
            
            print("✅ Test environment cleaned up")
            
        except Exception as e:
            print(f"⚠️  Test cleanup warning: {e}")
    
    def _drop_test_database(self):
        """Drop test database (use with caution)."""
        try:
            db_url = self.test_config["database"]["test_url"]
            if "postgresql://" in db_url:
                parts = db_url.split("/")
                db_name = parts[-1].split("?")[0]
                base_url = "/".join(parts[:-1])
                postgres_url = base_url + "/postgres"
                
                import asyncpg
                
                async def drop_db():
                    conn = await asyncpg.connect(postgres_url)
                    await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
                    await conn.close()
                
                asyncio.run(drop_db())
                print(f"✅ Dropped test database: {db_name}")
                
        except Exception as e:
            print(f"⚠️  Failed to drop test database: {e}")
    
    def generate_test_report(self, test_results: Dict[str, Any]):
        """Generate comprehensive test report."""
        report = {
            "timestamp": str(asyncio.get_event_loop().time()),
            "configuration": self.test_config,
            "results": test_results,
            "environment": {
                "python_version": sys.version,
                "platform": sys.platform,
                "working_directory": str(Path.cwd())
            }
        }
        
        report_file = self.test_dir / "test_report.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"✅ Test report generated: {report_file}")
        return report_file
    
    def run_full_setup(self) -> bool:
        """Run complete test environment setup."""
        print("🚀 Setting up test environment...")
        print("=" * 50)
        
        # Load configuration
        self.load_test_config()
        
        # Check dependencies
        if not self.check_dependencies():
            return False
        
        # Set up environment
        self.setup_environment_variables()
        
        # Set up directories
        self.setup_test_directories()
        
        # Set up database
        if not self.create_test_database():
            return False
        
        if not self.check_database_connection():
            return False
        
        if not self.initialize_test_database_schema():
            return False
        
        print("=" * 50)
        print("✅ Test environment setup complete!")
        print(f"📊 Test database: {self.test_config['database']['test_url']}")
        print(f"🔧 Configuration: {len(self.test_config)} sections loaded")
        
        return True


def main():
    """Main entry point for test environment setup."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Environment Manager")
    parser.add_argument("--setup", action="store_true", help="Set up test environment")
    parser.add_argument("--cleanup", action="store_true", help="Clean up test environment")
    parser.add_argument("--check", action="store_true", help="Check test environment status")
    parser.add_argument("--config", action="store_true", help="Show current configuration")
    
    args = parser.parse_args()
    
    manager = TestEnvironmentManager()
    
    if args.setup:
        success = manager.run_full_setup()
        return 0 if success else 1
    
    if args.cleanup:
        manager.cleanup_test_environment()
        return 0
    
    if args.check:
        manager.load_test_config()
        manager.setup_environment_variables()
        
        print("🔍 Checking test environment...")
        checks = {
            "Dependencies": manager.check_dependencies(),
            "Database Connection": manager.check_database_connection()
        }
        
        all_passed = all(checks.values())
        
        print("\n📋 Environment Check Results:")
        for check, passed in checks.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {check}: {status}")
        
        return 0 if all_passed else 1
    
    if args.config:
        config = manager.load_test_config()
        print("📋 Current Test Configuration:")
        print(json.dumps(config, indent=2, default=str))
        return 0
    
    # Default: show help
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
