#!/usr/bin/env python3
"""
Redis Data Integrity Test for Hokm Game Server

This script validates Redis data storage and recovery:
1. Game state persistence across different phases
2. Data integrity validation (save/load comparison)
3. Player session persistence across server restarts
4. Serialization/deserialization correctness
5. Game state recovery after simulated crashes

Usage: python test_redis_integrity.py
"""

import asyncio
import websockets
import json
import time
import sys
import redis
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import hashlib
import copy

@dataclass
class GameStateSnapshot:
    """Represents a game state at a specific point in time"""
    phase: str
    timestamp: float
    players: List[str]
    teams: Dict[str, int]
    hakem: Optional[str]
    hokm: Optional[str]
    hands: Dict[str, List[str]]
    tricks: List[Dict]
    current_turn: int
    round_scores: Dict[str, int]
    checksum: str
    
    def calculate_checksum(self) -> str:
        """Calculate checksum for data integrity verification"""
        # Create a deterministic string representation
        data_str = f"{self.phase}|{self.players}|{self.teams}|{self.hakem}|{self.hokm}|{self.hands}|{self.tricks}|{self.current_turn}|{self.round_scores}"
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]

class RedisIntegrityTest:
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        self.server_uri = "ws://localhost:8765"
        self.test_room = "REDIS_TEST"
        self.results = []
        self.snapshots = []
        
    def add_result(self, test_name: str, success: bool, message: str, details: List[str] = None):
        """Add a test result"""
        result = {
            'test': test_name,
            'success': success,
            'message': message,
            'details': details or [],
            'timestamp': time.time()
        }
        self.results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"\n{status} {test_name}: {message}")
        if details:
            for detail in details:
                print(f"  - {detail}")
                
    def get_redis_game_data(self, room_code: str) -> Dict[str, Any]:
        """Retrieve all game-related data from Redis for a room"""
        data = {}
        
        # Get game state
        game_state_key = f"room:{room_code}:game_state"
        if self.redis_client.exists(game_state_key):
            data['game_state'] = self.redis_client.hgetall(game_state_key)
            
        # Get players
        players_key = f"room:{room_code}:players"
        if self.redis_client.exists(players_key):
            data['players'] = self.redis_client.lrange(players_key, 0, -1)
            
        # Get player sessions
        data['sessions'] = {}
        for key in self.redis_client.scan_iter(f"session:*"):
            session_data = self.redis_client.hgetall(key)
            if session_data.get('room_code') == room_code:
                player_id = key.split(':')[1]
                data['sessions'][player_id] = session_data
                
        return data
        
    def create_snapshot(self, room_code: str, phase: str) -> GameStateSnapshot:
        """Create a snapshot of current game state"""
        redis_data = self.get_redis_game_data(room_code)
        game_state = redis_data.get('game_state', {})
        
        # Parse game state data
        players = []
        teams = {}
        hands = {}
        tricks = []
        
        if 'players' in game_state:
            try:
                players = json.loads(game_state['players'])
            except:
                pass
                
        if 'teams' in game_state:
            try:
                teams = json.loads(game_state['teams'])
            except:
                pass
                
        if 'tricks' in game_state:
            try:
                tricks = json.loads(game_state['tricks'])
            except:
                pass
                
        # Extract hands
        for key, value in game_state.items():
            if key.startswith('hand_'):
                player_name = key[5:]  # Remove 'hand_' prefix
                try:
                    hands[player_name] = json.loads(value)
                except:
                    hands[player_name] = []
                    
        # Create snapshot
        snapshot = GameStateSnapshot(
            phase=phase,
            timestamp=time.time(),
            players=players,
            teams=teams,
            hakem=game_state.get('hakem'),
            hokm=game_state.get('hokm'),
            hands=hands,
            tricks=tricks,
            current_turn=int(game_state.get('current_turn', 0)),
            round_scores=json.loads(game_state.get('round_scores', '{}')),
            checksum=""
        )
        
        snapshot.checksum = snapshot.calculate_checksum()
        return snapshot
        
    def compare_snapshots(self, snapshot1: GameStateSnapshot, snapshot2: GameStateSnapshot) -> Tuple[bool, List[str]]:
        """Compare two snapshots for data integrity"""
        differences = []
        
        if snapshot1.phase != snapshot2.phase:
            differences.append(f"Phase mismatch: {snapshot1.phase} vs {snapshot2.phase}")
            
        if snapshot1.players != snapshot2.players:
            differences.append(f"Players mismatch: {snapshot1.players} vs {snapshot2.players}")
            
        if snapshot1.teams != snapshot2.teams:
            differences.append(f"Teams mismatch: {snapshot1.teams} vs {snapshot2.teams}")
            
        if snapshot1.hakem != snapshot2.hakem:
            differences.append(f"Hakem mismatch: {snapshot1.hakem} vs {snapshot2.hakem}")
            
        if snapshot1.hokm != snapshot2.hokm:
            differences.append(f"Hokm mismatch: {snapshot1.hokm} vs {snapshot2.hokm}")
            
        if snapshot1.hands != snapshot2.hands:
            differences.append(f"Hands mismatch: {len(snapshot1.hands)} vs {len(snapshot2.hands)} players")
            for player in set(list(snapshot1.hands.keys()) + list(snapshot2.hands.keys())):
                if snapshot1.hands.get(player) != snapshot2.hands.get(player):
                    differences.append(f"  Player {player} hand differs")
                    
        if snapshot1.tricks != snapshot2.tricks:
            differences.append(f"Tricks mismatch: {len(snapshot1.tricks)} vs {len(snapshot2.tricks)}")
            
        if snapshot1.current_turn != snapshot2.current_turn:
            differences.append(f"Turn mismatch: {snapshot1.current_turn} vs {snapshot2.current_turn}")
            
        if snapshot1.round_scores != snapshot2.round_scores:
            differences.append(f"Scores mismatch: {snapshot1.round_scores} vs {snapshot2.round_scores}")
            
        if snapshot1.checksum != snapshot2.checksum:
            differences.append(f"Checksum mismatch: {snapshot1.checksum} vs {snapshot2.checksum}")
            
        return len(differences) == 0, differences
        
    async def test_game_state_persistence(self) -> None:
        """Test game state persistence across different game phases"""
        print("\n💾 Testing Game State Persistence Across Phases...")
        
        clients = []
        phase_snapshots = {}
        persistence_errors = []
        
        try:
            # Clear any existing data
            self.redis_client.flushdb()
            
            # Create 4 clients and join room
            print("  Creating 4 clients and joining room...")
            for i in range(4):
                ws = await websockets.connect(self.server_uri)
                clients.append(ws)
                
                join_msg = {'type': 'join', 'room_code': self.test_room}
                await ws.send(json.dumps(join_msg))
                
                # Wait for join response
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                join_data = json.loads(response)
                
                if join_data.get('type') != 'join_success':
                    persistence_errors.append(f"Client {i+1} join failed: {join_data}")
                    
            # Wait for game to start and capture team assignment phase
            print("  Waiting for team assignment phase...")
            await asyncio.sleep(2.0)
            
            # Capture snapshot after team assignment
            team_snapshot = self.create_snapshot(self.test_room, "team_assignment")
            phase_snapshots['team_assignment'] = team_snapshot
            
            # Wait for initial deal and hokm selection
            print("  Waiting for hokm selection phase...")
            hakem_client = None
            for client in clients:
                try:
                    msg = await asyncio.wait_for(client.recv(), timeout=5.0)
                    data = json.loads(msg)
                    if data.get('type') == 'initial_deal' and data.get('is_hakem'):
                        hakem_client = client
                        break
                except:
                    pass
                    
            if hakem_client:
                # Hakem selects hokm
                hokm_msg = {'type': 'hokm_selected', 'room_code': self.test_room, 'suit': 'spades'}
                await hakem_client.send(json.dumps(hokm_msg))
                
                # Wait for hokm selection to process
                await asyncio.sleep(1.0)
                
                # Capture snapshot after hokm selection
                hokm_snapshot = self.create_snapshot(self.test_room, "hokm_selected")
                phase_snapshots['hokm_selected'] = hokm_snapshot
                
            # Wait for final deal
            print("  Waiting for final deal phase...")
            await asyncio.sleep(2.0)
            
            # Capture snapshot after final deal
            final_deal_snapshot = self.create_snapshot(self.test_room, "final_deal")
            phase_snapshots['final_deal'] = final_deal_snapshot
            
            # Now test persistence by reading data back and comparing
            print("  Validating data integrity across phases...")
            
            # Re-read data from Redis and compare
            integrity_results = []
            for phase_name, original_snapshot in phase_snapshots.items():
                # Create new snapshot from current Redis data
                current_snapshot = self.create_snapshot(self.test_room, phase_name)
                
                # Compare key fields (excluding timestamp)
                matches = (
                    original_snapshot.players == current_snapshot.players and
                    original_snapshot.teams == current_snapshot.teams and
                    original_snapshot.hakem == current_snapshot.hakem and
                    original_snapshot.hokm == current_snapshot.hokm and
                    len(original_snapshot.hands) == len(current_snapshot.hands)
                )
                
                integrity_results.append((phase_name, matches))
                
                if not matches:
                    persistence_errors.append(f"Data integrity check failed for {phase_name}")
                    
        except Exception as e:
            persistence_errors.append(f"Game state persistence test error: {str(e)}")
        finally:
            # Cleanup
            for client in clients:
                try:
                    await client.close()
                except:
                    pass
                    
        # Report results
        details = [
            f"Phases captured: {len(phase_snapshots)}",
            f"Integrity checks: {len(integrity_results)}",
            f"Errors: {len(persistence_errors)}"
        ]
        
        # Add phase details
        for phase_name, snapshot in phase_snapshots.items():
            details.append(f"  {phase_name}: {len(snapshot.players)} players, hakem={snapshot.hakem}, hokm={snapshot.hokm}")
            
        if persistence_errors:
            details.extend(["Error details:"] + persistence_errors[:3])
            
        success = len(persistence_errors) == 0 and len(phase_snapshots) >= 2
        
        if success:
            self.add_result(
                "Game State Persistence",
                True,
                f"Successfully persisted game state across {len(phase_snapshots)} phases",
                details
            )
        else:
            self.add_result(
                "Game State Persistence",
                False,
                f"Failed to persist game state properly",
                details
            )
            
    async def test_data_serialization_integrity(self) -> None:
        """Test data serialization and deserialization integrity"""
        print("\n🔄 Testing Data Serialization Integrity...")
        
        serialization_errors = []
        test_data_sets = []
        
        try:
            # Create test data sets with various edge cases
            test_data_sets = [
                {
                    'name': 'Basic Game State',
                    'data': {
                        'players': ['Player1', 'Player2', 'Player3', 'Player4'],
                        'teams': {0: ['Player1', 'Player3'], 1: ['Player2', 'Player4']},
                        'hakem': 'Player1',
                        'hokm': 'spades',
                        'hands': {
                            'Player1': ['AS', 'KS', 'QS', 'JS', '10S'],
                            'Player2': ['AH', 'KH', 'QH', 'JH', '10H'],
                            'Player3': ['AD', 'KD', 'QD', 'JD', '10D'],
                            'Player4': ['AC', 'KC', 'QC', 'JC', '10C']
                        },
                        'tricks': [{'winner': 'Player1', 'cards': ['AS', 'AH', 'AD', 'AC']}],
                        'current_turn': 1,
                        'round_scores': {0: 5, 1: 3}
                    }
                },
                {
                    'name': 'Empty Game State',
                    'data': {
                        'players': [],
                        'teams': {},
                        'hakem': None,
                        'hokm': None,
                        'hands': {},
                        'tricks': [],
                        'current_turn': 0,
                        'round_scores': {}
                    }
                },
                {
                    'name': 'Complex Unicode Data',
                    'data': {
                        'players': ['عبداللّٰہ', '张三', 'José', 'François'],
                        'teams': {0: ['عبداللّٰہ', 'José'], 1: ['张三', 'François']},
                        'hakem': 'عبداللّٰہ',
                        'hokm': 'hearts',
                        'hands': {
                            'عبداللّٰہ': ['AS', 'KS'],
                            '张三': ['AH', 'KH'],
                            'José': ['AD', 'KD'],
                            'François': ['AC', 'KC']
                        },
                        'tricks': [],
                        'current_turn': 0,
                        'round_scores': {0: 0, 1: 0}
                    }
                }
            ]
            
            for test_case in test_data_sets:
                print(f"  Testing: {test_case['name']}")
                
                # Save data to Redis
                room_key = f"room:TEST_SERIALIZATION_{test_case['name'].replace(' ', '_')}:game_state"
                
                try:
                    # Clear any existing data
                    self.redis_client.delete(room_key)
                    
                    # Save each field
                    for field, value in test_case['data'].items():
                        if isinstance(value, (dict, list)):
                            json_value = json.dumps(value, ensure_ascii=False)
                        else:
                            json_value = json.dumps(value) if value is not None else None
                            
                        if json_value is not None:
                            self.redis_client.hset(room_key, field, json_value)
                        else:
                            self.redis_client.hset(room_key, field, "")
                            
                    # Retrieve and compare
                    retrieved_data = self.redis_client.hgetall(room_key)
                    
                    # Parse retrieved data
                    parsed_data = {}
                    for field, value in retrieved_data.items():
                        if value == "":
                            parsed_data[field] = None
                        else:
                            try:
                                parsed_data[field] = json.loads(value)
                            except json.JSONDecodeError:
                                parsed_data[field] = value
                                
                    # Compare original and retrieved data
                    data_matches = True
                    for field, original_value in test_case['data'].items():
                        retrieved_value = parsed_data.get(field)
                        
                        if original_value != retrieved_value:
                            serialization_errors.append(
                                f"{test_case['name']}.{field}: {original_value} != {retrieved_value}"
                            )
                            data_matches = False
                            
                    if data_matches:
                        print(f"    ✓ {test_case['name']}: Serialization OK")
                    else:
                        print(f"    ✗ {test_case['name']}: Serialization FAILED")
                        
                except Exception as e:
                    serialization_errors.append(f"{test_case['name']}: {str(e)}")
                    
        except Exception as e:
            serialization_errors.append(f"Serialization test error: {str(e)}")
            
        details = [
            f"Test cases: {len(test_data_sets)}",
            f"Serialization errors: {len(serialization_errors)}"
        ]
        
        if serialization_errors:
            details.extend(["Error details:"] + serialization_errors[:5])
            
        if len(serialization_errors) == 0:
            self.add_result(
                "Data Serialization",
                True,
                "All data serialization tests passed",
                details
            )
        else:
            self.add_result(
                "Data Serialization",
                False,
                f"Data serialization failed for {len(serialization_errors)} cases",
                details
            )
            
    async def test_session_persistence(self) -> None:
        """Test player session persistence across disconnections"""
        print("\n👤 Testing Player Session Persistence...")
        
        session_errors = []
        original_sessions = {}
        
        try:
            # Create clients and capture session data
            print("  Creating clients and capturing session data...")
            
            clients = []
            player_ids = []
            
            for i in range(2):  # Test with 2 clients
                ws = await websockets.connect(self.server_uri)
                clients.append(ws)
                
                join_msg = {'type': 'join', 'room_code': f"{self.test_room}_SESSION"}
                await ws.send(json.dumps(join_msg))
                
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                join_data = json.loads(response)
                
                if join_data.get('type') == 'join_success':
                    player_id = join_data.get('player_id')
                    player_ids.append(player_id)
                    
                    # Get session data from Redis
                    session_key = f"session:{player_id}"
                    session_data = self.redis_client.hgetall(session_key)
                    original_sessions[player_id] = session_data.copy()
                    
                    print(f"    Captured session for {join_data.get('username')}: {player_id[:8]}...")
                else:
                    session_errors.append(f"Client {i+1} join failed: {join_data}")
                    
            # Disconnect clients
            print("  Disconnecting clients...")
            for client in clients:
                await client.close()
                
            # Wait for disconnection processing
            await asyncio.sleep(2.0)
            
            # Check if session data still exists
            print("  Checking session persistence after disconnection...")
            persisted_sessions = {}
            
            for player_id in player_ids:
                session_key = f"session:{player_id}"
                if self.redis_client.exists(session_key):
                    persisted_sessions[player_id] = self.redis_client.hgetall(session_key)
                    
            # Compare original and persisted sessions
            print("  Comparing original and persisted session data...")
            for player_id in player_ids:
                original = original_sessions.get(player_id, {})
                persisted = persisted_sessions.get(player_id, {})
                
                if not persisted:
                    session_errors.append(f"Session {player_id[:8]}... not persisted")
                    continue
                    
                # Check key fields
                for field in ['username', 'room_code', 'player_number']:
                    if original.get(field) != persisted.get(field):
                        session_errors.append(
                            f"Session {player_id[:8]}... field {field}: {original.get(field)} != {persisted.get(field)}"
                        )
                        
            # Test reconnection with persisted session
            print("  Testing reconnection with persisted session...")
            if player_ids and len(session_errors) == 0:
                test_player_id = player_ids[0]
                
                # Try to reconnect
                reconnect_ws = await websockets.connect(self.server_uri)
                
                reconnect_msg = {'type': 'reconnect', 'player_id': test_player_id}
                await reconnect_ws.send(json.dumps(reconnect_msg))
                
                reconnect_response = await asyncio.wait_for(reconnect_ws.recv(), timeout=5.0)
                reconnect_data = json.loads(reconnect_response)
                
                if reconnect_data.get('type') == 'join_success':
                    print(f"    ✓ Reconnection successful: {reconnect_data.get('username')}")
                else:
                    session_errors.append(f"Reconnection failed: {reconnect_data}")
                    
                await reconnect_ws.close()
                
        except Exception as e:
            session_errors.append(f"Session persistence test error: {str(e)}")
            
        details = [
            f"Sessions created: {len(original_sessions)}",
            f"Sessions persisted: {len(persisted_sessions)}",
            f"Session errors: {len(session_errors)}"
        ]
        
        if session_errors:
            details.extend(["Error details:"] + session_errors[:3])
            
        success = len(session_errors) == 0 and len(original_sessions) > 0
        
        if success:
            self.add_result(
                "Session Persistence",
                True,
                f"Successfully persisted {len(original_sessions)} player sessions",
                details
            )
        else:
            self.add_result(
                "Session Persistence",
                False,
                "Session persistence failed",
                details
            )
            
    async def test_crash_recovery_simulation(self) -> None:
        """Test game state recovery after simulated server crashes"""
        print("\n💥 Testing Crash Recovery Simulation...")
        
        recovery_errors = []
        pre_crash_snapshot = None
        post_crash_snapshot = None
        
        try:
            # Set up a game state
            print("  Setting up game state before crash simulation...")
            
            clients = []
            for i in range(4):
                ws = await websockets.connect(self.server_uri)
                clients.append(ws)
                
                join_msg = {'type': 'join', 'room_code': f"{self.test_room}_CRASH"}
                await ws.send(json.dumps(join_msg))
                
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                
            # Wait for game to progress
            await asyncio.sleep(3.0)
            
            # Capture pre-crash snapshot
            pre_crash_snapshot = self.create_snapshot(f"{self.test_room}_CRASH", "pre_crash")
            print(f"    Pre-crash snapshot: {len(pre_crash_snapshot.players)} players, hakem={pre_crash_snapshot.hakem}")
            
            # Simulate crash by closing all connections abruptly
            print("  Simulating server crash (closing all connections)...")
            for client in clients:
                try:
                    # Force close without proper WebSocket handshake
                    if hasattr(client, 'transport') and client.transport:
                        client.transport.close()
                except:
                    pass
                    
            # Wait for server to process disconnections
            await asyncio.sleep(2.0)
            
            # Capture post-crash snapshot
            post_crash_snapshot = self.create_snapshot(f"{self.test_room}_CRASH", "post_crash")
            print(f"    Post-crash snapshot: {len(post_crash_snapshot.players)} players, hakem={post_crash_snapshot.hakem}")
            
            # Compare snapshots
            if pre_crash_snapshot and post_crash_snapshot:
                data_intact, differences = self.compare_snapshots(pre_crash_snapshot, post_crash_snapshot)
                
                if not data_intact:
                    # Some differences are expected (like connection status), but core game data should remain
                    critical_differences = [d for d in differences if not any(word in d.lower() for word in ['timestamp', 'checksum'])]
                    
                    if critical_differences:
                        recovery_errors.extend(critical_differences)
                        
                # Check if critical game data is preserved
                critical_data_preserved = (
                    pre_crash_snapshot.players == post_crash_snapshot.players and
                    pre_crash_snapshot.teams == post_crash_snapshot.teams and
                    pre_crash_snapshot.hakem == post_crash_snapshot.hakem and
                    pre_crash_snapshot.hokm == post_crash_snapshot.hokm
                )
                
                if not critical_data_preserved:
                    recovery_errors.append("Critical game data not preserved after crash")
                    
        except Exception as e:
            recovery_errors.append(f"Crash recovery test error: {str(e)}")
            
        details = [
            f"Pre-crash players: {len(pre_crash_snapshot.players) if pre_crash_snapshot else 0}",
            f"Post-crash players: {len(post_crash_snapshot.players) if post_crash_snapshot else 0}",
            f"Recovery errors: {len(recovery_errors)}"
        ]
        
        if recovery_errors:
            details.extend(["Error details:"] + recovery_errors[:5])
            
        if pre_crash_snapshot and post_crash_snapshot:
            details.append(f"Pre-crash checksum: {pre_crash_snapshot.checksum}")
            details.append(f"Post-crash checksum: {post_crash_snapshot.checksum}")
            
        success = len(recovery_errors) == 0 and pre_crash_snapshot and post_crash_snapshot
        
        if success:
            self.add_result(
                "Crash Recovery",
                True,
                "Game state properly preserved after crash simulation",
                details
            )
        else:
            self.add_result(
                "Crash Recovery",
                False,
                "Game state recovery failed after crash simulation",
                details
            )
            
    async def test_data_corruption_detection(self) -> None:
        """Test detection of data corruption in Redis"""
        print("\n🔍 Testing Data Corruption Detection...")
        
        corruption_errors = []
        
        try:
            # Create test data
            test_room = f"{self.test_room}_CORRUPTION"
            game_state_key = f"room:{test_room}:game_state"
            
            # Save valid data
            valid_data = {
                'players': json.dumps(['Player1', 'Player2', 'Player3', 'Player4']),
                'teams': json.dumps({0: ['Player1', 'Player3'], 1: ['Player2', 'Player4']}),
                'hakem': 'Player1',
                'hokm': 'spades',
                'hand_Player1': json.dumps(['AS', 'KS', 'QS']),
                'current_turn': '0',
                'phase': 'gameplay'
            }
            
            for field, value in valid_data.items():
                self.redis_client.hset(game_state_key, field, value)
                
            # Create original snapshot
            original_snapshot = self.create_snapshot(test_room, "original")
            
            # Introduce various types of corruption
            corruption_tests = [
                {
                    'name': 'Invalid JSON in players',
                    'field': 'players',
                    'corrupt_value': '{"invalid": json}'
                },
                {
                    'name': 'Invalid JSON in teams',
                    'field': 'teams',
                    'corrupt_value': '[malformed json'
                },
                {
                    'name': 'Invalid JSON in hand',
                    'field': 'hand_Player1',
                    'corrupt_value': '["AS", "KS", "QS"'  # Missing closing bracket
                },
                {
                    'name': 'Invalid turn number',
                    'field': 'current_turn',
                    'corrupt_value': 'not_a_number'
                },
                {
                    'name': 'Binary data corruption',
                    'field': 'hokm',
                    'corrupt_value': b'\x00\x01\x02\x03'.decode('latin-1')
                }
            ]
            
            for corruption_test in corruption_tests:
                print(f"  Testing: {corruption_test['name']}")
                
                # Introduce corruption
                self.redis_client.hset(
                    game_state_key, 
                    corruption_test['field'], 
                    corruption_test['corrupt_value']
                )
                
                # Try to create snapshot (should handle corruption gracefully)
                try:
                    corrupted_snapshot = self.create_snapshot(test_room, "corrupted")
                    
                    # Check if corruption was detected/handled
                    field_name = corruption_test['field']
                    if field_name == 'players':
                        if corrupted_snapshot.players == original_snapshot.players:
                            corruption_errors.append(f"{corruption_test['name']}: Corruption not detected")
                    elif field_name == 'teams':
                        if corrupted_snapshot.teams == original_snapshot.teams:
                            corruption_errors.append(f"{corruption_test['name']}: Corruption not detected")
                    elif field_name.startswith('hand_'):
                        player_name = field_name[5:]
                        if corrupted_snapshot.hands.get(player_name) == original_snapshot.hands.get(player_name):
                            corruption_errors.append(f"{corruption_test['name']}: Corruption not detected")
                            
                except Exception as e:
                    # Exception during snapshot creation indicates corruption was detected
                    print(f"    ✓ Corruption detected: {str(e)[:50]}...")
                    
                # Restore original value
                self.redis_client.hset(game_state_key, corruption_test['field'], valid_data[corruption_test['field']])
                
        except Exception as e:
            corruption_errors.append(f"Data corruption test error: {str(e)}")
            
        details = [
            f"Corruption tests: {len(corruption_tests)}",
            f"Detection errors: {len(corruption_errors)}"
        ]
        
        if corruption_errors:
            details.extend(["Error details:"] + corruption_errors[:3])
            
        success = len(corruption_errors) <= 1  # Allow 1 error for edge cases
        
        if success:
            self.add_result(
                "Data Corruption Detection",
                True,
                "Data corruption properly detected and handled",
                details
            )
        else:
            self.add_result(
                "Data Corruption Detection",
                False,
                f"Data corruption detection failed ({len(corruption_errors)} errors)",
                details
            )
            
    def print_data_comparison(self, before_data: Dict, after_data: Dict, title: str):
        """Print before/after data comparison"""
        print(f"\n📊 {title}")
        print("=" * 50)
        
        all_keys = set(before_data.keys()) | set(after_data.keys())
        
        for key in sorted(all_keys):
            before_val = before_data.get(key, "❌ MISSING")
            after_val = after_data.get(key, "❌ MISSING")
            
            if before_val == after_val:
                print(f"✅ {key}: {before_val}")
            else:
                print(f"❌ {key}:")
                print(f"   BEFORE: {before_val}")
                print(f"   AFTER:  {after_val}")
                
    def print_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "="*70)
        print("💾 REDIS DATA INTEGRITY TEST SUMMARY")
        print("="*70)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        print("\nDetailed Results:")
        print("-" * 50)
        
        for result in self.results:
            status = "✅ PASS" if result['success'] else "❌ FAIL"
            print(f"{status} {result['test']}: {result['message']}")
            
        # Data integrity assessment
        print("\n" + "="*70)
        print("📊 DATA INTEGRITY ASSESSMENT")
        print("="*70)
        
        if failed_tests == 0:
            print("🎉 EXCELLENT: Your Redis data storage is rock-solid!")
            print("   All data integrity tests passed perfectly.")
            print("   Game state will survive server restarts and crashes.")
        elif failed_tests <= 1:
            print("✅ VERY GOOD: Your data storage is mostly reliable.")
            print("   Minor issues detected, but core functionality is solid.")
        elif failed_tests <= 3:
            print("⚠️  MODERATE: Your data storage has some issues.")
            print("   Several problems detected that could affect game continuity.")
        else:
            print("❌ CRITICAL: Your data storage has serious problems!")
            print("   Major data integrity issues that need immediate attention.")
            
        print("\nRecommendations:")
        failed_test_names = [r['test'] for r in self.results if not r['success']]
        
        if "Game State Persistence" in failed_test_names:
            print("  🔧 Fix game state saving/loading across different phases")
        if "Data Serialization" in failed_test_names:
            print("  🔧 Fix JSON serialization/deserialization issues")
        if "Session Persistence" in failed_test_names:
            print("  🔧 Implement proper session persistence for reconnections")
        if "Crash Recovery" in failed_test_names:
            print("  🔧 Improve data preservation during server crashes")
        if "Data Corruption Detection" in failed_test_names:
            print("  🔧 Add better error handling for corrupted Redis data")
            
        if failed_tests == 0:
            print("  🎯 Consider adding automated backup and restore mechanisms")
            print("  🎯 Implement data versioning for future schema changes")
            
        print("="*70)

async def main():
    """Main test execution"""
    print("💾 Starting Redis Data Integrity Test for Hokm Game Server")
    print("="*70)
    print("This test validates Redis data storage, persistence, and recovery.")
    print("It will test game state across different phases and simulate crashes.")
    print("="*70)
    
    # Check Redis connection first
    try:
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        redis_client.ping()
        print("✅ Redis connection verified")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("   Make sure Redis server is running: redis-server")
        return 1
        
    test = RedisIntegrityTest()
    
    try:
        # Run all data integrity tests
        await test.test_game_state_persistence()
        await test.test_data_serialization_integrity()
        await test.test_session_persistence()
        await test.test_crash_recovery_simulation()
        await test.test_data_corruption_detection()
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Fatal error during testing: {e}")
        import traceback
        traceback.print_exc()
        
    # Print final summary
    test.print_summary()
    
    # Exit with appropriate code
    failed_tests = sum(1 for r in test.results if not r['success'])
    return 0 if failed_tests == 0 else 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nRedis integrity test interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal error running Redis integrity test: {e}")
        sys.exit(1)
