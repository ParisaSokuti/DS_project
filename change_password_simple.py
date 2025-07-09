#!/usr/bin/env python3
"""
Simple PostgreSQL Password Changer for Hokm Game
"""
import getpass
import subprocess
import sys

def run_psql_command(command, user="postgres", database="postgres"):
    """Run a psql command and return the result."""
    try:
        cmd = ['psql', '-U', user, '-d', database, '-c', command]
        result = subprocess.run(cmd, capture_output=True, text=True, input='\n')
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def test_connection(username, password, database="hokm_game"):
    """Test database connection."""
    try:
        env = {'PGPASSWORD': password}
        cmd = ['psql', '-U', username, '-d', database, '-c', 'SELECT current_user;']
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)

def change_password(admin_user, admin_password, target_user, new_password):
    """Change password for a user."""
    try:
        # Set admin password in environment
        env = {'PGPASSWORD': admin_password}
        
        # Change password using psql
        cmd = ['psql', '-U', admin_user, '-d', 'postgres', '-c', 
               f"ALTER USER {target_user} WITH PASSWORD '{new_password}';"]
        
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def main():
    print("🔐 Simple PostgreSQL Password Changer for Hokm Game")
    print("=" * 60)
    
    # Get available users
    success, stdout, stderr = run_psql_command("SELECT usename FROM pg_user;")
    
    if success:
        lines = stdout.strip().split('\n')
        users = []
        for line in lines[2:-1]:  # Skip header and footer
            user = line.strip()
            if user and user != '-' and user != 'usename':
                users.append(user)
        print(f"Available users: {', '.join(users)}")
    else:
        print("Could not get user list. Make sure PostgreSQL is running.")
        return
    
    print("\nChoose an option:")
    print("1. Change password for existing user")
    print("2. Test connection")
    print("3. Create hokm_admin user")
    
    choice = input("Enter your choice (1-3): ").strip()
    
    if choice == "1":
        # Change password
        print(f"\nAvailable users: {', '.join(users)}")
        target_user = input("Enter username to change password for: ").strip()
        
        if target_user not in users:
            print(f"❌ User {target_user} not found!")
            return
        
        admin_user = input("Admin username (postgres): ").strip() or "postgres"
        admin_password = getpass.getpass(f"Admin password for {admin_user}: ")
        
        new_password = getpass.getpass(f"New password for {target_user}: ")
        confirm_password = getpass.getpass("Confirm new password: ")
        
        if new_password != confirm_password:
            print("❌ Passwords do not match!")
            return
        
        success, stdout, stderr = change_password(admin_user, admin_password, target_user, new_password)
        
        if success:
            print(f"✅ Password changed successfully for {target_user}!")
            
            # Test new password
            test_success, test_result = test_connection(target_user, new_password)
            if test_success:
                print(f"✅ Connection test passed!")
                print(f"New DSN: postgresql://{target_user}:{new_password}@localhost:5432/hokm_game")
            else:
                print(f"⚠️  Password changed but connection test failed: {test_result}")
        else:
            print(f"❌ Failed to change password:")
            print(f"Error: {stderr}")
    
    elif choice == "2":
        # Test connection
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        database = input("Database (hokm_game): ").strip() or "hokm_game"
        
        success, result = test_connection(username, password, database)
        
        if success:
            print(f"✅ Connection successful!")
            print(f"Connected to: {database}")
            print(f"DSN: postgresql://{username}:{password}@localhost:5432/{database}")
        else:
            print(f"❌ Connection failed!")
            print("Make sure:")
            print("1. PostgreSQL is running")
            print("2. Database exists")
            print("3. Username and password are correct")
    
    elif choice == "3":
        # Create hokm_admin user
        admin_user = input("Admin username (postgres): ").strip() or "postgres"
        admin_password = getpass.getpass(f"Admin password for {admin_user}: ")
        
        new_password = getpass.getpass("Password for hokm_admin: ")
        confirm_password = getpass.getpass("Confirm password: ")
        
        if new_password != confirm_password:
            print("❌ Passwords do not match!")
            return
        
        # Create user
        success, stdout, stderr = change_password(admin_user, admin_password, "hokm_admin", new_password)
        
        if "does not exist" in stderr:
            # User doesn't exist, create it
            env = {'PGPASSWORD': admin_password}
            cmd = ['psql', '-U', admin_user, '-d', 'postgres', '-c', 
                   f"CREATE USER hokm_admin WITH PASSWORD '{new_password}';"]
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
            
            if result.returncode == 0:
                print("✅ Created hokm_admin user!")
                
                # Grant permissions
                commands = [
                    "GRANT ALL PRIVILEGES ON DATABASE hokm_game TO hokm_admin;",
                    "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO hokm_admin;",
                    "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO hokm_admin;"
                ]
                
                for cmd_sql in commands:
                    cmd = ['psql', '-U', admin_user, '-d', 'hokm_game', '-c', cmd_sql]
                    subprocess.run(cmd, capture_output=True, text=True, env=env)
                
                print("✅ Granted permissions to hokm_admin!")
                print(f"DSN: postgresql://hokm_admin:{new_password}@localhost:5432/hokm_game")
            else:
                print(f"❌ Failed to create user: {result.stderr}")
        else:
            print(f"✅ hokm_admin user already exists, password updated!")
            print(f"DSN: postgresql://hokm_admin:{new_password}@localhost:5432/hokm_game")
    
    else:
        print("❌ Invalid choice!")

if __name__ == "__main__":
    main()
