#!/usr/bin/env python3
import json
import unittest
import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from redis_manager import RedisManager
from game_board import GameBoard
from game_states import GameState
import time

class TestRedisConnection(unittest.TestCase):
    def setUp(self):
        """Initialize Redis manager and test data before each test"""
        try:
            self.redis = RedisManager()
            self.test_room = "test_room_123"
            self.test_players = ["Player 1", "Player 2", "Player 3", "Player 4"]
            
            # Verify Redis connection
            self.redis.redis.ping()
            
            # Clean all test data
            self._clean_test_data()
            
            # Create base game state
            self.game = GameBoard(self.test_players, self.test_room)
            
        except Exception as e:
            print(f"Setup failed: {str(e)}")
            raise
    
    def tearDown(self):
        """Clean up after each test"""
        self._clean_test_data()
        
    def _clean_test_data(self):
        """Helper to clean up test data from Redis"""
        try:
            # Clean room data
            self.redis.delete_room(self.test_room)
            
            # Clean all keys matching test room
            for key in self.redis.redis.scan_iter(f"*{self.test_room}*"):
                self.redis.redis.delete(key)
                
            # Clean test player sessions
            for key in self.redis.redis.scan_iter("session:test_player*"):
                self.redis.redis.delete(key)
                
        except Exception as e:
            print(f"[WARNING] Cleanup error: {str(e)}")
        
    def test_redis_connection(self):
        """Test basic Redis connectivity"""
        try:
            self.redis.redis.ping()
            connection_successful = True
        except Exception as e:
            connection_successful = False
            print(f"Redis connection failed: {str(e)}")
        
        self.assertTrue(connection_successful, "Redis connection failed")
    
    def test_room_creation(self):
        """Test room creation and validation"""
        # Create room with proper initialization
        success = self.redis.create_room(self.test_room)
        self.assertTrue(success, "Room creation failed")
        
        # Verify room exists
        self.assertTrue(
            self.redis.room_exists(self.test_room),
            "Room was not created successfully"
        )
        
        # Add test players
        for idx, player in enumerate(self.test_players, 1):
            self.redis.add_player_to_room(self.test_room, {
                'username': player,
                'player_id': f'test_id_{idx}',
                'player_number': idx,
                'joined_at': str(int(time.time()))
            })
        
        # Verify player count
        room_players = self.redis.get_room_players(self.test_room)
        self.assertEqual(
            len(room_players),
            4,
            f"Expected 4 players, got {len(room_players)}"
        )
    
    def test_team_persistence(self):
        """Test team assignment and persistence"""
        try:
            # Assign teams with proper game phase
            self.game.game_phase = GameState.TEAM_ASSIGNMENT.value
            team_result = self.game.assign_teams_and_hakem(self.redis_manager)
            
            # Save game state with all required fields
            game_state = {
                'teams': json.dumps(self.game.teams),
                'hakem': self.game.hakem,
                'phase': GameState.TEAM_ASSIGNMENT.value,
                'players': json.dumps(self.game.players),
                'created_at': str(int(time.time())),
                'room_code': self.test_room,
                'last_activity': str(int(time.time()))
            }
            success = self.redis.save_game_state(self.test_room, game_state)
            self.assertTrue(success, "Failed to save game state")
            
            # Retrieve and validate state
            saved_state = self.redis.get_game_state(self.test_room)
            self.assertIsNotNone(saved_state, "Failed to retrieve game state")
            
            # Validate team assignments
            self.assertEqual(
                saved_state['teams'],  # get_game_state already decodes JSON
                self.game.teams,
                "Team assignments don't match"
            )
            
            # Validate hakem
            self.assertEqual(
                saved_state['hakem'],
                self.game.hakem,
                "Hakem doesn't match"
            )
            
            # Validate game phase
            self.assertEqual(
                saved_state['phase'],
                GameState.TEAM_ASSIGNMENT.value,
                "Game phase doesn't match"
            )
        except Exception as e:
            self.fail(f"Test failed with error: {str(e)}")
    
    def test_game_state_updates(self):
        """Test game state updates and retrieval"""
        try:
            # Create room and initialize game state
            self.redis.create_room(self.test_room)
            
            # Set initial team assignment state
            self.game.game_phase = GameState.TEAM_ASSIGNMENT.value
            team_result = self.game.assign_teams_and_hakem(self.redis_manager)
            
            initial_state = {
                'phase': GameState.TEAM_ASSIGNMENT.value,
                'teams': json.dumps(self.game.teams),
                'hakem': self.game.hakem,
                'players': json.dumps(self.test_players),
                'created_at': str(int(time.time())),
                'last_activity': str(int(time.time()))
            }
            success = self.redis.save_game_state(self.test_room, initial_state)
            self.assertTrue(success, "Failed to save initial state")
            
            # Move to hokm selection phase
            self.game.game_phase = GameState.GAMEPLAY.value
            hokm_state = initial_state.copy()
            hokm_state.update({
                'phase': GameState.GAMEPLAY.value,
                'hokm': 'hearts',
                'last_activity': str(int(time.time()))
            })
            success = self.redis.save_game_state(self.test_room, hokm_state)
            self.assertTrue(success, "Failed to save hokm state")
            
            # Retrieve and verify state
            saved_state = self.redis.get_game_state(self.test_room)
            self.assertIsNotNone(saved_state, "Failed to retrieve state")
            
            # Verify state updates
            self.assertEqual(saved_state['hokm'], 'hearts',
                          "Hokm was not updated correctly")
            self.assertEqual(saved_state['phase'], GameState.GAMEPLAY.value,
                          "Game phase was not updated correctly")
            self.assertTrue('last_activity' in saved_state,
                         "Last activity timestamp missing")
            
        except Exception as e:
            self.fail(f"Test failed with error: {str(e)}")
    
    def test_session_management(self):
        """Test player session management"""
        try:
            player_id = 'test_player_123'
            current_time = int(time.time())
            
            session_data = {
                'username': 'Test Player',
                'room_code': self.test_room,
                'connected_at': str(current_time),
                'expires_at': str(current_time + 3600),
                'player_number': 1,
                'connection_status': 'active',
                'last_heartbeat': str(current_time)
            }
            
            # Save session
            success = self.redis.save_player_session(player_id, session_data)
            self.assertTrue(success, "Failed to save session")
            
            # Retrieve and validate session
            saved_session = self.redis.get_player_session(player_id)
            self.assertIsNotNone(saved_session, "Session was not saved")
            self.assertEqual(
                saved_session['username'],
                session_data['username'],
                "Session data doesn't match"
            )
            
            # Test session cleanup
            self.redis.cleanup_expired_sessions()
            active_session = self.redis.get_player_session(player_id)
            self.assertIsNotNone(
                active_session,
                "Valid session was incorrectly cleaned up"
            )
            
            # Test session expiration
            expired_session_data = session_data.copy()
            expired_session_data['expires_at'] = str(current_time - 3600)
            player_id_expired = 'test_player_expired'
            self.redis.save_player_session(player_id_expired, expired_session_data)
            
            # Cleanup should remove expired session
            self.redis.cleanup_expired_sessions()
            expired_session = self.redis.get_player_session(player_id_expired)
            self.assertEqual(expired_session, {}, "Expired session was not cleaned up")
            
        except Exception as e:
            self.fail(f"Test failed with error: {str(e)}")
    
    def test_state_validation(self):
        """Test game state validation"""
        try:
            # Test invalid state (missing required fields)
            invalid_state = {
                'phase': 'gameplay'  # Missing created_at and last_activity
            }
            is_valid, error = self.redis.validate_game_state(invalid_state)
            self.assertFalse(is_valid)
            self.assertIn("Missing required field", error)
            
            # Test invalid phase
            invalid_state = {
                'phase': 'invalid_phase',
                'created_at': str(int(time.time())),
                'last_activity': str(int(time.time()))
            }
            is_valid, error = self.redis.validate_game_state(invalid_state)
            self.assertFalse(is_valid)
            self.assertIn("Invalid game phase", error)
            
            # Test valid state
            valid_state = {
                'phase': 'gameplay',
                'created_at': str(int(time.time())),
                'last_activity': str(int(time.time())),
                'teams': json.dumps({'team1': ['p1', 'p2'], 'team2': ['p3', 'p4']})
            }
            is_valid, error = self.redis.validate_game_state(valid_state)
            self.assertTrue(is_valid)
            self.assertEqual(error, "")
            
        except Exception as e:
            self.fail(f"Test failed with error: {str(e)}")
            
    def test_atomic_operations(self):
        """Test atomic state updates"""
        try:
            # Create room
            self.redis.create_room(self.test_room)
            
            # Prepare test data
            game_state = {
                'phase': 'team_assignment',
                'teams': json.dumps({'team1': ['p1', 'p2'], 'team2': ['p3', 'p4']}),
                'created_at': str(int(time.time())),
                'last_activity': str(int(time.time()))
            }
            
            # Test atomic save
            success = self.redis.save_game_state(self.test_room, game_state)
            self.assertTrue(success, "Atomic save failed")
            
            # Verify state was saved correctly
            saved_state = self.redis.get_game_state(self.test_room)
            self.assertEqual(saved_state['phase'], 'team_assignment')
            self.assertIn('teams', saved_state)
            
        except Exception as e:
            self.fail(f"Test failed with error: {str(e)}")
            
    def test_performance_benchmarks(self):
        """Test Redis operation performance"""
        try:
            # Reset metrics
            self.redis.metrics = {
                'operations': 0,
                'errors': 0,
                'latency_sum': 0
            }
            
            # Perform a series of operations
            num_operations = 100
            for i in range(num_operations):
                room_code = f"bench_room_{i}"
                game_state = {
                    'phase': 'waiting_for_players',
                    'created_at': str(int(time.time())),
                    'last_activity': str(int(time.time()))
                }
                self.redis.save_game_state(room_code, game_state)
                # Cleanup
                self.redis.delete_room(room_code)
            
            # Get metrics
            metrics = self.redis.get_performance_metrics()
            
            # Verify metrics
            self.assertEqual(metrics['total_operations'], num_operations)
            self.assertLess(metrics['avg_latency'], 0.1,  # 100ms max average
                          "Average operation latency too high")
            self.assertLess(metrics['error_rate'], 0.01,  # 1% max error rate
                          "Error rate too high")
            
        except Exception as e:
            self.fail(f"Test failed with error: {str(e)}")

if __name__ == '__main__':
    # Run tests
    print("Running Redis connectivity and persistence tests...")
    try:
        unittest.main(verbosity=2)
    except Exception as e:
        print(f"Test execution failed: {str(e)}")
        import sys
        sys.exit(1)
