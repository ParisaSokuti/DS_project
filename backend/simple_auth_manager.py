"""
Simple Authentication Manager - Fallback when database is not available
"""
import jwt
import uuid
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from werkzeug.security import generate_password_hash, check_password_hash

class SimpleAuthManager:
    """Simple file-based authentication for development/testing"""
    
    def __init__(self):
        self.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
        self.authenticated_players = {}  # websocket -> player_info
        self.player_sessions = {}  # player_id -> websocket
        self.users_file = 'simple_users.json'
        self.users = self.load_users()
        
    def load_users(self) -> Dict[str, Any]:
        """Load users from file"""
        try:
            if os.path.exists(self.users_file):
                with open(self.users_file, 'r') as f:
                    return json.load(f)
            else:
                # Create default users for testing
                default_users = {
                    'testuser': {
                        'player_id': str(uuid.uuid4()),
                        'username': 'testuser',
                        'password_hash': generate_password_hash('password123'),
                        'display_name': 'Test User',
                        'email': 'test@example.com',
                        'rating': 1000,
                        'created_at': datetime.now().isoformat()
                    },
                    'player1': {
                        'player_id': str(uuid.uuid4()),
                        'username': 'player1',
                        'password_hash': generate_password_hash('password123'),
                        'display_name': 'Player One',
                        'email': 'player1@example.com',
                        'rating': 1100,
                        'created_at': datetime.now().isoformat()
                    },
                    'player2': {
                        'player_id': str(uuid.uuid4()),
                        'username': 'player2',
                        'password_hash': generate_password_hash('password123'),
                        'display_name': 'Player Two',
                        'email': 'player2@example.com',
                        'rating': 1200,
                        'created_at': datetime.now().isoformat()
                    }
                }
                self.save_users(default_users)
                return default_users
        except Exception as e:
            print(f"Error loading users: {e}")
            return {}
    
    def save_users(self, users: Dict[str, Any]):
        """Save users to file"""
        try:
            with open(self.users_file, 'w') as f:
                json.dump(users, f, indent=2)
        except Exception as e:
            print(f"Error saving users: {e}")
    
    async def authenticate_player(self, websocket, auth_data: Dict[str, Any]) -> Dict[str, Any]:
        """Authenticate a player for game access"""
        try:
            auth_type = auth_data.get('type', 'login')
            
            if auth_type == 'login':
                return await self._handle_login(websocket, auth_data)
            elif auth_type == 'register':
                return await self._handle_register(websocket, auth_data)
            elif auth_type == 'token':
                return await self._handle_token_auth(websocket, auth_data)
            else:
                return {
                    'success': False,
                    'message': 'Invalid authentication type'
                }
                
        except Exception as e:
            print(f"Authentication error: {e}")
            return {
                'success': False,
                'message': f'Authentication error: {str(e)}'
            }
    
    async def _handle_login(self, websocket, auth_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle username/password login"""
        username = auth_data.get('username')
        password = auth_data.get('password')
        
        if not username or not password:
            return {
                'success': False,
                'message': 'Username and password are required'
            }
        
        # Check if user exists
        user = self.users.get(username)
        if not user:
            return {
                'success': False,
                'message': 'Invalid username or password'
            }
        
        # Check password
        if not check_password_hash(user['password_hash'], password):
            return {
                'success': False,
                'message': 'Invalid username or password'
            }
        
        # Check if player is already connected
        player_id = user['player_id']
        if player_id in self.player_sessions:
            existing_websocket = self.player_sessions[player_id]
            if existing_websocket in self.authenticated_players:
                try:
                    await existing_websocket.ping()
                    return {
                        'success': False,
                        'message': 'Player already connected from another session'
                    }
                except:
                    # Old connection is dead, remove it
                    self.disconnect_player(existing_websocket)
        
        # Create player info
        player_info = {
            'player_id': player_id,
            'username': username,
            'display_name': user['display_name'],
            'email': user.get('email'),
            'rating': user.get('rating', 1000)
        }
        
        # Generate JWT token
        token_payload = {
            'player_id': player_id,
            'username': username,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }
        token = jwt.encode(token_payload, self.secret_key, algorithm='HS256')
        
        # Store authentication
        self.authenticated_players[websocket] = player_info
        self.player_sessions[player_id] = websocket
        
        return {
            'success': True,
            'message': 'Login successful',
            'token': token,
            'player_info': player_info
        }
    
    async def _handle_register(self, websocket, auth_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user registration"""
        username = auth_data.get('username')
        password = auth_data.get('password')
        email = auth_data.get('email')
        display_name = auth_data.get('display_name', username)
        
        if not username or not password:
            return {
                'success': False,
                'message': 'Username and password are required'
            }
        
        if len(username) < 3:
            return {
                'success': False,
                'message': 'Username must be at least 3 characters long'
            }
        
        if len(password) < 6:
            return {
                'success': False,
                'message': 'Password must be at least 6 characters long'
            }
        
        # Check if username already exists
        if username in self.users:
            return {
                'success': False,
                'message': 'Username already exists'
            }
        
        # Create new user
        player_id = str(uuid.uuid4())
        new_user = {
            'player_id': player_id,
            'username': username,
            'password_hash': generate_password_hash(password),
            'display_name': display_name,
            'email': email,
            'rating': 1000,
            'created_at': datetime.now().isoformat()
        }
        
        # Save user
        self.users[username] = new_user
        self.save_users(self.users)
        
        # Create player info
        player_info = {
            'player_id': player_id,
            'username': username,
            'display_name': display_name,
            'email': email,
            'rating': 1000
        }
        
        # Generate JWT token
        token_payload = {
            'player_id': player_id,
            'username': username,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }
        token = jwt.encode(token_payload, self.secret_key, algorithm='HS256')
        
        # Store authentication
        self.authenticated_players[websocket] = player_info
        self.player_sessions[player_id] = websocket
        
        return {
            'success': True,
            'message': 'Registration successful',
            'token': token,
            'player_info': player_info
        }
    
    async def _handle_token_auth(self, websocket, auth_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle JWT token authentication"""
        token = auth_data.get('token')
        
        if not token:
            return {
                'success': False,
                'message': 'Token is required'
            }
        
        try:
            # Decode token
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            player_id = payload['player_id']
            username = payload['username']
            
            # Find user
            user = None
            for u in self.users.values():
                if u['player_id'] == player_id:
                    user = u
                    break
            
            if not user:
                return {
                    'success': False,
                    'message': 'Invalid token - user not found'
                }
            
            # Check if player is already connected
            if player_id in self.player_sessions:
                existing_websocket = self.player_sessions[player_id]
                if existing_websocket in self.authenticated_players:
                    try:
                        await existing_websocket.ping()
                        return {
                            'success': False,
                            'message': 'Player already connected from another session'
                        }
                    except:
                        # Old connection is dead, remove it
                        self.disconnect_player(existing_websocket)
            
            # Create player info
            player_info = {
                'player_id': player_id,
                'username': username,
                'display_name': user['display_name'],
                'email': user.get('email'),
                'rating': user.get('rating', 1000)
            }
            
            # Store authentication
            self.authenticated_players[websocket] = player_info
            self.player_sessions[player_id] = websocket
            
            return {
                'success': True,
                'message': 'Token authentication successful',
                'token': token,  # Return the same token
                'player_info': player_info
            }
            
        except jwt.ExpiredSignatureError:
            return {
                'success': False,
                'message': 'Token has expired'
            }
        except jwt.InvalidTokenError:
            return {
                'success': False,
                'message': 'Invalid token'
            }
    
    def is_authenticated(self, websocket) -> bool:
        """Check if websocket is authenticated"""
        return websocket in self.authenticated_players
    
    def get_authenticated_player(self, websocket) -> Optional[Dict[str, Any]]:
        """Get authenticated player info"""
        return self.authenticated_players.get(websocket)
    
    def disconnect_player(self, websocket):
        """Handle player disconnection"""
        if websocket in self.authenticated_players:
            player_info = self.authenticated_players[websocket]
            player_id = player_info['player_id']
            
            # Remove from authenticated players
            del self.authenticated_players[websocket]
            
            # Remove from player sessions
            if player_id in self.player_sessions:
                del self.player_sessions[player_id]
            
            print(f"[AUTH] Player {player_info['username']} disconnected")
