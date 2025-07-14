#!/usr/bin/env python3
"""
Redis Sentinel-Aware Manager for Hokm Game
Provides automatic failover support for Redis master-replica setup
"""
import asyncio
import aioredis
import logging
from typing import Optional, List, Dict, Any
import time
import json

logger = logging.getLogger(__name__)

class RedisSentinelManager:
    """
    Redis manager with Sentinel support for automatic failover
    """
    
    def __init__(
        self,
        sentinels: List[tuple] = None,
        master_name: str = "hokm-master",
        password: str = "redis_game_password123",
        db: int = 0,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        retry_on_timeout: bool = True,
        health_check_interval: int = 30
    ):
        # Default Sentinel configurations
        self.sentinels = sentinels or [
            ('localhost', 26379),
            ('localhost', 26380), 
            ('localhost', 26381)
        ]
        self.master_name = master_name
        self.password = password
        self.db = db
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout
        self.health_check_interval = health_check_interval
        
        # Connection objects
        self.sentinel = None
        self.redis_master = None
        self.redis_replica = None
        self.current_master_addr = None
        
        # Health monitoring
        self.last_health_check = 0
        self.is_healthy = False
        self.connection_errors = 0
        self.max_connection_errors = 3
        
        # Statistics
        self.stats = {
            'connections_created': 0,
            'failovers_detected': 0,
            'operations_completed': 0,
            'errors_encountered': 0
        }
        
    async def initialize(self) -> bool:
        """
        Initialize Sentinel connection and discover Redis master
        """
        try:
            logger.info("Initializing Redis Sentinel Manager...")
            
            # Try to connect to Sentinel
            await self._connect_sentinel()
            
            # Discover master and replica
            await self._discover_redis_instances()
            
            # Test connections
            await self._test_connections()
            
            self.is_healthy = True
            logger.info("✅ Redis Sentinel Manager initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Redis Sentinel Manager: {e}")
            # Fallback to direct Redis connection
            return await self._fallback_direct_connection()
    
    async def _connect_sentinel(self):
        """Connect to Redis Sentinel"""
        try:
            # Import redis-sentinel
            import redis.sentinel
            
            # Create Sentinel connection
            self.sentinel = redis.sentinel.Sentinel(
                self.sentinels,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                password=self.password
            )
            
            # Test Sentinel connection
            masters = self.sentinel.discover_master(self.master_name)
            logger.info(f"📡 Connected to Sentinel, master at: {masters}")
            
        except Exception as e:
            logger.warning(f"⚠️  Sentinel connection failed: {e}")
            raise
    
    async def _discover_redis_instances(self):
        """Discover Redis master and replica through Sentinel"""
        try:
            if self.sentinel:
                # Get master connection through Sentinel
                self.redis_master = self.sentinel.master_for(
                    self.master_name,
                    socket_timeout=self.socket_timeout,
                    password=self.password,
                    db=self.db
                )
                
                # Get replica connection through Sentinel
                replicas = self.sentinel.slave_for(
                    self.master_name,
                    socket_timeout=self.socket_timeout,
                    password=self.password,
                    db=self.db
                )
                
                # Track current master address
                master_addr = self.sentinel.discover_master(self.master_name)
                self.current_master_addr = f"{master_addr[0]}:{master_addr[1]}"
                
                logger.info(f"🔍 Discovered Redis master: {self.current_master_addr}")
                self.stats['connections_created'] += 1
                
            else:
                # Direct connection fallback
                await self._setup_direct_connections()
                
        except Exception as e:
            logger.error(f"❌ Failed to discover Redis instances: {e}")
            await self._setup_direct_connections()
    
    async def _setup_direct_connections(self):
        """Fallback: Setup direct Redis connections"""
        try:
            # Try master connection
            self.redis_master = aioredis.from_url(
                f"redis://:{self.password}@localhost:6379/{self.db}",
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                retry_on_timeout=self.retry_on_timeout
            )
            
            # Try replica connection
            self.redis_replica = aioredis.from_url(
                f"redis://:{self.password}@localhost:6380/{self.db}",
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                retry_on_timeout=self.retry_on_timeout
            )
            
            self.current_master_addr = "localhost:6379"
            logger.info("📡 Using direct Redis connections (no Sentinel)")
            
        except Exception as e:
            logger.error(f"❌ Direct Redis connection failed: {e}")
            raise
    
    async def _fallback_direct_connection(self) -> bool:
        """Fallback to direct Redis connection without Sentinel"""
        try:
            logger.warning("⚠️  Falling back to direct Redis connection...")
            await self._setup_direct_connections()
            await self._test_connections()
            self.is_healthy = True
            logger.info("✅ Direct Redis connection established")
            return True
        except Exception as e:
            logger.error(f"❌ All Redis connection methods failed: {e}")
            return False
    
    async def _test_connections(self):
        """Test Redis connections"""
        try:
            # Test master connection
            if self.redis_master:
                await self.redis_master.ping()
                logger.info("✅ Master connection test passed")
            
            # Test replica connection
            if self.redis_replica:
                await self.redis_replica.ping()
                logger.info("✅ Replica connection test passed")
                
        except Exception as e:
            logger.warning(f"⚠️  Connection test failed: {e}")
            raise
    
    async def get_connection(self, read_only: bool = False) -> aioredis.Redis:
        """
        Get Redis connection with automatic failover
        
        Args:
            read_only: If True, prefer replica for read operations
            
        Returns:
            Redis connection object
        """
        try:
            # Health check
            await self._health_check()
            
            # Return appropriate connection
            if read_only and self.redis_replica:
                try:
                    await self.redis_replica.ping()
                    return self.redis_replica
                except:
                    # Replica failed, use master
                    logger.warning("⚠️  Replica unavailable, using master for read")
            
            # Use master connection
            if self.redis_master:
                await self.redis_master.ping()
                return self.redis_master
            
            # Last resort: try to reconnect
            logger.warning("🔄 Attempting to reconnect to Redis...")
            await self.initialize()
            return self.redis_master
            
        except Exception as e:
            logger.error(f"❌ Failed to get Redis connection: {e}")
            self.connection_errors += 1
            if self.connection_errors >= self.max_connection_errors:
                await self._handle_connection_failure()
            raise
    
    async def _health_check(self):
        """Periodic health check for Redis connections"""
        current_time = time.time()
        if current_time - self.last_health_check < self.health_check_interval:
            return  # Skip if checked recently
        
        try:
            # Check if master address changed (failover detection)
            if self.sentinel:
                new_master_addr = self.sentinel.discover_master(self.master_name)
                new_addr_str = f"{new_master_addr[0]}:{new_master_addr[1]}"
                
                if new_addr_str != self.current_master_addr:
                    logger.warning(f"🔄 Failover detected! Master changed: {self.current_master_addr} -> {new_addr_str}")
                    self.current_master_addr = new_addr_str
                    self.stats['failovers_detected'] += 1
                    
                    # Reconnect to new master
                    await self._discover_redis_instances()
            
            # Reset error counter on successful health check
            self.connection_errors = 0
            self.last_health_check = current_time
            
        except Exception as e:
            logger.warning(f"⚠️  Health check failed: {e}")
    
    async def _handle_connection_failure(self):
        """Handle persistent connection failures"""
        logger.error("❌ Maximum connection errors reached, attempting full reconnection...")
        try:
            # Close existing connections
            await self.close()
            
            # Reinitialize
            await self.initialize()
            
            # Reset error counter
            self.connection_errors = 0
            
        except Exception as e:
            logger.error(f"❌ Full reconnection failed: {e}")
            self.is_healthy = False
    
    async def set(self, key: str, value: str, ex: int = None) -> bool:
        """Set key-value with automatic failover"""
        try:
            redis_conn = await self.get_connection(read_only=False)
            result = await redis_conn.set(key, value, ex=ex)
            self.stats['operations_completed'] += 1
            return result
        except Exception as e:
            logger.error(f"❌ Redis SET failed for key {key}: {e}")
            self.stats['errors_encountered'] += 1
            raise
    
    async def get(self, key: str) -> Optional[str]:
        """Get value with automatic failover"""
        try:
            redis_conn = await self.get_connection(read_only=True)
            result = await redis_conn.get(key)
            self.stats['operations_completed'] += 1
            return result.decode('utf-8') if result else None
        except Exception as e:
            logger.error(f"❌ Redis GET failed for key {key}: {e}")
            self.stats['errors_encountered'] += 1
            raise
    
    async def delete(self, key: str) -> int:
        """Delete key with automatic failover"""
        try:
            redis_conn = await self.get_connection(read_only=False)
            result = await redis_conn.delete(key)
            self.stats['operations_completed'] += 1
            return result
        except Exception as e:
            logger.error(f"❌ Redis DELETE failed for key {key}: {e}")
            self.stats['errors_encountered'] += 1
            raise
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        """Hash get with automatic failover"""
        try:
            redis_conn = await self.get_connection(read_only=True)
            result = await redis_conn.hget(name, key)
            self.stats['operations_completed'] += 1
            return result.decode('utf-8') if result else None
        except Exception as e:
            logger.error(f"❌ Redis HGET failed for {name}.{key}: {e}")
            self.stats['errors_encountered'] += 1
            raise
    
    async def hset(self, name: str, key: str, value: str) -> int:
        """Hash set with automatic failover"""
        try:
            redis_conn = await self.get_connection(read_only=False)
            result = await redis_conn.hset(name, key, value)
            self.stats['operations_completed'] += 1
            return result
        except Exception as e:
            logger.error(f"❌ Redis HSET failed for {name}.{key}: {e}")
            self.stats['errors_encountered'] += 1
            raise
    
    async def exists(self, key: str) -> bool:
        """Check key existence with automatic failover"""
        try:
            redis_conn = await self.get_connection(read_only=True)
            result = await redis_conn.exists(key)
            self.stats['operations_completed'] += 1
            return bool(result)
        except Exception as e:
            logger.error(f"❌ Redis EXISTS failed for key {key}: {e}")
            self.stats['errors_encountered'] += 1
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Redis manager statistics"""
        return {
            **self.stats,
            'is_healthy': self.is_healthy,
            'current_master': self.current_master_addr,
            'connection_errors': self.connection_errors,
            'last_health_check': self.last_health_check
        }
    
    async def close(self):
        """Close all Redis connections"""
        try:
            if self.redis_master:
                await self.redis_master.close()
            if self.redis_replica:
                await self.redis_replica.close()
            logger.info("🔒 Redis connections closed")
        except Exception as e:
            logger.warning(f"⚠️  Error closing Redis connections: {e}")

# Global Redis manager instance
redis_manager = None

async def get_redis_manager() -> RedisSentinelManager:
    """Get global Redis manager instance"""
    global redis_manager
    if redis_manager is None:
        redis_manager = RedisSentinelManager()
        await redis_manager.initialize()
    return redis_manager
