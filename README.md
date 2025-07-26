# Hokm Card Game - Distributed Server

A production-ready WebSocket-based Hokm card game server with distributed architecture, fault tolerance, and horizontal scaling capabilities.

## 🎮 Features

- **Complete Hokm Game Logic**: Full 4-player team-based card game implementation
- **Real-time WebSocket Communication**: Instant messaging and game updates
- **Authentication System**: Secure JWT-based player authentication
- **Distributed Architecture**: Horizontal scaling with load balancing
- **Fault Tolerance**: Circuit breaker patterns and automatic recovery
- **Data Persistence**: Redis for real-time state, PostgreSQL for permanent storage
- **Enterprise Features**: Monitoring, backup systems, and high availability

## 🏗️ Architecture

### Core Components

- **Backend Server** (`backend/`): Main game server with WebSocket handling
- **Database Layer**: Dual persistence with Redis (sessions) and PostgreSQL (permanent data)
- **Authentication**: JWT-based authentication with user management
- **Load Balancing**: HAProxy configuration for horizontal scaling
- **Monitoring**: Health checks and performance monitoring

### Technology Stack

- **Backend**: Python 3.11+ with asyncio WebSockets
- **Database**: Redis (sessions), PostgreSQL (persistence)
- **Authentication**: JWT tokens with secure password hashing
- **Load Balancer**: HAProxy with WebSocket support
- **Deployment**: Docker Compose, Kubernetes support

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Redis Server
- PostgreSQL (optional, has fallback)

### Installation

```bash
# Clone the repository
git clone https://github.com/ParisaSokuti/DS_project.git
cd DS_project

# Install dependencies
pip install -r requirements.txt

# Start Redis (macOS with Homebrew)
brew services start redis

# Start the game server
python backend/server.py
```

### Testing

```bash
# Run comprehensive tests
python -m pytest tests/

# Test specific functionality
python tests/test_core_functionality.py

# Run interactive demo
python backend/client.py
```

## 🎲 Game Rules

Hokm is a Persian trick-taking card game for 4 players in 2 teams:

1. **Setup**: 4 players, 2 teams (North-South vs East-West)
2. **Hakem Selection**: Random player chooses trump suit (Hokm)
3. **Card Dealing**: 5 cards initially, then 8 more after Hokm selection
4. **Gameplay**: Players play cards in turns, highest card wins trick
5. **Scoring**: First team to 7 points wins

## 📁 Project Structure

```
DS_project/
├── backend/                 # Core server implementation
│   ├── server.py           # Main WebSocket game server
│   ├── game_board.py       # Game logic and rules
│   ├── auth_service.py     # Authentication system
│   ├── redis_manager.py    # Redis integration
│   └── client.py           # Test client
├── docs/                   # Documentation
├── tests/                  # Test suites
├── examples_archive/       # Configuration examples
├── scripts/                # Deployment scripts
├── requirements.txt        # Python dependencies
└── docker-compose.yml      # Container orchestration
```

## 🔧 Configuration

### Environment Variables

```bash
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_password

# PostgreSQL Configuration (optional)
DB_HOST=localhost
DB_NAME=hokm_game
DB_USER=postgres
DB_PASSWORD=your_db_password

# Authentication
JWT_SECRET=your_jwt_secret_key
SESSION_SECRET=your_session_secret
```

### Docker Deployment

```bash
# Start all services
docker-compose up -d

# Scale game servers
docker-compose up --scale game-server=3
```

## 🏥 Health & Monitoring

- Health endpoint: `http://localhost:8765/health`
- Game statistics: Built-in player and game analytics
- Performance monitoring: Redis and PostgreSQL metrics
- Logging: Comprehensive application and error logs

## 🔒 Security Features

- JWT token-based authentication
- Secure password hashing (bcrypt)
- Session management with expiration
- Input validation and sanitization
- Rate limiting and DDoS protection

## 🚀 Production Features

### High Availability
- Circuit breaker patterns for fault tolerance
- Automatic failover between storage layers
- Health checks and recovery mechanisms

### Scalability
- Horizontal scaling with HAProxy load balancer
- WebSocket-aware sticky sessions
- Auto-scaling based on player load

### Backup & Recovery
- Automated PostgreSQL and Redis backups
- Database replication support
- Disaster recovery procedures

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🛠️ Support

For issues and questions:
- Check the [documentation](docs/)
- Review the [test results](tests/)
- Open an issue on GitHub

---

**Status**: Production Ready ✅  
**Last Updated**: July 2025  
**Version**: 2.0.0
