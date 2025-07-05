"""
Comprehensive Test Suite for SQLAlchemy 2.0 Async Integration
Tests all database operations, connection pooling, and game integration
"""

import asyncio
import pytest
import logging
from typing import List, Dict, Any
from uuid import uuid4
import json

# Configure test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestAsyncDatabaseIntegration:
    """
    Test suite for async database operations
    Validates all CRUD operations and integration layer functionality
    """
    
    @pytest.fixture(scope="session")
    async def database_setup(self):
        """
        Set up test database configuration
        """
        from backend.database.config import DatabaseConfig, set_database_config
        from backend.database.session_manager import set_session_manager, AsyncSessionManager
        
        # Create test configuration
        test_config = DatabaseConfig.for_testing()
        set_database_config(test_config)
        
        # Create test session manager
        session_manager = AsyncSessionManager(test_config)
        await session_manager.initialize()
        await set_session_manager(session_manager)
        
        yield session_manager
        
        # Cleanup
        await session_manager.cleanup()
    
    @pytest.fixture
    async def clean_database(self, database_setup):
        """
        Clean database before each test
        """
        session_manager = database_setup
        
        # Clean up test data
        from backend.database.models import (
            Player, GameSession, GameParticipant, GameMove, WebSocketConnection
        )
        
        async with session_manager.get_session() as session:
            # Delete in correct order to avoid foreign key constraints
            await session.execute(delete(GameMove))
            await session.execute(delete(WebSocketConnection))
            await session.execute(delete(GameParticipant))
            await session.execute(delete(GameSession))
            await session.execute(delete(Player))
            await session.commit()
        
        yield
    
    async def test_session_manager_initialization(self, database_setup):
        """
        Test session manager initialization and health check
        """
        session_manager = database_setup
        
        # Test health check
        health = await session_manager.health_check()
        assert health['status'] == 'healthy'
        assert health['is_initialized'] is True
        assert health['circuit_breaker_open'] is False
        
        # Test connection stats
        stats = session_manager.get_stats()
        assert 'total_connections' in stats
        assert 'active_sessions_count' in stats
    
    async def test_player_crud_operations(self, clean_database, database_setup):
        """
        Test all player CRUD operations
        """
        from backend.database.crud import player_crud
        
        session_manager = database_setup
        
        async with session_manager.get_session() as session:
            # Test create player
            player = await player_crud.create_player(
                session,
                username="test_player",
                email="test@example.com",
                display_name="Test Player"
            )
            
            assert player.username == "test_player"
            assert player.email == "test@example.com"
            assert player.display_name == "Test Player"
            assert player.rating == 1000  # Default rating
            
            await session.commit()
            
            # Test get by username
            found_player = await player_crud.get_by_username(session, "test_player")
            assert found_player is not None
            assert found_player.id == player.id
            
            # Test get by email
            found_player = await player_crud.get_by_email(session, "test@example.com")
            assert found_player is not None
            assert found_player.id == player.id
            
            # Test update stats
            await player_crud.update_game_stats(
                session,
                player.id,
                games_increment=1,
                wins_increment=1,
                points_increment=100,
                rating_change=50
            )
            await session.commit()
            
            # Verify updates
            await session.refresh(player)
            assert player.total_games == 1
            assert player.wins == 1
            assert player.total_points == 100
            assert player.rating == 1050
    
    async def test_game_session_crud_operations(self, clean_database, database_setup):
        """
        Test game session CRUD operations
        """
        from backend.database.crud import game_session_crud
        
        session_manager = database_setup
        
        async with session_manager.get_session() as session:
            # Test create game
            game = await game_session_crud.create_game(
                session,
                room_id="TEST_ROOM",
                session_key="test_session_key",
                game_type="standard",
                max_players=4
            )
            
            assert game.room_id == "TEST_ROOM"
            assert game.session_key == "test_session_key"
            assert game.game_type == "standard"
            assert game.max_players == 4
            assert game.status == "waiting"
            
            await session.commit()
            
            # Test get by room ID
            found_game = await game_session_crud.get_by_room_id(session, "TEST_ROOM")
            assert found_game is not None
            assert found_game.id == game.id
            
            # Test update game state
            updated_game = await game_session_crud.update_game_state(
                session,
                game.id,
                status="active",
                phase="playing",
                current_round=2
            )
            await session.commit()
            
            assert updated_game.status == "active"
            assert updated_game.phase == "playing"
            assert updated_game.current_round == 2
            
            # Test increment player count
            await game_session_crud.increment_player_count(session, game.id, 2)
            await session.commit()
            
            await session.refresh(game)
            assert game.current_players == 2
    
    async def test_game_participant_operations(self, clean_database, database_setup):
        """
        Test game participant operations
        """
        from backend.database.crud import player_crud, game_session_crud, game_participant_crud
        
        session_manager = database_setup
        
        async with session_manager.get_session() as session:
            # Create test data
            player = await player_crud.create_player(session, username="participant_test")
            game = await game_session_crud.create_game(
                session, room_id="PARTICIPANT_TEST", session_key="test_key"
            )
            await session.commit()
            
            # Test add participant
            participant = await game_participant_crud.add_participant(
                session,
                game_id=game.id,
                player_id=player.id,
                position=0,
                team=1
            )
            
            assert participant.position == 0
            assert participant.team == 1
            assert participant.is_connected is True
            
            await session.commit()
            
            # Test get game participants
            participants = await game_participant_crud.get_game_participants(session, game.id)
            assert len(participants) == 1
            assert participants[0].id == participant.id
            
            # Test update connection status
            await game_participant_crud.update_connection_status(
                session, participant.id, False, "conn_123"
            )
            await session.commit()
            
            await session.refresh(participant)
            assert participant.is_connected is False
            assert participant.connection_id == "conn_123"
    
    async def test_game_move_operations(self, clean_database, database_setup):
        """
        Test game move recording and retrieval
        """
        from backend.database.crud import (
            player_crud, game_session_crud, game_participant_crud, game_move_crud
        )
        
        session_manager = database_setup
        
        async with session_manager.get_session() as session:
            # Create test data
            player = await player_crud.create_player(session, username="move_test")
            game = await game_session_crud.create_game(
                session, room_id="MOVE_TEST", session_key="test_key"
            )
            await session.commit()
            
            # Test record move
            move = await game_move_crud.record_move(
                session,
                game_id=game.id,
                player_id=player.id,
                move_type="play_card",
                move_data={"card": {"suit": "hearts", "rank": "ace"}},
                round_number=1,
                trick_number=1
            )
            
            assert move.move_type == "play_card"
            assert move.move_data["card"]["suit"] == "hearts"
            assert move.round_number == 1
            assert move.trick_number == 1
            assert move.sequence_number == 1
            
            await session.commit()
            
            # Test get game moves
            moves = await game_move_crud.get_game_moves(session, game.id)
            assert len(moves) == 1
            assert moves[0].id == move.id
            
            # Test get moves by type
            card_moves = await game_move_crud.get_game_moves(
                session, game.id, move_type="play_card"
            )
            assert len(card_moves) == 1
            
            # Test get recent moves
            recent = await game_move_crud.get_recent_moves(session, game.id, limit=5)
            assert len(recent) == 1
    
    async def test_websocket_connection_operations(self, clean_database, database_setup):
        """
        Test WebSocket connection tracking
        """
        from backend.database.crud import player_crud, websocket_connection_crud
        
        session_manager = database_setup
        
        async with session_manager.get_session() as session:
            # Create test player
            player = await player_crud.create_player(session, username="ws_test")
            await session.commit()
            
            # Test create connection
            connection = await websocket_connection_crud.create_connection(
                session,
                connection_id="ws_conn_123",
                player_id=player.id,
                ip_address="127.0.0.1",
                user_agent="Test Browser"
            )
            
            assert connection.connection_id == "ws_conn_123"
            assert connection.player_id == player.id
            assert connection.is_active is True
            
            await session.commit()
            
            # Test get by connection ID
            found_conn = await websocket_connection_crud.get_by_connection_id(
                session, "ws_conn_123"
            )
            assert found_conn is not None
            assert found_conn.id == connection.id
            
            # Test update last ping
            await websocket_connection_crud.update_last_ping(session, "ws_conn_123")
            await session.commit()
            
            # Test disconnect
            await websocket_connection_crud.disconnect_connection(
                session, "ws_conn_123", "user_disconnect"
            )
            await session.commit()
            
            await session.refresh(connection)
            assert connection.is_active is False
            assert connection.disconnect_reason == "user_disconnect"
    
    async def test_game_integration_layer(self, clean_database, database_setup):
        """
        Test high-level game integration operations
        """
        from backend.database.integration import game_integration
        
        # Test create player if not exists
        player, created = await game_integration.create_player_if_not_exists("integration_test")
        assert created is True
        assert player.username == "integration_test"
        
        # Test get existing player
        same_player, created = await game_integration.create_player_if_not_exists("integration_test")
        assert created is False
        assert same_player.id == player.id
        
        # Test create game room
        game = await game_integration.create_game_room(
            room_id="INTEGRATION_TEST",
            creator_username="integration_test"
        )
        
        assert game.room_id == "INTEGRATION_TEST"
        assert game.current_players == 1
        
        # Test join game room
        game2, participant = await game_integration.join_game_room(
            room_id="INTEGRATION_TEST",
            username="player2"
        )
        
        assert game2.id == game.id
        assert participant.position == 1
        assert participant.team == 2
        
        # Test get game state
        game_state = await game_integration.get_game_state("INTEGRATION_TEST")
        assert game_state is not None
        assert len(game_state['participants']) == 2
        assert game_state['game']['current_players'] == 2
    
    async def test_transaction_handling(self, clean_database, database_setup):
        """
        Test transaction rollback on errors
        """
        from backend.database.crud import player_crud
        from backend.database.session_manager import get_db_transaction
        
        # Test successful transaction
        async with get_db_transaction() as session:
            player = await player_crud.create_player(session, username="tx_test")
            assert player.username == "tx_test"
            # Transaction automatically commits on success
        
        # Verify player was created
        async with get_db_transaction() as session:
            found = await player_crud.get_by_username(session, "tx_test")
            assert found is not None
        
        # Test failed transaction (should rollback)
        try:
            async with get_db_transaction() as session:
                await player_crud.create_player(session, username="tx_test_fail")
                # Simulate an error
                raise ValueError("Simulated error")
        except ValueError:
            pass
        
        # Verify player was not created due to rollback
        async with get_db_transaction() as session:
            found = await player_crud.get_by_username(session, "tx_test_fail")
            assert found is None
    
    async def test_connection_pool_performance(self, database_setup):
        """
        Test connection pool under concurrent load
        """
        from backend.database.crud import player_crud
        from backend.database.session_manager import get_db_session
        
        async def create_test_player(player_num: int):
            """Create a test player in a separate session"""
            async with get_db_session() as session:
                player = await player_crud.create_player(
                    session, username=f"perf_test_{player_num}"
                )
                await session.commit()
                return player
        
        # Create 20 concurrent operations
        tasks = [create_test_player(i) for i in range(20)]
        players = await asyncio.gather(*tasks)
        
        # Verify all players were created
        assert len(players) == 20
        for i, player in enumerate(players):
            assert player.username == f"perf_test_{i}"
    
    async def test_error_handling(self, clean_database, database_setup):
        """
        Test error handling and recovery
        """
        from backend.database.crud import player_crud
        from backend.database.session_manager import get_db_session
        
        # Test duplicate username error
        async with get_db_session() as session:
            await player_crud.create_player(session, username="duplicate_test")
            await session.commit()
        
        # Should raise ValueError for duplicate username
        with pytest.raises(ValueError, match="already exists"):
            async with get_db_session() as session:
                await player_crud.create_player(session, username="duplicate_test")
                await session.commit()


