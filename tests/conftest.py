import pytest
import threading
import asyncio
import time
import os
from typing import AsyncGenerator, Dict, Any, List
from unittest.mock import AsyncMock
from faker import Faker
import uuid
from datetime import datetime, timedelta
from backend.server import main as server_main

# Import database modules (adjust based on your structure)
try:
    from backend.database.connection import DatabaseManager
    from backend.database.models import Player, GameSession, GameMove, PlayerStats
    from backend.database.game_integration import GameIntegration
    from backend.database.analytics import AnalyticsManager
except ImportError:
    # Mock classes if not available
    class DatabaseManager:
        async def initialize(self): pass
        async def create_tables(self): pass
        async def cleanup(self): pass
        def get_session(self): return AsyncMock()
    
    class GameIntegration:
        def __init__(self, session): self.session = session
    
    class AnalyticsManager:
        def __init__(self, session): self.session = session
    
    class Player:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    
    class GameSession:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    
    class GameMove:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    
    class PlayerStats:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)

# Test database configuration
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", 
    "postgresql://test_user:test_password@localhost:5432/hokm_test"
)

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)

@pytest.fixture(scope="session", autouse=True)
def start_server():
    """Start the Hokm WebSocket server before any tests run."""
    thread = threading.Thread(target=lambda: asyncio.run(server_main()), daemon=True)
    thread.start()
    # Wait for server to initialize
    time.sleep(1)
    yield

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def db_manager() -> AsyncGenerator[DatabaseManager, None]:
    """Create a database manager for testing."""
    manager = DatabaseManager(
        database_url=TEST_DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        environment="test"
    )
    
    try:
        await manager.initialize()
        await manager.create_tables()
        yield manager
    finally:
        await manager.cleanup()

@pytest.fixture
async def db_session(db_manager: DatabaseManager):
    """Create a database session with automatic rollback for test isolation."""
    async with db_manager.get_session() as session:
        # Start a savepoint for test isolation
        trans = await session.begin()
        try:
            yield session
        finally:
            # Always rollback to ensure test isolation
            await trans.rollback()

@pytest.fixture
async def game_integration(db_session) -> GameIntegration:
    """Create a game integration instance for testing."""
    return GameIntegration(db_session)

@pytest.fixture
async def analytics_manager(db_session) -> AnalyticsManager:
    """Create an analytics manager instance for testing."""
    return AnalyticsManager(db_session)

@pytest.fixture
def faker_instance() -> Faker:
    """Create a Faker instance for generating test data."""
    fake = Faker()
    Faker.seed(42)  # For reproducible test data
    return fake

@pytest.fixture
async def sample_player(db_session, faker_instance) -> Player:
    """Create a sample player for testing."""
    from backend.database.models import Player
    
    player_data = {
        "username": faker_instance.user_name(),
        "email": faker_instance.email(),
        "display_name": faker_instance.name(),
        "created_at": datetime.utcnow(),
        "is_active": True,
        "total_games": 0,
        "games_won": 0,
        "games_lost": 0,
        "total_score": 0,
        "average_score": 0.0,
        "rank": "Beginner",
        "last_active": datetime.utcnow()
    }
    
    player = Player(**player_data)
    db_session.add(player)
    await db_session.flush()
    return player

@pytest.fixture
async def sample_players(db_session, faker_instance) -> List[Player]:
    """Create 4 sample players for a complete game."""
    from backend.database.models import Player
    
    players = []
    for i in range(4):
        player_data = {
            "username": f"player_{i}_{faker_instance.user_name()}",
            "email": faker_instance.email(),
            "display_name": faker_instance.name(),
            "created_at": datetime.utcnow(),
            "is_active": True,
            "total_games": faker_instance.random_int(0, 100),
            "games_won": faker_instance.random_int(0, 50),
            "games_lost": faker_instance.random_int(0, 50),
            "total_score": faker_instance.random_int(0, 10000),
            "average_score": faker_instance.random.uniform(0, 100),
            "rank": faker_instance.random_element(["Beginner", "Intermediate", "Advanced", "Expert"]),
            "last_active": datetime.utcnow()
        }
        
        player = Player(**player_data)
        db_session.add(player)
        players.append(player)
    
    await db_session.flush()
    return players

