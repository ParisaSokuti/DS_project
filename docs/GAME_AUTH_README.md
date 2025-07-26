# Hokm Game with Integrated Authentication System

A complete authentication system integrated into the Hokm card game server and client, featuring Phase 0 authentication before game access.

## 🎮 Game Flow with Authentication

### Phase 0: Authentication (NEW)
- User connects to game server
- Authentication prompt appears
- User can login or register
- Server validates credentials
- Player receives unique, persistent player ID
- Session is saved for future connections

### Phase 1+: Game Play
- Authenticated players join game rooms
- All game actions tied to authenticated player ID
- Player statistics tracked across sessions
- Persistent player identity and ratings

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements-auth.txt
```

### 2. Setup Database
```bash
# Update DATABASE_URL in .env file
python backend/database.py
```

### 3. Start Authentication API Server
```bash
python backend/app.py
```
*Runs on http://localhost:5000*

### 4. Start Game Server
```bash
python backend/server.py
```
*Runs on ws://localhost:8765*

### 5. Start Game Client
```bash
python backend/client.py
```

## 🔐 Authentication Features

### User Registration
- Username validation (3-50 chars, alphanumeric + underscore/hyphen)
- Password requirements (minimum 6 characters)
- Optional email and display name
- Automatic player ID assignment
- Initial rating of 1000

### User Login
- Username/password authentication
- JWT token generation (24-hour expiration)
- Session persistence
- Automatic reconnection with saved tokens

### Security
- Werkzeug password hashing
- JWT token-based sessions
- SQL injection prevention
- Input validation and sanitization

## 📋 System Architecture

### Server Components

#### `GameAuthManager` (backend/game_auth_manager.py)
- Handles WebSocket authentication
- Manages authenticated player sessions
- Integrates with PostgreSQL database
- Provides player lookup and validation

#### `AuthenticationService` (backend/auth_service.py)
- Core authentication business logic
- User registration and login
- Password management
- Token generation and validation

#### `GameServer` (backend/server.py)
- Integrated authentication handlers
- Phase 0 authentication enforcement
- Authenticated player tracking
- Connection management

### Client Components

#### `ClientAuthManager` (backend/client_auth_manager.py)
- Client-side authentication handling
- Session persistence
- User interaction (login/register prompts)
- Token management

#### Game Client (backend/client.py)
- Phase 0 authentication flow
- Automatic re-authentication
- Persistent session handling
- Integrated game experience

## 🔄 Authentication Flow

```
1. Client connects to game server
2. Client checks for saved session
3. If no session or invalid token:
   a. Prompt user for login/register
   b. Send credentials to server
   c. Server validates with database
   d. Server returns player info + JWT token
   e. Client saves session
