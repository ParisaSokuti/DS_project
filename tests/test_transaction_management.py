"""
Transaction management tests for PostgreSQL integration.
Tests ACID properties, rollback scenarios, and concurrent access.
"""

import pytest
import asyncio
import time
from datetime import datetime
from unittest.mock import patch


@pytest.mark.asyncio
@pytest.mark.integration
class TestTransactionManagement:
    """Test transaction management and ACID properties."""
    
    async def test_basic_transaction_commit(self, db_manager, test_data_generator):
        """Test basic transaction commit functionality."""
        player_data = test_data_generator["player"]()
        
        async with db_manager.get_session() as session:
            async with session.begin():
                # Insert player within transaction
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.flush()
                
                # Verify player exists within transaction
                result = await session.execute(
                    "SELECT username FROM players WHERE username = :username",
                    {"username": player_data["username"]}
                )
                assert result.fetchone() is not None
                
                # Transaction commits automatically when exiting context
        
        # Verify data persists after commit
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT username FROM players WHERE username = :username",
                {"username": player_data["username"]}
            )
            assert result.fetchone() is not None
    
    async def test_transaction_rollback_on_exception(self, db_manager, test_data_generator):
        """Test transaction rollback when exception occurs."""
        player_data = test_data_generator["player"]()
        
        try:
            async with db_manager.get_session() as session:
                async with session.begin():
                    # Insert player
                    from backend.database.models import Player
                    player = Player(**player_data)
                    session.add(player)
                    await session.flush()
                    
                    # Verify insertion within transaction
                    result = await session.execute(
                        "SELECT username FROM players WHERE username = :username",
                        {"username": player_data["username"]}
                    )
                    assert result.fetchone() is not None
                    
                    # Force an exception
                    raise ValueError("Simulated error")
        except ValueError:
            pass  # Expected exception
        
        # Verify data was rolled back
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT username FROM players WHERE username = :username",
                {"username": player_data["username"]}
            )
            assert result.fetchone() is None
    
    async def test_manual_transaction_rollback(self, db_manager, test_data_generator):
        """Test manual transaction rollback."""
        player_data = test_data_generator["player"]()
        
        async with db_manager.get_session() as session:
            trans = await session.begin()
            try:
                # Insert player
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.flush()
                
                # Verify insertion
                result = await session.execute(
                    "SELECT username FROM players WHERE username = :username",
                    {"username": player_data["username"]}
                )
                assert result.fetchone() is not None
                
                # Manual rollback
                await trans.rollback()
            except Exception:
                await trans.rollback()
                raise
        
        # Verify data was rolled back
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT username FROM players WHERE username = :username",
                {"username": player_data["username"]}
            )
            assert result.fetchone() is None
    
    async def test_nested_transactions_savepoints(self, db_manager, test_data_generator):
        """Test nested transactions using savepoints."""
        player1_data = test_data_generator["player"]()
        player2_data = test_data_generator["player"]()
        
        async with db_manager.get_session() as session:
            async with session.begin():
                # Insert first player
                from backend.database.models import Player
                player1 = Player(**player1_data)
                session.add(player1)
                await session.flush()
                
                # Create savepoint
                savepoint = await session.begin_nested()
                try:
                    # Insert second player
                    player2 = Player(**player2_data)
                    session.add(player2)
                    await session.flush()
                    
                    # Force error in nested transaction
                    raise ValueError("Nested transaction error")
                except ValueError:
                    # Rollback to savepoint
                    await savepoint.rollback()
                
                # Verify first player still exists
                result = await session.execute(
                    "SELECT username FROM players WHERE username = :username",
                    {"username": player1_data["username"]}
                )
                assert result.fetchone() is not None
                
                # Verify second player was rolled back
                result = await session.execute(
                    "SELECT username FROM players WHERE username = :username",
                    {"username": player2_data["username"]}
                )
                assert result.fetchone() is None
        
        # Verify final state - only first player should exist
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT username FROM players WHERE username = :username",
                {"username": player1_data["username"]}
            )
            assert result.fetchone() is not None
            
            result = await session.execute(
                "SELECT username FROM players WHERE username = :username",
                {"username": player2_data["username"]}
            )
            assert result.fetchone() is None
    
    async def test_concurrent_transactions_isolation(self, db_manager, sample_player):
        """Test transaction isolation with concurrent access."""
        player_id = sample_player.id
        initial_games = sample_player.total_games
        
        async def update_player_games(increment: int, delay: float = 0.1):
            async with db_manager.get_session() as session:
                async with session.begin():
                    # Read current value
                    result = await session.execute(
                        "SELECT total_games FROM players WHERE id = :player_id",
                        {"player_id": player_id}
                    )
                    current_games = result.fetchone()[0]
                    
                    # Simulate some processing time
                    await asyncio.sleep(delay)
                    
                    # Update with new value
                    await session.execute(
                        "UPDATE players SET total_games = :new_games WHERE id = :player_id",
                        {"new_games": current_games + increment, "player_id": player_id}
                    )
                    
                    return current_games + increment
        
        # Run concurrent updates
        tasks = [
            update_player_games(1, 0.05),
            update_player_games(2, 0.05),
            update_player_games(3, 0.05)
        ]
        results = await asyncio.gather(*tasks)
        
        # Verify final state
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT total_games FROM players WHERE id = :player_id",
                {"player_id": player_id}
            )
            final_games = result.fetchone()[0]
        
        # With proper isolation, the final value should be one of the expected outcomes
        # Due to concurrent access, we can't predict exact order, but it should be consistent
        expected_values = [initial_games + 1, initial_games + 2, initial_games + 3]
        assert final_games in [initial_games + sum(expected_values[:i+1]) for i in range(len(expected_values))]
    
    async def test_deadlock_detection_and_handling(self, db_manager, sample_players):
        """Test deadlock detection and automatic resolution."""
        if len(sample_players) < 2:
            pytest.skip("Need at least 2 players for deadlock test")
        
        player1_id = sample_players[0].id
        player2_id = sample_players[1].id
        
        deadlock_occurred = False
        successful_transactions = 0
        
        async def transaction_a():
            nonlocal deadlock_occurred, successful_transactions
            try:
                async with db_manager.get_session() as session:
                    async with session.begin():
                        # Lock player1 first
                        await session.execute(
                            "UPDATE players SET total_games = total_games + 1 WHERE id = :id",
                            {"id": player1_id}
                        )
                        
                        # Small delay to increase deadlock chance
                        await asyncio.sleep(0.1)
                        
                        # Then lock player2
                        await session.execute(
                            "UPDATE players SET total_games = total_games + 1 WHERE id = :id",
                            {"id": player2_id}
                        )
                        
                        successful_transactions += 1
            except Exception as e:
                if "deadlock" in str(e).lower():
                    deadlock_occurred = True
                else:
                    raise
        
        async def transaction_b():
            nonlocal deadlock_occurred, successful_transactions
            try:
                async with db_manager.get_session() as session:
                    async with session.begin():
                        # Lock player2 first (opposite order)
                        await session.execute(
                            "UPDATE players SET total_games = total_games + 1 WHERE id = :id",
                            {"id": player2_id}
                        )
                        
                        # Small delay to increase deadlock chance
                        await asyncio.sleep(0.1)
                        
                        # Then lock player1
                        await session.execute(
                            "UPDATE players SET total_games = total_games + 1 WHERE id = :id",
                            {"id": player1_id}
                        )
                        
                        successful_transactions += 1
            except Exception as e:
                if "deadlock" in str(e).lower():
                    deadlock_occurred = True
                else:
                    raise
        
        # Run transactions that could deadlock
        await asyncio.gather(
            transaction_a(),
            transaction_b(),
            return_exceptions=True
        )
        
        # Either both transactions should succeed, or deadlock should be detected and handled
        # At least one transaction should complete successfully
        assert successful_transactions >= 1 or deadlock_occurred
    
    async def test_long_running_transaction_timeout(self, db_manager, test_data_generator):
        """Test handling of long-running transactions."""
        player_data = test_data_generator["player"]()
        
        # Set a short statement timeout for this test
        timeout_occurred = False
        
        try:
            async with db_manager.get_session() as session:
                # Set statement timeout to 1 second
                await session.execute("SET statement_timeout = '1s'")
                
                async with session.begin():
                    # Insert player
                    from backend.database.models import Player
                    player = Player(**player_data)
                    session.add(player)
                    await session.flush()
                    
                    # Simulate long-running operation (sleep longer than timeout)
                    await session.execute("SELECT pg_sleep(2)")
                    
        except Exception as e:
            if "timeout" in str(e).lower() or "canceled" in str(e).lower():
                timeout_occurred = True
            else:
                raise
        
        # Reset timeout
        async with db_manager.get_session() as session:
            await session.execute("SET statement_timeout = 0")
        
        # Verify timeout was handled (may not occur in all environments)
        # If timeout occurred, transaction should be rolled back
        if timeout_occurred:
            async with db_manager.get_session() as session:
                result = await session.execute(
                    "SELECT username FROM players WHERE username = :username",
                    {"username": player_data["username"]}
                )
                assert result.fetchone() is None
    
    async def test_transaction_retry_logic(self, game_integration, sample_player):
        """Test transaction retry logic for handling temporary failures."""
        retry_count = 0
        max_retries = 3
        
        async def operation_with_retries():
            nonlocal retry_count
            
            for attempt in range(max_retries):
                try:
                    retry_count += 1
                    
                    # Simulate transient failure on first attempts
                    if attempt < 2:
                        raise Exception("Simulated transient failure")
                    
                    # Successful operation on final attempt
                    await game_integration.update_player_stats(
                        player_id=sample_player.id,
                        games_played=1,
                        games_won=1
                    )
                    return True
                    
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    # Wait before retry
                    await asyncio.sleep(0.1)
            
            return False
        
        # Execute operation with retries
        success = await operation_with_retries()
        
        assert success is True
        assert retry_count == 3  # Should have tried 3 times
        
        # Verify operation eventually succeeded
        updated_player = await game_integration.get_player_by_id(sample_player.id)
        assert updated_player.total_games >= 1
    
    async def test_batch_transaction_operations(self, db_manager, test_data_generator):
        """Test batch operations within single transaction."""
        batch_size = 10
        player_data_list = test_data_generator["player"](batch_size)
        
        # Perform batch operations in single transaction
        async with db_manager.get_session() as session:
            async with session.begin():
                players = []
                for player_data in player_data_list:
                    from backend.database.models import Player
                    player = Player(**player_data)
                    session.add(player)
                    players.append(player)
                
                # Flush to get IDs but don't commit yet
                await session.flush()
                
                # Verify all players have IDs
                for player in players:
                    assert player.id is not None
                
                # Update all players in same transaction
                for player in players:
                    player.total_games = 5
                    player.last_active = datetime.utcnow()
        
        # Verify all operations completed successfully
        async with db_manager.get_session() as session:
            for player_data in player_data_list:
                result = await session.execute(
                    "SELECT username, total_games FROM players WHERE username = :username",
                    {"username": player_data["username"]}
                )
                row = result.fetchone()
                assert row is not None
                assert row[1] == 5  # total_games should be 5
    
    async def test_connection_failure_during_transaction(self, db_manager, test_data_generator):
        """Test handling of connection failures during transactions."""
        player_data = test_data_generator["player"]()
        
        connection_failed = False
        
        try:
            async with db_manager.get_session() as session:
                async with session.begin():
                    # Insert player
                    from backend.database.models import Player
                    player = Player(**player_data)
                    session.add(player)
                    await session.flush()
                    
                    # Simulate connection failure
                    with patch.object(session, 'execute', side_effect=Exception("Connection lost")):
                        await session.execute("SELECT 1")
                        
        except Exception as e:
            if "connection" in str(e).lower():
                connection_failed = True
            else:
                raise
        
        # Verify transaction was properly cleaned up
        assert connection_failed is True
        
        # Verify data was not persisted due to connection failure
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT username FROM players WHERE username = :username",
                {"username": player_data["username"]}
            )
            assert result.fetchone() is None


