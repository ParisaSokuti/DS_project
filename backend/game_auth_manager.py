"""
Server-side authentication manager for game server integration
"""
import asyncio
import json
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import os
import sys

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth_service import AuthenticationService
from db_connection import SessionLocal

class GameAuthManager:
    """Authentication manager for game server"""
    
    def __init__(self):
        self.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
        self.authenticated_players = {}  # websocket -> player_info
        self.player_sessions = {}  # player_id -> websocket
        
    def get_db_session(self):
        """Get database session"""
        return SessionLocal()
    
    async def authenticate_player(self, websocket, auth_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Authenticate a player for game access
        
        Args:
            websocket: WebSocket connection
            auth_data: Authentication data from client
            
        Returns:
            Dict with authentication result
        """
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
        
        # Run authentication in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def authenticate():
            db_session = self.get_db_session()
            try:
                auth_service = AuthenticationService(db_session, self.secret_key)
                result = auth_service.login_user(username, password)
                return result
            finally:
                db_session.close()
        
        result = await loop.run_in_executor(None, authenticate)
        
        if result['success']:
            player_id = result['player_id']
            
            # Check if player is already connected
            if player_id in self.player_sessions:
                existing_websocket = self.player_sessions[player_id]
                
                # Check if existing connection is still active
                if existing_websocket in self.authenticated_players:
                    try:
                        # Try to ping the existing connection
                        await existing_websocket.ping()
                        
                        # If ping succeeds, the connection is still active
                        return {
                            'success': False,
                            'message': f'User {username} is already connected from another session. Please disconnect from the other session first.',
                            'error_code': 'ALREADY_CONNECTED'
                        }
                    except Exception:
                        # Existing connection is dead, clean it up
                        print(f"[AUTH] Cleaning up dead connection for {username}")
                        await self._cleanup_player_session(existing_websocket)
            
            # Store authenticated player info
            player_info = {
                'player_id': player_id,
                'username': result['username'],
                'display_name': result['display_name'],
                'rating': result['rating'],
                'token': result['token'],
                'authenticated_at': datetime.utcnow().isoformat()
            }
            
            self.authenticated_players[websocket] = player_info
            self.player_sessions[player_id] = websocket
            
            print(f"[AUTH] User {username} authenticated successfully (player_id: {player_id})")
            
            return {
                'success': True,
                'message': 'Login successful',
                'player_info': player_info
            }
        else:
            return result
    
    async def _handle_register(self, websocket, auth_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user registration"""
        username = auth_data.get('username')
        password = auth_data.get('password')
        email = auth_data.get('email')
        display_name = auth_data.get('display_name')
        
        if not username or not password:
            return {
                'success': False,
                'message': 'Username and password are required'
            }
        
        # Run registration in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def register():
            db_session = self.get_db_session()
            try:
                auth_service = AuthenticationService(db_session, self.secret_key)
                result = auth_service.register_user(username, password, email, display_name)
                return result
            finally:
                db_session.close()
        
        result = await loop.run_in_executor(None, register)
        
        if result['success']:
            player_id = result['player_id']
            
            # Check if player is already connected (shouldn't happen during registration, but just in case)
            if player_id in self.player_sessions:
                existing_websocket = self.player_sessions[player_id]
                
                # Check if existing connection is still active
                if existing_websocket in self.authenticated_players:
                    try:
                        # Try to ping the existing connection
                        await existing_websocket.ping()
                        
                        # If ping succeeds, the connection is still active
                        return {
                            'success': False,
                            'message': f'User {username} is already connected from another session.',
                            'error_code': 'ALREADY_CONNECTED'
                        }
                    except Exception:
                        # Existing connection is dead, clean it up
                        print(f"[AUTH] Cleaning up dead connection during registration for {username}")
                        await self._cleanup_player_session(existing_websocket)
            
            # Store authenticated player info
            player_info = {
                'player_id': player_id,
                'username': result['username'],
                'display_name': result['display_name'],
                'rating': result['rating'],
                'token': result['token'],
                'authenticated_at': datetime.utcnow().isoformat()
            }
            
            self.authenticated_players[websocket] = player_info
            self.player_sessions[player_id] = websocket
            
            print(f"[AUTH] User {username} registered and authenticated successfully (player_id: {player_id})")
            
            return {
                'success': True,
                'message': 'Registration successful',
                'player_info': player_info
            }
        else:
            return result
    
    async def _handle_token_auth(self, websocket, auth_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle JWT token authentication"""
        token = auth_data.get('token')
        
        if not token:
            return {
                'success': False,
                'message': 'Token is required'
            }
        
        # Run token verification in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def verify():
            db_session = self.get_db_session()
            try:
                auth_service = AuthenticationService(db_session, self.secret_key)
                user_info = auth_service.verify_token(token)
                return user_info
            finally:
                db_session.close()
        
        user_info = await loop.run_in_executor(None, verify)
        
        if user_info:
            player_id = user_info['player_id']
            username = user_info['username']
            
            # Check if player is already connected
            if player_id in self.player_sessions:
                existing_websocket = self.player_sessions[player_id]
                
                # Check if existing connection is still active
                if existing_websocket in self.authenticated_players:
                    try:
                        # Try to ping the existing connection
                        await existing_websocket.ping()
                        
                        # If ping succeeds, the connection is still active
                        return {
                            'success': False,
                            'message': f'User {username} is already connected from another session. Please disconnect from the other session first.',
                            'error_code': 'ALREADY_CONNECTED'
                        }
                    except Exception:
                        # Existing connection is dead, clean it up
                        print(f"[AUTH] Cleaning up dead connection for {username}")
                        await self._cleanup_player_session(existing_websocket)
            
            # Store authenticated player info
            player_info = {
                'player_id': player_id,
                'username': username,
                'display_name': user_info['display_name'],
                'rating': user_info['rating'],
                'token': token,
                'authenticated_at': datetime.utcnow().isoformat()
            }
            
            self.authenticated_players[websocket] = player_info
            self.player_sessions[player_id] = websocket
            
            print(f"[AUTH] User {username} authenticated with token successfully (player_id: {player_id})")
            
            return {
                'success': True,
                'message': 'Token authentication successful',
                'player_info': player_info
            }
        else:
            return {
                'success': False,
                'message': 'Invalid or expired token'
            }
    
    async def _cleanup_player_session(self, websocket):
        """Clean up a player session (both mappings)"""
        if websocket in self.authenticated_players:
            player_info = self.authenticated_players[websocket]
            player_id = player_info['player_id']
            username = player_info['username']
            
            # Remove from both mappings
            del self.authenticated_players[websocket]
            if player_id in self.player_sessions:
                del self.player_sessions[player_id]
            
            print(f"[AUTH] Cleaned up session for {username} (player_id: {player_id})")
    
    def get_authenticated_player(self, websocket) -> Optional[Dict[str, Any]]:
        """Get authenticated player info for a websocket"""
        return self.authenticated_players.get(websocket)
    
    def is_authenticated(self, websocket) -> bool:
        """Check if a websocket is authenticated"""
        return websocket in self.authenticated_players
    
    def get_player_websocket(self, player_id: str) -> Optional[any]:
        """Get websocket for a player ID"""
        return self.player_sessions.get(player_id)
    
    def disconnect_player(self, websocket):
        """Clean up when player disconnects"""
        if websocket in self.authenticated_players:
            player_info = self.authenticated_players[websocket]
            player_id = player_info['player_id']
            username = player_info['username']
            
            # Remove from both mappings
            del self.authenticated_players[websocket]
            if player_id in self.player_sessions:
                del self.player_sessions[player_id]
                
            print(f"[AUTH] Player {username} disconnected (player_id: {player_id})")
    
    def get_authenticated_players_count(self) -> int:
        """Get count of authenticated players"""
        return len(self.authenticated_players)
    
    def get_all_authenticated_players(self) -> Dict[str, Dict[str, Any]]:
        """Get all authenticated players info"""
        return {
            player_info['player_id']: player_info 
            for player_info in self.authenticated_players.values()
        }
    
    async def refresh_token(self, websocket) -> Dict[str, Any]:
        """Refresh JWT token for authenticated player"""
        player_info = self.get_authenticated_player(websocket)
        if not player_info:
            return {
                'success': False,
                'message': 'Player not authenticated'
            }
        
        loop = asyncio.get_event_loop()
        
        def refresh():
            db_session = self.get_db_session()
            try:
                auth_service = AuthenticationService(db_session, self.secret_key)
                new_token = auth_service.refresh_token(player_info['token'])
                return new_token
            finally:
                db_session.close()
        
        new_token = await loop.run_in_executor(None, refresh)
        
        if new_token:
            # Update token in player info
            player_info['token'] = new_token
            self.authenticated_players[websocket] = player_info
            
            return {
                'success': True,
                'message': 'Token refreshed successfully',
                'token': new_token
            }
        else:
            return {
                'success': False,
                'message': 'Failed to refresh token'
            }
    
    async def update_player_stats(self, player_id: str, stats_update: Dict[str, Any]):
        """Update player statistics after game completion"""
        loop = asyncio.get_event_loop()
        
        def update_stats():
            db_session = self.get_db_session()
            try:
                from models import Player
                player = db_session.query(Player).filter(Player.id == player_id).first()
                if player:
                    # Update game statistics
                    if 'total_games' in stats_update:
                        player.total_games += stats_update['total_games']
                    if 'wins' in stats_update:
                        player.wins += stats_update['wins']
                    if 'losses' in stats_update:
                        player.losses += stats_update['losses']
                    if 'draws' in stats_update:
                        player.draws += stats_update['draws']
                    if 'rating_change' in stats_update:
                        player.rating += stats_update['rating_change']
                    if 'points' in stats_update:
                        player.total_points += stats_update['points']
                    
                    player.last_seen = datetime.utcnow()
                    db_session.commit()
                    return True
                return False
            except Exception as e:
                db_session.rollback()
                print(f"Error updating player stats: {e}")
                return False
            finally:
                db_session.close()
        
        return await loop.run_in_executor(None, update_stats)
