"""
Database Configuration Management for Hokm Game Server
Support for multiple environments with proper connection pooling settings
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from urllib.parse import quote_plus
import logging

logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    """
    Database configuration with environment-specific settings
    Optimized for real-time gaming workloads with proper connection pooling
    """
    # Database connection settings
    host: str = "localhost"
    port: int = 5432
    database: str = "hokm_game"
    username: str = "hokm_app"
    password: str = "app_secure_password"
    
    # Connection pool settings (critical for async/WebSocket performance)
    pool_size: int = 20  # Number of persistent connections
    max_overflow: int = 30  # Additional connections during peak load
    pool_timeout: int = 30  # Seconds to wait for connection
    pool_recycle: int = 3600  # Recycle connections every hour
    pool_pre_ping: bool = True  # Validate connections before use
    
    # Query optimization settings
    echo_sql: bool = False  # Log all SQL queries (disable in production)
    echo_pool: bool = False  # Log connection pool events
    query_timeout: int = 30  # Query timeout in seconds
    
    # Transaction settings
    autocommit: bool = False
    autoflush: bool = True
    expire_on_commit: bool = False  # Keep objects usable after commit
    
    # Environment-specific settings
    environment: str = "development"
    ssl_mode: str = "prefer"  # prefer, require, disable
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None
    ssl_ca_path: Optional[str] = None
    
    # Monitoring and debugging
    enable_query_logging: bool = False
    slow_query_threshold: float = 1.0  # Log queries slower than 1 second
    log_level: str = "INFO"
    
    # Connection string components
    driver: str = "postgresql+asyncpg"  # Async PostgreSQL driver
    charset: str = "utf8"
    
    # Additional connection parameters
    connect_args: Dict[str, Any] = field(default_factory=lambda: {
        'command_timeout': 30,
        'server_settings': {
            'jit': 'off',  # Disable JIT for consistent performance
            'application_name': 'hokm_game_server'
        }
    })
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        if self.pool_size <= 0:
            raise ValueError("pool_size must be positive")
        if self.max_overflow < 0:
            raise ValueError("max_overflow cannot be negative")
        if self.pool_timeout <= 0:
            raise ValueError("pool_timeout must be positive")
            
    @property
    def connection_url(self) -> str:
        """
        Generate SQLAlchemy connection URL with proper escaping
        Includes all necessary parameters for production use
        """
        # URL-encode password to handle special characters
        encoded_password = quote_plus(self.password)
        
        # Base connection URL
        url = f"{self.driver}://{self.username}:{encoded_password}@{self.host}:{self.port}/{self.database}"
        
        # Add SSL parameters if configured
        params = []
        if self.ssl_mode != "disable":
            params.append(f"sslmode={self.ssl_mode}")
            if self.ssl_cert_path:
                params.append(f"sslcert={self.ssl_cert_path}")
            if self.ssl_key_path:
                params.append(f"sslkey={self.ssl_key_path}")
            if self.ssl_ca_path:
                params.append(f"sslrootcert={self.ssl_ca_path}")
        
        # Add charset
        params.append(f"charset={self.charset}")
        
        # Append parameters to URL
        if params:
            url += "?" + "&".join(params)
            
        return url
    
    @property
    def engine_options(self) -> Dict[str, Any]:
        """
        Generate SQLAlchemy engine options optimized for async WebSocket servers
        These settings are critical for maintaining responsive real-time communication
        """
        options = {
            # Connection pool configuration
            'pool_size': self.pool_size,
            'max_overflow': self.max_overflow,
            'pool_timeout': self.pool_timeout,
            'pool_recycle': self.pool_recycle,
            'pool_pre_ping': self.pool_pre_ping,
            
            # Async-specific settings
            'connect_args': self.connect_args,
            
            # Query and logging settings
            'echo': self.echo_sql,
            'echo_pool': self.echo_pool,
            
            # Performance optimization
            'future': True,  # Enable SQLAlchemy 2.0 mode
        }
        
        # Add environment-specific optimizations
        if self.environment == "production":
            # Production optimizations
            options.update({
                'pool_size': max(self.pool_size, 25),  # Minimum 25 connections for production
                'max_overflow': max(self.max_overflow, 50),  # Higher overflow for traffic spikes
                'echo': False,  # Never log SQL in production
                'echo_pool': False,
            })
        elif self.environment == "development":
            # Development debugging
            options.update({
                'echo': self.echo_sql,
                'echo_pool': self.echo_pool,
            })
            
        return options
    
    @classmethod
    def from_env(cls, env_prefix: str = "DB_") -> "DatabaseConfig":
        """
        Create configuration from environment variables
        Supports multiple deployment environments with proper defaults
        """
        def get_env_bool(key: str, default: bool) -> bool:
            """Convert environment variable to boolean"""
            value = os.getenv(f"{env_prefix}{key}")
            if value is None:
                return default
            return value.lower() in ('true', '1', 'yes', 'on')
        
        def get_env_int(key: str, default: int) -> int:
            """Convert environment variable to integer"""
            value = os.getenv(f"{env_prefix}{key}")
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                logger.warning(f"Invalid integer value for {env_prefix}{key}: {value}, using default: {default}")
                return default
        
        def get_env_float(key: str, default: float) -> float:
            """Convert environment variable to float"""
            value = os.getenv(f"{env_prefix}{key}")
            if value is None:
                return default
            try:
                return float(value)
            except ValueError:
                logger.warning(f"Invalid float value for {env_prefix}{key}: {value}, using default: {default}")
                return default
        
        # Determine environment
        environment = os.getenv("ENVIRONMENT", "development").lower()
        
        # Environment-specific defaults
        if environment == "production":
            default_pool_size = 25
            default_max_overflow = 50
            default_echo_sql = False
        elif environment == "test":
            default_pool_size = 5
            default_max_overflow = 10
            default_echo_sql = False
        else:  # development
            default_pool_size = 10
            default_max_overflow = 20
            default_echo_sql = get_env_bool("ECHO_SQL", False)
        
        return cls(
            # Connection settings
            host=os.getenv(f"{env_prefix}HOST", "localhost"),
            port=get_env_int("PORT", 5432),
            database=os.getenv(f"{env_prefix}DATABASE", "hokm_game"),
            username=os.getenv(f"{env_prefix}USERNAME", "hokm_app"),
            password=os.getenv(f"{env_prefix}PASSWORD", "app_secure_password"),
            
            # Pool settings
            pool_size=get_env_int("POOL_SIZE", default_pool_size),
            max_overflow=get_env_int("MAX_OVERFLOW", default_max_overflow),
            pool_timeout=get_env_int("POOL_TIMEOUT", 30),
            pool_recycle=get_env_int("POOL_RECYCLE", 3600),
            pool_pre_ping=get_env_bool("POOL_PRE_PING", True),
            
            # Query settings
            echo_sql=get_env_bool("ECHO_SQL", default_echo_sql),
            echo_pool=get_env_bool("ECHO_POOL", False),
            query_timeout=get_env_int("QUERY_TIMEOUT", 30),
            
            # Environment
            environment=environment,
            ssl_mode=os.getenv(f"{env_prefix}SSL_MODE", "prefer"),
            ssl_cert_path=os.getenv(f"{env_prefix}SSL_CERT"),
            ssl_key_path=os.getenv(f"{env_prefix}SSL_KEY"),
            ssl_ca_path=os.getenv(f"{env_prefix}SSL_CA"),
            
            # Monitoring
            enable_query_logging=get_env_bool("ENABLE_QUERY_LOGGING", False),
            slow_query_threshold=get_env_float("SLOW_QUERY_THRESHOLD", 1.0),
            log_level=os.getenv(f"{env_prefix}LOG_LEVEL", "INFO"),
        )
    
    @classmethod
    def for_testing(cls) -> "DatabaseConfig":
        """
        Create configuration optimized for testing
        Uses smaller connection pools and enables debugging
        """
        return cls(
            database="hokm_game_test",
            pool_size=5,
            max_overflow=10,
            pool_timeout=10,
            environment="test",
            echo_sql=False,  # Keep quiet during tests
            echo_pool=False,
            enable_query_logging=False,
        )
    
    @classmethod
    def for_development(cls) -> "DatabaseConfig":
        """
        Create configuration optimized for development
        Enables debugging and uses moderate connection pools
        """
        return cls(
            pool_size=10,
            max_overflow=20,
            environment="development",
            echo_sql=True,
            echo_pool=False,
            enable_query_logging=True,
            slow_query_threshold=0.5,  # Log slower queries in dev
        )
    
    @classmethod
    def for_production(cls) -> "DatabaseConfig":
        """
        Create configuration optimized for production
        Uses large connection pools and disables debugging
        """
        return cls.from_env().replace(
            environment="production",
            pool_size=max(25, cls.from_env().pool_size),
            max_overflow=max(50, cls.from_env().max_overflow),
            echo_sql=False,
            echo_pool=False,
            enable_query_logging=False,
        )
    
    def replace(self, **kwargs) -> "DatabaseConfig":
        """Create a new config with updated values"""
        import copy
        new_config = copy.deepcopy(self)
        for key, value in kwargs.items():
            if hasattr(new_config, key):
                setattr(new_config, key, value)
            else:
                raise ValueError(f"Unknown configuration key: {key}")
        return new_config


# Global configuration instance
_database_config: Optional[DatabaseConfig] = None


def get_database_config() -> DatabaseConfig:
    """
    Get the global database configuration
    Thread-safe singleton pattern for configuration management
    """
    global _database_config
    if _database_config is None:
        _database_config = DatabaseConfig.from_env()
    return _database_config


def set_database_config(config: DatabaseConfig) -> None:
    """
    Set the global database configuration
    Useful for testing and custom configurations
    """
    global _database_config
    _database_config = config


def configure_logging(config: DatabaseConfig) -> None:
    """
    Configure logging based on database configuration
    Sets up appropriate log levels for different environments
    """
    # Configure SQLAlchemy logging
    sqlalchemy_logger = logging.getLogger('sqlalchemy')
    
    if config.environment == "production":
        # Minimal logging in production
        sqlalchemy_logger.setLevel(logging.WARNING)
    elif config.environment == "development":
        # Detailed logging in development
        if config.echo_sql:
            sqlalchemy_logger.setLevel(logging.INFO)
        else:
            sqlalchemy_logger.setLevel(logging.WARNING)
    else:  # test
        # Quiet logging during tests
        sqlalchemy_logger.setLevel(logging.ERROR)
    
    # Configure database-specific logger
    db_logger = logging.getLogger('hokm_game.database')
    db_logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    
    # Log configuration summary
    logger.info(f"Database configuration loaded for environment: {config.environment}")
    logger.info(f"Connection pool: {config.pool_size} + {config.max_overflow} overflow")
    logger.info(f"SQL echo: {config.echo_sql}, Query logging: {config.enable_query_logging}")
