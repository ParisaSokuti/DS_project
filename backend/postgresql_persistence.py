"""
PostgreSQL Persistent Data Manager for Hokm Game Server
Handles long-term data persistence, analytics, and historical records
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update, delete, func, text, and_, or_
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Import your models
from backend.database.models import (
    Player, GameSession, GameParticipant, GameMove, 
    PlayerStatistic, Achievement, PerformanceMetric
)
from backend.database.session_manager import AsyncSessionManager

logger = logging.getLogger(__name__)

@dataclass
class PersistenceConfig:
    """Configuration for PostgreSQL persistence"""
    batch_size: int = 100
    batch_timeout: float = 30.0  # seconds
    enable_analytics: bool = True
    enable_audit_logs: bool = True
    cleanup_old_records: bool = True
    old_records_threshold_days: int = 90

class PostgreSQLPersistenceManager:
    """
    PostgreSQL-based persistence manager for long-term data storage,
    analytics, and historical records in the Hokm game server.
    """
    
    def __init__(self, session_manager: AsyncSessionManager, config: PersistenceConfig = None):
        self.session_manager = session_manager
        self.config = config or PersistenceConfig()
        
        # Batch processing
        self.batch_queue = {}
        self.batch_task = None
        self.batch_running = False
        
        # Performance tracking
        self.operation_counts = {
            'player_creates': 0,
            'game_persists': 0,
            'statistics_updates': 0,
            'analytics_queries': 0,
            'batch_operations': 0
        }
        
        logger.info("PostgreSQL Persistence Manager initialized")
    
    async def initialize(self):
        """Initialize the persistence manager"""
        if self.config.batch_size > 1:
            await self.start_batch_processing()
        
        logger.info("PostgreSQL Persistence Manager fully initialized")
    
    # Player Management
    async def create_or_update_player(self, player_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create or update player profile"""
        try:
            async with self.session_manager.get_session() as session:
                # Check if player exists
                stmt = select(Player).where(Player.username == player_data['username'])
                result = await session.execute(stmt)
                existing_player = result.scalar_one_or_none()
                
                if existing_player:
                    # Update existing player
                    for key, value in player_data.items():
                        if hasattr(existing_player, key) and key != 'id':
                            setattr(existing_player, key, value)
                    
                    existing_player.last_seen = datetime.utcnow()
                    await session.commit()
                    
                    player_dict = {
                        'id': str(existing_player.id),
                        'username': existing_player.username,
                        'email': existing_player.email,
                        'display_name': existing_player.display_name,
                        'total_games': existing_player.total_games,
                        'wins': existing_player.wins,
                        'rating': float(existing_player.rating) if existing_player.rating else 0.0,
                        'created_at': existing_player.created_at.isoformat(),
                        'last_seen': existing_player.last_seen.isoformat(),
                        'is_active': existing_player.is_active
                    }
                    
                    self.operation_counts['player_creates'] += 1
                    return player_dict
                else:
                    # Create new player
                    new_player = Player(
                        id=uuid4(),
                        username=player_data['username'],
                        email=player_data.get('email'),
                        display_name=player_data.get('display_name', player_data['username']),
                        password_hash=player_data.get('password_hash'),
                        total_games=0,
                        wins=0,
                        rating=1200.0,  # Default rating
                        created_at=datetime.utcnow(),
                        last_seen=datetime.utcnow(),
                        is_active=True
                    )
                    
                    session.add(new_player)
                    await session.commit()
                    
                    player_dict = {
                        'id': str(new_player.id),
                        'username': new_player.username,
                        'email': new_player.email,
                        'display_name': new_player.display_name,
                        'total_games': new_player.total_games,
                        'wins': new_player.wins,
                        'rating': float(new_player.rating),
                        'created_at': new_player.created_at.isoformat(),
                        'last_seen': new_player.last_seen.isoformat(),
                        'is_active': new_player.is_active
                    }
                    
                    self.operation_counts['player_creates'] += 1
                    return player_dict
                    
        except Exception as e:
            logger.error(f"Failed to create/update player {player_data.get('username')}: {str(e)}")
            return None
    
    async def get_player_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get player by username"""
        try:
            async with self.session_manager.get_session() as session:
                stmt = select(Player).where(Player.username == username)
                result = await session.execute(stmt)
                player = result.scalar_one_or_none()
                
                if player:
                    return {
                        'id': str(player.id),
                        'username': player.username,
                        'email': player.email,
                        'display_name': player.display_name,
                        'total_games': player.total_games,
                        'wins': player.wins,
                        'rating': float(player.rating) if player.rating else 0.0,
                        'created_at': player.created_at.isoformat(),
                        'last_seen': player.last_seen.isoformat(),
                        'is_active': player.is_active
                    }
                return None
                
        except Exception as e:
            logger.error(f"Failed to get player {username}: {str(e)}")
            return None
    
    async def get_player_statistics(self, player_id: str) -> Dict[str, Any]:
        """Get comprehensive player statistics"""
        try:
            async with self.session_manager.get_session() as session:
                # Get basic player info
                player_stmt = select(Player).where(Player.id == UUID(player_id))
                player_result = await session.execute(player_stmt)
                player = player_result.scalar_one_or_none()
                
                if not player:
                    return {}
                
                # Get detailed statistics
                stats_stmt = select(PlayerStatistic).where(PlayerStatistic.player_id == UUID(player_id))
                stats_result = await session.execute(stats_stmt)
                stats = stats_result.scalars().all()
                
                # Get recent games
                recent_games_stmt = (
                    select(GameSession, GameParticipant)
                    .join(GameParticipant, GameSession.id == GameParticipant.game_session_id)
                    .where(GameParticipant.player_id == UUID(player_id))
                    .order_by(GameSession.completed_at.desc())
                    .limit(10)
                )
                recent_games_result = await session.execute(recent_games_stmt)
                recent_games = recent_games_result.all()
                
                # Compile statistics
                statistics = {
                    'player_id': player_id,
                    'username': player.username,
                    'total_games': player.total_games,
                    'wins': player.wins,
                    'losses': player.total_games - player.wins,
                    'win_rate': (player.wins / player.total_games * 100) if player.total_games > 0 else 0,
                    'rating': float(player.rating) if player.rating else 0.0,
                    'detailed_stats': {},
                    'recent_games': []
                }
                
                # Process detailed statistics
                for stat in stats:
                    statistics['detailed_stats'][stat.statistic_name] = {
                        'value': float(stat.statistic_value) if stat.statistic_value else 0.0,
                        'games_count': stat.games_count,
                        'last_updated': stat.last_updated.isoformat() if stat.last_updated else None
                    }
                
                # Process recent games
                for game_session, participant in recent_games:
                    game_info = {
                        'game_id': str(game_session.id),
                        'room_id': game_session.room_id,
                        'completed_at': game_session.completed_at.isoformat() if game_session.completed_at else None,
                        'duration_minutes': int(game_session.duration_seconds / 60) if game_session.duration_seconds else 0,
                        'team': participant.team,
                        'won': participant.won,
                        'score_earned': participant.score_earned,
                        'cards_played': participant.cards_played
                    }
                    statistics['recent_games'].append(game_info)
                
                return statistics
                
        except Exception as e:
            logger.error(f"Failed to get player statistics for {player_id}: {str(e)}")
            return {}
    
    # Game Session Persistence
    async def persist_game_session(self, game_data: Dict[str, Any]) -> bool:
        """Persist completed game session"""
        try:
            async with self.session_manager.get_session() as session:
                # Create game session record
                game_session = GameSession(
                    id=uuid4(),
                    room_id=game_data['room_id'],
                    status='completed',
                    phase='game_complete',
                    player_count=game_data.get('player_count', 4),
                    team_assignments=game_data.get('team_assignments', {}),
                    settings=game_data.get('settings', {}),
                    game_metadata=game_data.get('metadata', {}),
                    team1_score=game_data.get('team1_score', 0),
                    team2_score=game_data.get('team2_score', 0),
                    winner_team=game_data.get('winner_team'),
                    started_at=datetime.fromisoformat(game_data['started_at']) if game_data.get('started_at') else datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    duration_seconds=game_data.get('duration_seconds', 0)
                )
                
                session.add(game_session)
                await session.flush()  # Get the ID
                
                # Create participant records
                participants = game_data.get('participants', [])
                for participant_data in participants:
                    # Get player ID
                    player_stmt = select(Player.id).where(Player.username == participant_data['username'])
                    player_result = await session.execute(player_stmt)
                    player_id = player_result.scalar_one_or_none()
                    
                    if player_id:
                        participant = GameParticipant(
                            id=uuid4(),
                            game_session_id=game_session.id,
                            player_id=player_id,
                            team=participant_data.get('team'),
                            won=participant_data.get('won', False),
                            score_earned=participant_data.get('score_earned', 0),
                            cards_played=participant_data.get('cards_played', 0),
                            tricks_won=participant_data.get('tricks_won', 0),
                            hokm_selected=participant_data.get('hokm_selected', False),
                            joined_at=datetime.fromisoformat(participant_data['joined_at']) if participant_data.get('joined_at') else datetime.utcnow()
                        )
                        session.add(participant)
                
                await session.commit()
                
                # Update player statistics asynchronously
                asyncio.create_task(self._update_player_statistics_from_game(game_data))
                
                self.operation_counts['game_persists'] += 1
                logger.info(f"Persisted game session {game_data['room_id']}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to persist game session {game_data.get('room_id')}: {str(e)}")
            return False
    
    async def persist_game_moves(self, room_id: str, moves: List[Dict[str, Any]]) -> bool:
        """Persist game moves in batch"""
        try:
            async with self.session_manager.get_session() as session:
                # Get game session ID
                game_stmt = select(GameSession.id).where(GameSession.room_id == room_id)
                game_result = await session.execute(game_stmt)
                game_session_id = game_result.scalar_one_or_none()
                
                if not game_session_id:
                    logger.warning(f"Game session not found for room {room_id}")
                    return False
                
                # Prepare move records
                move_records = []
                for move_data in moves:
                    # Get player ID
                    player_stmt = select(Player.id).where(Player.username == move_data['player_id'])
                    player_result = await session.execute(player_stmt)
                    player_id = player_result.scalar_one_or_none()
                    
                    if player_id:
                        move_record = GameMove(
                            id=uuid4(),
                            game_session_id=game_session_id,
                            player_id=player_id,
                            move_number=move_data.get('move_number', 0),
                            move_type=move_data.get('move_type', 'play_card'),
                            move_data=move_data.get('move_data', {}),
                            timestamp=datetime.fromisoformat(move_data['timestamp']) if move_data.get('timestamp') else datetime.utcnow(),
                            is_valid=move_data.get('is_valid', True)
                        )
                        move_records.append(move_record)
                
                if move_records:
                    session.add_all(move_records)
                    await session.commit()
                    
                    logger.info(f"Persisted {len(move_records)} moves for game {room_id}")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Failed to persist moves for game {room_id}: {str(e)}")
            return False
    
    # Statistics and Analytics
    async def _update_player_statistics_from_game(self, game_data: Dict[str, Any]):
        """Update player statistics based on completed game"""
        try:
            async with self.session_manager.get_session() as session:
                participants = game_data.get('participants', [])
                
                for participant_data in participants:
                    # Get player
                    player_stmt = select(Player).where(Player.username == participant_data['username'])
                    player_result = await session.execute(player_stmt)
                    player = player_result.scalar_one_or_none()
                    
                    if player:
                        # Update basic stats
                        player.total_games += 1
                        if participant_data.get('won', False):
                            player.wins += 1
                        
                        # Update rating (simple system for now)
                        if participant_data.get('won', False):
                            player.rating += 25
                        else:
                            player.rating = max(800, player.rating - 15)
                        
                        player.last_seen = datetime.utcnow()
                        
                        # Update detailed statistics
                        await self._update_detailed_player_statistics(
                            session, player.id, participant_data, game_data
                        )
                
                await session.commit()
                self.operation_counts['statistics_updates'] += 1
                
        except Exception as e:
            logger.error(f"Failed to update player statistics: {str(e)}")
    
    async def _update_detailed_player_statistics(
        self, 
        session: AsyncSession, 
        player_id: UUID, 
        participant_data: Dict[str, Any], 
        game_data: Dict[str, Any]
    ):
        """Update detailed player statistics"""
        statistics_to_update = [
            ('games_as_hakem', 1 if participant_data.get('hokm_selected') else 0),
            ('total_tricks_won', participant_data.get('tricks_won', 0)),
            ('total_cards_played', participant_data.get('cards_played', 0)),
            ('total_score_earned', participant_data.get('score_earned', 0)),
            ('games_in_team_1', 1 if participant_data.get('team') == 'team1' else 0),
            ('games_in_team_2', 1 if participant_data.get('team') == 'team2' else 0),
        ]
        
        # Add win statistics by team
        if participant_data.get('won'):
            if participant_data.get('team') == 'team1':
                statistics_to_update.append(('wins_as_team_1', 1))
            else:
                statistics_to_update.append(('wins_as_team_2', 1))
        
        # Update statistics
        for stat_name, stat_value in statistics_to_update:
            if stat_value > 0:  # Only update if there's a value to add
                # Check if statistic exists
                stat_stmt = select(PlayerStatistic).where(
                    and_(
                        PlayerStatistic.player_id == player_id,
                        PlayerStatistic.statistic_name == stat_name
                    )
                )
                stat_result = await session.execute(stat_stmt)
                existing_stat = stat_result.scalar_one_or_none()
                
                if existing_stat:
                    # Update existing
                    existing_stat.statistic_value += stat_value
                    existing_stat.games_count += 1
                    existing_stat.last_updated = datetime.utcnow()
                else:
                    # Create new
                    new_stat = PlayerStatistic(
                        id=uuid4(),
                        player_id=player_id,
                        statistic_name=stat_name,
                        statistic_value=stat_value,
                        games_count=1,
                        last_updated=datetime.utcnow()
                    )
                    session.add(new_stat)
    
    async def get_leaderboard(self, limit: int = 50, stat_type: str = 'rating') -> List[Dict[str, Any]]:
        """Get player leaderboard"""
        try:
            async with self.session_manager.get_session() as session:
                if stat_type == 'rating':
                    stmt = (
                        select(Player)
                        .where(and_(Player.is_active == True, Player.total_games >= 5))
                        .order_by(Player.rating.desc())
                        .limit(limit)
                    )
                elif stat_type == 'wins':
                    stmt = (
                        select(Player)
                        .where(Player.is_active == True)
                        .order_by(Player.wins.desc())
                        .limit(limit)
                    )
                elif stat_type == 'win_rate':
                    stmt = (
                        select(Player)
                        .where(and_(Player.is_active == True, Player.total_games >= 10))
                        .order_by((Player.wins / Player.total_games).desc())
                        .limit(limit)
                    )
                else:
                    # Default to rating
                    stmt = (
                        select(Player)
                        .where(Player.is_active == True)
                        .order_by(Player.rating.desc())
                        .limit(limit)
                    )
                
                result = await session.execute(stmt)
                players = result.scalars().all()
                
                leaderboard = []
                for i, player in enumerate(players, 1):
                    player_data = {
                        'rank': i,
                        'player_id': str(player.id),
                        'username': player.username,
                        'display_name': player.display_name,
                        'rating': float(player.rating) if player.rating else 0.0,
                        'total_games': player.total_games,
                        'wins': player.wins,
                        'win_rate': (player.wins / player.total_games * 100) if player.total_games > 0 else 0
                    }
                    leaderboard.append(player_data)
                
                self.operation_counts['analytics_queries'] += 1
                return leaderboard
                
        except Exception as e:
            logger.error(f"Failed to get leaderboard: {str(e)}")
            return []
    
    async def get_game_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get game analytics for the specified period"""
        try:
            async with self.session_manager.get_session() as session:
                start_date = datetime.utcnow() - timedelta(days=days)
                
                # Total games
                total_games_stmt = select(func.count(GameSession.id)).where(
                    GameSession.completed_at >= start_date
                )
                total_games_result = await session.execute(total_games_stmt)
                total_games = total_games_result.scalar() or 0
                
                # Active players
                active_players_stmt = select(func.count(func.distinct(Player.id))).where(
                    Player.last_seen >= start_date
                )
                active_players_result = await session.execute(active_players_stmt)
                active_players = active_players_result.scalar() or 0
                
                # Average game duration
                avg_duration_stmt = select(func.avg(GameSession.duration_seconds)).where(
                    and_(
                        GameSession.completed_at >= start_date,
                        GameSession.duration_seconds.isnot(None)
                    )
                )
                avg_duration_result = await session.execute(avg_duration_stmt)
                avg_duration = avg_duration_result.scalar() or 0
                
                # Games per day
                games_per_day_stmt = select(
                    func.date(GameSession.completed_at).label('date'),
                    func.count(GameSession.id).label('count')
                ).where(
                    GameSession.completed_at >= start_date
                ).group_by(
                    func.date(GameSession.completed_at)
                ).order_by('date')
                
                games_per_day_result = await session.execute(games_per_day_stmt)
                games_per_day = [
                    {'date': str(row.date), 'count': row.count}
                    for row in games_per_day_result
                ]
                
                analytics = {
                    'period_days': days,
                    'total_games': total_games,
                    'active_players': active_players,
                    'average_game_duration_minutes': int(avg_duration / 60) if avg_duration else 0,
                    'games_per_day': games_per_day,
                    'generated_at': datetime.utcnow().isoformat()
                }
                
                self.operation_counts['analytics_queries'] += 1
                return analytics
                
        except Exception as e:
            logger.error(f"Failed to get game analytics: {str(e)}")
            return {}
    
    # Batch Processing
    async def start_batch_processing(self):
        """Start batch processing task"""
        if self.batch_running:
            return
        
        self.batch_running = True
        self.batch_task = asyncio.create_task(self._batch_processing_loop())
        logger.info("Batch processing started")
    
    async def stop_batch_processing(self):
        """Stop batch processing task"""
        if not self.batch_running:
            return
        
        self.batch_running = False
        if self.batch_task:
            self.batch_task.cancel()
            try:
                await self.batch_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Batch processing stopped")
    
    async def _batch_processing_loop(self):
        """Main batch processing loop"""
        while self.batch_running:
            try:
                await self._process_batches()
                await asyncio.sleep(self.config.batch_timeout)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Batch processing error: {str(e)}")
                await asyncio.sleep(5)
    
    async def _process_batches(self):
        """Process pending batches"""
        if not self.batch_queue:
            return
        
        for operation_type, items in self.batch_queue.items():
            if len(items) >= self.config.batch_size or self._batch_timeout_reached(items):
                try:
                    await self._execute_batch(operation_type, items)
                    self.batch_queue[operation_type] = []
                    self.operation_counts['batch_operations'] += 1
                except Exception as e:
                    logger.error(f"Failed to execute batch {operation_type}: {str(e)}")
    
    def _batch_timeout_reached(self, items: List[Dict[str, Any]]) -> bool:
        """Check if batch timeout has been reached"""
        if not items:
            return False
        
        oldest_item = min(items, key=lambda x: x.get('timestamp', datetime.utcnow()))
        oldest_time = oldest_item.get('timestamp', datetime.utcnow())
        
        if isinstance(oldest_time, str):
            oldest_time = datetime.fromisoformat(oldest_time)
        
        return (datetime.utcnow() - oldest_time).total_seconds() >= self.config.batch_timeout
    
    async def _execute_batch(self, operation_type: str, items: List[Dict[str, Any]]):
        """Execute a batch of operations"""
        if operation_type == 'performance_metrics':
            await self._batch_insert_performance_metrics(items)
        # Add other batch operations as needed
    
    async def _batch_insert_performance_metrics(self, metrics: List[Dict[str, Any]]):
        """Batch insert performance metrics"""
        try:
            async with self.session_manager.get_session() as session:
                metric_objects = []
                for metric_data in metrics:
                    metric = PerformanceMetric(
                        id=uuid4(),
                        metric_name=metric_data['metric_name'],
                        metric_category=metric_data.get('metric_category', 'general'),
                        metric_value=metric_data.get('metric_value'),
                        metric_count=metric_data.get('metric_count'),
                        metric_text=metric_data.get('metric_text'),
                        server_instance=metric_data.get('server_instance'),
                        metadata_context=metric_data.get('metadata', {}),
                        tags=metric_data.get('tags', []),
                        timestamp=datetime.fromisoformat(metric_data['timestamp']) if metric_data.get('timestamp') else datetime.utcnow()
                    )
                    metric_objects.append(metric)
                
                session.add_all(metric_objects)
                await session.commit()
                
                logger.debug(f"Batch inserted {len(metric_objects)} performance metrics")
                
        except Exception as e:
            logger.error(f"Failed to batch insert performance metrics: {str(e)}")
    
    # Cleanup and Maintenance
    async def cleanup_old_records(self) -> Dict[str, int]:
        """Cleanup old records based on configuration"""
        cleanup_results = {}
        
        if not self.config.cleanup_old_records:
            return cleanup_results
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.config.old_records_threshold_days)
            
            async with self.session_manager.get_session() as session:
                # Cleanup old performance metrics
                old_metrics_stmt = delete(PerformanceMetric).where(
                    PerformanceMetric.timestamp < cutoff_date
                )
                metrics_result = await session.execute(old_metrics_stmt)
                cleanup_results['performance_metrics'] = metrics_result.rowcount
                
                # Cleanup old game moves (keep moves for completed games)
                old_moves_stmt = delete(GameMove).where(
                    and_(
                        GameMove.timestamp < cutoff_date,
                        GameMove.game_session_id.in_(
                            select(GameSession.id).where(
                                GameSession.completed_at < cutoff_date
                            )
                        )
                    )
                )
                moves_result = await session.execute(old_moves_stmt)
                cleanup_results['game_moves'] = moves_result.rowcount
                
                await session.commit()
                
                logger.info(f"Cleaned up old records: {cleanup_results}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old records: {str(e)}")
        
        return cleanup_results
    
    # Health and Monitoring
    async def get_health_status(self) -> Dict[str, Any]:
        """Get health status of PostgreSQL persistence"""
        status = {
            'healthy': True,
            'batch_processing_running': self.batch_running,
            'batch_queue_sizes': {k: len(v) for k, v in self.batch_queue.items()},
            'operation_counts': self.operation_counts.copy()
        }
        
        try:
            async with self.session_manager.get_session() as session:
                await session.execute(text("SELECT 1"))
        except Exception as e:
            status['healthy'] = False
            status['error'] = str(e)
        
        return status
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.stop_batch_processing()
        logger.info("PostgreSQL Persistence Manager cleaned up")
