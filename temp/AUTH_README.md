# Hokm Game Authentication System

A comprehensive authentication system for the Hokm card game with user registration, login, and session management.

## Features

- ✅ User registration with username validation
- ✅ Secure password hashing (Werkzeug)
- ✅ JWT token-based authentication
- ✅ Session management
- ✅ Profile management
- ✅ Password change functionality
- ✅ Account deactivation
- ✅ PostgreSQL database integration
- ✅ RESTful API endpoints
- ✅ CORS support
- ✅ Input validation
- ✅ Error handling

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements-auth.txt
```

### 2. Setup Environment

Create a `.env` file in the project root:

```bash
SECRET_KEY=your-super-secret-key-here
DATABASE_URL=postgresql://username:password@localhost/hokm_game
FLASK_ENV=development
FLASK_DEBUG=True
```

### 3. Initialize Database

```bash
python backend/database.py
```

### 4. Run the Server

```bash
python backend/app.py
```

The server will start on `http://localhost:5000`

### 5. Test the Frontend

Open `temp/frontend/auth_demo.html` in your browser to test the authentication system.

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | User login |
| GET | `/api/auth/verify` | Verify token |
| POST | `/api/auth/refresh` | Refresh token |
| POST | `/api/auth/logout` | User logout |

### Profile Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/profile` | Get user profile |
| PUT | `/api/auth/profile` | Update profile |
| POST | `/api/auth/change-password` | Change password |
| GET | `/api/auth/stats` | Get user statistics |
| POST | `/api/auth/deactivate` | Deactivate account |

### Utilities

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/check-username` | Check username availability |
| GET | `/api/auth/health` | Health check |

## API Usage Examples

### Register a New User

```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "player123",
    "password": "mypassword",
    "email": "player@example.com",
    "display_name": "Player One"
  }'
```

### Login

```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "player123",
    "password": "mypassword"
  }'
```

### Get Profile (with token)

```bash
curl -X GET http://localhost:5000/api/auth/profile \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Response Format

All API responses follow this format:

```json
{
  "success": true,
  "message": "Operation successful",
  "data": {...}
}
```

Error responses:

```json
{
  "success": false,
  "message": "Error description"
}
```

## Database Schema

### Player Table

The authentication system uses the existing `Player` model with these key fields:

- `id`: UUID primary key (auto-generated)
- `username`: Unique username (3-50 chars, alphanumeric + underscore/hyphen)
- `password_hash`: Hashed password (Werkzeug)
- `email`: Optional email address
- `display_name`: Optional display name
- `rating`: Player rating (default: 1000)
- `total_games`, `wins`, `losses`, `draws`: Game statistics
- `account_status`: Account status (active, suspended, banned, deleted)
- `created_at`, `updated_at`, `last_seen`, `last_login`: Timestamps

## Security Features

### Password Security
- Minimum 6 characters required
- Werkzeug PBKDF2 hashing
- Salt-based hashing for security

### Token Security
- JWT tokens with 24-hour expiration
- Token refresh capability
- Secure token validation

### Input Validation
- Username format validation (alphanumeric + underscore/hyphen)
- Email format validation
- SQL injection prevention through SQLAlchemy ORM
- CSRF protection through proper session handling

### Session Management
- HTTP-only cookies
- Secure session configuration
- Session timeout handling

## Frontend Integration

The system includes a complete HTML/JavaScript frontend example (`temp/frontend/auth_demo.html`) that demonstrates:

- User registration form
- Login form
- Profile display
- Statistics display
- Session management
- Error handling

### JavaScript AuthManager Class

```javascript
const authManager = new AuthManager();

// Register user
const result = await authManager.register(username, password, email, displayName);

// Login user
const result = await authManager.login(username, password);

// Check if authenticated
if (authManager.isAuthenticated()) {
    const user = authManager.getCurrentUser();
    console.log(`Player ID: ${user.player_id}`);
}

// Logout
authManager.logout();
```

## Game Integration

### Getting Player ID

Once authenticated, you can access the player's unique ID:

```javascript
const user = authManager.getCurrentUser();
const playerId = user.player_id; // This is the UUID assigned to the player
```

### WebSocket Integration

For real-time game features, include the JWT token in WebSocket connections:

```javascript
const token = authManager.token;
const ws = new WebSocket(`ws://localhost:5000/game?token=${token}`);
```

### Game State Management

The player ID is used throughout the game system:

- `GameSession.hakem_id` references the player
- `GameParticipant.player_id` links players to games
- `GameMove.player_id` tracks player actions

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing secret | `your-secret-key-change-in-production` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:password@localhost/hokm_game` |
| `FLASK_ENV` | Flask environment | `development` |
| `FLASK_DEBUG` | Enable debug mode | `True` |

## Error Handling

The system includes comprehensive error handling:

- **400 Bad Request**: Invalid input data
- **401 Unauthorized**: Invalid credentials or expired token
- **404 Not Found**: User not found
- **409 Conflict**: Username or email already exists
- **500 Internal Server Error**: Server-side errors

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-flask

# Run tests
pytest tests/
```

### Code Structure

```
backend/
├── auth_service.py     # Authentication business logic
├── auth_routes.py      # Flask API endpoints
├── database.py         # Database configuration
├── models.py          # SQLAlchemy models
└── app.py             # Flask application

temp/frontend/
└── auth_demo.html     # Frontend demo

requirements-auth.txt   # Python dependencies
setup_auth.py          # Setup script
```

## Production Deployment

### Security Checklist

- [ ] Change `SECRET_KEY` to a strong random value
- [ ] Use HTTPS in production
- [ ] Set `SESSION_COOKIE_SECURE=True`
- [ ] Configure proper CORS origins
- [ ] Set up database connection pooling
- [ ] Enable rate limiting
- [ ] Set up proper logging
- [ ] Use environment variables for sensitive data

### Database Migration

For production, use proper database migrations:

```bash
# Create migration
alembic revision --autogenerate -m "Add authentication tables"

# Apply migration
alembic upgrade head
```

## Troubleshooting

### Common Issues

1. **Import errors**: Install dependencies with `pip install -r requirements-auth.txt`
2. **Database connection**: Check PostgreSQL is running and DATABASE_URL is correct
3. **CORS errors**: Ensure frontend and backend are on allowed origins
4. **Token expiration**: Implement token refresh in your frontend
5. **Password validation**: Ensure passwords meet minimum requirements

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## License

This authentication system is part of the Hokm Game project.
