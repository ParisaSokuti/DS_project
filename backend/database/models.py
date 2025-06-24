"""
SQLAlchemy 2.0 Async Models for Hokm Game Server
Comprehensive ORM models optimized for real-time gaming workloads
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, 
    ForeignKey, CheckConstraint, Index, DECIMAL, BigInteger,
    UniqueConstraint, Interval, func, select
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, INET, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates
from sqlalchemy.sql import expression

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

class Base(DeclarativeBase):
    """
    Base class for all database models
    Provides common functionality and optimizations for gaming workloads
    """
    
    # Common columns that most gaming tables need
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now()
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert model instance to dictionary
        Useful for JSON serialization and caching
        """
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                result[column.name] = value.isoformat()
            elif isinstance(value, UUID):
                result[column.name] = str(value)
            elif isinstance(value, timedelta):
                result[column.name] = value.total_seconds()
            else:
                result[column.name] = value
        return result
    
    @classmethod
    async def get_by_id(cls, session: AsyncSession, id_value: UUID):
        """Get a model instance by ID"""
        result = await session.execute(
            select(cls).where(cls.id == id_value)
        )
        return result.scalar_one_or_none()


class Player(Base):
    """
    Player model - Core user management with gaming statistics
    Optimized for frequent queries and real-time updates
    """
    __tablename__ = 'players'
    __table_args__ = (
        # Validation constraints
        CheckConstraint(
            "email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'", 
            name='valid_email'
        ),
        CheckConstraint(
            "length(username) >= 3 AND username ~* '^[A-Za-z0-9_-]+$'", 
            name='valid_username'
        ),
        CheckConstraint('wins + losses + draws <= total_games', name='valid_stats'),
        CheckConstraint('total_games >= 0', name='non_negative_games'),
        CheckConstraint('rating >= 0 AND rating <= 3000', name='valid_rating'),
        CheckConstraint(
            "account_status IN ('active', 'suspended', 'banned', 'deleted')", 
            name='valid_account_status'
        ),
        
        # Performance indexes
        Index('idx_players_username', 'username'),
        Index('idx_players_email', 'email'),
        Index('idx_players_rating', 'rating', 'total_games'),
        Index('idx_players_last_seen', 'last_seen'),
        Index('idx_players_stats', 'total_games', 'wins', 'rating'),
        Index('idx_players_active_recent', 'is_active', 'last_seen'),
    )
    
    # Remove inherited columns to avoid duplication
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Core identification
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Profile information
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Authentication and security
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    account_status: Mapped[str] = mapped_column(String(20), default='active')
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_reset_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    email_verification_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Game statistics (denormalized for performance)
    total_games: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[int] = mapped_column(Integer, default=1000)
    
    # Tracking
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    game_participants: Mapped[List["GameParticipant"]] = relationship(
        "GameParticipant", back_populates="player", cascade="all, delete-orphan"
    )
    game_moves: Mapped[List["GameMove"]] = relationship(
        "GameMove", back_populates="player", cascade="all, delete-orphan"
    )
    websocket_connections: Mapped[List["WebSocketConnection"]] = relationship(
        "WebSocketConnection", back_populates="player", cascade="all, delete-orphan"
    )
    game_stats: Mapped[List["PlayerGameStats"]] = relationship(
        "PlayerGameStats", back_populates="player", cascade="all, delete-orphan"
    )
    achievements: Mapped[List["PlayerAchievement"]] = relationship(
        "PlayerAchievement", back_populates="player", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="player", cascade="all, delete-orphan"
    )
    statistics: Mapped[List["PlayerStatistic"]] = relationship(
        "PlayerStatistic", back_populates="player", cascade="all, delete-orphan"
    )
    
    @property
    def win_percentage(self) -> float:
        """Calculate win percentage"""
        if self.total_games == 0:
            return 0.0
        return round((self.wins / self.total_games) * 100, 2)
    
    @classmethod
    async def get_by_username(cls, session: AsyncSession, username: str) -> Optional["Player"]:
        """Get player by username"""
        result = await session.execute(
            select(cls).where(cls.username == username)
        )
        return result.scalar_one_or_none()
    
    @classmethod
    async def get_by_email(cls, session: AsyncSession, email: str) -> Optional["Player"]:
        """Get player by email"""
        result = await session.execute(
            select(cls).where(cls.email == email)
        )
        return result.scalar_one_or_none()
    
    def __repr__(self):
        return f"<Player(username='{self.username}', rating={self.rating})>"