4. Client proceeds to game with authenticated identity
5. All game actions use authenticated player ID
```

## 📊 Database Integration

### Player Model
- Unique player ID (UUID)
- Username (unique)
- Email (optional, unique)
- Password hash (Werkzeug)
- Game statistics (wins, losses, rating)
- Timestamps (created, last seen, last login)
- Account status management

### Game Integration
- GameSession.hakem_id → Player.id
- GameParticipant.player_id → Player.id  
- GameMove.player_id → Player.id
- PlayerGameStats.player_id → Player.id

## 🎯 WebSocket Message Protocol

### Authentication Messages

#### Login Request
```json
{
  "type": "auth_login",
  "username": "player123",
  "password": "mypassword"
}
```

#### Registration Request
```json
{
  "type": "auth_register",
  "username": "newplayer",
  "password": "mypassword",
  "email": "optional@example.com",
  "display_name": "Optional Name"
}
```

#### Token Authentication
```json
{
  "type": "auth_token",
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

#### Authentication Response
```json
{
  "type": "auth_response",
  "success": true,
  "message": "Login successful",
  "player_info": {
    "player_id": "uuid-string",
    "username": "player123",
    "display_name": "Player Name",
    "rating": 1000,
    "total_games": 0,
    "wins": 0,
    "losses": 0,
    "draws": 0,
    "win_percentage": 0,
    "token": "jwt-token"
  }
}
```

### Game Messages
All existing game messages now require authentication:
- `join` - Join game room
- `play_card` - Play a card
- `hokm_selected` - Select trump suit
- `reconnect` - Reconnect to game

## 🛠️ Development

### File Structure
```
backend/
├── game_states.py              # Added AUTHENTICATION phase
├── game_auth_manager.py        # Server authentication manager
├── client_auth_manager.py      # Client authentication manager
├── server.py                   # Updated with auth integration
├── client.py                   # Updated with auth flow
├── auth_service.py             # Core authentication logic
├── auth_routes.py              # REST API endpoints
├── database.py                 # Database configuration
├── models.py                   # SQLAlchemy models
└── app.py                      # Flask API server

frontend/
└── auth_demo.html              # Web authentication demo

requirements-auth.txt           # Authentication dependencies
setup_auth.py                   # Setup script
test_auth.py                    # Authentication tests
test_integration.py             # Integration test script
AUTH_README.md                  # Authentication documentation
```

### Running Tests

#### Authentication API Tests
```bash
python test_auth.py
```

#### Integration Tests
```bash
python test_integration.py
```

### Development Mode
```bash
# Terminal 1: Authentication API
python backend/app.py

# Terminal 2: Game Server  
python backend/server.py

# Terminal 3: Game Client
python backend/client.py
```

## 🔧 Configuration

### Environment Variables
```bash
# .env file
SECRET_KEY=your-super-secret-jwt-key
DATABASE_URL=postgresql://user:password@localhost/hokm_game
FLASK_ENV=development
FLASK_DEBUG=True
```

### Database Setup
```sql
-- PostgreSQL database
CREATE DATABASE hokm_game;
CREATE USER hokm_user WITH PASSWORD 'hokm_password';
GRANT ALL PRIVILEGES ON DATABASE hokm_game TO hokm_user;
```

## 🎮 User Experience

### First Time Users
1. Connect to game
2. See authentication prompt
3. Choose "Register new account"
4. Enter username, password, optional email
5. Automatic login after registration
6. Proceed to game with unique player ID

### Returning Users
1. Connect to game
2. Automatic authentication with saved token
3. If token expired, prompted to login
4. Enter username/password
5. Proceed to game with persistent player ID

### Session Management
- Sessions saved to `.game_session` file
- Automatic reconnection on client restart
- Token refresh handling
- Graceful fallback to login prompt

## 🔒 Security Considerations

### Production Deployment
- [ ] Change SECRET_KEY to strong random value
- [ ] Use HTTPS for web components
- [ ] Enable database SSL connections  
- [ ] Implement rate limiting
- [ ] Add account lockout protection
- [ ] Set up proper logging and monitoring
- [ ] Use environment variables for all secrets

### Password Security
- Minimum 6 characters required
- Werkzeug PBKDF2 hashing with salt
- No password storage in plain text
- Secure password change functionality

### Token Security  
- JWT tokens with 24-hour expiration
- Secure token generation
- Token refresh capability
- Automatic token validation

## 🐛 Troubleshooting

### Common Issues

**"Authentication required" error**
- Ensure client authenticates before joining game
- Check if token has expired
- Verify database connection

**"Username already exists" error**
- Choose a different username
- Check for typos in username

**Database connection errors**
- Verify PostgreSQL is running
- Check DATABASE_URL configuration
- Ensure database and user exist

**WebSocket connection errors**
- Verify game server is running on port 8765
- Check firewall settings
- Ensure no other services using the port

### Debug Mode
```bash
# Enable debug logging
export FLASK_DEBUG=True
python backend/app.py

# Enable server debug
python backend/server.py  # Already has debug logging
```

## 📈 Statistics and Analytics

### Player Statistics
- Total games played
- Wins, losses, draws
- Win percentage calculation
- Player rating system
- Game history tracking

### Database Queries
```sql
-- Top players by rating
SELECT username, rating, total_games, wins 
FROM players 
ORDER BY rating DESC 
LIMIT 10;

-- Player game history
SELECT p.username, gh.game_type, gh.winning_team, pgs.is_winner
FROM players p
JOIN player_game_stats pgs ON p.id = pgs.player_id
JOIN game_history gh ON pgs.game_history_id = gh.id
WHERE p.username = 'player123'
ORDER BY gh.completed_at DESC;
```

## 🚀 Future Enhancements

### Planned Features
- [ ] Password reset via email
- [ ] Email verification
- [ ] Two-factor authentication
- [ ] Social login (Google, Facebook)
- [ ] Player profiles and avatars
- [ ] Friend system
- [ ] Private game rooms
- [ ] Tournament system
- [ ] Leaderboards
- [ ] Achievement system

### API Extensions
- [ ] Player search API
- [ ] Game history API
- [ ] Statistics API
- [ ] Admin management API
- [ ] Reporting and analytics

## 📝 License

This authentication system is part of the Hokm Game project.

---

## 🎊 Congratulations!

Your Hokm game now has a complete authentication system! Players must authenticate before accessing the game, ensuring persistent player identities, statistics tracking, and a professional gaming experience.

**Ready to play authenticated Hokm!** 🃏🎮
