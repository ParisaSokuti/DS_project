"""
Optimized Database Configuration and Connection Management
High-performance PostgreSQL connection with pooling and monitoring
"""

import os
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.engine import Engine

try:
    from .models import Base
except ImportError:
    from models import Base

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:0097kasraAa22@localhost/hokm_game')

# Create optimized engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging during development
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=20,  # Increased pool size for better performance
    max_overflow=30,
    poolclass=QueuePool,
    connect_args={
        "options": "-c timezone=utc",
        "application_name": "hokm_game_server"
    }
)

# Performance monitoring
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set connection-level optimizations"""
    if 'postgresql' in str(dbapi_connection):
        # PostgreSQL-specific optimizations can be added here
        pass

# Create optimized session factory
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    expire_on_commit=False  # Better for async operations
)

def get_db() -> Generator[Session, None, None]:
    """Database session dependency with proper error handling"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_tables() -> None:
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)


def drop_tables() -> None:
    """Drop all database tables"""
    Base.metadata.drop_all(bind=engine)


def init_database() -> None:
    """Initialize database with tables"""
    create_tables()
    print("Database initialized successfully")


def get_db_health() -> dict:
    """Check database connection health"""
    try:
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            return {
                "status": "healthy",
                "connection_pool": {
                    "size": engine.pool.size(),
                    "checked_in": engine.pool.checkedin(),
                    "checked_out": engine.pool.checkedout(),
                    "overflow": engine.pool.overflow(),
                    "invalid": engine.pool.invalid()
                }
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
    print("Database tables created successfully!")

if __name__ == "__main__":
    init_database()
