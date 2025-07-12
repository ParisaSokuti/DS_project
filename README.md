# Hokm Card Game - Optimized & Clean

## 🎮 Production-Ready Persian Card Game

### Project Structure
```
DS_project/
├── backend/                    # Optimized game logic and server
│   ├── __init__.py
│   ├── server.py              # Main WebSocket game server
│   ├── client.py              # Game client
│   ├── game_board.py          # Core game logic (optimized)
│   ├── game_states.py         # Game state management
│   ├── game_auth_manager.py   # Authentication manager
│   ├── auth_service.py        # Authentication service (bcrypt)
│   ├── client_auth_manager.py # Client authentication
│   ├── models.py              # Database models (optimized)
│   ├── db_session.py          # Database connection (pooled)
│   ├── redis_manager.py       # Redis state management (pooled)
│   ├── network.py             # Network utilities (optimized)
│   ├── create_tables.py       # Database setup
│   └── database_schema.sql    # Database schema
├── start_game.py              # Server launcher
├── start_client.py            # Client launcher
├── requirements.txt           # Dependencies
└── .git/                      # Version control

```

### 🚀 Quick Start

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the Server:**
   ```bash
   python start_game.py
   ```

3. **Start Clients (in separate terminals):**
   ```bash
   python start_client.py
   ```

### 🎯 Game Features

- **4-Player Multiplayer:** Real-time Persian Hokm card game
- **WebSocket Server:** ws://localhost:8765
- **User Authentication:** JWT-based with PostgreSQL
- **Game State Management:** Redis caching + PostgreSQL persistence
- **Team Play:** 2v2 team formation
- **Hokm Selection:** Traditional Persian card game rules
- **13 Tricks:** Complete game rounds with scoring

### 🔧 Technical Stack

- **Backend:** Python 3.7+ with asyncio
- **WebSocket:** Real-time communication
- **Database:** PostgreSQL with SQLAlchemy (connection pooled)
- **Cache:** Redis for game state (connection pooled)
- **Authentication:** JWT tokens with bcrypt hashing
- **Cards:** Standard 52-card deck with Persian Hokm rules

### ⚡ Optimizations

- **Performance:** Connection pooling, optimized algorithms, type hints
- **Security:** Bcrypt password hashing, enhanced validation
- **Code Quality:** Clean imports, comprehensive error handling
- **Memory:** Efficient data structures, reduced overhead
- **Network:** Optimized WebSocket handling and broadcasting

### 📊 Database

- **Clean Database:** Reset and ready for new games
- **User System:** Registration, login, statistics
- **Game Sessions:** Persistent game history
- **Rating System:** Player skill tracking
- **Health Monitoring:** Connection pool status tracking

### 🎪 Ready to Play!

The game is now fully optimized with enhanced performance, security, and maintainability while preserving all original functionality!
