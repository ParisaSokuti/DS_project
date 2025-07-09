"""
Authentication Routes for Hokm Card Game
RESTful API endpoints for user authentication and management
"""
from flask import Blueprint, request, jsonify, session
from flask_cors import cross_origin
from functools import wraps
import os
import re
from datetime import datetime
from auth_service import AuthenticationService
from models import Player, Base
from database import SessionLocal


# Create blueprint
auth_bp = Blueprint('auth', __name__)

# Get secret key from environment
SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')


def require_auth(f):
    """Decorator to require authentication for endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token:
            token = session.get('token')
        
        if not token:
            return jsonify({
                "success": False,
                "message": "Authentication required"
            }), 401
        
        # Create database session
        db_session = SessionLocal()
        auth_service = AuthenticationService(db_session, SECRET_KEY)
        
        try:
            user_info = auth_service.verify_token(token)
            
            if not user_info:
                return jsonify({
                    "success": False,
                    "message": "Invalid or expired token"
                }), 401
            
            # Add user info to request context
            request.current_user = user_info
            
            return f(*args, **kwargs)
            
        finally:
            db_session.close()
    
    return decorated_function


def validate_email(email):
    """Validate email format"""
    if not email:
        return True  # Email is optional
    
    pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    return re.match(pattern, email) is not None


def validate_username(username):
    """Validate username format"""
    if not username:
        return False
    
    if len(username) < 3 or len(username) > 50:
        return False
    
    pattern = r'^[A-Za-z0-9_-]+$'
    return re.match(pattern, username) is not None


@auth_bp.route('/register', methods=['POST'])
@cross_origin()
def register():
    """User registration endpoint"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "No data provided"
            }), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        email = data.get('email', '').strip() if data.get('email') else None
        display_name = data.get('display_name', '').strip() if data.get('display_name') else None
        
        # Validation
        if not validate_username(username):
            return jsonify({
                "success": False,
                "message": "Username must be 3-50 characters long and contain only letters, numbers, hyphens, and underscores"
            }), 400
        
        if not password or len(password) < 6:
            return jsonify({
                "success": False,
                "message": "Password must be at least 6 characters long"
            }), 400
        
        if email and not validate_email(email):
            return jsonify({
                "success": False,
                "message": "Invalid email format"
            }), 400
        
        # Create database session
        db_session = SessionLocal()
        auth_service = AuthenticationService(db_session, SECRET_KEY)
        
        try:
            result = auth_service.register_user(username, password, email, display_name)
            
            if result["success"]:
                # Store user info in session
                session['player_id'] = result["player_id"]
                session['username'] = result["username"]
                session['token'] = result["token"]
                
                return jsonify(result), 201
            else:
                return jsonify(result), 400
                
        finally:
            db_session.close()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Registration failed: {str(e)}"
        }), 500


@auth_bp.route('/login', methods=['POST'])
@cross_origin()
def login():
    """User login endpoint"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "No data provided"
            }), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({
                "success": False,
                "message": "Username and password are required"
            }), 400
        
        # Create database session
        db_session = SessionLocal()
        auth_service = AuthenticationService(db_session, SECRET_KEY)
        
        try:
            result = auth_service.login_user(username, password)
            
            if result["success"]:
                # Store user info in session
                session['player_id'] = result["player_id"]
                session['username'] = result["username"]
                session['token'] = result["token"]
                
                return jsonify(result), 200
            else:
                return jsonify(result), 401
                
        finally:
            db_session.close()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Login failed: {str(e)}"
        }), 500


@auth_bp.route('/verify', methods=['GET'])
@cross_origin()
def verify_session():
    """Verify current session/token"""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token:
            token = session.get('token')
        
        if not token:
            return jsonify({
                "success": False,
                "message": "No token provided"
            }), 401
        
        # Create database session
        db_session = SessionLocal()
        auth_service = AuthenticationService(db_session, SECRET_KEY)
        
        try:
            user_info = auth_service.verify_token(token)
            
            if user_info:
                return jsonify({
                    "success": True,
                    "user": user_info
                }), 200
            else:
                return jsonify({
                    "success": False,
                    "message": "Invalid or expired token"
                }), 401
                
        finally:
            db_session.close()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Verification failed: {str(e)}"
        }), 500


@auth_bp.route('/refresh', methods=['POST'])
@cross_origin()
@require_auth
def refresh_token():
    """Refresh JWT token"""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token:
            token = session.get('token')
        
        # Create database session
        db_session = SessionLocal()
        auth_service = AuthenticationService(db_session, SECRET_KEY)
        
        try:
            new_token = auth_service.refresh_token(token)
            
            if new_token:
                session['token'] = new_token
                return jsonify({
                    "success": True,
                    "message": "Token refreshed successfully",
                    "token": new_token
                }), 200
            else:
                return jsonify({
                    "success": False,
                    "message": "Token refresh failed"
                }), 401
                
        finally:
            db_session.close()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Token refresh failed: {str(e)}"
        }), 500


@auth_bp.route('/logout', methods=['POST'])
@cross_origin()
def logout():
    """User logout endpoint"""
    try:
        # Clear session
        session.clear()
        
        return jsonify({
            "success": True,
            "message": "Logged out successfully"
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Logout failed: {str(e)}"
        }), 500


@auth_bp.route('/profile', methods=['GET'])
@cross_origin()
@require_auth
def get_profile():
    """Get current user profile"""
    try:
        # Create database session
        db_session = SessionLocal()
        auth_service = AuthenticationService(db_session, SECRET_KEY)
        
        try:
            # Get full player details
            player = auth_service.get_player_by_id(request.current_user['player_id'])
            
            if not player:
                return jsonify({
                    "success": False,
                    "message": "Player not found"
                }), 404
            
            return jsonify({
                "success": True,
                "player": {
                    "id": str(player.id),
                    "username": player.username,
                    "display_name": player.display_name,
                    "email": player.email,
                    "country_code": player.country_code,
                    "timezone": player.timezone,
                    "rating": player.rating,
                    "total_games": player.total_games,
                    "wins": player.wins,
                    "losses": player.losses,
                    "draws": player.draws,
                    "total_points": player.total_points,
                    "win_percentage": player.win_percentage,
                    "account_status": player.account_status,
                    "email_verified": player.email_verified,
                    "created_at": player.created_at.isoformat() if player.created_at else None,
                    "last_seen": player.last_seen.isoformat() if player.last_seen else None,
                    "last_login": player.last_login.isoformat() if player.last_login else None
                }
            }), 200
            
        finally:
            db_session.close()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Profile retrieval failed: {str(e)}"
        }), 500


@auth_bp.route('/profile', methods=['PUT'])
@cross_origin()
@require_auth
def update_profile():
    """Update current user profile"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "No data provided"
            }), 400
        
        display_name = data.get('display_name')
        email = data.get('email')
        country_code = data.get('country_code')
        timezone = data.get('timezone')
        
        # Validate email if provided
        if email and not validate_email(email):
            return jsonify({
                "success": False,
                "message": "Invalid email format"
            }), 400
        
        # Create database session
        db_session = SessionLocal()
        auth_service = AuthenticationService(db_session, SECRET_KEY)
        
        try:
            result = auth_service.update_profile(
                request.current_user['player_id'],
                display_name=display_name,
                email=email,
                country_code=country_code,
                timezone=timezone
            )
            
            return jsonify(result), 200 if result["success"] else 400
            
        finally:
            db_session.close()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Profile update failed: {str(e)}"
        }), 500


