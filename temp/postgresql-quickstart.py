#!/usr/bin/env python3
"""
Quick start script for PostgreSQL integration with Hokm Game Server
Sets up and validates the complete PostgreSQL environment
"""
import asyncio
import os
import subprocess
import sys
import time


def run_command(command, description=""):
    """Run a shell command and return success status."""
    if description:
        print(f"🔧 {description}")
    
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr


def check_docker():
    """Check if Docker is available."""
    success, output = run_command("docker --version", "Checking Docker availability")
    if success:
        print("✅ Docker is available")
        return True
    else:
        print("❌ Docker is not available. Please install Docker first.")
        return False


def check_docker_compose():
    """Check if Docker Compose is available."""
    success, output = run_command("docker-compose --version", "Checking Docker Compose availability")
    if success:
        print("✅ Docker Compose is available")
        return True
    else:
        print("❌ Docker Compose is not available. Please install Docker Compose first.")
        return False


def setup_environment():
    """Set up the environment."""
    print("🏗️  Setting up PostgreSQL environment...")
    
    # Run setup script
    if os.path.exists("setup-postgresql.sh"):
        success, output = run_command("./setup-postgresql.sh", "Running setup script")
        if success:
            print("✅ Environment setup completed")
            return True
        else:
            print(f"❌ Environment setup failed: {output}")
            return False
    else:
        print("❌ setup-postgresql.sh not found")
        return False


def start_services():
    """Start Docker services."""
    print("🚀 Starting PostgreSQL services...")
    
    # Check if services are already running
    success, output = run_command("docker-compose ps", "Checking service status")
    if "Up" in output:
        print("ℹ️  Some services are already running")
    
    # Start services
    success, output = run_command("docker-compose up -d", "Starting services")
    if success:
        print("✅ Services started successfully")
        
        # Wait for services to be ready
        print("⏳ Waiting for services to be ready...")
        time.sleep(30)
        
        return True
    else:
        print(f"❌ Failed to start services: {output}")
        return False


def check_service_health():
    """Check the health of services."""
    print("🏥 Checking service health...")
    
    services_to_check = [
        ("postgres-primary", "PostgreSQL Primary"),
        ("redis-master", "Redis"),
        ("pgbouncer", "pgBouncer"),
    ]
    
    all_healthy = True
    
    for service, name in services_to_check:
        success, output = run_command(f"docker-compose exec -T {service} echo 'OK'", f"Checking {name}")
        if success:
            print(f"✅ {name} is healthy")
        else:
            print(f"❌ {name} is not healthy")
            all_healthy = False
    
    return all_healthy


def install_python_dependencies():
    """Install Python dependencies."""
    print("🐍 Installing Python dependencies...")
    
    # Check if requirements file exists
    if os.path.exists("requirements-postgresql.txt"):
        success, output = run_command("pip install -r requirements-postgresql.txt", "Installing PostgreSQL requirements")
        if success:
            print("✅ Python dependencies installed")
            return True
        else:
            print(f"❌ Failed to install dependencies: {output}")
            return False
    else:
        print("⚠️  requirements-postgresql.txt not found, skipping")
        return True


def run_tests():
    """Run the PostgreSQL integration tests."""
    print("🧪 Running PostgreSQL integration tests...")
    
    if os.path.exists("test_postgresql_integration.py"):
        success, output = run_command("python test_postgresql_integration.py", "Running PostgreSQL tests")
        if success:
            print("✅ PostgreSQL integration tests passed")
            return True
        else:
            print(f"❌ PostgreSQL integration tests failed: {output}")
            return False
    else:
        print("⚠️  test_postgresql_integration.py not found, skipping")
        return True


def show_service_info():
    """Show information about running services."""
    print("\n" + "="*60)
    print("🎉 PostgreSQL Environment is Ready!")
    print("="*60)
    
    services_info = [
        ("PostgreSQL Primary", "localhost:5432", "Database server"),
        ("PostgreSQL Replica", "localhost:5433", "Read-only replica"),
        ("pgBouncer", "localhost:6432", "Connection pooler"),
        ("Redis", "localhost:6379", "Cache server"),
        ("pgAdmin", "http://localhost:5050", "Database admin tool"),
        ("Grafana", "http://localhost:3000", "Monitoring dashboard"),
        ("Prometheus", "http://localhost:9090", "Metrics collector"),
    ]
    
    print("\n📊 Available Services:")
    for name, address, description in services_info:
        print(f"  • {name:20} {address:25} - {description}")
    
    print("\n🔧 Quick Commands:")
    print("  • View logs:           docker-compose logs -f")
    print("  • Stop services:       docker-compose down")
    print("  • Restart services:    docker-compose restart")
    print("  • Run game tests:      python test_basic_game.py")
    print("  • Check DB health:     python test_postgresql_integration.py")
    
    print("\n📚 Documentation:")
    print("  • Setup Guide:         POSTGRESQL_SETUP_GUIDE.md")
    print("  • Test Documentation:  TEST_README.md")
    
    print("\n🎮 Ready to start your Hokm game server!")


def main():
    """Main setup function."""
    print("🐘 Hokm Game Server - PostgreSQL Quick Start")
    print("=" * 50)
    
    # Prerequisites check
    if not check_docker():
        sys.exit(1)
    
    if not check_docker_compose():
        sys.exit(1)
    
    # Setup steps
    steps = [
        ("Environment Setup", setup_environment),
        ("Start Services", start_services),
        ("Check Service Health", check_service_health),
        ("Install Python Dependencies", install_python_dependencies),
        ("Run Integration Tests", run_tests),
    ]
    
    for step_name, step_func in steps:
        print(f"\n📋 Step: {step_name}")
        print("-" * 40)
        
        if not step_func():
            print(f"\n❌ Failed at step: {step_name}")
            print("Please check the errors above and try again.")
            sys.exit(1)
    
    # Show final information
    show_service_info()
    
    print("\n✨ Setup completed successfully!")


if __name__ == "__main__":
    main()