async def run_integration_tests():
    """
    Run all integration tests manually (without pytest)
    """
    logger.info("Starting SQLAlchemy 2.0 async integration tests")
    
    try:
        # Initialize test environment
        from backend.database.config import DatabaseConfig, set_database_config
        from backend.database.session_manager import set_session_manager, AsyncSessionManager
        
        # Create test configuration
        test_config = DatabaseConfig.for_testing()
        set_database_config(test_config)
        
        # Create session manager
        session_manager = AsyncSessionManager(test_config)
        await session_manager.initialize()
        await set_session_manager(session_manager)
        
        logger.info("✓ Database initialized")
        
        # Test session manager health
        health = await session_manager.health_check()
        assert health['status'] == 'healthy'
        logger.info("✓ Health check passed")
        
        # Test basic CRUD operations
        from backend.database.crud import player_crud
        async with session_manager.get_session() as session:
            player = await player_crud.create_player(
                session, username="test_user", email="test@example.com"
            )
            await session.commit()
            
            found = await player_crud.get_by_username(session, "test_user")
            assert found is not None
            assert found.username == "test_user"
        
        logger.info("✓ Basic CRUD operations working")
        
        # Test integration layer
        from backend.database.integration import game_integration
        
        game = await game_integration.create_game_room(
            room_id="TEST123",
            creator_username="test_creator"
        )
        assert game.room_id == "TEST123"
        logger.info("✓ Game room creation working")
        
        game_state = await game_integration.get_game_state("TEST123")
        assert game_state is not None
        logger.info("✓ Game state retrieval working")
        
        # Cleanup
        await session_manager.cleanup()
        logger.info("✓ Cleanup completed")
        
        logger.info("🎉 All integration tests passed!")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    # Run tests manually
    asyncio.run(run_integration_tests())