class GameSession(Base):
    """
    Game session model - Core game state management
    Optimized for real-time updates and concurrent access
    """
    __tablename__ = 'game_sessions'
    __table_args__ = (
        # Validation constraints
        CheckConstraint("max_players BETWEEN 2 AND 4", name='valid_max_players'),
        CheckConstraint("current_players >= 0", name='non_negative_current_players'),
        CheckConstraint("rounds_to_win BETWEEN 1 AND 13", name='valid_rounds_to_win'),
        CheckConstraint("current_round BETWEEN 1 AND 13", name='valid_current_round'),
        CheckConstraint("current_trick BETWEEN 1 AND 13", name='valid_current_trick'),
        CheckConstraint("current_player_position BETWEEN 0 AND 3", name='valid_current_player_position'),
        CheckConstraint("hakem_position BETWEEN 0 AND 3", name='valid_hakem_position'),
        CheckConstraint("length(room_id) >= 3", name='valid_room_id'),
        CheckConstraint("length(session_key) >= 10", name='valid_session_key'),
        CheckConstraint("current_players <= max_players", name='valid_player_count'),
        CheckConstraint("started_at IS NULL OR started_at >= created_at", name='valid_game_timing'),
        CheckConstraint("completed_at IS NULL OR completed_at >= started_at", name='valid_completion_timing'),
        CheckConstraint(
            "status IN ('waiting', 'starting', 'active', 'paused', 'completed', 'abandoned', 'cancelled')",
            name='valid_status'
        ),
        CheckConstraint(
            "phase IN ('waiting', 'dealing', 'trump_selection', 'playing', 'round_complete', 'game_complete')",
            name='valid_phase'
        ),
        CheckConstraint(
            "trump_suit IS NULL OR trump_suit IN ('hearts', 'diamonds', 'clubs', 'spades')",
            name='valid_trump_suit'
        ),
        CheckConstraint(
            "game_type IN ('standard', 'tournament', 'friendly', 'ranked')",
            name='valid_game_type'
        ),
        
        # Performance indexes
        Index('idx_game_sessions_room_id', 'room_id'),
        Index('idx_game_sessions_status', 'status', 'created_at'),
        Index('idx_game_sessions_active', 'status', 'updated_at'),
        Index('idx_game_sessions_hakem', 'hakem_id'),
        Index('idx_game_sessions_game_type', 'game_type', 'status', 'created_at'),
        Index('idx_game_sessions_game_state', 'game_state'),
        Index('idx_game_sessions_scores', 'scores'),
        Index('idx_games_active_players', 'status'),
    )
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Session identification
    room_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    session_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    
    # Game configuration
    game_type: Mapped[str] = mapped_column(String(20), default='standard')
    max_players: Mapped[int] = mapped_column(Integer, default=4)
    current_players: Mapped[int] = mapped_column(Integer, default=0)
    rounds_to_win: Mapped[int] = mapped_column(Integer, default=7)
    
    # Game state
    status: Mapped[str] = mapped_column(String(20), default='waiting')
    phase: Mapped[str] = mapped_column(String(20), default='waiting')
    current_round: Mapped[int] = mapped_column(Integer, default=1)
    current_trick: Mapped[int] = mapped_column(Integer, default=1)
    current_player_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Game participants
    hakem_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey('players.id'), nullable=True)
    hakem_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trump_suit: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    # Game state storage (JSONB for flexibility and performance)
    game_state: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    player_hands: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    played_cards: Mapped[List[Any]] = mapped_column(JSONB, default=list)
    completed_tricks: Mapped[List[Any]] = mapped_column(JSONB, default=list)
    scores: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=lambda: {"team1": 0, "team2": 0})
    round_scores: Mapped[List[Any]] = mapped_column(JSONB, default=list)
    team_assignments: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=lambda: {"team1": [], "team2": []})
    
    # Settings and metadata
    settings: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    game_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Timestamps
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    hakem: Mapped[Optional["Player"]] = relationship("Player", foreign_keys=[hakem_id])
    participants: Mapped[List["GameParticipant"]] = relationship(
        "GameParticipant", back_populates="game_session", cascade="all, delete-orphan"
    )
    moves: Mapped[List["GameMove"]] = relationship(
        "GameMove", back_populates="game_session", cascade="all, delete-orphan"
    )
    websocket_connections: Mapped[List["WebSocketConnection"]] = relationship(
        "WebSocketConnection", back_populates="game_session", cascade="all, delete-orphan"
    )
    game_history: Mapped[Optional["GameHistory"]] = relationship(
        "GameHistory", back_populates="game_session", uselist=False
    )
    
    @classmethod
    async def get_by_room_id(cls, session: AsyncSession, room_id: str) -> Optional["GameSession"]:
        """Get game session by room ID"""
        result = await session.execute(
            select(cls).where(cls.room_id == room_id)
        )
        return result.scalar_one_or_none()
    
    @classmethod
    async def get_active_games(cls, session: AsyncSession) -> List["GameSession"]:
        """Get all active game sessions"""
        result = await session.execute(
            select(cls).where(cls.status.in_(['waiting', 'starting', 'active', 'paused']))
            .order_by(cls.created_at.desc())
        )
        return list(result.scalars().all())
    
    def is_full(self) -> bool:
        """Check if game is full"""
        return self.current_players >= self.max_players
    
    def can_join(self) -> bool:
        """Check if players can join the game"""
        return self.status == 'waiting' and not self.is_full()
    
    def __repr__(self):
        return f"<GameSession(room_id='{self.room_id}', status='{self.status}')>"


