"""
Authentication Service for Hokm Card Game
Handles user registration, login, and session management
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import jwt
import uuid

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import Player, Base


class AuthenticationService:
    def __init__(self, db_session: Session, secret_key: str):
        self.db = db_session
        self.secret_key = secret_key
        self.token_expire_hours = 24
    
    def register_user(self, username: str, password: str, email: str = None, 
                     display_name: str = None) -> Dict[str, Any]:
        """Register a new user"""
        try:
            # Validate input
            if not username or len(username) < 3:
                return {
                    "success": False,
                    "message": "Username must be at least 3 characters long"
                }
            
            if not password or len(password) < 6:
                return {
                    "success": False,
                    "message": "Password must be at least 6 characters long"
                }
            
            # Check if username already exists
            existing_user = self.db.query(Player).filter(Player.username == username).first()
            if existing_user:
                return {
                    "success": False,
                    "message": "Username already exists"
                }
            
            # Check if email already exists (if provided)
            if email:
                existing_email = self.db.query(Player).filter(Player.email == email).first()
                if existing_email:
                    return {
                        "success": False,
                        "message": "Email already registered"
                    }
            
            # Create new player
            player = Player(
                username=username,
                password_hash=generate_password_hash(password),
                email=email,
                display_name=display_name or username,
                created_at=datetime.utcnow(),
                last_seen=datetime.utcnow(),
                last_login=datetime.utcnow()
            )
            
            self.db.add(player)
            self.db.commit()
            
            # Generate JWT token
            token = self._generate_token(player.id, username)
            
            return {
                "success": True,
                "message": "User registered successfully",
                "player_id": str(player.id),
                "username": username,
                "display_name": player.display_name,
                "rating": player.rating,
                "token": token
            }
            
        except IntegrityError as e:
            self.db.rollback()
            if "username" in str(e):
                return {
                    "success": False,
                    "message": "Username already exists"
                }
            elif "email" in str(e):
                return {
                    "success": False,
                    "message": "Email already registered"
                }
            else:
                return {
                    "success": False,
                    "message": "Registration failed due to constraint violation"
                }
        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "message": f"Registration failed: {str(e)}"
            }
    
    def login_user(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticate user login"""
        try:
            # Validate input
            if not username or not password:
                return {
                    "success": False,
                    "message": "Username and password are required"
                }
            
            # Find user by username
            player = self.db.query(Player).filter(Player.username == username).first()
            
            if not player:
                return {
                    "success": False,
                    "message": "Invalid username or password"
                }
            
            # Check if password_hash exists
            if not player.password_hash:
                return {
                    "success": False,
                    "message": "Account not properly configured. Please contact support."
                }
            
            # Check password
            if not check_password_hash(player.password_hash, password):
                return {
                    "success": False,
                    "message": "Invalid username or password"
                }
            
            # Check account status
            if player.account_status != 'active':
                return {
                    "success": False,
                    "message": f"Account is {player.account_status}"
                }
            
            # Update last login and last seen
            player.last_login = datetime.utcnow()
            player.last_seen = datetime.utcnow()
            self.db.commit()
            
            # Generate JWT token
            token = self._generate_token(player.id, username)
            
            return {
                "success": True,
                "message": "Login successful",
                "player_id": str(player.id),
                "username": username,
                "display_name": player.display_name,
                "rating": player.rating,
                "total_games": player.total_games,
                "wins": player.wins,
                "losses": player.losses,
                "draws": player.draws,
                "win_percentage": player.win_percentage,
                "token": token
            }
            
        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "message": f"Login failed: {str(e)}"
            }
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return user info"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            player_id = payload.get('player_id')
            username = payload.get('username')
            
            if not player_id or not username:
                return None
            
            # Verify player still exists and is active
            player = self.db.query(Player).filter(
                Player.id == player_id,
                Player.username == username,
                Player.account_status == 'active'
            ).first()
            
            if not player:
                return None
            
            # Update last seen
            player.last_seen = datetime.utcnow()
            self.db.commit()
            
            return {
                "player_id": str(player.id),
                "username": player.username,
                "display_name": player.display_name,
                "rating": player.rating,
                "total_games": player.total_games,
                "wins": player.wins,
                "losses": player.losses,
                "draws": player.draws,
                "win_percentage": player.win_percentage
            }
            
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
        except Exception:
            return None
    
    def refresh_token(self, token: str) -> Optional[str]:
        """Refresh JWT token"""
        user_info = self.verify_token(token)
        if user_info:
            return self._generate_token(user_info['player_id'], user_info['username'])
        return None
    
    def change_password(self, player_id: str, old_password: str, new_password: str) -> Dict[str, Any]:
        """Change user password"""
        try:
            if not new_password or len(new_password) < 6:
                return {
                    "success": False,
                    "message": "New password must be at least 6 characters long"
                }
            
            player = self.db.query(Player).filter(Player.id == player_id).first()
            
            if not player:
                return {
                    "success": False,
                    "message": "Player not found"
                }
            
            # Verify old password
            if not check_password_hash(player.password_hash, old_password):
                return {
                    "success": False,
                    "message": "Current password is incorrect"
                }
            
            # Update password
            player.password_hash = generate_password_hash(new_password)
            self.db.commit()
            
            return {
                "success": True,
                "message": "Password changed successfully"
            }
            
        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "message": f"Password change failed: {str(e)}"
            }
    
    def update_profile(self, player_id: str, display_name: str = None, 
                      email: str = None, country_code: str = None, 
                      timezone: str = None) -> Dict[str, Any]:
        """Update user profile"""
        try:
            player = self.db.query(Player).filter(Player.id == player_id).first()
            
            if not player:
                return {
                    "success": False,
                    "message": "Player not found"
                }
            
            # Update fields if provided
            if display_name is not None:
                player.display_name = display_name
            
            if email is not None:
                # Check if email already exists
                if email != player.email:
                    existing_email = self.db.query(Player).filter(
                        Player.email == email,
                        Player.id != player_id
                    ).first()
                    if existing_email:
                        return {
                            "success": False,
                            "message": "Email already registered"
                        }
                player.email = email
            
            if country_code is not None:
                player.country_code = country_code
            
            if timezone is not None:
                player.timezone = timezone
            
            player.updated_at = datetime.utcnow()
            self.db.commit()
            
            return {
                "success": True,
                "message": "Profile updated successfully",
                "player": {
                    "id": str(player.id),
                    "username": player.username,
                    "display_name": player.display_name,
                    "email": player.email,
                    "country_code": player.country_code,
                    "timezone": player.timezone
                }
            }
            
        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "message": f"Profile update failed: {str(e)}"
            }
    
    def get_player_by_id(self, player_id: str) -> Optional[Player]:
        """Get player by ID"""
        try:
            return self.db.query(Player).filter(Player.id == player_id).first()
        except Exception:
            return None
    
    def get_player_by_username(self, username: str) -> Optional[Player]:
        """Get player by username"""
        try:
            return self.db.query(Player).filter(Player.username == username).first()
        except Exception:
            return None
    
    def deactivate_account(self, player_id: str) -> Dict[str, Any]:
        """Deactivate user account"""
        try:
            player = self.db.query(Player).filter(Player.id == player_id).first()
            
            if not player:
                return {
                    "success": False,
                    "message": "Player not found"
                }
            
            player.account_status = 'deleted'
            player.is_active = False
            player.updated_at = datetime.utcnow()
            self.db.commit()
            
            return {
                "success": True,
                "message": "Account deactivated successfully"
            }
            
        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "message": f"Account deactivation failed: {str(e)}"
            }
    
    def _generate_token(self, player_id: uuid.UUID, username: str) -> str:
        """Generate JWT token for user"""
        payload = {
            'player_id': str(player_id),
            'username': username,
            'exp': datetime.utcnow() + timedelta(hours=self.token_expire_hours),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm='HS256')
    
    def get_player_stats(self, player_id: str) -> Dict[str, Any]:
        """Get comprehensive player statistics"""
        try:
            player = self.db.query(Player).filter(Player.id == player_id).first()
            
            if not player:
                return {
                    "success": False,
                    "message": "Player not found"
                }
            
            return {
                "success": True,
                "stats": {
                    "id": str(player.id),
                    "username": player.username,
                    "display_name": player.display_name,
                    "rating": player.rating,
                    "total_games": player.total_games,
                    "wins": player.wins,
                    "losses": player.losses,
                    "draws": player.draws,
                    "total_points": player.total_points,
                    "win_percentage": player.win_percentage,
                    "created_at": player.created_at.isoformat() if player.created_at else None,
                    "last_seen": player.last_seen.isoformat() if player.last_seen else None,
                    "last_login": player.last_login.isoformat() if player.last_login else None,
                    "account_status": player.account_status,
                    "is_active": player.is_active
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to get player stats: {str(e)}"
            }