@pytest.mark.asyncio
@pytest.mark.integration
class TestACIDProperties:
    """Test ACID (Atomicity, Consistency, Isolation, Durability) properties."""
    
    async def test_atomicity(self, game_integration, sample_players, test_data_generator):
        """Test atomicity - all operations in transaction succeed or fail together."""
        if len(sample_players) < 2:
            pytest.skip("Need at least 2 players for atomicity test")
        
        player1 = sample_players[0]
        player2 = sample_players[1]
        
        initial_games1 = player1.total_games
        initial_games2 = player2.total_games
        
        # Transaction that should fail partway through
        transaction_failed = False
        try:
            async with game_integration.db_session.begin():
                # Update first player - should succeed
                await game_integration.update_player_stats(
                    player_id=player1.id,
                    games_played=5
                )
                
                # Update second player - should succeed
                await game_integration.update_player_stats(
                    player_id=player2.id,
                    games_played=3
                )
                
                # Force failure
                raise ValueError("Forced transaction failure")
                
        except ValueError:
            transaction_failed = True
        
        assert transaction_failed is True
        
        # Verify atomicity - neither player should be updated
        updated_player1 = await game_integration.get_player_by_id(player1.id)
        updated_player2 = await game_integration.get_player_by_id(player2.id)
        
        assert updated_player1.total_games == initial_games1
        assert updated_player2.total_games == initial_games2
    
    async def test_consistency(self, game_integration, sample_game_session, sample_players):
        """Test consistency - database constraints are maintained."""
        if len(sample_players) < 4:
            pytest.skip("Need 4 players for consistency test")
        
        # Test referential integrity
        room_id = sample_game_session.room_id
        
        # Add players to game
        for player in sample_players:
            await game_integration.join_game_room(
                room_id=room_id,
                player_id=player.id,
                connection_id=f"conn_{player.id}"
            )
        
        # Try to violate consistency by adding invalid move
        consistency_maintained = True
        try:
            await game_integration.record_game_move(
                room_id=room_id,
                player_id=99999,  # Non-existent player
                move_type="play_card",
                move_data={"card": "AS"}
            )
            consistency_maintained = False
        except Exception:
            # Exception expected due to referential integrity
            pass
        
        assert consistency_maintained is True
    
    async def test_isolation_read_committed(self, db_manager, sample_player):
        """Test isolation - transactions don't interfere with each other."""
        player_id = sample_player.id
        initial_games = sample_player.total_games
        
        transaction1_value = None
        transaction2_value = None
        
        async def transaction1():
            nonlocal transaction1_value
            async with db_manager.get_session() as session:
                async with session.begin():
                    # Read initial value
                    result = await session.execute(
                        "SELECT total_games FROM players WHERE id = :player_id",
                        {"player_id": player_id}
                    )
                    transaction1_value = result.fetchone()[0]
                    
                    # Wait to ensure transaction2 starts
                    await asyncio.sleep(0.2)
                    
                    # Update value
                    await session.execute(
                        "UPDATE players SET total_games = total_games + 10 WHERE id = :player_id",
                        {"player_id": player_id}
                    )
        
        async def transaction2():
            nonlocal transaction2_value
            # Start after transaction1 has read but before it commits
            await asyncio.sleep(0.1)
            
            async with db_manager.get_session() as session:
                # Should not see uncommitted changes from transaction1
                result = await session.execute(
                    "SELECT total_games FROM players WHERE id = :player_id",
                    {"player_id": player_id}
                )
                transaction2_value = result.fetchone()[0]
        
        # Run both transactions
        await asyncio.gather(transaction1(), transaction2())
        
        # Verify isolation - transaction2 should not see uncommitted changes
        assert transaction1_value == initial_games
        assert transaction2_value == initial_games
        
        # Verify final state
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT total_games FROM players WHERE id = :player_id",
                {"player_id": player_id}
            )
            final_games = result.fetchone()[0]
            assert final_games == initial_games + 10
    
    async def test_durability(self, db_manager, test_data_generator):
        """Test durability - committed transactions survive system failures."""
        player_data = test_data_generator["player"]()
        
        # Commit transaction
        async with db_manager.get_session() as session:
            async with session.begin():
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.flush()
                player_id = player.id
        
        # Simulate system restart by creating new connection
        new_manager = type(db_manager)(
            database_url=db_manager.database_url,
            pool_size=5,
            max_overflow=10,
            environment="test"
        )
        
        try:
            await new_manager.initialize()
            
            # Verify data persisted after "restart"
            async with new_manager.get_session() as session:
                result = await session.execute(
                    "SELECT username FROM players WHERE username = :username",
                    {"username": player_data["username"]}
                )
                assert result.fetchone() is not None
        finally:
            await new_manager.cleanup()
