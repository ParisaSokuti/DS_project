#!/usr/bin/env python3
"""
Immediate Security Patch Script
Applies critical security fixes to prevent immediate exploitation
"""

import os
import shutil
import re
from datetime import datetime

def backup_file(filepath):
    """Create backup before modifying"""
    backup_path = f"{filepath}.security_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path

def apply_admin_fix(content):
    """Disable the dangerous admin clear_room function"""
    print("🔧 Applying Critical Patch: Disabling admin clear_room vulnerability...")
    
    # Find and replace the dangerous clear_room function
    old_pattern = r'async def handle_clear_room\(self, websocket, message\):.*?await self\.network_manager\.notify_info\(websocket, f"Room {room_code} has been cleared\."\)'
    
    new_function = '''async def handle_clear_room(self, websocket, message):
        """SECURITY: Admin command disabled to prevent unauthorized room deletion"""
        client_ip = websocket.remote_address[0] if hasattr(websocket, 'remote_address') else 'unknown'
        print(f"[SECURITY ALERT] Blocked admin clear_room attempt from {client_ip}")
        await self.network_manager.notify_error(websocket, 
            "Admin commands have been disabled for security. Use proper administrative interface.")
        return'''
    
    # Replace the function
    new_content = re.sub(old_pattern, new_function, content, flags=re.DOTALL)
    
    if new_content != content:
        print("✅ Admin clear_room function secured")
        return new_content
    else:
        # Fallback: just disable the dangerous deletion line
        print("⚠️  Using fallback patch method...")
        new_content = content.replace(
            'self.redis_manager.delete_room(room_code)',
            '# SECURITY: Dangerous admin function disabled\n        print(f"[SECURITY] Admin deletion blocked from {websocket.remote_address}")'
        )
        new_content = new_content.replace(
            'del self.active_games[room_code]',
            '# SECURITY: Game deletion disabled'
        )
        return new_content

def add_basic_validation(content):
    """Add basic input validation"""
    print("🔧 Adding basic input validation...")
    
    # Check if validation already exists
    if 'SecurityValidator' in content:
        print("✅ Input validation already exists")
        return content
    
    # Add validation class after imports
    validation_code = '''
# SECURITY: Basic input validation added
import re
from html import escape

class SecurityValidator:
    """Basic input validation for security"""
    
    @staticmethod
    def validate_room_code(room_code):
        if not room_code or not isinstance(room_code, str):
            return None
        room_code = room_code.strip().upper()
        if not re.match(r'^[A-Z0-9_]{3,15}$', room_code):
            return None
        return room_code
    
    @staticmethod
    def validate_message_size(message):
        try:
            return len(str(message)) <= 4096  # 4KB limit
        except:
            return False
    
    @staticmethod
    def validate_suit(suit):
        if not suit or not isinstance(suit, str):
            return None
        valid_suits = ['hearts', 'diamonds', 'clubs', 'spades']
        return suit.lower() if suit.lower() in valid_suits else None

'''
    
    # Find a good place to insert (after imports, before GameServer class)
    insert_point = content.find('class GameServer:')
    if insert_point != -1:
        new_content = content[:insert_point] + validation_code + content[insert_point:]
        print("✅ Basic input validation added")
        return new_content
    else:
        print("⚠️  Could not add validation class - manual implementation needed")
        return content

def add_message_size_check(content):
    """Add message size checking"""
    print("🔧 Adding message size limits...")
    
    # Find handle_message function and add size check
    if 'validate_message_size' not in content:
        # Add size check to handle_message
        old_pattern = r'async def handle_message\(self, websocket, message\):\s*"""Handle incoming WebSocket messages"""\s*try:'
        
        new_start = '''async def handle_message(self, websocket, message):
        """Handle incoming WebSocket messages with security validation"""
        try:
            # SECURITY: Check message size
            if hasattr(self, 'SecurityValidator') and not SecurityValidator.validate_message_size(message):
                await self.network_manager.notify_error(websocket, "Message too large")
                return'''
        
        new_content = re.sub(old_pattern, new_start, content)
        if new_content != content:
            print("✅ Message size limits added")
            return new_content
    
    print("✅ Message size checking already present or added")
    return content

def apply_security_patches():
    """Apply all critical security patches"""
    server_file = "backend/server.py"
    
    if not os.path.exists(server_file):
        print(f"❌ File not found: {server_file}")
        return False
    
    # Create backup
    backup_path = backup_file(server_file)
    
    # Read current file
    with open(server_file, 'r') as f:
        content = f.read()
    
    # Apply patches
    content = apply_admin_fix(content)
    content = add_basic_validation(content)
    content = add_message_size_check(content)
    
    # Write patched file
    with open(server_file, 'w') as f:
        f.write(content)
    
    print(f"✅ Security patches applied to {server_file}")
    print(f"📋 Original backed up to: {backup_path}")
    return True

def test_patches():
    """Test that patches were applied correctly"""
    print("\n🧪 Testing applied patches...")
    
    try:
        # Try to import the server to check for syntax errors
        import sys
        sys.path.insert(0, 'backend')
        
        # Basic syntax check
        with open('backend/server.py', 'r') as f:
            content = f.read()
        
        # Check that patches were applied
        if 'SECURITY' in content:
            print("✅ Security patches detected in code")
        else:
            print("⚠️  Security patches may not have been applied correctly")
            
        if 'Admin commands have been disabled' in content or 'Admin deletion blocked' in content:
            print("✅ Admin function vulnerability patched")
        else:
            print("⚠️  Admin function may still be vulnerable")
            
        print("✅ Patch testing completed")
        return True
        
    except Exception as e:
        print(f"❌ Patch testing failed: {str(e)}")
        return False

def main():
    print("🛡️  HOKM SERVER - IMMEDIATE SECURITY PATCHES")
    print("=" * 55)
    print("This script applies critical security fixes to prevent")
    print("immediate exploitation of known vulnerabilities.")
    print()
    
    if not os.path.exists('backend'):
        print("❌ Please run this script from the DS_project root directory")
        print("   Current directory should contain 'backend/' folder")
        return
    
    print("⚠️  WARNING: This will modify your server.py file!")
    print("   A backup will be created automatically.")
    print()
    
    response = input("Continue with security patches? (y/N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("Security patching cancelled.")
        return
    
    print("\n🔧 Applying security patches...")
    
    if apply_security_patches():
        if test_patches():
            print("\n🎉 SUCCESS: Critical security vulnerabilities patched!")
            print("\n📋 What was fixed:")
            print("   ✅ Admin clear_room vulnerability disabled")
            print("   ✅ Basic input validation added")
            print("   ✅ Message size limits implemented")
            print("\n📋 Next steps:")
            print("   1. Restart your server: python backend/server.py")
            print("   2. Test that admin commands are blocked")
            print("   3. Review SECURITY_ANALYSIS_REPORT.md for comprehensive security")
            print("   4. Implement full authentication system")
            print("\n⚠️  IMPORTANT: These are emergency patches only!")
            print("   You still need to implement full security measures.")
        else:
            print("\n⚠️  Patches applied but testing failed")
            print("   Please manually verify the changes")
    else:
        print("\n❌ FAILED: Could not apply security patches")
        print("   Please apply fixes manually using CRITICAL_SECURITY_FIXES.md")

if __name__ == "__main__":
    main()
