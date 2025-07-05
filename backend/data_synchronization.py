"""
Data Synchronization Manager for Hybrid Redis + PostgreSQL Architecture
Handles synchronization, transactions, and consistency between data layers
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import uuid
from contextlib import asynccontextmanager

from backend.hybrid_data_layer import HybridDataLayer
from backend.redis_game_state import RedisGameStateManager
from backend.postgresql_persistence import PostgreSQLPersistenceManager

logger = logging.getLogger(__name__)

class SyncOperation(Enum):
    """Types of synchronization operations"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    BATCH_UPDATE = "batch_update"

class SyncPriority(Enum):
    """Synchronization priority levels"""
    HIGH = "high"       # Immediate sync (game completion, critical events)
    MEDIUM = "medium"   # Regular sync (player stats, game states)
    LOW = "low"         # Background sync (analytics, cleanup)

class TransactionType(Enum):
    """Types of hybrid transactions"""
    REDIS_ONLY = "redis_only"
    POSTGRESQL_ONLY = "postgresql_only"
    HYBRID_WRITE_THROUGH = "hybrid_write_through"
    HYBRID_WRITE_BEHIND = "hybrid_write_behind"
    HYBRID_EVENTUAL = "hybrid_eventual"

@dataclass
class SyncTask:
    """Synchronization task definition"""
    id: str
    operation: SyncOperation
    priority: SyncPriority
    source_layer: str
    target_layer: str
    data_type: str
    data_key: str
    data_payload: Dict[str, Any]
    created_at: datetime
    retry_count: int = 0
    max_retries: int = 3
    scheduled_for: Optional[datetime] = None

@dataclass
class SyncConfig:
    """Configuration for data synchronization"""
    # Sync intervals by priority
    high_priority_interval: float = 1.0      # 1 second
    medium_priority_interval: float = 30.0   # 30 seconds
    low_priority_interval: float = 300.0     # 5 minutes
    
    # Batch settings
    batch_size: int = 50
    batch_timeout: float = 10.0
    
    # Retry settings
    max_retries: int = 3
    retry_backoff_multiplier: float = 2.0
    retry_max_delay: float = 60.0
    
    # Error handling
    dead_letter_queue_enabled: bool = True
    error_notification_enabled: bool = True
    
    # Performance
    concurrent_sync_workers: int = 5
    sync_metrics_enabled: bool = True

