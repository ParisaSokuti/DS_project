"""
Client-side authentication manager for game client
"""
import json
import os
import asyncio
import websockets
from typing import Optional, Dict, Any

class ClientAuthManager:
    """Client-side authentication manager"""
    
    def __init__(self):
        self.token = None
        self.player_info = None
        self.session_file = ".game_session"
        self.load_session()
    
    def load_session(self):
        """Load saved session from file"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r') as f:
                    session_data = json.load(f)
                    self.token = session_data.get('token')
                    self.player_info = session_data.get('player_info')
                    print(f"📂 Loaded session for {self.player_info.get('username') if self.player_info else 'unknown'}")
        except Exception as e:
            print(f"❌ Error loading session: {e}")
    
    def save_session(self):
        """Save current session to file"""
        try:
            session_data = {
                'token': self.token,
                'player_info': self.player_info
            }
            with open(self.session_file, 'w') as f:
                json.dump(session_data, f)
            print(f"💾 Session saved for {self.player_info.get('username') if self.player_info else 'unknown'}")
        except Exception as e:
            print(f"❌ Error saving session: {e}")
    
    def clear_session(self):
        """Clear current session"""
        self.token = None
        self.player_info = None
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
                print("🗑️ Session cleared")
        except Exception as e:
            print(f"❌ Error clearing session: {e}")
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return self.token is not None and self.player_info is not None
    
    def get_player_info(self) -> Optional[Dict[str, Any]]:
        """Get current player info"""
        return self.player_info
    
    def get_token(self) -> Optional[str]:
        """Get current JWT token"""
        return self.token
    
    async def authenticate_with_server(self, websocket) -> bool:
        """Authenticate with the game server"""
        if not self.is_authenticated():
            return await self.prompt_authentication(websocket)
        else:
            # Try token authentication first
            return await self.authenticate_with_token(websocket)
    
    async def authenticate_with_token(self, websocket) -> bool:
        """Authenticate using existing token"""
        if not self.token:
            return False
        
        try:
            auth_message = {
                'type': 'auth_token',
                'token': self.token
            }
            
            print(f"🔐 Authenticating with token for {self.player_info.get('username')}...")
            await websocket.send(json.dumps(auth_message))
            
            # Wait for authentication response
            response = await websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get('type') == 'auth_response':
                if response_data.get('success'):
                    self.player_info = response_data.get('player_info')
                    self.save_session()
                    print(f"✅ Authentication successful! Welcome back, {self.player_info['username']}")
                    return True
                else:
                    print(f"❌ Token authentication failed: {response_data.get('message')}")
                    # Clear invalid session
                    self.clear_session()
                    return await self.prompt_authentication(websocket)
            
            return False
            
        except Exception as e:
            print(f"❌ Token authentication error: {e}")
            return await self.prompt_authentication(websocket)
    
    async def prompt_authentication(self, websocket) -> bool:
        """Prompt user for authentication"""
        print("\n" + "="*60)
        print("🎮 Welcome to Hokm Card Game!")
        print("="*60)
        print("Please authenticate to continue:")
        print("1. Login with existing account")
        print("2. Register new account")
        print("3. Exit")
        
        while True:
            try:
                choice = input("\nEnter your choice (1-3): ").strip()
                
                if choice == '1':
                    return await self.handle_login(websocket)
                elif choice == '2':
                    return await self.handle_register(websocket)
                elif choice == '3':
                    print("👋 Goodbye!")
                    return False
                else:
                    print("❌ Please enter 1, 2, or 3")
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                return False
    
    async def handle_login(self, websocket) -> bool:
        """Handle user login"""
        print("\n📝 Login")
        print("-" * 20)
        
        try:
            username = input("Username: ").strip()
            if not username:
                print("❌ Username cannot be empty")
                return await self.prompt_authentication(websocket)
            
            import getpass
            password = getpass.getpass("Password: ").strip()
            if not password:
                print("❌ Password cannot be empty")
                return await self.prompt_authentication(websocket)
            
            auth_message = {
                'type': 'auth_login',
                'username': username,
                'password': password
            }
            
            print(f"🔐 Logging in as {username}...")
            await websocket.send(json.dumps(auth_message))
            
            # Wait for authentication response
            response = await websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get('type') == 'auth_response':
                if response_data.get('success'):
                    self.player_info = response_data.get('player_info')
                    self.token = self.player_info.get('token')
                    self.save_session()
                    print(f"✅ Login successful! Welcome, {self.player_info['username']}")
                    print(f"🏆 Rating: {self.player_info.get('rating', 1000)}")
                    print(f"📊 Games: {self.player_info.get('total_games', 0)} | "
                          f"Wins: {self.player_info.get('wins', 0)} | "
                          f"Win Rate: {self.player_info.get('win_percentage', 0)}%")
                    return True
                else:
                    print(f"❌ Login failed: {response_data.get('message')}")
                    return await self.prompt_authentication(websocket)
            
            return False
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return await self.prompt_authentication(websocket)
    
    async def handle_register(self, websocket) -> bool:
        """Handle user registration"""
        print("\n📝 Register New Account")
        print("-" * 30)
        
        try:
            username = input("Username (3-50 characters, alphanumeric + underscore/hyphen): ").strip()
            if not username or len(username) < 3:
                print("❌ Username must be at least 3 characters long")
                return await self.prompt_authentication(websocket)
            
            import getpass
            password = getpass.getpass("Password (min 6 characters): ").strip()
            if not password or len(password) < 6:
                print("❌ Password must be at least 6 characters long")
                return await self.prompt_authentication(websocket)
            
            confirm_password = getpass.getpass("Confirm password: ").strip()
            if password != confirm_password:
                print("❌ Passwords don't match")
                return await self.prompt_authentication(websocket)
            
            email = input("Email (optional): ").strip()
            if email == '':
                email = None
            
            display_name = input("Display name (optional): ").strip()
            if display_name == '':
                display_name = None
            
            auth_message = {
                'type': 'auth_register',
                'username': username,
                'password': password,
                'email': email,
                'display_name': display_name
            }
            
            print(f"📝 Registering account for {username}...")
            await websocket.send(json.dumps(auth_message))
            
            # Wait for authentication response
            response = await websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get('type') == 'auth_response':
                if response_data.get('success'):
                    self.player_info = response_data.get('player_info')
                    self.token = self.player_info.get('token')
                    self.save_session()
                    print(f"✅ Registration successful! Welcome, {self.player_info['username']}")
                    print(f"🏆 Starting Rating: {self.player_info.get('rating', 1000)}")
                    print(f"🎮 Player ID: {self.player_info['player_id']}")
                    return True
                else:
                    print(f"❌ Registration failed: {response_data.get('message')}")
                    return await self.prompt_authentication(websocket)
            
            return False
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            return False
        except Exception as e:
            print(f"❌ Registration error: {e}")
            return await self.prompt_authentication(websocket)
    
    def display_player_info(self):
        """Display current player information"""
        if not self.player_info:
            print("❌ No player information available")
            return
        
        print("\n" + "="*40)
        print("👤 Player Information")
        print("="*40)
        print(f"Username: {self.player_info.get('username', 'N/A')}")
        print(f"Display Name: {self.player_info.get('display_name', 'N/A')}")
        print(f"Player ID: {self.player_info.get('player_id', 'N/A')}")
        print(f"Rating: {self.player_info.get('rating', 1000)}")
        print(f"Total Games: {self.player_info.get('total_games', 0)}")
        print(f"Wins: {self.player_info.get('wins', 0)}")
        print(f"Losses: {self.player_info.get('losses', 0)}")
        print(f"Draws: {self.player_info.get('draws', 0)}")
        print(f"Win Percentage: {self.player_info.get('win_percentage', 0)}%")
        print("="*40)
    
    def get_player_id(self) -> Optional[str]:
        """Get current player ID"""
        return self.player_info.get('player_id') if self.player_info else None
    
    def get_username(self) -> Optional[str]:
        """Get current username"""
        return self.player_info.get('username') if self.player_info else None
    
    def get_display_name(self) -> Optional[str]:
        """Get current display name"""
        return self.player_info.get('display_name') if self.player_info else None
