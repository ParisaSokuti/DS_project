#!/usr/bin/env python3
"""
Database Deployment Quick Setup
Installs missing dependencies and sets up environment for database deployment automation

Run this script to quickly set up the database deployment environment:
./database/setup.py
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(command, description):
    """Run a command and handle errors"""
    print(f"📦 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✓ {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed: {e}")
        if e.stdout:
            print(f"STDOUT: {e.stdout}")
        if e.stderr:
            print(f"STDERR: {e.stderr}")
        return False


def install_missing_packages():
    """Install missing Python packages"""
    packages = [
        'aiofiles>=22.0.0',
        'psutil>=5.9.0'
    ]
    
    for package in packages:
        if not run_command(f"pip install {package}", f"Installing {package}"):
            return False
    
    return True


def create_env_example():
    """Create example environment file"""
    env_content = """# Database Deployment Environment Variables
# Copy this file to .env and fill in your values

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=hokm_game
DB_USER=hokm_app

# Environment-specific Database Passwords
DB_PASSWORD_DEV=dev_password_change_me
DB_PASSWORD_TEST=test_password_change_me
DB_PASSWORD_STAGING=staging_secure_password_change_me
DB_PASSWORD_PRODUCTION=production_ultra_secure_password_change_me

# Backup Configuration (for staging/production)
BACKUP_ENCRYPTION_KEY=your_backup_encryption_key_here
S3_BACKUP_BUCKET_STAGING=your-staging-backup-bucket
S3_BACKUP_BUCKET_PRODUCTION=your-production-backup-bucket

# Notification Configuration
SLACK_WEBHOOK_STAGING=https://hooks.slack.com/your/staging/webhook
SLACK_WEBHOOK_PRODUCTION=https://hooks.slack.com/your/production/webhook

# AWS Configuration (for S3 backups)
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_DEFAULT_REGION=us-west-2
"""
    
    env_example_path = Path(__file__).parent.parent / '.env.database.example'
    
    if not env_example_path.exists():
        with open(env_example_path, 'w') as f:
            f.write(env_content)
        print(f"✓ Created {env_example_path}")
    else:
        print(f"ℹ️  {env_example_path} already exists")
    
    return True


def main():
    """Main setup function"""
    print("🚀 Database Deployment Automation Setup")
    print("=" * 50)
    
    success = True
    
    # Install missing packages
    print("\n1. Installing missing Python packages...")
    if not install_missing_packages():
        success = False
    
    # Create environment example
    print("\n2. Creating environment configuration example...")
    if not create_env_example():
        success = False
    
    # Validate setup
    print("\n3. Validating setup...")
    if run_command("python database/validate_setup.py", "Running validation"):
        print("🎉 Setup completed successfully!")
        print("\nNext steps:")
        print("1. Copy .env.database.example to .env and configure your database credentials")
        print("2. Set up your PostgreSQL database")
        print("3. Test deployment: python database/deploy.py --environment development --dry-run")
    else:
        print("⚠️  Setup completed with warnings. Check validation output above.")
        success = False
    
    if not success:
        print("\n❌ Setup encountered some issues. Please review the output above.")
        sys.exit(1)


if __name__ == '__main__':
    main()