class GameParticipant(Base):
    """
    Game participant model - Links players to game sessions
    Tracks player-specific game state and performance
    """
    __tablename__ = 'game_participants'
    __table_args__ = (
        # Validation constraints
        CheckConstraint("position BETWEEN 0 AND 3", name='valid_position'),
        CheckConstraint("team IN (1, 2)", name='valid_team'),
        CheckConstraint("left_at IS NULL OR left_at >= joined_at", name='valid_connection_timing'),
        
        # Unique constraints
        UniqueConstraint('game_session_id', 'position', name='unique_position_per_game'),
        UniqueConstraint('game_session_id', 'player_id', name='unique_player_per_game'),
        
        # Performance indexes
        Index('idx_game_participants_session', 'game_session_id', 'position'),
        Index('idx_game_participants_player', 'player_id', 'joined_at'),
        Index('idx_game_participants_connected', 'is_connected', 'last_action_at'),
        Index('idx_game_participants_game_player', 'game_session_id', 'player_id'),
    )
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Foreign keys
    game_session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=False
    )
    player_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('players.id', ondelete='CASCADE'), nullable=False
    )
    
    # Position and team
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    team: Mapped[int] = mapped_column(Integer, nullable=False)
    is_hakem: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Connection status
    is_connected: Mapped[bool] = mapped_column(Boolean, default=True)
    connection_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Participation tracking
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_action_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    disconnections: Mapped[int] = mapped_column(Integer, default=0)
    
    # Game performance
    cards_played: Mapped[int] = mapped_column(Integer, default=0)
    tricks_won: Mapped[int] = mapped_column(Integer, default=0)
    points_earned: Mapped[int] = mapped_column(Integer, default=0)
    average_response_time: Mapped[Optional[timedelta]] = mapped_column(Interval, nullable=True)
    
    # Relationships
    game_session: Mapped["GameSession"] = relationship("GameSession", back_populates="participants")
    player: Mapped["Player"] = relationship("Player", back_populates="game_participants")
    
    def __repr__(self):
        return f"<GameParticipant(player_id='{self.player_id}', position={self.position}, team={self.team})>"


