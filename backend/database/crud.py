"""
SQLAlchemy 2.0 Async CRUD Operations for Hokm Game Server
Comprehensive database operations optimized for real-time gaming
"""

from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import select, update, delete, and_, or_, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError, NoResultFound

from .models import (
    Player, GameSession, GameParticipant, GameMove, 
    WebSocketConnection, GameHistory, PlayerGameStats,
    PlayerAchievement, PerformanceMetric, AuditLog
)


class BaseCRUD:
    """
    Base CRUD operations class
    Provides common database operations with proper error handling
    """
    
    def __init__(self, model_class):
        self.model_class = model_class
    
    async def get_by_id(self, session: AsyncSession, id_value: UUID) -> Optional[Any]:
        """Get a record by ID"""
        result = await session.execute(
            select(self.model_class).where(self.model_class.id == id_value)
        )
        return result.scalar_one_or_none()
    
    async def get_all(
        self, 
        session: AsyncSession, 
        skip: int = 0, 
        limit: int = 100,
        order_by: Optional[str] = None
    ) -> List[Any]:
        """Get all records with pagination"""
        query = select(self.model_class)
        
        if order_by:
            if hasattr(self.model_class, order_by):
                query = query.order_by(getattr(self.model_class, order_by))
        else:
            query = query.order_by(self.model_class.created_at.desc())
        
        query = query.offset(skip).limit(limit)
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    async def create(self, session: AsyncSession, **kwargs) -> Any:
        """Create a new record"""
        instance = self.model_class(**kwargs)
        session.add(instance)
        await session.flush()
        await session.refresh(instance)
        return instance
    
    async def update(
        self, 
        session: AsyncSession, 
        id_value: UUID, 
        **kwargs
    ) -> Optional[Any]:
        """Update a record by ID"""
        result = await session.execute(
            update(self.model_class)
            .where(self.model_class.id == id_value)
            .values(**kwargs)
            .returning(self.model_class)
        )
        return result.scalar_one_or_none()
    
    async def delete(self, session: AsyncSession, id_value: UUID) -> bool:
        """Delete a record by ID"""
        result = await session.execute(
            delete(self.model_class).where(self.model_class.id == id_value)
        )
        return result.rowcount > 0
    
    async def count(self, session: AsyncSession, **filters) -> int:
        """Count records with optional filters"""
        query = select(func.count(self.model_class.id))
        
        for key, value in filters.items():
            if hasattr(self.model_class, key):
                query = query.where(getattr(self.model_class, key) == value)
        
        result = await session.execute(query)
        return result.scalar()


