#!/usr/bin/env python3
"""
Script to change PostgreSQL password for the Hokm game database
"""
import asyncio
import asyncpg
import getpass
import sys
from typing import Optional

async def change_postgresql_password(old_password: str, new_password: str, username: str = "hokm_admin"):
    """
    Change PostgreSQL password for the specified user.
    
    Args:
        old_password: Current password
        new_password: New password to set
        username: Database username (default: hokm_admin)
    """
    try:
        # Connect with current credentials
        current_dsn = f"postgresql://{username}:{old_password}@localhost:5432/hokm_game"
        
        print(f"Connecting to database as {username}...")
        conn = await asyncpg.connect(current_dsn)
        
        # Change password
        print("Changing password...")
        await conn.execute(f"ALTER USER {username} WITH PASSWORD $1", new_password)
        
        # Test new connection
        print("Testing new password...")
        await conn.close()
        
        new_dsn = f"postgresql://{username}:{new_password}@localhost:5432/hokm_game"
        test_conn = await asyncpg.connect(new_dsn)
        result = await test_conn.fetchval("SELECT current_user")
        await test_conn.close()
        
        print(f"✅ Password changed successfully! Connected as: {result}")
        print(f"New DSN: postgresql://{username}:{new_password}@localhost:5432/hokm_game")
        
        return True
        
    except Exception as e:
        print(f"❌ Error changing password: {e}")
        return False

async def create_new_user(admin_password: str, new_username: str, new_password: str):
    """
    Create a new database user with the specified password.
    
    Args:
        admin_password: Current admin password
        new_username: New username to create
        new_password: Password for new user
    """
    try:
        # Connect as admin
        admin_dsn = f"postgresql://hokm_admin:{admin_password}@localhost:5432/hokm_game"
        
        print(f"Connecting as admin...")
        conn = await asyncpg.connect(admin_dsn)
        
        # Create new user
        print(f"Creating user {new_username}...")
        await conn.execute(f"CREATE USER {new_username} WITH PASSWORD $1", new_password)
        
        # Grant permissions
        print("Granting permissions...")
        await conn.execute(f"GRANT ALL PRIVILEGES ON DATABASE hokm_game TO {new_username}")
        await conn.execute(f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {new_username}")
        await conn.execute(f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {new_username}")
        
        await conn.close()
        
        # Test new user
        print("Testing new user...")
        new_dsn = f"postgresql://{new_username}:{new_password}@localhost:5432/hokm_game"
        test_conn = await asyncpg.connect(new_dsn)
        result = await test_conn.fetchval("SELECT current_user")
        await test_conn.close()
        
        print(f"✅ User created successfully! Connected as: {result}")
        print(f"New DSN: postgresql://{new_username}:{new_password}@localhost:5432/hokm_game")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating user: {e}")
        return False

async def main():
    """Main function to handle password change operations."""
    print("🔐 PostgreSQL Password Management for Hokm Game")
    print("=" * 50)
    
    print("Choose an option:")
    print("1. Change password for existing user (hokm_admin)")
    print("2. Create new user with new password")
    print("3. Test current connection")
    
    choice = input("Enter your choice (1-3): ").strip()
    
    if choice == "1":
        # Change existing password
        print(f"\nChanging password for user: hokm_admin")
        old_password = getpass.getpass("Enter current password: ")
        new_password = getpass.getpass("Enter new password: ")
        confirm_password = getpass.getpass("Confirm new password: ")
        
        if new_password != confirm_password:
            print("❌ Passwords do not match!")
            return
        
        success = await change_postgresql_password(old_password, new_password)
        
        if success:
            print("\n📝 Update your configuration files with the new password:")
            print("1. Update environment variables")
            print("2. Update test files")
            print("3. Update any configuration files")
            
    elif choice == "2":
        # Create new user
        print(f"\nCreating new database user")
        admin_password = getpass.getpass("Enter current admin password (hokm_admin): ")
        new_username = input("Enter new username: ").strip()
        new_password = getpass.getpass("Enter password for new user: ")
        confirm_password = getpass.getpass("Confirm password: ")
        
        if new_password != confirm_password:
            print("❌ Passwords do not match!")
            return
        
        success = await create_new_user(admin_password, new_username, new_password)
        
        if success:
            print(f"\n📝 Update your configuration to use the new user:")
            print(f"DATABASE_URL=postgresql://{new_username}:{new_password}@localhost:5432/hokm_game")
            
    elif choice == "3":
        # Test current connection
        print(f"\nTesting current connection...")
        try:
            current_dsn = "postgresql://hokm_admin:hokm_secure_2024!@localhost:5432/hokm_game"
            conn = await asyncpg.connect(current_dsn)
            result = await conn.fetchval("SELECT current_user, current_database()")
            await conn.close()
            print(f"✅ Connection successful! Connected as: {result}")
            print(f"Current DSN: {current_dsn}")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            print("Try updating your password or check if PostgreSQL is running")
    
    else:
        print("❌ Invalid choice!")

if __name__ == "__main__":
    asyncio.run(main())
