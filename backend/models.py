"""
SQLAlchemy Models for Hokm Card Game Database Schema
Comprehensive ORM models matching the optimized PostgreSQL schema
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, JSON, 
    ForeignKey, CheckConstraint, Index, DECIMAL, BigInteger,
    UniqueConstraint, Interval
)
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class Player(Base):
    """Player model - Core user management"""
    __tablename__ = 'players'
    __table_args__ = (
        CheckConstraint("email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'", name='valid_email'),
        CheckConstraint("length(username) >= 3 AND username ~* '^[A-Za-z0-9_-]+$'", name='valid_username'),
        CheckConstraint('wins + losses + draws <= total_games', name='valid_stats'),
        CheckConstraint('total_games >= 0', name='non_negative_games'),
        CheckConstraint('rating >= 0 AND rating <= 3000', name='valid_rating'),
        Index('idx_players_username', 'username'),
        Index('idx_players_email', 'email'),
        Index('idx_players_rating', 'rating', 'total_games'),
        Index('idx_players_last_seen', 'last_seen', postgresql_where='is_active = TRUE'),
        Index('idx_players_stats', 'total_games', 'wins', 'rating'),
    )
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Basic info
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    
    # Profile information
    display_name = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    country_code = Column(String(2), nullable=True)  # ISO country code
    timezone = Column(String(50), nullable=True)  # IANA timezone
    
    # Authentication and security
    email_verified = Column(Boolean, default=False)
    account_status = Column(String(20), default='active')
    last_login = Column(DateTime(timezone=True), nullable=True)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime(timezone=True), nullable=True)
    email_verification_token = Column(String(255), nullable=True)
    
    # Game statistics (denormalized for performance)
    total_games = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    total_points = Column(Integer, default=0)
    rating = Column(Integer, default=1000)
    
    # Tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    
    # Relationships
    game_participants = relationship("GameParticipant", back_populates="player")
    game_moves = relationship("GameMove", back_populates="player")
    websocket_connections = relationship("WebSocketConnection", back_populates="player")
    game_stats = relationship("PlayerGameStats", back_populates="player")
    achievements = relationship("PlayerAchievement", back_populates="player")
    audit_logs = relationship("AuditLog", back_populates="player")
    
    @validates('account_status')
    def validate_account_status(self, key, account_status):
        allowed_statuses = ['active', 'suspended', 'banned', 'deleted']
        if account_status not in allowed_statuses:
            raise ValueError(f"Account status must be one of: {allowed_statuses}")
        return account_status
    
    @property
    def win_percentage(self) -> float:
        """Calculate win percentage"""
        if self.total_games == 0:
            return 0.0
        return round((self.wins / self.total_games) * 100, 2)
    
    def __repr__(self):
        return f"<Player(username='{self.username}', rating={self.rating})>"


class GameSession(Base):
    """Game session model - Active and completed games"""
    __tablename__ = 'game_sessions'
    __table_args__ = (
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
        Index('idx_game_sessions_room_id', 'room_id'),
        Index('idx_game_sessions_status', 'status', 'created_at'),
        Index('idx_game_sessions_active', 'status', 'updated_at'),
        Index('idx_game_sessions_hakem', 'hakem_id'),
        Index('idx_game_sessions_game_type', 'game_type', 'status', 'created_at'),
        Index('idx_game_sessions_game_state', 'game_state', postgresql_using='gin'),
        Index('idx_game_sessions_scores', 'scores', postgresql_using='gin'),
    )
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Session identification
    room_id = Column(String(100), unique=True, nullable=False)
    session_key = Column(String(255), unique=True, nullable=False)
    
    # Game configuration
    game_type = Column(String(20), default='standard')
    max_players = Column(Integer, default=4)
    current_players = Column(Integer, default=0)
    rounds_to_win = Column(Integer, default=7)
    
    # Game state
    status = Column(String(20), default='waiting')
    phase = Column(String(20), default='waiting')
    current_round = Column(Integer, default=1)
    current_trick = Column(Integer, default=1)
    current_player_position = Column(Integer, nullable=True)
    
    # Game participants
    hakem_id = Column(UUID(as_uuid=True), ForeignKey('players.id'), nullable=True)
    hakem_position = Column(Integer, nullable=True)
    trump_suit = Column(String(10), nullable=True)
    
    # Game state storage (JSONB for flexibility)
    game_state = Column(JSONB, default={})
    player_hands = Column(JSONB, default={})  # Private hands per player
    played_cards = Column(JSONB, default=[])  # Cards played in current trick
    completed_tricks = Column(JSONB, default=[])  # All completed tricks
    scores = Column(JSONB, default={"team1": 0, "team2": 0})
    round_scores = Column(JSONB, default=[])  # Score history per round
    team_assignments = Column(JSONB, default={"team1": [], "team2": []})
    
    # Settings and metadata
    settings = Column(JSONB, default={})
    extra_data = Column(JSONB, default={})
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    hakem = relationship("Player", foreign_keys=[hakem_id])
    participants = relationship("GameParticipant", back_populates="game_session", cascade="all, delete-orphan")
    moves = relationship("GameMove", back_populates="game_session", cascade="all, delete-orphan")
    websocket_connections = relationship("WebSocketConnection", back_populates="game_session")
    game_history = relationship("GameHistory", back_populates="game_session", uselist=False)
    
    @validates('game_type')
    def validate_game_type(self, key, game_type):
        allowed_types = ['standard', 'tournament', 'friendly', 'ranked']
        if game_type not in allowed_types:
            raise ValueError(f"Game type must be one of: {allowed_types}")
        return game_type
    
    @validates('status')
    def validate_status(self, key, status):
        allowed_statuses = ['waiting', 'starting', 'active', 'paused', 'completed', 'abandoned', 'cancelled']
        if status not in allowed_statuses:
            raise ValueError(f"Status must be one of: {allowed_statuses}")
        return status
    
    @validates('phase')
    def validate_phase(self, key, phase):
        allowed_phases = ['waiting', 'dealing', 'trump_selection', 'playing', 'round_complete', 'game_complete']
        if phase not in allowed_phases:
            raise ValueError(f"Phase must be one of: {allowed_phases}")
        return phase
    
    @validates('trump_suit')
    def validate_trump_suit(self, key, trump_suit):
        if trump_suit is not None:
            allowed_suits = ['hearts', 'diamonds', 'clubs', 'spades']
            if trump_suit not in allowed_suits:
                raise ValueError(f"Trump suit must be one of: {allowed_suits}")
        return trump_suit
    
    def __repr__(self):
        return f"<GameSession(room_id='{self.room_id}', status='{self.status}')>"


class GameParticipant(Base):
    """Game participant model - Links players to game sessions"""
    __tablename__ = 'game_participants'
    __table_args__ = (
        CheckConstraint("position BETWEEN 0 AND 3", name='valid_position'),
        CheckConstraint("team IN (1, 2)", name='valid_team'),
        CheckConstraint("left_at IS NULL OR left_at >= joined_at", name='valid_connection_timing'),
        UniqueConstraint('game_session_id', 'position', name='unique_position_per_game'),
        UniqueConstraint('game_session_id', 'player_id', name='unique_player_per_game'),
        Index('idx_game_participants_session', 'game_session_id', 'position'),
        Index('idx_game_participants_player', 'player_id', 'joined_at'),
        Index('idx_game_participants_connected', 'is_connected', 'last_action_at'),
    )
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    game_session_id = Column(UUID(as_uuid=True), ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey('players.id', ondelete='CASCADE'), nullable=False)
    
    # Position and team
    position = Column(Integer, nullable=False)
    team = Column(Integer, nullable=False)
    is_hakem = Column(Boolean, default=False)
    
    # Connection status
    is_connected = Column(Boolean, default=True)
    connection_id = Column(String(255), nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Participation tracking
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    left_at = Column(DateTime(timezone=True), nullable=True)
    last_action_at = Column(DateTime(timezone=True), server_default=func.now())
    disconnections = Column(Integer, default=0)
    
    # Game performance
    cards_played = Column(Integer, default=0)
    tricks_won = Column(Integer, default=0)
    points_earned = Column(Integer, default=0)
    average_response_time = Column(Interval, nullable=True)
    
    # Relationships
    game_session = relationship("GameSession", back_populates="participants")
    player = relationship("Player", back_populates="game_participants")
    
    def __repr__(self):
        return f"<GameParticipant(player_id='{self.player_id}', position={self.position}, team={self.team})>"


class GameMove(Base):
    """Game move model - Complete audit trail of all game actions"""
    __tablename__ = 'game_moves'
    __table_args__ = (
        CheckConstraint("round_number >= 1", name='valid_round_number'),
        CheckConstraint("trick_number >= 1", name='valid_trick_number'),
        UniqueConstraint('game_session_id', 'sequence_number', name='unique_sequence_per_game'),
        Index('idx_game_moves_session', 'game_session_id', 'sequence_number'),
        Index('idx_game_moves_player', 'player_id', 'timestamp'),
        Index('idx_game_moves_type', 'move_type', 'timestamp'),
        Index('idx_game_moves_round_trick', 'game_session_id', 'round_number', 'trick_number', 'sequence_number'),
        Index('idx_game_moves_data', 'move_data', postgresql_using='gin'),
    )
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    game_session_id = Column(UUID(as_uuid=True), ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey('players.id', ondelete='CASCADE'), nullable=False)
    
    # Move details
    move_type = Column(String(30), nullable=False)
    move_data = Column(JSONB, nullable=False, default={})
    
    # Game context
    round_number = Column(Integer, nullable=False)
    trick_number = Column(Integer, nullable=True)
    sequence_number = Column(Integer, nullable=False)
    
    # Validation and processing
    is_valid = Column(Boolean, default=True)
    validation_errors = Column(JSONB, default=[])
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timing
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    response_time = Column(Interval, nullable=True)
    
    # Relationships
    game_session = relationship("GameSession", back_populates="moves")
    player = relationship("Player", back_populates="game_moves")
    
    @validates('move_type')
    def validate_move_type(self, key, move_type):
        allowed_types = [
            'join_game', 'leave_game', 'ready', 'not_ready',
            'choose_trump', 'play_card', 'pass_turn',
            'chat_message', 'reconnect', 'disconnect',
            'game_start', 'round_start', 'trick_complete', 'round_complete', 'game_complete'
        ]
        if move_type not in allowed_types:
            raise ValueError(f"Move type must be one of: {allowed_types}")
        return move_type
    
    def __repr__(self):
        return f"<GameMove(type='{self.move_type}', round={self.round_number}, sequence={self.sequence_number})>"


class WebSocketConnection(Base):
    """WebSocket connection model - Real-time connection management"""
    __tablename__ = 'websocket_connections'
    __table_args__ = (
        CheckConstraint("connection_quality BETWEEN 0 AND 1", name='valid_connection_quality'),
        CheckConstraint(
            "(is_active = TRUE AND disconnected_at IS NULL) OR (is_active = FALSE AND disconnected_at IS NOT NULL)",
            name='valid_connection_lifecycle'
        ),
        Index('idx_websocket_connections_player', 'player_id', 'connected_at'),
        Index('idx_websocket_connections_session', 'game_session_id', 'is_active'),
        Index('idx_websocket_connections_active', 'is_active', 'last_ping'),
    )
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(String(255), unique=True, nullable=False)
    
    # Associated entities
    player_id = Column(UUID(as_uuid=True), ForeignKey('players.id', ondelete='CASCADE'), nullable=True)
    game_session_id = Column(UUID(as_uuid=True), ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=True)
    
    # Connection details
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    protocol_version = Column(String(10), default='1.0')
    
    # Connection lifecycle
    connected_at = Column(DateTime(timezone=True), server_default=func.now())
    last_ping = Column(DateTime(timezone=True), server_default=func.now())
    disconnected_at = Column(DateTime(timezone=True), nullable=True)
    disconnect_reason = Column(String(100), nullable=True)
    
    # Status and metrics
    is_active = Column(Boolean, default=True)
    message_count = Column(Integer, default=0)
    bytes_sent = Column(BigInteger, default=0)
    bytes_received = Column(BigInteger, default=0)
    
    # Performance tracking
    average_latency = Column(Interval, nullable=True)
    peak_latency = Column(Interval, nullable=True)
    connection_quality = Column(DECIMAL(3, 2), nullable=True)
    
    # Relationships
    player = relationship("Player", back_populates="websocket_connections")
    game_session = relationship("GameSession", back_populates="websocket_connections")
    
    def __repr__(self):
        return f"<WebSocketConnection(connection_id='{self.connection_id}', active={self.is_active})>"


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
        Index('idx_game_history_session', 'game_session_id'),
        Index('idx_game_history_completed_at', 'completed_at'),
        Index('idx_game_history_hakem', 'hakem_player_id', 'completed_at'),
        Index('idx_game_history_game_type', 'game_type', 'completed_at'),
    )
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_session_id = Column(UUID(as_uuid=True), ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=False)
    
    # Game summary
    game_type = Column(String(20), nullable=False)
    total_rounds = Column(Integer, nullable=False)
    total_tricks = Column(Integer, nullable=False)
    game_duration = Column(Interval, nullable=False)
    
    # Outcome
    winning_team = Column(Integer, nullable=True)
    final_scores = Column(JSONB, nullable=False)
    is_draw = Column(Boolean, default=False)
    completion_reason = Column(String(50), default='normal')
    
    # Metadata
    trump_suit = Column(String(10), nullable=True)
    hakem_player_id = Column(UUID(as_uuid=True), ForeignKey('players.id'), nullable=True)
    total_moves = Column(Integer, default=0)
    
    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    game_session = relationship("GameSession", back_populates="game_history")
    hakem_player = relationship("Player", foreign_keys=[hakem_player_id])
    player_stats = relationship("PlayerGameStats", back_populates="game_history", cascade="all, delete-orphan")
    
    @validates('completion_reason')
    def validate_completion_reason(self, key, completion_reason):
        allowed_reasons = ['normal', 'forfeit', 'timeout', 'disconnect', 'admin_action']
        if completion_reason not in allowed_reasons:
            raise ValueError(f"Completion reason must be one of: {allowed_reasons}")
        return completion_reason
    
    def __repr__(self):
        return f"<GameHistory(game_type='{self.game_type}', winning_team={self.winning_team})>"


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
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    game_history_id = Column(UUID(as_uuid=True), ForeignKey('game_history.id', ondelete='CASCADE'), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey('players.id', ondelete='CASCADE'), nullable=False)
    
    # Game context
    team = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False)
    was_hakem = Column(Boolean, default=False)
    
    # Performance metrics
    cards_played = Column(Integer, default=0)
    tricks_won = Column(Integer, default=0)
    points_earned = Column(Integer, default=0)
    trump_cards_played = Column(Integer, default=0)
    successful_trump_calls = Column(Integer, default=0)
    
    # Timing metrics
    total_thinking_time = Column(Interval, default=timedelta(0))
    average_move_time = Column(Interval, default=timedelta(0))
    fastest_move_time = Column(Interval, nullable=True)
    slowest_move_time = Column(Interval, nullable=True)
    
    # Connection metrics
    disconnections = Column(Integer, default=0)
    total_offline_time = Column(Interval, default=timedelta(0))
    
    # Outcome
    is_winner = Column(Boolean, default=False)
    rating_change = Column(Integer, default=0)
    points_change = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    game_history = relationship("GameHistory", back_populates="player_stats")
    player = relationship("Player", back_populates="game_stats")
    
    def __repr__(self):
        return f"<PlayerGameStats(player_id='{self.player_id}', points={self.points_earned})>"


class PlayerAchievement(Base):
    """Player achievement model - Badges and milestones"""
    __tablename__ = 'player_achievements'
    __table_args__ = (
        CheckConstraint("current_progress <= required_progress", name='valid_progress'),
        CheckConstraint(
            "(is_completed = TRUE AND earned_at IS NOT NULL AND current_progress = required_progress) OR (is_completed = FALSE)",
            name='valid_completion'
        ),
        UniqueConstraint('player_id', 'achievement_type', 'achievement_name', name='unique_player_achievement'),
        Index('idx_player_achievements_player', 'player_id', 'earned_at'),
        Index('idx_player_achievements_type', 'achievement_type', 'is_completed', 'earned_at'),
        Index('idx_player_achievements_completed', 'is_completed', 'earned_at'),
    )
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), ForeignKey('players.id', ondelete='CASCADE'), nullable=False)
    
    # Achievement details
    achievement_type = Column(String(50), nullable=False)
    achievement_name = Column(String(100), nullable=False)
    achievement_description = Column(Text, nullable=True)
    achievement_tier = Column(String(20), default='bronze')
    
    # Progress tracking
    current_progress = Column(Integer, default=0)
    required_progress = Column(Integer, default=1)
    is_completed = Column(Boolean, default=False)
    
    # Associated data
    game_session_id = Column(UUID(as_uuid=True), ForeignKey('game_sessions.id'), nullable=True)
    extra_data = Column(JSONB, default={})
    
    # Timestamps
    earned_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    player = relationship("Player", back_populates="achievements")
    
    @validates('achievement_tier')
    def validate_achievement_tier(self, key, achievement_tier):
        allowed_tiers = ['bronze', 'silver', 'gold', 'platinum', 'diamond']
        if achievement_tier not in allowed_tiers:
            raise ValueError(f"Achievement tier must be one of: {allowed_tiers}")
        return achievement_tier
    
    def __repr__(self):
        return f"<PlayerAchievement(type='{self.achievement_type}', name='{self.achievement_name}')>"


class PerformanceMetrics(Base):
    """Performance metrics model - System monitoring"""
    __tablename__ = 'performance_metrics'
    __table_args__ = (
        CheckConstraint(
            "(metric_value IS NOT NULL) OR (metric_count IS NOT NULL) OR (metric_text IS NOT NULL)",
            name='valid_metric_value'
        ),
        Index('idx_performance_metrics_type_name', 'metric_type', 'metric_name', 'timestamp'),
        Index('idx_performance_metrics_timestamp', 'timestamp'),
        Index('idx_performance_metrics_server', 'server_instance', 'timestamp'),
    )
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Metric identification
    metric_type = Column(String(50), nullable=False)
    metric_name = Column(String(100), nullable=False)
    metric_category = Column(String(50), default='general')
    
    # Metric values
    metric_value = Column(DECIMAL(15, 4), nullable=True)
    metric_count = Column(Integer, nullable=True)
    metric_text = Column(Text, nullable=True)
    
    # Context and metadata
    server_instance = Column(String(100), nullable=True)
    extra_data = Column(JSONB, default={})
    tags = Column(JSONB, default=[])
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<PerformanceMetrics(type='{self.metric_type}', name='{self.metric_name}')>"


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
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Actor and action
    player_id = Column(UUID(as_uuid=True), ForeignKey('players.id'), nullable=True)
    admin_id = Column(UUID(as_uuid=True), nullable=True)  # Reference to admin users
    action_type = Column(String(50), nullable=False)
    action_description = Column(Text, nullable=False)
    
    # Context
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Data changes
    old_values = Column(JSONB, default={})
    new_values = Column(JSONB, default={})
    
    # Result
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    retention_until = Column(DateTime(timezone=True), default=lambda: datetime.utcnow() + timedelta(days=730))  # 2 years
    
    # Relationships
    player = relationship("Player", back_populates="audit_logs")
    
    def __repr__(self):
        return f"<AuditLog(action='{self.action_type}', success={self.success})>"


# Views (read-only models for complex queries)
class ActiveGameView(Base):
    """View for active games with participant details"""
    __tablename__ = 'active_games'
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    room_id = Column(String(100))
    status = Column(String(20))
    phase = Column(String(20))
    current_players = Column(Integer)
    max_players = Column(Integer)
    game_type = Column(String(20))
    created_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    hakem_username = Column(String(50))
    players = Column(Text)
    
    # This is a view, so we don't create it
    __table_args__ = {'info': {'is_view': True}}


class PlayerLeaderboardView(Base):
    """View for player leaderboard"""
    __tablename__ = 'player_leaderboard'
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    username = Column(String(50))
    display_name = Column(String(100))
    rating = Column(Integer)
    total_games = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    draws = Column(Integer)
    win_percentage = Column(DECIMAL(5, 2))
    rank = Column(Integer)
    last_seen = Column(DateTime(timezone=True))
    
    # This is a view, so we don't create it
    __table_args__ = {'info': {'is_view': True}}


# Schema version tracking
class SchemaVersion(Base):
    """Schema version tracking"""
    __tablename__ = 'schema_versions'
    
    version = Column(String(20), primary_key=True)
    description = Column(Text)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<SchemaVersion(version='{self.version}')>"


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
    'PerformanceMetrics',
    'AuditLog',
    'ActiveGameView',
    'PlayerLeaderboardView',
    'SchemaVersion'
]
