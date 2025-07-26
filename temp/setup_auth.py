#!/usr/bin/env python3
"""
Setup script for Hokm Game Authentication System
"""
import os
import sys
import subprocess
from pathlib import Path

def install_dependencies():
    """Install required Python packages"""
    print("Installing authentication dependencies...")
    
    requirements_file = Path(__file__).parent / "requirements-auth.txt"
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
        ])
        print("✓ Dependencies installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"✗ Error installing dependencies: {e}")
        sys.exit(1)

def setup_environment():
    """Set up environment variables"""
    print("Setting up environment...")
    
    env_file = Path(__file__).parent / ".env"
    
    if not env_file.exists():
        with open(env_file, 'w') as f:
            f.write("# Hokm Game Authentication Environment\n")
            f.write("SECRET_KEY=your-secret-key-change-in-production\n")
            f.write("DATABASE_URL=postgresql://user:password@localhost/hokm_game\n")
            f.write("FLASK_ENV=development\n")
            f.write("FLASK_DEBUG=True\n")
        
        print("✓ Environment file created (.env)")
        print("⚠️  Please update the SECRET_KEY and DATABASE_URL in .env file")
    else:
        print("✓ Environment file already exists")

def create_database_tables():
    """Create database tables"""
    print("Creating database tables...")
    
    try:
        from database import init_database
        init_database()
        print("✓ Database tables created successfully!")
    except Exception as e:
        print(f"✗ Error creating database tables: {e}")
        print("⚠️  Make sure PostgreSQL is running and DATABASE_URL is correct")

def main():
    """Main setup function"""
    print("🎮 Hokm Game Authentication System Setup")
    print("=" * 50)
    
    # Install dependencies
    install_dependencies()
    
    # Setup environment
    setup_environment()
    
    # Create database tables
    create_database_tables()
    
    print("\n" + "=" * 50)
    print("✓ Setup completed successfully!")
    print("\nNext steps:")
    print("1. Update .env file with your database credentials")
    print("2. Run: python backend/app.py")
    print("3. Open frontend/auth_demo.html in your browser")
    print("4. Start testing the authentication system!")

if __name__ == "__main__":
    main()
