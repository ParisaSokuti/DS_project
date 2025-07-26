#!/usr/bin/env python3
"""
PostgreSQL Password Management for Hokm Game
Works with your actual database setup
"""
import asyncio
import asyncpg
import getpass
import sys
import subprocess

async def test_connection(username: str, password: str, database: str = "hokm_game"):
    """Test database connection with given credentials."""
    try:
        dsn = f"postgresql://{username}:{password}@localhost:5432/{database}"
        conn = await asyncpg.connect(dsn)
        result = await conn.fetchval("SELECT current_user, current_database()")
        await conn.close()
        return True, result
    except Exception as e:
        return False, str(e)

async def change_user_password(admin_user: str, admin_password: str, target_user: str, new_password: str):
    """Change password for a specific user."""
    try:
        # Connect as admin
        admin_dsn = f"postgresql://{admin_user}:{admin_password}@localhost:5432/postgres"
        conn = await asyncpg.connect(admin_dsn)
        
        # Change password
        await conn.execute(f"ALTER USER {target_user} WITH PASSWORD $1", new_password)
        await conn.close()
        
        # Test new password
        success, result = await test_connection(target_user, new_password, "hokm_game")
        return success, result
        
    except Exception as e:
        return False, str(e)

async def create_database_and_user(admin_user: str, admin_password: str, new_user: str, new_password: str):
    """Create hokm_game database and user if they don't exist."""
    try:
        # Connect as admin to postgres database
        admin_dsn = f"postgresql://{admin_user}:{admin_password}@localhost:5432/postgres"
        conn = await asyncpg.connect(admin_dsn)
        
        # Create database if it doesn't exist
        try:
            await conn.execute("CREATE DATABASE hokm_game")
            print("✅ Created hokm_game database")
        except Exception as e:
            if "already exists" in str(e):
                print("ℹ️  hokm_game database already exists")
            else:
                print(f"⚠️  Error creating database: {e}")
        
        # Create user if it doesn't exist
        try:
            await conn.execute(f"CREATE USER {new_user} WITH PASSWORD $1", new_password)
            print(f"✅ Created user {new_user}")
        except Exception as e:
            if "already exists" in str(e):
                print(f"ℹ️  User {new_user} already exists")
                # Update password for existing user
                await conn.execute(f"ALTER USER {new_user} WITH PASSWORD $1", new_password)
                print(f"✅ Updated password for {new_user}")
            else:
                print(f"⚠️  Error creating user: {e}")
        
        # Grant permissions
        await conn.execute(f"GRANT ALL PRIVILEGES ON DATABASE hokm_game TO {new_user}")
        await conn.close()
        
        # Connect to hokm_game database and grant table permissions
        db_dsn = f"postgresql://{admin_user}:{admin_password}@localhost:5432/hokm_game"
        conn = await asyncpg.connect(db_dsn)
        
        try:
            await conn.execute(f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {new_user}")
            await conn.execute(f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {new_user}")
            await conn.execute(f"GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO {new_user}")
            await conn.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {new_user}")
            await conn.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {new_user}")
        except Exception as e:
            print(f"⚠️  Error granting permissions: {e}")
        
        await conn.close()
        
        # Test the new user
        success, result = await test_connection(new_user, new_password, "hokm_game")
        return success, result
        
    except Exception as e:
        return False, str(e)

def get_available_users():
    """Get list of available PostgreSQL users."""
    try:
        result = subprocess.run(
            ['psql', '-U', 'postgres', '-d', 'postgres', '-c', 'SELECT usename FROM pg_user;'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            users = []
            for line in lines[2:-1]:  # Skip header and footer
                user = line.strip()
                if user and user != '-':
                    users.append(user)
            return users
        return []
    except Exception:
        return []

async def main():
    """Main function."""
    print("🔐 PostgreSQL Password Management for Hokm Game")
    print("=" * 60)
    
    # Get available users
    users = get_available_users()
    if users:
        print(f"Available users: {', '.join(users)}")
    else:
        print("Could not retrieve user list")
    
    print("\nChoose an option:")
    print("1. Change password for existing user")
    print("2. Create/setup hokm_admin user with new password")
    print("3. Test connection with current credentials")
    print("4. Setup complete database (recommended)")
    
    choice = input("Enter your choice (1-4): ").strip()
    
    if choice == "1":
        # Change existing user password
        print(f"\nAvailable users: {', '.join(users)}")
        target_user = input("Enter username to change password for: ").strip()
        
        if target_user not in users:
            print(f"❌ User {target_user} not found!")
            return
        
        print("Enter admin credentials (usually 'postgres' user):")
        admin_user = input("Admin username (postgres): ").strip() or "postgres"
        admin_password = getpass.getpass(f"Admin password for {admin_user}: ")
        
        new_password = getpass.getpass(f"New password for {target_user}: ")
        confirm_password = getpass.getpass("Confirm new password: ")
        
        if new_password != confirm_password:
            print("❌ Passwords do not match!")
            return
        
        success, result = await change_user_password(admin_user, admin_password, target_user, new_password)
        
        if success:
            print(f"✅ Password changed successfully! {result}")
            print(f"New DSN: postgresql://{target_user}:{new_password}@localhost:5432/hokm_game")
        else:
            print(f"❌ Failed to change password: {result}")
    
    elif choice == "2":
        # Create hokm_admin user
        print("Enter admin credentials (usually 'postgres' user):")
        admin_user = input("Admin username (postgres): ").strip() or "postgres"
        admin_password = getpass.getpass(f"Admin password for {admin_user}: ")
        
        new_password = getpass.getpass("Password for hokm_admin: ")
        confirm_password = getpass.getpass("Confirm password: ")
        
        if new_password != confirm_password:
            print("❌ Passwords do not match!")
            return
        
        success, result = await create_database_and_user(admin_user, admin_password, "hokm_admin", new_password)
        
        if success:
            print(f"✅ hokm_admin user setup successfully! {result}")
            print(f"DSN: postgresql://hokm_admin:{new_password}@localhost:5432/hokm_game")
        else:
            print(f"❌ Failed to setup user: {result}")
    
    elif choice == "3":
        # Test connection
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        database = input("Database (hokm_game): ").strip() or "hokm_game"
        
        success, result = await test_connection(username, password, database)
        
        if success:
            print(f"✅ Connection successful! {result}")
            print(f"DSN: postgresql://{username}:{password}@localhost:5432/{database}")
        else:
            print(f"❌ Connection failed: {result}")
    
    elif choice == "4":
        # Complete setup
        print("🚀 Setting up complete database for Hokm game")
        print("This will create/update the hokm_admin user and hokm_game database")
        
        admin_user = input("Admin username (postgres): ").strip() or "postgres"
        admin_password = getpass.getpass(f"Admin password for {admin_user}: ")
        
        new_password = getpass.getpass("Password for hokm_admin: ")
        confirm_password = getpass.getpass("Confirm password: ")
        
        if new_password != confirm_password:
            print("❌ Passwords do not match!")
            return
        
        success, result = await create_database_and_user(admin_user, admin_password, "hokm_admin", new_password)
        
        if success:
            print(f"✅ Complete setup successful! {result}")
            print("\n📝 Update your configuration files:")
            print(f"DATABASE_URL=postgresql://hokm_admin:{new_password}@localhost:5432/hokm_game")
            print(f"DATABASE_READ_URL=postgresql://hokm_admin:{new_password}@localhost:5433/hokm_game")
            print("\n🔧 Next steps:")
            print("1. Copy .env.example to .env")
            print("2. Update the passwords in .env")
            print("3. Run your database schema setup script")
        else:
            print(f"❌ Setup failed: {result}")
    
    else:
        print("❌ Invalid choice!")

if __name__ == "__main__":
    asyncio.run(main())