class GameMove(Base):
    """
    Game move model - Complete audit trail of all game actions
    Critical for game state reconstruction and cheat detection
    """
    __tablename__ = 'game_moves'
    __table_args__ = (
        # Validation constraints
        CheckConstraint("round_number >= 1", name='valid_round_number'),
        CheckConstraint("trick_number >= 1", name='valid_trick_number'),
        CheckConstraint(
            "move_type IN ('join_game', 'leave_game', 'ready', 'not_ready', 'choose_trump', "
            "'play_card', 'pass_turn', 'chat_message', 'reconnect', 'disconnect', "
            "'game_start', 'round_start', 'trick_complete', 'round_complete', 'game_complete')",
            name='valid_move_type'
        ),
        
        # Unique constraints
        UniqueConstraint('game_session_id', 'sequence_number', name='unique_sequence_per_game'),
        
        # Performance indexes
        Index('idx_game_moves_session', 'game_session_id', 'sequence_number'),
        Index('idx_game_moves_player', 'player_id', 'timestamp'),
        Index('idx_game_moves_type', 'move_type', 'timestamp'),
        Index('idx_game_moves_round_trick', 'game_session_id', 'round_number', 'trick_number', 'sequence_number'),
        Index('idx_game_moves_data', 'move_data'),
        Index('idx_game_moves_game_created', 'game_session_id', 'created_at'),
    )
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Foreign keys
    game_session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=False
    )
    player_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('players.id', ondelete='CASCADE'), nullable=False
    )
    
    # Move details
    move_type: Mapped[str] = mapped_column(String(30), nullable=False)
    move_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    
    # Game context
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    trick_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Validation and processing
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_errors: Mapped[List[Any]] = mapped_column(JSONB, default=list)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timing
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    response_time: Mapped[Optional[timedelta]] = mapped_column(Interval, nullable=True)
    
    # Relationships
    game_session: Mapped["GameSession"] = relationship("GameSession", back_populates="moves")
    player: Mapped["Player"] = relationship("Player", back_populates="game_moves")
    
    def __repr__(self):
        return f"<GameMove(type='{self.move_type}', round={self.round_number}, sequence={self.sequence_number})>"


class WebSocketConnection(Base):
    """
    WebSocket connection model - Real-time connection management
    Tracks active connections for each player and game session
    """
    __tablename__ = 'websocket_connections'
    __table_args__ = (
        # Validation constraints
        CheckConstraint("connection_quality BETWEEN 0 AND 1", name='valid_connection_quality'),
        CheckConstraint(
            "(is_active = TRUE AND disconnected_at IS NULL) OR (is_active = FALSE AND disconnected_at IS NOT NULL)",
            name='valid_connection_lifecycle'
        ),
        
        # Performance indexes
        Index('idx_websocket_connections_player', 'player_id', 'connected_at'),
        Index('idx_websocket_connections_session', 'game_session_id', 'is_active'),
        Index('idx_websocket_connections_active', 'is_active', 'last_ping'),
        Index('idx_websocket_connections_cleanup', 'last_ping'),
    )
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    connection_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    
    # Associated entities
    player_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('players.id', ondelete='CASCADE'), nullable=True
    )
    game_session_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=True
    )
    
    # Connection details
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    protocol_version: Mapped[str] = mapped_column(String(10), default='1.0')
    
    # Connection lifecycle
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_ping: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    disconnected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnect_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Status and metrics
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    bytes_sent: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_received: Mapped[int] = mapped_column(BigInteger, default=0)
    
    # Performance tracking
    average_latency: Mapped[Optional[timedelta]] = mapped_column(Interval, nullable=True)
    peak_latency: Mapped[Optional[timedelta]] = mapped_column(Interval, nullable=True)
    connection_quality: Mapped[Optional[float]] = mapped_column(DECIMAL(3, 2), nullable=True)
    
    # Relationships
    player: Mapped[Optional["Player"]] = relationship("Player", back_populates="websocket_connections")
    game_session: Mapped[Optional["GameSession"]] = relationship("GameSession", back_populates="websocket_connections")
    
    def __repr__(self):
        return f"<WebSocketConnection(connection_id='{self.connection_id}', active={self.is_active})>"