class DataSynchronizationManager:
    """
    Manages synchronization between Redis and PostgreSQL data layers,
    ensuring data consistency while maintaining performance.
    """
    
    def __init__(
        self,
        redis_manager: RedisGameStateManager,
        postgresql_manager: PostgreSQLPersistenceManager,
        config: SyncConfig = None
    ):
        self.redis_manager = redis_manager
        self.postgresql_manager = postgresql_manager
        self.config = config or SyncConfig()
        
        # Sync queues by priority
        self.sync_queues = {
            SyncPriority.HIGH: asyncio.Queue(),
            SyncPriority.MEDIUM: asyncio.Queue(),
            SyncPriority.LOW: asyncio.Queue()
        }
        
        # Dead letter queue for failed operations
        self.dead_letter_queue = asyncio.Queue()
        
        # Sync workers
        self.sync_workers = []
        self.sync_running = False
        
        # Performance tracking
        self.sync_metrics = {
            'tasks_processed': 0,
            'tasks_failed': 0,
            'tasks_retried': 0,
            'sync_latency_ms': [],
            'last_sync_times': {},
            'error_counts': {}
        }
        
        # Transaction management
        self.active_transactions = {}
        self.transaction_timeout = 30.0  # seconds
        
        logger.info("Data Synchronization Manager initialized")
    
    async def initialize(self):
        """Initialize the synchronization manager"""
        await self.start_sync_workers()
        logger.info("Data Synchronization Manager fully initialized")
    
    # Synchronization Task Management
    async def queue_sync_task(
        self,
        operation: SyncOperation,
        priority: SyncPriority,
        source_layer: str,
        target_layer: str,
        data_type: str,
        data_key: str,
        data_payload: Dict[str, Any],
        delay_seconds: float = 0
    ) -> str:
        """Queue a synchronization task"""
        
        task_id = str(uuid.uuid4())
        scheduled_for = datetime.utcnow() + timedelta(seconds=delay_seconds) if delay_seconds > 0 else None
        
        sync_task = SyncTask(
            id=task_id,
            operation=operation,
            priority=priority,
            source_layer=source_layer,
            target_layer=target_layer,
            data_type=data_type,
            data_key=data_key,
            data_payload=data_payload,
            created_at=datetime.utcnow(),
            scheduled_for=scheduled_for
        )
        
        await self.sync_queues[priority].put(sync_task)
        
        logger.debug(f"Queued sync task {task_id}: {operation.value} {data_type}:{data_key}")
        return task_id
    
    async def start_sync_workers(self):
        """Start synchronization worker tasks"""
        if self.sync_running:
            return
        
        self.sync_running = True
        
        # Start workers for each priority level
        for priority in SyncPriority:
            for i in range(self.config.concurrent_sync_workers):
                worker = asyncio.create_task(
                    self._sync_worker(priority, f"{priority.value}_worker_{i}")
                )
                self.sync_workers.append(worker)
        
        # Start dead letter queue processor
        dlq_worker = asyncio.create_task(self._dead_letter_queue_processor())
        self.sync_workers.append(dlq_worker)
        
        logger.info(f"Started {len(self.sync_workers)} sync workers")
    
    async def stop_sync_workers(self):
        """Stop synchronization worker tasks"""
        if not self.sync_running:
            return
        
        self.sync_running = False
        
        # Cancel all workers
        for worker in self.sync_workers:
            worker.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*self.sync_workers, return_exceptions=True)
        
        self.sync_workers.clear()
        logger.info("Stopped all sync workers")
    
    async def _sync_worker(self, priority: SyncPriority, worker_name: str):
        """Synchronization worker for a specific priority level"""
        queue = self.sync_queues[priority]
        
        # Get sync interval for this priority
        if priority == SyncPriority.HIGH:
            check_interval = self.config.high_priority_interval
        elif priority == SyncPriority.MEDIUM:
            check_interval = self.config.medium_priority_interval
        else:
            check_interval = self.config.low_priority_interval
        
        logger.debug(f"Started sync worker {worker_name}")
        
        while self.sync_running:
            try:
                # Wait for tasks with timeout
                try:
                    task = await asyncio.wait_for(queue.get(), timeout=check_interval)
                    await self._process_sync_task(task)
                except asyncio.TimeoutError:
                    # No tasks available, continue
                    continue
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync worker {worker_name} error: {str(e)}")
                await asyncio.sleep(1)  # Brief pause on error
    
    async def _process_sync_task(self, task: SyncTask):
        """Process a single synchronization task"""
        start_time = datetime.utcnow()
        
        try:
            # Check if task is scheduled for future
            if task.scheduled_for and datetime.utcnow() < task.scheduled_for:
                # Re-queue for later
                delay = (task.scheduled_for - datetime.utcnow()).total_seconds()
                await asyncio.sleep(min(delay, 1.0))  # Sleep max 1 second
                await self.sync_queues[task.priority].put(task)
                return
            
            # Execute the synchronization
            success = await self._execute_sync_operation(task)
            
            if success:
                # Record success metrics
                latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                self.sync_metrics['tasks_processed'] += 1
                self.sync_metrics['sync_latency_ms'].append(latency_ms)
                self.sync_metrics['last_sync_times'][task.data_type] = datetime.utcnow()
                
                # Keep only last 1000 latency measurements
                if len(self.sync_metrics['sync_latency_ms']) > 1000:
                    self.sync_metrics['sync_latency_ms'] = self.sync_metrics['sync_latency_ms'][-1000:]
                
                logger.debug(f"Completed sync task {task.id} in {latency_ms:.2f}ms")
            else:
                # Handle failure
                await self._handle_sync_failure(task)
                
        except Exception as e:
            logger.error(f"Failed to process sync task {task.id}: {str(e)}")
            await self._handle_sync_failure(task, str(e))
    
    async def _execute_sync_operation(self, task: SyncTask) -> bool:
        """Execute the actual synchronization operation"""
        try:
            if task.source_layer == "redis" and task.target_layer == "postgresql":
                return await self._sync_redis_to_postgresql(task)
            elif task.source_layer == "postgresql" and task.target_layer == "redis":
                return await self._sync_postgresql_to_redis(task)
            else:
                logger.error(f"Unsupported sync direction: {task.source_layer} -> {task.target_layer}")
                return False
                
        except Exception as e:
            logger.error(f"Sync operation failed for task {task.id}: {str(e)}")
            return False
    
    async def _sync_redis_to_postgresql(self, task: SyncTask) -> bool:
        """Synchronize data from Redis to PostgreSQL"""
        try:
            data_type = task.data_type
            operation = task.operation
            payload = task.data_payload
            
            if data_type == "game_session":
                if operation == SyncOperation.CREATE:
                    return await self.postgresql_manager.persist_game_session(payload)
                elif operation == SyncOperation.UPDATE:
                    # Update existing game session
                    # This would be implemented based on your specific needs
                    return True
                    
            elif data_type == "game_moves":
                if operation == SyncOperation.BATCH_UPDATE:
                    moves = payload.get('moves', [])
                    room_id = payload.get('room_id')
                    return await self.postgresql_manager.persist_game_moves(room_id, moves)
                    
            elif data_type == "player_statistics":
                if operation == SyncOperation.UPDATE:
                    # Update player statistics
                    # This would be implemented based on your specific needs
                    return True
            
            return True
            
        except Exception as e:
            logger.error(f"Redis to PostgreSQL sync failed: {str(e)}")
            return False
    
    async def _sync_postgresql_to_redis(self, task: SyncTask) -> bool:
        """Synchronize data from PostgreSQL to Redis"""
        try:
            data_type = task.data_type
            operation = task.operation
            payload = task.data_payload
            
            if data_type == "player_profile":
                if operation == SyncOperation.UPDATE:
                    # Cache updated player profile in Redis
                    player_id = task.data_key
                    # Implementation would depend on your Redis structure
                    return True
                    
            elif data_type == "leaderboard":
                if operation == SyncOperation.UPDATE:
                    # Update cached leaderboard in Redis
                    return True
            
            return True
            
        except Exception as e:
            logger.error(f"PostgreSQL to Redis sync failed: {str(e)}")
            return False
    
    async def _handle_sync_failure(self, task: SyncTask, error_msg: str = ""):
        """Handle synchronization task failure"""
        task.retry_count += 1
        
        # Update error metrics
        self.sync_metrics['tasks_failed'] += 1
        error_key = f"{task.data_type}_{task.operation.value}"
        self.sync_metrics['error_counts'][error_key] = self.sync_metrics['error_counts'].get(error_key, 0) + 1
        
        if task.retry_count <= task.max_retries:
            # Calculate retry delay with exponential backoff
            delay = min(
                self.config.retry_backoff_multiplier ** (task.retry_count - 1),
                self.config.retry_max_delay
            )
            
            task.scheduled_for = datetime.utcnow() + timedelta(seconds=delay)
            
            # Re-queue for retry
            await self.sync_queues[task.priority].put(task)
            
            self.sync_metrics['tasks_retried'] += 1
            logger.warning(f"Retrying sync task {task.id} in {delay}s (attempt {task.retry_count})")
        else:
            # Max retries exceeded, send to dead letter queue
            if self.config.dead_letter_queue_enabled:
                await self.dead_letter_queue.put((task, error_msg))
            
            logger.error(f"Sync task {task.id} failed permanently after {task.retry_count} attempts")
    
    async def _dead_letter_queue_processor(self):
        """Process failed tasks from dead letter queue"""
        while self.sync_running:
            try:
                # Check for failed tasks
                try:
                    failed_task, error_msg = await asyncio.wait_for(
                        self.dead_letter_queue.get(), timeout=60.0
                    )
                    
                    # Log the permanently failed task
                    logger.error(
                        f"Permanently failed sync task: {failed_task.id} "
                        f"({failed_task.data_type}:{failed_task.data_key}) - {error_msg}"
                    )
                    
                    # Here you could implement additional error handling:
                    # - Send notifications
                    # - Store in error log database
                    # - Trigger manual intervention workflows
                    
                except asyncio.TimeoutError:
                    continue  # No failed tasks
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dead letter queue processor error: {str(e)}")
                await asyncio.sleep(5)
    
    # Transaction Management
    @asynccontextmanager
    async def hybrid_transaction(
        self,
        transaction_type: TransactionType,
        transaction_id: str = None
    ):
        """Context manager for hybrid transactions across Redis and PostgreSQL"""
        
        if transaction_id is None:
            transaction_id = str(uuid.uuid4())
        
        transaction_start = datetime.utcnow()
        self.active_transactions[transaction_id] = {
            'type': transaction_type,
            'start_time': transaction_start,
            'operations': []
        }
        
        try:
            if transaction_type == TransactionType.REDIS_ONLY:
                # Redis-only transaction (not atomic, best effort)
                yield RedisTransactionContext(self.redis_manager, transaction_id)
                
            elif transaction_type == TransactionType.POSTGRESQL_ONLY:
                # PostgreSQL-only transaction (fully atomic)
                async with self.postgresql_manager.session_manager.get_session() as session:
                    yield PostgreSQLTransactionContext(session, transaction_id)
                    
            elif transaction_type == TransactionType.HYBRID_WRITE_THROUGH:
                # Write to both immediately, PostgreSQL first for consistency
                yield HybridWriteThroughContext(
                    self.redis_manager, 
                    self.postgresql_manager, 
                    self,
                    transaction_id
                )
                
            elif transaction_type == TransactionType.HYBRID_WRITE_BEHIND:
                # Write to Redis immediately, queue PostgreSQL writes
                yield HybridWriteBehindContext(
                    self.redis_manager,
                    self,
                    transaction_id
                )
                
            elif transaction_type == TransactionType.HYBRID_EVENTUAL:
                # Write to primary layer, eventually sync to secondary
                yield HybridEventualContext(
                    self.redis_manager,
                    self,
                    transaction_id
                )
            
            # Transaction completed successfully
            logger.debug(f"Transaction {transaction_id} completed successfully")
            
        except Exception as e:
            # Transaction failed, attempt rollback if possible
            logger.error(f"Transaction {transaction_id} failed: {str(e)}")
            await self._rollback_transaction(transaction_id)
            raise
            
        finally:
            # Cleanup transaction
            if transaction_id in self.active_transactions:
                duration = (datetime.utcnow() - transaction_start).total_seconds()
                logger.debug(f"Transaction {transaction_id} duration: {duration:.3f}s")
                del self.active_transactions[transaction_id]
    
    async def _rollback_transaction(self, transaction_id: str):
        """Attempt to rollback a failed transaction"""
        if transaction_id not in self.active_transactions:
            return
        
        transaction_info = self.active_transactions[transaction_id]
        operations = transaction_info['operations']
        
        # Attempt to rollback operations in reverse order
        for operation in reversed(operations):
            try:
                await self._rollback_operation(operation)
            except Exception as e:
                logger.error(f"Failed to rollback operation in transaction {transaction_id}: {str(e)}")
    
    async def _rollback_operation(self, operation: Dict[str, Any]):
        """Rollback a single operation"""
        # This would implement operation-specific rollback logic
        # For now, just log the attempt
        logger.warning(f"Attempted rollback of operation: {operation}")
    
    # High-level Data Operations
    async def sync_game_completion(self, room_id: str, game_data: Dict[str, Any]) -> bool:
        """Synchronize game completion data with high priority"""
        try:
            # Queue immediate sync to PostgreSQL
            await self.queue_sync_task(
                operation=SyncOperation.CREATE,
                priority=SyncPriority.HIGH,
                source_layer="redis",
                target_layer="postgresql",
                data_type="game_session",
                data_key=room_id,
                data_payload=game_data
            )
            
            # Queue move history sync
            moves = game_data.get('moves', [])
            if moves:
                await self.queue_sync_task(
                    operation=SyncOperation.BATCH_UPDATE,
                    priority=SyncPriority.HIGH,
                    source_layer="redis",
                    target_layer="postgresql",
                    data_type="game_moves",
                    data_key=room_id,
                    data_payload={'room_id': room_id, 'moves': moves}
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync game completion for {room_id}: {str(e)}")
            return False
    
    async def sync_player_statistics(self, player_id: str, stats_update: Dict[str, Any]) -> bool:
        """Synchronize player statistics updates"""
        try:
            await self.queue_sync_task(
                operation=SyncOperation.UPDATE,
                priority=SyncPriority.MEDIUM,
                source_layer="redis",
                target_layer="postgresql",
                data_type="player_statistics",
                data_key=player_id,
                data_payload=stats_update
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync player statistics for {player_id}: {str(e)}")
            return False
    
    async def sync_leaderboard_update(self, leaderboard_data: Dict[str, Any]) -> bool:
        """Synchronize leaderboard updates"""
        try:
            await self.queue_sync_task(
                operation=SyncOperation.UPDATE,
                priority=SyncPriority.LOW,
                source_layer="postgresql",
                target_layer="redis",
                data_type="leaderboard",
                data_key="global",
                data_payload=leaderboard_data
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync leaderboard update: {str(e)}")
            return False
    
    # Monitoring and Health
    async def get_sync_status(self) -> Dict[str, Any]:
        """Get synchronization status and metrics"""
        queue_sizes = {
            priority.value: queue.qsize() 
            for priority, queue in self.sync_queues.items()
        }
        
        avg_latency = 0
        if self.sync_metrics['sync_latency_ms']:
            avg_latency = sum(self.sync_metrics['sync_latency_ms']) / len(self.sync_metrics['sync_latency_ms'])
        
        return {
            'sync_running': self.sync_running,
            'active_workers': len([w for w in self.sync_workers if not w.done()]),
            'queue_sizes': queue_sizes,
            'dead_letter_queue_size': self.dead_letter_queue.qsize(),
            'active_transactions': len(self.active_transactions),
            'metrics': {
                **self.sync_metrics,
                'average_latency_ms': avg_latency
            }
        }
    
    async def force_sync_all_pending(self) -> Dict[str, int]:
        """Force synchronization of all pending tasks (for emergency situations)"""
        results = {'processed': 0, 'failed': 0}
        
        for priority, queue in self.sync_queues.items():
            while not queue.empty():
                try:
                    task = await queue.get()
                    success = await self._execute_sync_operation(task)
                    if success:
                        results['processed'] += 1
                    else:
                        results['failed'] += 1
                except Exception as e:
                    logger.error(f"Force sync failed: {str(e)}")
                    results['failed'] += 1
        
        return results
    
    async def cleanup(self):
        """Cleanup synchronization manager resources"""
        await self.stop_sync_workers()
        self.active_transactions.clear()
        logger.info("Data Synchronization Manager cleaned up")


# Transaction Context Classes
class RedisTransactionContext:
    """Context for Redis-only transactions"""
    def __init__(self, redis_manager: RedisGameStateManager, transaction_id: str):
        self.redis_manager = redis_manager
        self.transaction_id = transaction_id

class PostgreSQLTransactionContext:
    """Context for PostgreSQL-only transactions"""
    def __init__(self, session, transaction_id: str):
        self.session = session
        self.transaction_id = transaction_id

class HybridWriteThroughContext:
    """Context for hybrid write-through transactions"""
    def __init__(self, redis_manager, postgresql_manager, sync_manager, transaction_id: str):
        self.redis_manager = redis_manager
        self.postgresql_manager = postgresql_manager
        self.sync_manager = sync_manager
        self.transaction_id = transaction_id

class HybridWriteBehindContext:
    """Context for hybrid write-behind transactions"""
    def __init__(self, redis_manager, sync_manager, transaction_id: str):
        self.redis_manager = redis_manager
        self.sync_manager = sync_manager
        self.transaction_id = transaction_id

class HybridEventualContext:
    """Context for eventual consistency transactions"""
    def __init__(self, redis_manager, sync_manager, transaction_id: str):
        self.redis_manager = redis_manager
        self.sync_manager = sync_manager
        self.transaction_id = transaction_id