class PlayerCRUD(BaseCRUD):
    """
    Player CRUD operations
    Handles user management and authentication
    """
    
    def __init__(self):
        super().__init__(Player)
    
    async def get_by_username(self, session: AsyncSession, username: str) -> Optional[Player]:
        """Get player by username"""
        result = await session.execute(
            select(Player).where(Player.username == username)
        )
        return result.scalar_one_or_none()
    
    async def get_by_email(self, session: AsyncSession, email: str) -> Optional[Player]:
        """Get player by email"""
        result = await session.execute(
            select(Player).where(Player.email == email)
        )
        return result.scalar_one_or_none()
    
    async def create_player(
        self,
        session: AsyncSession,
        username: str,
        email: Optional[str] = None,
        password_hash: Optional[str] = None,
        display_name: Optional[str] = None,
        **kwargs
    ) -> Player:
        """Create a new player with validation"""
        # Check for existing username
        existing = await self.get_by_username(session, username)
        if existing:
            raise ValueError(f"Username '{username}' already exists")
        
        # Check for existing email if provided
        if email:
            existing = await self.get_by_email(session, email)
            if existing:
                raise ValueError(f"Email '{email}' already exists")
        
        player = Player(
            username=username,
            email=email,
            password_hash=password_hash,
            display_name=display_name or username,
            **kwargs
        )
        session.add(player)
        await session.flush()
        await session.refresh(player)
        return player
    
    async def update_last_seen(self, session: AsyncSession, player_id: UUID) -> None:
        """Update player's last seen timestamp"""
        await session.execute(
            update(Player)
            .where(Player.id == player_id)
            .values(last_seen=func.now())
        )
    
    async def update_game_stats(
        self,
        session: AsyncSession,
        player_id: UUID,
        games_increment: int = 0,
        wins_increment: int = 0,
        losses_increment: int = 0,
        draws_increment: int = 0,
        points_increment: int = 0,
        rating_change: int = 0
    ) -> None:
        """Update player's game statistics"""
        await session.execute(
            update(Player)
            .where(Player.id == player_id)
            .values(
                total_games=Player.total_games + games_increment,
                wins=Player.wins + wins_increment,
                losses=Player.losses + losses_increment,
                draws=Player.draws + draws_increment,
                total_points=Player.total_points + points_increment,
                rating=Player.rating + rating_change,
                last_seen=func.now()
            )
        )
    
    async def update_game_stats(
        self,
        session: AsyncSession,
        player_id: UUID,
        won: bool = False,
        points: int = 0
    ) -> None:
        """Update player's game statistics after a game"""
        update_values = {
            'total_games': Player.total_games + 1,
            'total_points': Player.total_points + points,
            'last_seen': func.now()
        }
        
        if won:
            update_values['wins'] = Player.wins + 1
        else:
            update_values['losses'] = Player.losses + 1
        
        await session.execute(
            update(Player)
            .where(Player.id == player_id)
            .values(**update_values)
        )
    
    async def get_leaderboard(
        self,
        session: AsyncSession,
        limit: int = 100,
        min_games: int = 5
    ) -> List[Player]:
        """Get player leaderboard"""
        result = await session.execute(
            select(Player)
            .where(Player.is_active == True)
            .where(Player.total_games >= min_games)
            .order_by(Player.rating.desc(), Player.wins.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def search_players(
        self,
        session: AsyncSession,
        search_term: str,
        limit: int = 20
    ) -> List[Player]:
        """Search players by username or display name"""
        search_pattern = f"%{search_term}%"
        result = await session.execute(
            select(Player)
            .where(Player.is_active == True)
            .where(
                or_(
                    Player.username.ilike(search_pattern),
                    Player.display_name.ilike(search_pattern)
                )
            )
            .order_by(Player.rating.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class GameSessionCRUD(BaseCRUD):
    """
    Game session CRUD operations
    Handles core game state management
    """
    
    def __init__(self):
        super().__init__(GameSession)
    
    async def get_by_room_id(self, session: AsyncSession, room_id: str) -> Optional[GameSession]:
        """Get game session by room ID"""
        result = await session.execute(
            select(GameSession)
            .options(selectinload(GameSession.participants))
            .where(GameSession.room_id == room_id)
        )
        return result.scalar_one_or_none()
    
    async def create_game(
        self,
        session: AsyncSession,
        room_id: str,
        session_key: str,
        game_type: str = 'standard',
        max_players: int = 4,
        rounds_to_win: int = 7,
        **kwargs
    ) -> GameSession:
        """Create a new game session"""
        # Check for existing room
        existing = await self.get_by_room_id(session, room_id)
        if existing:
            raise ValueError(f"Room '{room_id}' already exists")
        
        game = GameSession(
            room_id=room_id,
            session_key=session_key,
            game_type=game_type,
            max_players=max_players,
            rounds_to_win=rounds_to_win,
            **kwargs
        )
        session.add(game)
        await session.flush()
        await session.refresh(game)
        return game
    
    async def get_active_games(self, session: AsyncSession) -> List[GameSession]:
        """Get all active game sessions"""
        result = await session.execute(
            select(GameSession)
            .options(selectinload(GameSession.participants))
            .where(GameSession.status.in_(['waiting', 'starting', 'active', 'paused']))
            .order_by(GameSession.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def get_joinable_games(self, session: AsyncSession) -> List[GameSession]:
        """Get games that players can join"""
        result = await session.execute(
            select(GameSession)
            .options(selectinload(GameSession.participants))
            .where(GameSession.status == 'waiting')
            .where(GameSession.current_players < GameSession.max_players)
            .order_by(GameSession.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def update_game_state(
        self,
        session: AsyncSession,
        game_id: UUID,
        **state_updates
    ) -> Optional[GameSession]:
        """Update game state and metadata"""
        result = await session.execute(
            update(GameSession)
            .where(GameSession.id == game_id)
            .values(**state_updates, updated_at=func.now())
            .returning(GameSession)
        )
        return result.scalar_one_or_none()
    
    async def increment_player_count(
        self,
        session: AsyncSession,
        game_id: UUID,
        increment: int = 1
    ) -> None:
        """Increment or decrement player count"""
        await session.execute(
            update(GameSession)
            .where(GameSession.id == game_id)
            .values(
                current_players=GameSession.current_players + increment,
                updated_at=func.now()
            )
        )
    
    async def set_hakem(
        self,
        session: AsyncSession,
        game_id: UUID,
        hakem_id: UUID,
        hakem_position: int
    ) -> None:
        """Set the hakem (trump selector) for the game"""
        await session.execute(
            update(GameSession)
            .where(GameSession.id == game_id)
            .values(
                hakem_id=hakem_id,
                hakem_position=hakem_position,
                updated_at=func.now()
            )
        )
    
    async def set_trump_suit(
        self,
        session: AsyncSession,
        game_id: UUID,
        trump_suit: str
    ) -> None:
        """Set the trump suit for the game"""
        await session.execute(
            update(GameSession)
            .where(GameSession.id == game_id)
            .values(trump_suit=trump_suit, updated_at=func.now())
        )
    
    async def update_scores(
        self,
        session: AsyncSession,
        game_id: UUID,
        team1_score: int,
        team2_score: int
    ) -> None:
        """Update team scores"""
        scores = {"team1": team1_score, "team2": team2_score}
        await session.execute(
            update(GameSession)
            .where(GameSession.id == game_id)
            .values(scores=scores, updated_at=func.now())
        )
    
    async def complete_game(
        self,
        session: AsyncSession,
        game_id: UUID,
        winner_data: Dict[str, Any],
        final_scores: Dict[str, Any],
        duration: float
    ) -> None:
        """Mark a game as completed with final results"""
        await session.execute(
            update(GameSession)
            .where(GameSession.id == game_id)
            .values(
                status='completed',
                end_time=func.now(),
                winner_data=winner_data,
                final_scores=final_scores,
                game_duration=int(duration),
                updated_at=func.now()
            )
        )
    
    async def update_game(
        self,
        session: AsyncSession,
        game_id: UUID,
        **kwargs
    ) -> Optional[GameSession]:
        """Update game with arbitrary fields"""
        if kwargs:
            kwargs['updated_at'] = func.now()
            result = await session.execute(
                update(GameSession)
                .where(GameSession.id == game_id)
                .values(**kwargs)
                .returning(GameSession)
            )
            return result.scalar_one_or_none()
        return None


class GameParticipantCRUD(BaseCRUD):
    """
    Game participant CRUD operations
    Manages player participation in games
    """
    
    def __init__(self):
        super().__init__(GameParticipant)
    
    async def add_participant(
        self,
        session: AsyncSession,
        game_id: UUID,
        player_id: UUID,
        position: int,
        team: int,
        **kwargs
    ) -> GameParticipant:
        """Add a player to a game"""
        # Check for existing participation
        existing = await session.execute(
            select(GameParticipant)
            .where(GameParticipant.game_session_id == game_id)
            .where(GameParticipant.player_id == player_id)
        )
        if existing.scalar_one_or_none():
            raise ValueError("Player already in this game")
        
        # Check position availability
        existing_position = await session.execute(
            select(GameParticipant)
            .where(GameParticipant.game_session_id == game_id)
            .where(GameParticipant.position == position)
        )
        if existing_position.scalar_one_or_none():
            raise ValueError(f"Position {position} already taken")
        
        participant = GameParticipant(
            game_session_id=game_id,
            player_id=player_id,
            position=position,
            team=team,
            **kwargs
        )
        session.add(participant)
        await session.flush()
        await session.refresh(participant)
        return participant
    
    async def get_game_participants(
        self,
        session: AsyncSession,
        game_id: UUID
    ) -> List[GameParticipant]:
        """Get all participants for a game"""
        result = await session.execute(
            select(GameParticipant)
            .options(joinedload(GameParticipant.player))
            .where(GameParticipant.game_session_id == game_id)
            .order_by(GameParticipant.position)
        )
        return list(result.scalars().all())
    
    async def get_player_games(
        self,
        session: AsyncSession,
        player_id: UUID,
        active_only: bool = True,
        limit: int = 50
    ) -> List[GameParticipant]:
        """Get all games for a player"""
        query = (
            select(GameParticipant)
            .options(joinedload(GameParticipant.game_session))
            .where(GameParticipant.player_id == player_id)
        )
        
        if active_only:
            query = query.where(
                GameParticipant.game_session.has(
                    GameSession.status.in_(['waiting', 'starting', 'active', 'paused'])
                )
            )
        
        result = await session.execute(
            query.order_by(GameParticipant.joined_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
    
    async def update_connection_status(
        self,
        session: AsyncSession,
        participant_id: UUID,
        is_connected: bool
    ) -> None:
        """Update participant connection status"""
        await session.execute(
            update(GameParticipant)
            .where(GameParticipant.id == participant_id)
            .values(is_connected=is_connected)
        )
    
    async def remove_participant(
        self,
        session: AsyncSession,
        game_id: UUID,
        player_id: UUID
    ) -> bool:
        """Remove a player from a game"""
        # Update leave time instead of deleting for audit trail
        result = await session.execute(
            update(GameParticipant)
            .where(GameParticipant.game_session_id == game_id)
            .where(GameParticipant.player_id == player_id)
            .values(left_at=func.now(), is_connected=False)
        )
        return result.rowcount > 0


class GameMoveCRUD(BaseCRUD):
    """
    Game move CRUD operations
    Handles move recording and game history
    """
    
    def __init__(self):
        super().__init__(GameMove)
    
    async def record_move(
        self,
        session: AsyncSession,
        game_id: UUID,
        player_id: UUID,
        move_type: str,
        move_data: Dict[str, Any],
        round_number: int,
        trick_number: Optional[int] = None,
        sequence_number: Optional[int] = None,
        **kwargs
    ) -> GameMove:
        """Record a game move"""
        # Auto-generate sequence number if not provided
        if sequence_number is None:
            result = await session.execute(
                select(func.coalesce(func.max(GameMove.sequence_number), 0))
                .where(GameMove.game_session_id == game_id)
            )
            sequence_number = result.scalar() + 1
        
        move = GameMove(
            game_session_id=game_id,
            player_id=player_id,
            move_type=move_type,
            move_data=move_data,
            round_number=round_number,
            trick_number=trick_number,
            sequence_number=sequence_number,
            **kwargs
        )
        session.add(move)
        await session.flush()
        await session.refresh(move)
        return move
    
    async def get_game_moves(
        self,
        session: AsyncSession,
        game_id: UUID,
        round_number: Optional[int] = None,
        move_type: Optional[str] = None
    ) -> List[GameMove]:
        """Get moves for a game with optional filters"""
        query = (
            select(GameMove)
            .options(joinedload(GameMove.player))
            .where(GameMove.game_session_id == game_id)
        )
        
        if round_number is not None:
            query = query.where(GameMove.round_number == round_number)
        
        if move_type is not None:
            query = query.where(GameMove.move_type == move_type)
        
        result = await session.execute(query.order_by(GameMove.sequence_number))
        return list(result.scalars().all())
    
    async def get_player_moves(
        self,
        session: AsyncSession,
        player_id: UUID,
        game_id: Optional[UUID] = None,
        limit: int = 100
    ) -> List[GameMove]:
        """Get moves by a specific player"""
        query = select(GameMove).where(GameMove.player_id == player_id)
        
        if game_id is not None:
            query = query.where(GameMove.game_session_id == game_id)
        
        result = await session.execute(
            query.order_by(GameMove.timestamp.desc()).limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_recent_moves(
        self,
        session: AsyncSession,
        game_id: UUID,
        limit: int = 10
    ) -> List[GameMove]:
        """Get recent moves for a game"""
        result = await session.execute(
            select(GameMove)
            .options(joinedload(GameMove.player))
            .where(GameMove.game_session_id == game_id)
            .order_by(GameMove.timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class WebSocketConnectionCRUD(BaseCRUD):
    """
    WebSocket connection CRUD operations
    Manages real-time connection tracking
    """
    
    def __init__(self):
        super().__init__(WebSocketConnection)
    
    async def create_connection(
        self,
        session: AsyncSession,
        connection_id: str,
        player_id: Optional[UUID] = None,
        game_session_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        **kwargs
    ) -> WebSocketConnection:
        """Create a new WebSocket connection record"""
        connection = WebSocketConnection(
            connection_id=connection_id,
            player_id=player_id,
            game_session_id=game_session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            **kwargs
        )
        session.add(connection)
        await session.flush()
        await session.refresh(connection)
        return connection
    
    async def get_by_connection_id(
        self,
        session: AsyncSession,
        connection_id: str
    ) -> Optional[WebSocketConnection]:
        """Get connection by connection ID"""
        result = await session.execute(
            select(WebSocketConnection)
            .where(WebSocketConnection.connection_id == connection_id)
        )
        return result.scalar_one_or_none()
    
    async def get_player_connections(
        self,
        session: AsyncSession,
        player_id: UUID,
        active_only: bool = True
    ) -> List[WebSocketConnection]:
        """Get all connections for a player"""
        query = select(WebSocketConnection).where(WebSocketConnection.player_id == player_id)
        
        if active_only:
            query = query.where(WebSocketConnection.is_active == True)
        
        result = await session.execute(query.order_by(WebSocketConnection.connected_at.desc()))
        return list(result.scalars().all())
    
    async def get_game_connections(
        self,
        session: AsyncSession,
        game_id: UUID,
        active_only: bool = True
    ) -> List[WebSocketConnection]:
        """Get all connections for a game"""
        query = select(WebSocketConnection).where(WebSocketConnection.game_session_id == game_id)
        
        if active_only:
            query = query.where(WebSocketConnection.is_active == True)
        
        result = await session.execute(query.order_by(WebSocketConnection.connected_at))
        return list(result.scalars().all())
    
    async def update_last_ping(
        self,
        session: AsyncSession,
        connection_id: str
    ) -> None:
        """Update last ping time for a connection"""
        await session.execute(
            update(WebSocketConnection)
            .where(WebSocketConnection.connection_id == connection_id)
            .values(last_ping=func.now())
        )
    
    async def disconnect_connection(
        self,
        session: AsyncSession,
        connection_id: str,
        reason: Optional[str] = None
    ) -> None:
        """Mark a connection as disconnected"""
        await session.execute(
            update(WebSocketConnection)
            .where(WebSocketConnection.connection_id == connection_id)
            .values(
                is_active=False,
                disconnected_at=func.now(),
                disconnect_reason=reason
            )
        )
    
    async def update_connection_status(
        self,
        session: AsyncSession,
        connection_id: str,
        status: str
    ) -> None:
        """Update connection status"""
        await session.execute(
            update(WebSocketConnection)
            .where(WebSocketConnection.connection_id == connection_id)
            .values(status=status, last_ping=func.now())
        )
    
    async def associate_player(
        self,
        session: AsyncSession,
        connection_id: str,
        player_id: UUID
    ) -> None:
        """Associate a connection with a player"""
        await session.execute(
            update(WebSocketConnection)
            .where(WebSocketConnection.connection_id == connection_id)
            .values(player_id=player_id)
        )
    
    async def cleanup_stale_connections(
        self,
        session: AsyncSession,
        timeout_minutes: int = 5
    ) -> int:
        """Clean up stale connections"""
        cutoff_time = func.now() - timedelta(minutes=timeout_minutes)
        
        result = await session.execute(
            update(WebSocketConnection)
            .where(
                and_(
                    WebSocketConnection.is_active == True,
                    WebSocketConnection.last_ping < cutoff_time
                )
            )
            .values(
                is_active=False,
                disconnected_at=func.now(),
                disconnect_reason='timeout'
            )
        )
        
        return result.rowcount


# Create CRUD instances
player_crud = PlayerCRUD()
game_session_crud = GameSessionCRUD()
game_participant_crud = GameParticipantCRUD()
game_move_crud = GameMoveCRUD()
websocket_connection_crud = WebSocketConnectionCRUD()

# Export CRUD instances
__all__ = [
    'BaseCRUD',
    'PlayerCRUD',
    'GameSessionCRUD', 
    'GameParticipantCRUD',
    'GameMoveCRUD',
    'WebSocketConnectionCRUD',
    'player_crud',
    'game_session_crud',
    'game_participant_crud',
    'game_move_crud',
    'websocket_connection_crud',
]