@pytest.fixture
async def sample_game_session(db_session, sample_players) -> GameSession:
    """Create a sample game session with 4 players."""
    from backend.database.models import GameSession
    
    game_data = {
        "room_id": f"ROOM_{uuid.uuid4().hex[:8].upper()}",
        "status": "waiting",
        "max_players": 4,
        "current_players": len(sample_players),
        "game_type": "hokm",
        "created_at": datetime.utcnow(),
        "hakem_id": sample_players[0].id,
        "trump_suit": None,
        "current_round": 1,
        "rounds_to_win": 7,
        "team_1_score": 0,
        "team_2_score": 0,
        "current_turn": 0,
        "game_state": {
            "phase": "waiting",
            "deck": [],
            "players": {str(p.id): {"cards": [], "team": i % 2} for i, p in enumerate(sample_players)},
            "current_trick": [],
            "tricks_won": {"team_1": 0, "team_2": 0}
        }
    }
    
    game_session = GameSession(**game_data)
    db_session.add(game_session)
    await db_session.flush()
    return game_session

@pytest.fixture
def sample_game_state() -> Dict[str, Any]:
    """Create a sample game state for testing."""
    return {
        "phase": "playing",
        "round": 1,
        "trump_suit": "spades",
        "current_turn": 0,
        "hakem": "player_1",
        "teams": {
            "team_1": ["player_1", "player_3"],
            "team_2": ["player_2", "player_4"]
        },
        "scores": {
            "team_1": 0,
            "team_2": 0
        },
        "players": {
            "player_1": {"cards": ["AS", "KS", "QS", "JS", "10S"], "team": 1},
            "player_2": {"cards": ["AH", "KH", "QH", "JH", "10H"], "team": 2},
            "player_3": {"cards": ["AD", "KD", "QD", "JD", "10D"], "team": 1},
            "player_4": {"cards": ["AC", "KC", "QC", "JC", "10C"], "team": 2}
        },
        "current_trick": [],
        "tricks_won": {"team_1": 0, "team_2": 0}
    }

@pytest.fixture
def performance_config() -> Dict[str, Any]:
    """Configuration for performance testing."""
    return {
        "concurrent_users": int(os.getenv("PERF_TEST_CONCURRENT_USERS", "25")),
        "test_duration": int(os.getenv("PERF_TEST_DURATION_SECONDS", "30")),
        "operations_per_second": int(os.getenv("PERF_TEST_OPERATIONS_PER_SECOND", "20")),
        "max_response_time": float(os.getenv("PERF_TEST_MAX_RESPONSE_TIME", "0.1")),
        "memory_limit_mb": int(os.getenv("PERF_TEST_MEMORY_LIMIT_MB", "200"))
    }

@pytest.fixture
async def mock_websocket_connection():
    """Create a mock WebSocket connection for testing."""
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.receive = AsyncMock()
    mock_ws.close = AsyncMock()
    return mock_ws

@pytest.fixture
def test_data_generator(faker_instance):
    """Generate various types of test data."""
    def _generate_player_data(count: int = 1) -> List[Dict[str, Any]]:
        players = []
        for _ in range(count):
            players.append({
                "username": faker_instance.user_name(),
                "email": faker_instance.email(),
                "display_name": faker_instance.name(),
                "is_active": True,
                "created_at": faker_instance.date_time_this_year(),
                "last_active": faker_instance.date_time_this_month()
            })
        return players[0] if count == 1 else players
    
    def _generate_game_data() -> Dict[str, Any]:
        return {
            "room_id": f"ROOM_{faker_instance.random_string(8).upper()}",
            "status": faker_instance.random_element(["waiting", "active", "completed"]),
            "max_players": 4,
            "game_type": "hokm",
            "created_at": faker_instance.date_time_this_month(),
            "trump_suit": faker_instance.random_element(["spades", "hearts", "diamonds", "clubs"])
        }
    
    return {
        "player": _generate_player_data,
        "game": _generate_game_data
    }

# Custom assertion helpers
def assert_player_data_equal(actual: Player, expected: Dict[str, Any]):
    """Assert that player data matches expected values."""
    assert actual.username == expected["username"]
    assert actual.email == expected["email"]
    assert actual.display_name == expected["display_name"]

def assert_game_state_valid(game_state: Dict[str, Any]):
    """Assert that game state is valid."""
    required_fields = ["phase", "players", "current_turn", "teams"]
    for field in required_fields:
        assert field in game_state, f"Missing required field: {field}"
    
    assert len(game_state["players"]) == 4, "Game must have 4 players"
    assert game_state["phase"] in ["waiting", "hokm_selection", "dealing", "playing", "completed"]

# Pytest markers
pytest.mark.asyncio = pytest.mark.asyncio
pytest.mark.integration = pytest.mark.integration
pytest.mark.performance = pytest.mark.performance

# Environment setup
@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment variables."""
    os.environ["DATABASE_ENVIRONMENT"] = "test"
    os.environ["TESTING"] = "true"
    yield