# Additional models for history and analytics
class GameHistory(Base):
    """Game history model - Completed games summary"""
    __tablename__ = 'game_history'
    __table_args__ = (
        CheckConstraint("winning_team IN (1, 2)", name='valid_winning_team'),
        CheckConstraint("completed_at > started_at", name='valid_game_duration'),
        CheckConstraint(
            "(winning_team IS NOT NULL AND is_draw = FALSE) OR (winning_team IS NULL AND is_draw = TRUE)",
            name='valid_outcome'
        ),
        CheckConstraint(
            "completion_reason IN ('normal', 'forfeit', 'timeout', 'disconnect', 'admin_action')",
            name='valid_completion_reason'
        ),
        Index('idx_game_history_session', 'game_session_id'),
        Index('idx_game_history_completed_at', 'completed_at'),
        Index('idx_game_history_hakem', 'hakem_player_id', 'completed_at'),
        Index('idx_game_history_game_type', 'game_type', 'completed_at'),
    )
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    game_session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=False
    )
    
    # Game summary
    game_type: Mapped[str] = mapped_column(String(20), nullable=False)
    total_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tricks: Mapped[int] = mapped_column(Integer, nullable=False)
    game_duration: Mapped[timedelta] = mapped_column(Interval, nullable=False)
    
    # Outcome
    winning_team: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    final_scores: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_draw: Mapped[bool] = mapped_column(Boolean, default=False)
    completion_reason: Mapped[str] = mapped_column(String(50), default='normal')
    
    # Metadata
    trump_suit: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    hakem_player_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('players.id'), nullable=True
    )
    total_moves: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Relationships
    game_session: Mapped["GameSession"] = relationship("GameSession", back_populates="game_history")
    hakem_player: Mapped[Optional["Player"]] = relationship("Player", foreign_keys=[hakem_player_id])
    player_stats: Mapped[List["PlayerGameStats"]] = relationship(
        "PlayerGameStats", back_populates="game_history", cascade="all, delete-orphan"
    )


class PlayerGameStats(Base):
    """Player game statistics model - Detailed per-game stats"""
    __tablename__ = 'player_game_stats'
    __table_args__ = (
        CheckConstraint("team IN (1, 2)", name='valid_team'),
        CheckConstraint("position BETWEEN 0 AND 3", name='valid_position'),
        UniqueConstraint('game_history_id', 'player_id', name='unique_player_per_game_history'),
        Index('idx_player_game_stats_player', 'player_id', 'created_at'),
        Index('idx_player_game_stats_game', 'game_history_id'),
        Index('idx_player_game_stats_performance', 'points_earned', 'tricks_won'),
    )
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Foreign keys
    game_history_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('game_history.id', ondelete='CASCADE'), nullable=False
    )
    player_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('players.id', ondelete='CASCADE'), nullable=False
    )
    
    # Game context
    team: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    was_hakem: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Performance metrics
    cards_played: Mapped[int] = mapped_column(Integer, default=0)
    tricks_won: Mapped[int] = mapped_column(Integer, default=0)
    points_earned: Mapped[int] = mapped_column(Integer, default=0)
    trump_cards_played: Mapped[int] = mapped_column(Integer, default=0)
    successful_trump_calls: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timing metrics
    total_thinking_time: Mapped[timedelta] = mapped_column(Interval, default=timedelta(0))
    average_move_time: Mapped[timedelta] = mapped_column(Interval, default=timedelta(0))
    fastest_move_time: Mapped[Optional[timedelta]] = mapped_column(Interval, nullable=True)
    slowest_move_time: Mapped[Optional[timedelta]] = mapped_column(Interval, nullable=True)
    
    # Connection metrics
    disconnections: Mapped[int] = mapped_column(Integer, default=0)
    total_offline_time: Mapped[timedelta] = mapped_column(Interval, default=timedelta(0))
    
    # Outcome
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)
    rating_change: Mapped[int] = mapped_column(Integer, default=0)
    points_change: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    game_history: Mapped["GameHistory"] = relationship("GameHistory", back_populates="player_stats")
    player: Mapped["Player"] = relationship("Player", back_populates="game_stats")


