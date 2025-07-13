"""
SQLAlchemy 2.0 Async Game Integration Layer
High-level game operations that combine multiple CRUD operations
Designed for seamless integration with existing asyncio WebSocket server
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timedelta
import json

from sqlalchemy import update, func

from .session_manager import get_db_session, get_db_transaction
from .crud import (
    player_crud, game_session_crud, game_participant_crud,
    game_move_crud, websocket_connection_crud
)
from .models import Player, GameSession, GameParticipant, GameMove, WebSocketConnection

logger = logging.getLogger(__name__)


class GameIntegrationLayer:
    """
    High-level game operations that integrate with your existing server
    Provides transaction-safe operations for complex game state changes
    """
    
    async def create_player_if_not_exists(
        self,
        username: str,
        email: Optional[str] = None,
        **kwargs
    ) -> Tuple[Player, bool]:
        """
        Create a player if they don't exist, return existing player otherwise
        
        Returns:
            Tuple of (Player, was_created)
        """
        async with get_db_transaction() as session:
            # Try to get existing player
            existing_player = await player_crud.get_by_username(session, username)
            if existing_player:
                # Update last seen
                await player_crud.update_last_seen(session, existing_player.id)
                return existing_player, False
            
            # Create new player
            try:
                new_player = await player_crud.create_player(
                    session, username, email, **kwargs
                )
                return new_player, True
            except ValueError as e:
                # Handle race condition where player was created between check and create
                existing_player = await player_crud.get_by_username(session, username)
                if existing_player:
                    return existing_player, False
                raise e
    
    async def create_game_room(
        self,
        room_id: str,
        creator_username: str,
        game_type: str = 'standard',
        max_players: int = 4,
        **kwargs
    ) -> GameSession:
        """
        Create a new game room with the creator as first participant
        
        This is a transaction-safe operation that ensures consistency
        """
        async with get_db_transaction() as session:
            # Get or create the creator player
            creator, _ = await self.create_player_if_not_exists(creator_username)
            
            # Generate unique session key
            session_key = f"session_{room_id}_{uuid4().hex[:8]}"
            
            # Create the game session
            game = await game_session_crud.create_game(
                session,
                room_id=room_id,
                session_key=session_key,
                game_type=game_type,
                max_players=max_players,
                **kwargs
            )
            
            # Add creator as first participant
            await game_participant_crud.add_participant(
                session,
                game_id=game.id,
                player_id=creator.id,
                position=0,
                team=1,  # First player goes to team 1
                is_hakem=False  # Hakem will be determined later
            )
            
            # Update game player count
            await game_session_crud.increment_player_count(session, game.id, 1)
            
            # Log the action
            await self._log_game_action(
                session, game.id, creator.id, 'game_start',
                {'room_id': room_id, 'game_type': game_type}
            )
            
            return game
    
    async def join_game_room(
        self,
        room_id: str,
        username: str,
        connection_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[GameSession, GameParticipant]:
        """
        Add a player to an existing game room
        Handles team assignment and position management
        """
        async with get_db_transaction() as session:
            # Get or create player
            player, _ = await self.create_player_if_not_exists(username)
            
            # Get the game
            game = await game_session_crud.get_by_room_id(session, room_id)
            if not game:
                raise ValueError(f"Game room '{room_id}' not found")
            
            if not game.can_join():
                raise ValueError(f"Cannot join game '{room_id}': game is full or not waiting")
            
            # Check if player is already in the game
            existing_participants = await game_participant_crud.get_game_participants(
                session, game.id
            )
            
            for participant in existing_participants:
                if participant.player_id == player.id:
                    raise ValueError(f"Player '{username}' is already in this game")
            
            # Determine position and team
            taken_positions = {p.position for p in existing_participants}
            available_positions = [i for i in range(game.max_players) if i not in taken_positions]
            
            if not available_positions:
                raise ValueError("No available positions in the game")
            
            position = min(available_positions)
            # Alternate teams: positions 0,2 = team 1, positions 1,3 = team 2
            team = 1 if position % 2 == 0 else 2
            
            # Add participant
            participant = await game_participant_crud.add_participant(
                session,
                game_id=game.id,
                player_id=player.id,
                position=position,
                team=team,
                connection_id=connection_id,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # Update game player count
            await game_session_crud.increment_player_count(session, game.id, 1)
            
            # Log the action
            await self._log_game_action(
                session, game.id, player.id, 'join_game',
                {'position': position, 'team': team}
            )
            
            # If game is now full, update status to starting
            if game.current_players + 1 >= game.max_players:
                await game_session_crud.update_game_state(
                    session, game.id, status='starting'
                )
            
            return game, participant
    
    async def leave_game_room(
        self,
        room_id: str,
        username: str
    ) -> bool:
        """
        Remove a player from a game room
        Handles cleanup and state transitions
        """
        async with get_db_transaction() as session:
            # Get player
            player = await player_crud.get_by_username(session, username)
            if not player:
                return False
            
            # Get game
            game = await game_session_crud.get_by_room_id(session, room_id)
            if not game:
                return False
            
            # Remove participant
            removed = await game_participant_crud.remove_participant(
                session, game.id, player.id
            )
            
            if removed:
                # Update game player count
                await game_session_crud.increment_player_count(session, game.id, -1)
                
                # Log the action
                await self._log_game_action(
                    session, game.id, player.id, 'leave_game', {}
                )
                
                # If game becomes empty, mark as abandoned
                if game.current_players - 1 <= 0:
                    await game_session_crud.update_game_state(
                        session, game.id, status='abandoned'
                    )
                # If game was full and someone left, change status back to waiting
                elif game.status == 'starting' and game.current_players - 1 < game.max_players:
                    await game_session_crud.update_game_state(
                        session, game.id, status='waiting'
                    )
            
            return removed
    
    async def assign_teams_and_hakem(
        self,
        room_id: str
    ) -> Dict[str, Any]:
        """
        Assign teams and select hakem for a game
        Should be called when game is ready to start
        """
        async with get_db_transaction() as session:
            game = await game_session_crud.get_by_room_id(session, room_id)
            if not game:
                raise ValueError(f"Game '{room_id}' not found")
            
            participants = await game_participant_crud.get_game_participants(
                session, game.id
            )
            
            if len(participants) != game.max_players:
                raise ValueError("Game is not full, cannot assign teams")
            
            # Teams are already assigned based on position
            # Select hakem (randomly from all players)
            import random
            hakem_participant = random.choice(participants)
            
            # Update hakem in game
            await game_session_crud.set_hakem(
                session, game.id, hakem_participant.player_id, hakem_participant.position
            )
            
            # Update participant hakem status
            await session.execute(
                update(GameParticipant)
                .where(GameParticipant.id == hakem_participant.id)
                .values(is_hakem=True)
            )
            
            # Update game status
            await game_session_crud.update_game_state(
                session, game.id, status='active', phase='trump_selection'
            )
            
            # Log the action
            await self._log_game_action(
                session, game.id, hakem_participant.player_id, 'hakem_selected',
                {'hakem_position': hakem_participant.position}
            )
            
            # Return team assignments
            team_assignments = {
                'team1': [p for p in participants if p.team == 1],
                'team2': [p for p in participants if p.team == 2],
                'hakem': hakem_participant
            }
            
            return team_assignments
    
    async def record_trump_selection(
        self,
        room_id: str,
        username: str,
        trump_suit: str
    ) -> None:
        """
        Record trump suit selection by hakem
        """
        async with get_db_transaction() as session:
            # Get game and validate
            game = await game_session_crud.get_by_room_id(session, room_id)
            if not game:
                raise ValueError(f"Game '{room_id}' not found")
            
            # Get player
            player = await player_crud.get_by_username(session, username)
            if not player:
                raise ValueError(f"Player '{username}' not found")
            
            # Validate that this player is the hakem
            if game.hakem_id != player.id:
                raise ValueError(f"Player '{username}' is not the hakem")
            
            # Validate trump suit
            valid_suits = ['hearts', 'diamonds', 'clubs', 'spades']
            if trump_suit not in valid_suits:
                raise ValueError(f"Invalid trump suit: {trump_suit}")
            
            # Set trump suit
            await game_session_crud.set_trump_suit(session, game.id, trump_suit)
            
            # Update game phase
            await game_session_crud.update_game_state(
                session, game.id, phase='dealing'
            )
            
            # Log the action
            await self._log_game_action(
                session, game.id, player.id, 'choose_trump',
                {'trump_suit': trump_suit}
            )
    
    async def record_card_play(
        self,
        room_id: str,
        username: str,
        card: Dict[str, Any],
        round_number: int,
        trick_number: int
    ) -> GameMove:
        """
        Record a card play move
        """
        async with get_db_transaction() as session:
            # Get game and player
            game = await game_session_crud.get_by_room_id(session, room_id)
            if not game:
                raise ValueError(f"Game '{room_id}' not found")
            
            player = await player_crud.get_by_username(session, username)
            if not player:
                raise ValueError(f"Player '{username}' not found")
            
            # Record the move
            move = await game_move_crud.record_move(
                session,
                game_id=game.id,
                player_id=player.id,
                move_type='play_card',
                move_data={'card': card},
                round_number=round_number,
                trick_number=trick_number
            )
            
            # Update participant stats
            await session.execute(
                update(GameParticipant)
                .where(GameParticipant.game_session_id == game.id)
                .where(GameParticipant.player_id == player.id)
                .values(
                    cards_played=GameParticipant.cards_played + 1,
                    last_action_at=func.now()
                )
            )
            
            return move
    
    async def get_game_state(self, room_id: str) -> Optional[Dict[str, Any]]:
        """
        Get complete game state for a room
        Includes all participants, current status, and recent moves
        """
        async with get_db_session() as session:
            game = await game_session_crud.get_by_room_id(session, room_id)
            if not game:
                return None
            
            participants = await game_participant_crud.get_game_participants(
                session, game.id
            )
            
            recent_moves = await game_move_crud.get_recent_moves(
                session, game.id, limit=20
            )
            
            return {
                'game': game.to_dict(),
                'participants': [p.to_dict() for p in participants],
                'recent_moves': [m.to_dict() for m in recent_moves],
                'team_assignments': {
                    'team1': [p.to_dict() for p in participants if p.team == 1],
                    'team2': [p.to_dict() for p in participants if p.team == 2]
                }
            }
    
    async def register_websocket_connection(
        self,
        connection_id: str,
        username: Optional[str] = None,
        room_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> WebSocketConnection:
        """
        Register a new WebSocket connection
        """
        async with get_db_transaction() as session:
            player_id = None
            game_id = None
            
            if username:
                player, _ = await self.create_player_if_not_exists(username)
                player_id = player.id
            
            if room_id:
                game = await game_session_crud.get_by_room_id(session, room_id)
                if game:
                    game_id = game.id
            
            return await websocket_connection_crud.create_connection(
                session,
                connection_id=connection_id,
                player_id=player_id,
                game_session_id=game_id,
                ip_address=ip_address,
                user_agent=user_agent
            )
    
    async def handle_websocket_disconnect(
        self,
        connection_id: str,
        reason: Optional[str] = None
    ) -> None:
        """
        Handle WebSocket disconnection
        Updates connection status and participant status
        """
        async with get_db_transaction() as session:
            # Mark connection as disconnected
            await websocket_connection_crud.disconnect_connection(
                session, connection_id, reason
            )
            
            # Get connection to find associated participant
            connection = await websocket_connection_crud.get_by_connection_id(
                session, connection_id
            )
            
            if connection and connection.player_id and connection.game_session_id:
                # Update participant connection status
                participants = await game_participant_crud.get_game_participants(
                    session, connection.game_session_id
                )
                
                for participant in participants:
                    if (participant.player_id == connection.player_id and 
                        participant.connection_id == connection_id):
                        await game_participant_crud.update_connection_status(
                            session, participant.id, False
                        )
                        break
    
    async def cleanup_stale_connections(self, timeout_minutes: int = 5) -> int:
        """
        Clean up stale WebSocket connections
        Should be called periodically by a background task
        """
        async with get_db_transaction() as session:
            return await websocket_connection_crud.cleanup_stale_connections(
                session, timeout_minutes
            )
    
    async def get_player_active_games(self, username: str) -> List[Dict[str, Any]]:
        """
        Get all active games for a player
        """
        async with get_db_session() as session:
            player = await player_crud.get_by_username(session, username)
            if not player:
                return []
            
            participations = await game_participant_crud.get_player_games(
                session, player.id, active_only=True
            )
            
            games = []
            for participation in participations:
                game_state = await self.get_game_state(participation.game_session.room_id)
                if game_state:
                    games.append(game_state)
            
            return games
    
    async def get_joinable_games(self) -> List[Dict[str, Any]]:
        """
        Get all games that players can join
        """
        async with get_db_session() as session:
            games = await game_session_crud.get_joinable_games(session)
            
            result = []
            for game in games:
                participants = await game_participant_crud.get_game_participants(
                    session, game.id
                )
                
                result.append({
                    'game': game.to_dict(),
                    'participants': [p.to_dict() for p in participants],
                    'available_slots': game.max_players - len(participants)
                })
            
            return result
    
    async def update_websocket_connection(
        self,
        connection_id: str,
        player_username: Optional[str] = None,
        status: str = 'active'
    ) -> None:
        """
        Update WebSocket connection status and player association
        """
        async with get_db_transaction() as session:
            await websocket_connection_crud.update_connection_status(
                session, connection_id, status
            )
            
            if player_username:
                player, _ = await self.create_player_if_not_exists(player_username)
                await websocket_connection_crud.associate_player(
                    session, connection_id, player.id
                )
    
    async def get_game_participants(self, room_id: str) -> List[Any]:
        """
        Get all participants in a game room
        """
        async with get_db_session() as session:
            game = await game_session_crud.get_by_room_id(session, room_id)
            if not game:
                return []
            
            return await game_participant_crud.get_game_participants(session, game.id)
    
    async def update_game_state(
        self,
        room_id: str,
        game_phase: Optional[str] = None,
        current_turn: Optional[int] = None,
        status: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update game state in database
        """
        async with get_db_transaction() as session:
            game = await game_session_crud.get_by_room_id(session, room_id)
            if not game:
                return
            
            update_data = {}
            if game_phase:
                update_data['current_phase'] = game_phase
            if current_turn is not None:
                update_data['current_turn'] = current_turn
            if status:
                update_data['status'] = status
            if additional_data:
                current_metadata = game.game_metadata or {}
                current_metadata.update(additional_data)
                update_data['game_metadata'] = current_metadata
            
            if update_data:
                await game_session_crud.update_game(session, game.id, **update_data)
    
    async def get_recent_moves(self, room_id: str, limit: int = 10) -> List[Any]:
        """
        Get recent moves for a game
        """
        async with get_db_session() as session:
            game = await game_session_crud.get_by_room_id(session, room_id)
            if not game:
                return []
            
            return await game_move_crud.get_recent_moves(session, game.id, limit)
    
    async def complete_game(
        self,
        room_id: str,
        winner_data: Dict[str, Any],
        final_scores: Dict[str, Any],
        game_duration: float
    ) -> None:
        """
        Mark a game as completed and record final results
        """
        async with get_db_transaction() as session:
            game = await game_session_crud.get_by_room_id(session, room_id)
            if not game:
                return
            
            # Update game status
            await game_session_crud.complete_game(
                session,
                game.id,
                winner_data=winner_data,
                final_scores=final_scores,
                duration=game_duration
            )
            
            # Update player statistics
            participants = await game_participant_crud.get_game_participants(session, game.id)
            
            for participant in participants:
                is_winner = participant.player.username in winner_data.get('winners', [])
                await player_crud.update_game_stats(
                    session,
                    participant.player_id,
                    won=is_winner,
                    points=final_scores.get(participant.player.username, 0)
                )
    
    async def get_player_statistics(self, username: str) -> Dict[str, Any]:
        """
        Get comprehensive player statistics
        """
        async with get_db_session() as session:
            player = await player_crud.get_by_username(session, username)
            if not player:
                return {}
            
            # Get basic stats from player record
            stats = {
                'username': player.username,
                'total_games': player.total_games,
                'wins': player.wins,
                'losses': player.losses,
                'draws': player.draws,
                'rating': player.rating,
                'win_rate': player.wins / max(player.total_games, 1) * 100,
                'created_at': player.created_at.isoformat(),
                'last_seen': player.last_seen.isoformat() if player.last_seen else None
            }
            
            # Get recent games
            recent_participations = await game_participant_crud.get_player_games(
                session, player.id, limit=10
            )
            
            stats['recent_games'] = []
            for participation in recent_participations:
                game_info = {
                    'room_id': participation.game_session.room_id,
                    'status': participation.game_session.status,
                    'created_at': participation.game_session.created_at.isoformat(),
                    'position': participation.position,
                    'team': participation.team
                }
                stats['recent_games'].append(game_info)
            
            return stats

    async def _log_game_action(
        self,
        session,  # AsyncSession - avoiding import for now
        game_id: UUID,
        player_id: UUID,
        action_type: str,
        action_data: Dict[str, Any]
    ) -> None:
        """
        Internal method to log game actions
        """
        try:
            await game_move_crud.record_move(
                session,
                game_id=game_id,
                player_id=player_id,
                move_type=action_type,
                move_data=action_data,
                round_number=1,  # Default round
                trick_number=None
            )
        except Exception as e:
            logger.warning(f"Failed to log game action: {e}")


# Create global instance
game_integration = GameIntegrationLayer()

# Export the integration layer
__all__ = ['GameIntegrationLayer', 'game_integration']