@auth_bp.route('/change-password', methods=['POST'])
@cross_origin()
@require_auth
def change_password():
    """Change user password"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "No data provided"
            }), 400
        
        old_password = data.get('old_password', '').strip()
        new_password = data.get('new_password', '').strip()
        
        if not old_password or not new_password:
            return jsonify({
                "success": False,
                "message": "Both old and new passwords are required"
            }), 400
        
        # Create database session
        db_session = SessionLocal()
        auth_service = AuthenticationService(db_session, SECRET_KEY)
        
        try:
            result = auth_service.change_password(
                request.current_user['player_id'],
                old_password,
                new_password
            )
            
            return jsonify(result), 200 if result["success"] else 400
            
        finally:
            db_session.close()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Password change failed: {str(e)}"
        }), 500


@auth_bp.route('/stats', methods=['GET'])
@cross_origin()
@require_auth
def get_stats():
    """Get current user statistics"""
    try:
        # Create database session
        db_session = SessionLocal()
        auth_service = AuthenticationService(db_session, SECRET_KEY)
        
        try:
            result = auth_service.get_player_stats(request.current_user['player_id'])
            
            return jsonify(result), 200 if result["success"] else 404
            
        finally:
            db_session.close()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Stats retrieval failed: {str(e)}"
        }), 500


@auth_bp.route('/deactivate', methods=['POST'])
@cross_origin()
@require_auth
def deactivate_account():
    """Deactivate current user account"""
    try:
        # Create database session
        db_session = SessionLocal()
        auth_service = AuthenticationService(db_session, SECRET_KEY)
        
        try:
            result = auth_service.deactivate_account(request.current_user['player_id'])
            
            if result["success"]:
                # Clear session
                session.clear()
            
            return jsonify(result), 200 if result["success"] else 400
            
        finally:
            db_session.close()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Account deactivation failed: {str(e)}"
        }), 500


@auth_bp.route('/check-username', methods=['POST'])
@cross_origin()
def check_username():
    """Check if username is available"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "No data provided"
            }), 400
        
        username = data.get('username', '').strip()
        
        if not username:
            return jsonify({
                "success": False,
                "message": "Username is required"
            }), 400
        
        if not validate_username(username):
            return jsonify({
                "success": False,
                "message": "Invalid username format",
                "available": False
            }), 400
        
        # Create database session
        db_session = SessionLocal()
        auth_service = AuthenticationService(db_session, SECRET_KEY)
        
        try:
            existing_user = auth_service.get_player_by_username(username)
            
            return jsonify({
                "success": True,
                "available": existing_user is None,
                "message": "Username is available" if existing_user is None else "Username is already taken"
            }), 200
            
        finally:
            db_session.close()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Username check failed: {str(e)}"
        }), 500


@auth_bp.route('/health', methods=['GET'])
@cross_origin()
def health_check():
    """Health check endpoint"""
    return jsonify({
        "success": True,
        "message": "Authentication service is healthy",
        "timestamp": datetime.utcnow().isoformat()
    }), 200


# Error handlers
@auth_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "message": "Endpoint not found"
    }), 404


@auth_bp.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "success": False,
        "message": "Method not allowed"
    }), 405


@auth_bp.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "message": "Internal server error"
    }), 500
