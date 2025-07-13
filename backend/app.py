"""
Main Flask application with authentication integration
"""
from flask import Flask, jsonify
from flask_session import Session
from flask_cors import CORS
import os
from datetime import datetime

# Import authentication routes
from auth_routes import auth_bp


def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    # Configure CORS
    CORS(app, supports_credentials=True)
    
    # Configure session
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    
    # Initialize session
    Session(app)
    
    # Register authentication blueprint
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    
    # Main route
    @app.route('/')
    def index():
        return jsonify({
            "success": True,
            "message": "Hokm Card Game API",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat()
        })
    
    # Health check route
    @app.route('/health')
    def health_check():
        return jsonify({
            "success": True,
            "message": "API is healthy",
            "timestamp": datetime.utcnow().isoformat()
        })
    
    # Global error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "success": False,
            "message": "Endpoint not found"
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            "success": False,
            "message": "Internal server error"
        }), 500
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