class PlayerAchievement(Base):
    """Player achievement model - Badges and milestones"""
    __tablename__ = 'player_achievements'
    __table_args__ = (
        CheckConstraint("current_progress <= required_progress", name='valid_progress'),
        CheckConstraint(
            "(is_completed = TRUE AND earned_at IS NOT NULL AND current_progress = required_progress) OR (is_completed = FALSE)",
            name='valid_completion'
        ),
        CheckConstraint(
            "achievement_tier IN ('bronze', 'silver', 'gold', 'platinum', 'diamond')",
            name='valid_achievement_tier'
        ),
        UniqueConstraint('player_id', 'achievement_type', 'achievement_name', name='unique_player_achievement'),
        Index('idx_player_achievements_player', 'player_id', 'earned_at'),
        Index('idx_player_achievements_type', 'achievement_type', 'is_completed', 'earned_at'),
        Index('idx_player_achievements_completed', 'is_completed', 'earned_at'),
    )
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    player_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('players.id', ondelete='CASCADE'), nullable=False
    )
    
    # Achievement details
    achievement_type: Mapped[str] = mapped_column(String(50), nullable=False)
    achievement_name: Mapped[str] = mapped_column(String(100), nullable=False)
    achievement_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    achievement_tier: Mapped[str] = mapped_column(String(20), default='bronze')
    
    # Progress tracking
    current_progress: Mapped[int] = mapped_column(Integer, default=0)
    required_progress: Mapped[int] = mapped_column(Integer, default=1)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Associated data
    game_session_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('game_sessions.id'), nullable=True
    )
    metadata_info: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Timestamps
    earned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="achievements")


class PlayerStatistic(Base):
    """
    Player statistics and performance metrics
    """
    __tablename__ = 'player_statistics'
    
    player_id: Mapped[UUID] = mapped_column(ForeignKey('players.id'), nullable=False)
    
    # Game statistics
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    games_won: Mapped[int] = mapped_column(Integer, default=0)
    games_lost: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    
    # Performance metrics
    average_score: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0.0)
    win_rate: Mapped[float] = mapped_column(DECIMAL(5, 4), default=0.0)
    
    # Timing statistics
    average_move_time: Mapped[float] = mapped_column(DECIMAL(10, 3), default=0.0)
    total_play_time: Mapped[timedelta] = mapped_column(Interval, default=timedelta())
    
    # Hokm-specific statistics
    hakem_games: Mapped[int] = mapped_column(Integer, default=0)
    hakem_wins: Mapped[int] = mapped_column(Integer, default=0)
    successful_suit_calls: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="statistics")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_player_statistics_player_id', 'player_id'),
        Index('idx_player_statistics_win_rate', 'win_rate'),
        Index('idx_player_statistics_games_played', 'games_played'),
    )


