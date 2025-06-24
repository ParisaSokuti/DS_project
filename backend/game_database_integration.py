"""
Database Integration for Hokm Game Server
Integrates PostgreSQL database operations with the existing game server architecture
"""
import asyncio
import logging
import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime

from .database_manager import DatabaseManager
from .game_states import GameState


class GameDatabaseIntegration:
    """
    Integrates database operations with the existing game server,
    providing persistent storage for game states, player data, and sessions.
    """
    
    def __init__(self, database_manager: DatabaseManager):
        """
        Initialize the database integration.
        
        Args:
            database_manager: DatabaseManager instance
        """
        self.db = database_manager
        self.logger = logging.getLogger(__name__)
        
        # Cache for frequently accessed data
        self._player_cache = {}
        self._game_cache = {}
        
    async def initialize(self):
        """Initialize the database integration."""
        try:
            await self.db.initialize()
            self.logger.info("Database integration initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize database integration: {e}")
            raise
    
    async def close(self):
        """Close the database integration."""
        try:
            await self.db.close()
            self.logger.info("Database integration closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing database integration: {e}")
    
    # Player management
    
    async def create_or_get_player(self, username: str, connection_info: Dict) -> Dict:
        """
        Create a new player or get existing player data.
        
        Args:
            username: Player username
            connection_info: Connection metadata (IP, user agent, etc.)
            
        Returns:
            Player data dictionary
        """
        try:
            # Check cache first
            if username in self._player_cache:
                player = self._player_cache[username]
                # Update last seen
                await self.db.execute_command(
                    "UPDATE players SET last_seen = NOW() WHERE id = $1",
                    player['id']
                )
                return player
            
            # Try to get existing player
            player = await self.db.get_player(username=username)
            
            if not player:
                # Create new player
                player = await self.db.create_player(username=username)
                if player:
                    self.logger.info(f"Created new player: {username}")
                    
                    # Log player creation
                    await self.db.log_user_action(
                        player['id'],
                        'player_created',
                        {'username': username},
                        connection_info.get('ip_address'),
                        connection_info.get('user_agent')
                    )
                else:
                    raise RuntimeError(f"Failed to create player: {username}")
            else:
                # Update last seen for existing player
                await self.db.execute_command(
                    "UPDATE players SET last_seen = NOW() WHERE id = $1",
                    player['id']
                )
            
            # Cache player data
            self._player_cache[username] = player
            
            return player
            
        except Exception as e:
            self.logger.error(f"Error creating/getting player {username}: {e}")
            raise
    
    async def get_player_stats(self, player_id: str) -> Dict:
        """Get player statistics."""
        try:
            query = """
                SELECT 
                    p.*,
                    CASE 
                        WHEN p.total_games > 0 THEN ROUND((p.wins::DECIMAL / p.total_games) * 100, 2)
                        ELSE 0 
                    END as win_percentage,
                    COUNT(DISTINCT gs.id) FILTER (WHERE gs.created_at > NOW() - INTERVAL '7 days') as games_last_week
                FROM players p
                LEFT JOIN game_participants gp ON p.id = gp.player_id
                LEFT JOIN game_sessions gs ON gp.game_session_id = gs.id
                WHERE p.id = $1
                GROUP BY p.id
            """
            result = await self.db.execute_query(query, player_id, use_replica=True)
            return result[0] if result else None
            
        except Exception as e:
            self.logger.error(f"Error getting player stats: {e}")
            return None
    
    # Game session management
    
    async def create_game_session(self, room_id: str, session_key: str, 
                                max_players: int = 4, creator_id: Optional[str] = None) -> Dict:
        """
        Create a new game session with database persistence.
        
        Args:
            room_id: Room identifier
            session_key: Session key for reconnection
            max_players: Maximum number of players
            creator_id: ID of the player who created the session
            
        Returns:
            Game session data
        """
        try:
            # Create game session in database
            session = await self.db.create_game_session(room_id, session_key, max_players)
            
            if not session:
                raise RuntimeError(f"Failed to create game session: {room_id}")
            
            # Initialize game state
            initial_game_state = {
                'phase': 'waiting',
                'current_round': 1,
                'current_trick': 1,
                'current_player': 0,
                'trump_suit': None,
                'hakem_id': None,
                'teams': {1: [], 2: []},
                'scores': {1: 0, 2: 0},
                'round_scores': [],
                'created_at': datetime.utcnow().isoformat(),
                'creator_id': creator_id
            }
            
            # Update game state in database
            await self.db.update_game_state(
                session['id'],
                initial_game_state,
                {},  # Empty player hands initially
                {1: 0, 2: 0}  # Initial scores
            )
            
            # Cache session data
            self._game_cache[room_id] = {
                **session,
                'game_state': initial_game_state
            }
            
            self.logger.info(f"Created game session: {room_id}")
            
            return session
            
        except Exception as e:
            self.logger.error(f"Error creating game session {room_id}: {e}")
            raise
    
    async def get_or_create_game_session(self, room_id: str, session_key: str,
                                       max_players: int = 4, creator_id: Optional[str] = None) -> Dict:
        """Get existing game session or create new one."""
        try:
            # Check cache first
            if room_id in self._game_cache:
                return self._game_cache[room_id]
            
            # Try to get existing session
            session = await self.db.get_game_session(room_id=room_id)
            
            if session:
                # Load game state
                game_state = session.get('game_state', {})
                session['game_state'] = game_state
                
                # Cache session data
                self._game_cache[room_id] = session
                
                return session
            else:
                # Create new session
                return await self.create_game_session(room_id, session_key, max_players, creator_id)
                
        except Exception as e:
            self.logger.error(f"Error getting/creating game session {room_id}: {e}")
            raise
    
    async def add_player_to_session(self, room_id: str, player_id: str, 
                                  position: int, team: int, connection_id: str) -> bool:
        """Add a player to a game session."""
        try:
            # Get session data
            session = await self.db.get_game_session(room_id=room_id)
            if not session:
                self.logger.error(f"Game session not found: {room_id}")
                return False
            
            # Add player to database
            success = await self.db.add_player_to_game(
                session['id'], player_id, position, team
            )
            
            if success:
                # Create WebSocket connection record
                await self.db.execute_command(
                    """
                        INSERT INTO websocket_connections 
                        (player_id, game_session_id, connection_id, connected_at)
                        VALUES ($1, $2, $3, NOW())
                        ON CONFLICT (connection_id) DO UPDATE SET
                            last_ping = NOW(),
                            is_active = true,
                            disconnected_at = NULL
                    """,
                    player_id, session['id'], connection_id
                )
                
                # Update cache
                if room_id in self._game_cache:
                    del self._game_cache[room_id]  # Force refresh
                
                self.logger.info(f"Added player {player_id} to session {room_id}")
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error adding player to session: {e}")
            return False
    
    async def update_game_state_from_game_board(self, room_id: str, game_board) -> bool:
        """
        Update database game state from GameBoard instance.
        
        Args:
            room_id: Room identifier
            game_board: GameBoard instance
            
        Returns:
            True if update was successful
        """
        try:
            # Get session from database
            session = await self.db.get_game_session(room_id=room_id)
            if not session:
                self.logger.error(f"Game session not found: {room_id}")
                return False
            
            # Convert GameBoard state to database format
            game_state = {
                'phase': game_board.phase,
                'current_round': game_board.current_round,
                'current_trick': getattr(game_board, 'current_trick', 1),
                'current_player': game_board.current_player,
                'trump_suit': game_board.trump_suit,
                'hakem_id': str(game_board.hakem_id) if game_board.hakem_id else None,
                'teams': {
                    str(team): [str(pid) for pid in players] 
                    for team, players in game_board.teams.items()
                },
                'scores': {str(k): v for k, v in game_board.scores.items()},
                'round_scores': game_board.round_scores,
                'played_cards': getattr(game_board, 'played_cards', []),
                'current_trick_cards': getattr(game_board, 'current_trick_cards', []),
                'last_updated': datetime.utcnow().isoformat()
            }
            
            # Convert player hands
            player_hands = {}
            if hasattr(game_board, 'player_hands'):
                for player_id, hand in game_board.player_hands.items():
                    player_hands[str(player_id)] = [
                        {'suit': card.suit, 'rank': card.rank} 
                        for card in hand
                    ]
            
            # Update database
            success = await self.db.update_game_state(
                session['id'],
                game_state,
                player_hands,
                game_board.scores
            )
            
            if success:
                # Update cache
                if room_id in self._game_cache:
                    self._game_cache[room_id]['game_state'] = game_state
                
                self.logger.debug(f"Updated game state for session {room_id}")
                
            return success
            
        except Exception as e:
            self.logger.error(f"Error updating game state from GameBoard: {e}")
            return False
    
    async def record_player_move(self, room_id: str, player_id: str, 
                               move_type: str, move_data: Dict,
                               round_number: int, trick_number: Optional[int] = None) -> bool:
        """Record a player move in the database."""
        try:
            # Get session
            session = await self.db.get_game_session(room_id=room_id)
            if not session:
                return False
            
            # Record move
            move_id = await self.db.record_game_move(
                session['id'],
                player_id,
                move_type,
                move_data,
                round_number,
                trick_number
            )
            
            if move_id:
                self.logger.debug(f"Recorded move {move_type} for player {player_id} in {room_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error recording player move: {e}")
            return False
    
    async def handle_player_disconnect(self, player_id: str, connection_id: str) -> List[str]:
        """
        Handle player disconnection and return affected room IDs.
        
        Args:
            player_id: Player ID
            connection_id: WebSocket connection ID
            
        Returns:
            List of affected room IDs
        """
        try:
            # Update connection status
            await self.db.execute_command(
                """
                    UPDATE websocket_connections 
                    SET is_active = false, disconnected_at = NOW()
                    WHERE connection_id = $1
                """,
                connection_id
            )
            
            # Update player participation status
            affected_sessions = await self.db.execute_query(
                """
                    UPDATE game_participants 
                    SET is_connected = false, left_at = NOW()
                    WHERE player_id = $1 AND is_connected = true
                    RETURNING game_session_id
                """,
                player_id
            )
            
            if affected_sessions:
                # Get room IDs for affected sessions
                session_ids = [str(session['game_session_id']) for session in affected_sessions]
                room_ids = []
                
                for session_id in session_ids:
                    session = await self.db.get_game_session(session_id=session_id)
                    if session:
                        room_ids.append(session['room_id'])
                        
                        # Clear cache
                        if session['room_id'] in self._game_cache:
                            del self._game_cache[session['room_id']]
                
                self.logger.info(f"Player {player_id} disconnected from {len(room_ids)} sessions")
                return room_ids
            
            return []
            
        except Exception as e:
            self.logger.error(f"Error handling player disconnect: {e}")
            return []
    
    async def handle_player_reconnection(self, player_id: str, room_id: str, 
                                       connection_id: str) -> Optional[Dict]:
        """
        Handle player reconnection and return game state.
        
        Args:
            player_id: Player ID
            room_id: Room ID
            connection_id: New WebSocket connection ID
            
        Returns:
            Game state for reconnection or None if failed
        """
        try:
            # Get session
            session = await self.db.get_game_session(room_id=room_id)
            if not session:
                return None
            
            # Handle reconnection using stored function
            reconnection_data = await self.db.handle_player_reconnection(
                player_id, session['id'], connection_id
            )
            
            if reconnection_data:
                # Clear cache to force refresh
                if room_id in self._game_cache:
                    del self._game_cache[room_id]
                
                self.logger.info(f"Player {player_id} reconnected to {room_id}")
                
                return reconnection_data
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error handling player reconnection: {e}")
            return None
    
    async def complete_game_session(self, room_id: str, final_scores: Dict, 
                                  winning_team: int, game_duration: float) -> bool:
        """Mark a game session as completed and update player statistics."""
        try:
            # Get session
            session = await self.db.get_game_session(room_id=room_id)
            if not session:
                return False
            
            # Update game session
            await self.db.execute_command(
                """
                    UPDATE game_sessions 
                    SET status = 'completed', 
                        completed_at = NOW(),
                        scores = $2
                    WHERE id = $1
                """,
                session['id'],
                json.dumps(final_scores)
            )
            
            # Create game statistics records
            participants = await self.db.execute_query(
                """
                    SELECT player_id, team, position
                    FROM game_participants
                    WHERE game_session_id = $1
                """,
                session['id']
            )
            
            for participant in participants:
                await self.db.execute_command(
                    """
                        INSERT INTO game_statistics 
                        (game_session_id, player_id, team, final_score, 
                         rounds_won, created_at)
                        VALUES ($1, $2, $3, $4, $5, NOW())
                    """,
                    session['id'],
                    participant['player_id'],
                    participant['team'],
                    final_scores.get(str(participant['team']), 0),
                    1 if participant['team'] == winning_team else 0
                )
            
            # Clear cache
            if room_id in self._game_cache:
                del self._game_cache[room_id]
            
            self.logger.info(f"Completed game session {room_id} (duration: {game_duration:.1f}s)")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error completing game session: {e}")
            return False
    
    # Analytics and monitoring
    
    async def get_server_statistics(self) -> Dict:
        """Get comprehensive server statistics."""
        try:
            stats = await self.db.get_active_games_stats()
            
            # Add additional metrics
            health_status = await self.db.get_health_status()
            
            return {
                'active_games': stats,
                'health_status': health_status,
                'cache_size': {
                    'players': len(self._player_cache),
                    'games': len(self._game_cache)
                },
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting server statistics: {e}")
            return {'error': str(e)}
    
    async def log_performance_metric(self, metric_type: str, metric_name: str, 
                                   metric_value: float, metadata: Optional[Dict] = None) -> bool:
        """Log a performance metric."""
        try:
            await self.db.execute_command(
                """
                    INSERT INTO performance_metrics 
                    (metric_type, metric_name, metric_value, metadata)
                    VALUES ($1, $2, $3, $4)
                """,
                metric_type,
                metric_name,
                metric_value,
                json.dumps(metadata or {})
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Error logging performance metric: {e}")
            return False
    
    # Cache management
    
    def clear_cache(self):
        """Clear internal caches."""
        self._player_cache.clear()
        self._game_cache.clear()
        self.logger.info("Cleared database integration caches")
    
    async def warm_cache(self):
        """Warm up caches with frequently accessed data."""
        try:
            # Load active players
            active_players = await self.db.execute_query(
                """
                    SELECT * FROM players 
                    WHERE last_seen > NOW() - INTERVAL '1 hour'
                    AND is_active = true
                    LIMIT 100
                """,
                use_replica=True
            )
            
            for player in active_players:
                self._player_cache[player['username']] = player
            
            # Load active game sessions
            active_sessions = await self.db.execute_query(
                """
                    SELECT * FROM game_sessions 
                    WHERE status IN ('waiting', 'active')
                    AND created_at > NOW() - INTERVAL '2 hours'
                    LIMIT 50
                """,
                use_replica=True
            )
            
            for session in active_sessions:
                self._game_cache[session['room_id']] = session
            
            self.logger.info(f"Warmed cache: {len(active_players)} players, {len(active_sessions)} sessions")
            
        except Exception as e:
            self.logger.error(f"Error warming cache: {e}")


# Factory function for easy initialization
async def create_database_integration(
    primary_dsn: Optional[str] = None,
    replica_dsn: Optional[str] = None,
    redis_url: Optional[str] = None
) -> GameDatabaseIntegration:
    """
    Create and initialize a GameDatabaseIntegration instance.
    
    Args:
        primary_dsn: Primary database DSN (from environment if not provided)
        replica_dsn: Replica database DSN (from environment if not provided)
        redis_url: Redis URL (from environment if not provided)
        
    Returns:
        Initialized GameDatabaseIntegration instance
    """
    # Get connection strings from environment if not provided
    if not primary_dsn:
        primary_dsn = os.getenv('DATABASE_URL')
        
    if not replica_dsn:
        replica_dsn = os.getenv('DATABASE_READ_URL')
        
    if not redis_url:
        redis_url = os.getenv('REDIS_URL')
    
    if not primary_dsn:
        raise ValueError("Primary database DSN must be provided or set in DATABASE_URL environment variable")
    
    # Create database manager
    db_manager = DatabaseManager(
        primary_dsn=primary_dsn,
        replica_dsn=replica_dsn,
        redis_url=redis_url
    )
    
    # Create and initialize integration
    integration = GameDatabaseIntegration(db_manager)
    await integration.initialize()
    
    return integration