class Achievement(Base):
    """
    Achievement definitions and player achievements
    """
    __tablename__ = 'achievements'
    
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Achievement criteria
    criteria_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'games_won', 'consecutive_wins', etc.
    criteria_value: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Points and rewards
    points: Mapped[int] = mapped_column(Integer, default=0)
    badge_icon: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    player_achievements: Mapped[List["PlayerAchievement"]] = relationship(
        "PlayerAchievement", 
        back_populates="achievement"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_achievements_category', 'category'),
        Index('idx_achievements_active', 'is_active'),
    )


class PerformanceMetric(Base):
    """
    System performance metrics and monitoring data
    """
    __tablename__ = 'performance_metrics'
    
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_value: Mapped[float] = mapped_column(DECIMAL(15, 6), nullable=False)
    metric_unit: Mapped[str] = mapped_column(String(20), nullable=False)  # 'ms', 'ops/sec', '%', etc.
    
    # Context information
    component: Mapped[str] = mapped_column(String(50), nullable=False)  # 'redis', 'postgresql', 'sync'
    server_id: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Timing
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Additional metadata
    extra_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    
    # Indexes for time-series queries
    __table_args__ = (
        Index('idx_performance_metrics_timestamp', 'timestamp'),
        Index('idx_performance_metrics_component', 'component'),
        Index('idx_performance_metrics_name_timestamp', 'metric_name', 'timestamp'),
    )


class AuditLog(Base):
    """Audit log model - Sensitive operations tracking"""
    __tablename__ = 'audit_logs'
    __table_args__ = (
        Index('idx_audit_logs_player', 'player_id', 'timestamp'),
        Index('idx_audit_logs_action', 'action_type', 'timestamp'),
        Index('idx_audit_logs_entity', 'entity_type', 'entity_id', 'timestamp'),
        Index('idx_audit_logs_timestamp', 'timestamp'),
        Index('idx_audit_logs_retention', 'retention_until'),
    )
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Actor and action
    player_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey('players.id'), nullable=True
    )
    admin_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action_description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Context
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Data changes
    old_values: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    new_values: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Result
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    retention_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.utcnow() + timedelta(days=730)
    )
    
    # Relationships
    player: Mapped[Optional["Player"]] = relationship("Player", back_populates="audit_logs")


class MigrationLog(Base):
    """Track migration history and status for database schema changes"""
    __tablename__ = 'migration_logs'
    
    # Migration identification
    revision: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Migration execution details
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # 'running', 'completed', 'failed', 'rolled_back'
    
    # Migration metadata
    migration_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'upgrade', 'downgrade'
    execution_time_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Error information
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Migration context
    executed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # User or system that executed migration
    environment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 'development', 'staging', 'production'
    
    # Backup information
    backup_file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    backup_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Database state information
    pre_migration_schema_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    post_migration_schema_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    # Performance metrics
    affected_tables: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    affected_rows: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Rollback information
    is_rollback_safe: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rollback_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_migration_log_revision_status', 'revision', 'status'),
        Index('idx_migration_log_started_at', 'started_at'),
        Index('idx_migration_log_environment', 'environment'),
    )


class SchemaVersion(Base):
    """Track current schema version and migration state"""
    __tablename__ = 'schema_versions'
    
    # Version information
    version: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Version metadata
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_rollback_safe: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Dependencies
    depends_on: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    breaks_compatibility_with: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    
    # Migration timing
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Schema changes
    schema_changes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    data_migration_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Constraints
    __table_args__ = (
        CheckConstraint('length(version) > 0', name='check_version_not_empty'),
        Index('idx_schema_version_current', 'is_current'),
    )
    
    def __repr__(self):
        return f"<SchemaVersion(version={self.version}, is_current={self.is_current})>"


# Export all models
__all__ = [
    'Base',
    'Player',
    'GameSession',
    'GameParticipant', 
    'GameMove',
    'WebSocketConnection',
    'GameHistory',
    'PlayerGameStats',
    'PlayerAchievement',
    'PlayerStatistic',
    'PerformanceMetric',
    'AuditLog',
    'MigrationLog',
    'SchemaVersion',
]
