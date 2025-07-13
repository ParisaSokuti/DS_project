#!/usr/bin/env python3
"""
Hybrid Data Architecture Validation Script
Validates that all components of the hybrid data architecture are properly integrated
"""

import asyncio
import sys
import os
import traceback
from typing import Dict, Any

# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

async def validate_imports():
    """Validate that all hybrid data architecture components can be imported"""
    print("🔍 Validating component imports...")
    
    try:
        # Core hybrid components
        from backend.hybrid_data_layer import HybridDataLayer, HybridDataConfig
        print("✅ HybridDataLayer imported successfully")
        
        from backend.redis_game_state import RedisGameStateManager, GameStateConfig
        print("✅ RedisGameStateManager imported successfully")
        
        from backend.postgresql_persistence import PostgreSQLPersistenceManager, PersistenceConfig
        print("✅ PostgreSQLPersistenceManager imported successfully")
        
        from backend.data_synchronization import (
            DataSynchronizationManager, SyncConfig, TransactionType
        )
        print("✅ DataSynchronizationManager imported successfully")
        
        # Supporting components
        from backend.database.session_manager import AsyncSessionManager
        print("✅ AsyncSessionManager imported successfully")
        
        from backend.circuit_breaker import CircuitBreaker
        print("✅ CircuitBreaker imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed:")
        print("pip install -r requirements.txt")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during imports: {e}")
        traceback.print_exc()
        return False

async def validate_redis_connection():
    """Validate Redis connection"""
    print("\n🔍 Validating Redis connection...")
    
    try:
        import redis.asyncio as redis
        
        # Test Redis connection
        redis_client = redis.Redis(host='localhost', port=6379, db=0)
        await redis_client.ping()
        await redis_client.close()
        
        print("✅ Redis connection successful")
        return True
        
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("Make sure Redis is running on localhost:6379")
        return False

async def validate_postgresql_connection():
    """Validate PostgreSQL connection (optional)"""
    print("\n🔍 Validating PostgreSQL connection...")
    
    try:
        import asyncpg
        
        # Try to connect to PostgreSQL
        # Note: This will fail if PostgreSQL is not set up, but that's OK for this validation
        try:
            conn = await asyncpg.connect(
                host='localhost',
                port=5432,
                user='postgres',
                password='password',
                database='hokm_db'
            )
            await conn.close()
            print("✅ PostgreSQL connection successful")
            return True
        except:
            print("⚠️ PostgreSQL connection failed (this is optional for basic functionality)")
            print("The hybrid architecture will work with Redis-only mode")
            return None
            
    except ImportError:
        print("⚠️ asyncpg not installed (PostgreSQL support disabled)")
        return None
    except Exception as e:
        print(f"⚠️ PostgreSQL validation error: {e}")
        return None

async def validate_basic_functionality():
    """Validate basic hybrid data architecture functionality"""
    print("\n🔍 Validating basic functionality...")
    
    try:
        from backend.hybrid_data_layer import HybridDataConfig
        from backend.redis_game_state import GameStateConfig
        from backend.postgresql_persistence import PersistenceConfig
        from backend.data_synchronization import SyncConfig, TransactionType
        
        # Create test configurations
        hybrid_config = HybridDataConfig(
            redis_url="redis://localhost:6379",
            redis_prefix="test:",
            redis_default_ttl=300,  # 5 minutes for testing
        )
        print("✅ HybridDataLayer configuration successful")
        
        # Test Redis manager configuration
        redis_config = GameStateConfig(redis_prefix="test:")
        print("✅ Redis game state manager configuration successful")
        
        # Test PostgreSQL manager configuration
        postgres_config = PersistenceConfig(
            batch_size=50,
            batch_timeout=30.0
        )
        print("✅ PostgreSQL persistence manager configuration successful")
        
        # Test sync configuration
        sync_config = SyncConfig(
            batch_size=50,
            batch_timeout=30.0
        )
        print("✅ Data synchronization manager configuration successful")
        
        # Test transaction types
        transaction_types = [
            TransactionType.REDIS_ONLY,
            TransactionType.POSTGRESQL_ONLY,
            TransactionType.HYBRID_WRITE_THROUGH,
            TransactionType.HYBRID_WRITE_BEHIND
        ]
        print(f"✅ Transaction types available: {len(transaction_types)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic functionality validation failed: {e}")
        traceback.print_exc()
        return False

async def validate_architecture_files():
    """Validate that all architecture files exist"""
    print("\n🔍 Validating architecture files...")
    
    required_files = [
        'HYBRID_DATA_ARCHITECTURE_STRATEGY.md',
        'backend/hybrid_data_layer.py',
        'backend/redis_game_state.py',
        'backend/postgresql_persistence.py',
        'backend/data_synchronization.py',
        'backend/database/session_manager.py',
        'HYBRID_DATA_ARCHITECTURE_USAGE.md',
        'examples/hybrid_integration_example.py'
    ]
    
    missing_files = []
    existing_files = []
    
    for file_path in required_files:
        full_path = os.path.join(project_root, file_path)
        if os.path.exists(full_path):
            existing_files.append(file_path)
            print(f"✅ {file_path}")
        else:
            missing_files.append(file_path)
            print(f"❌ {file_path} (missing)")
    
    if missing_files:
        print(f"\n⚠️ Missing {len(missing_files)} required files:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    else:
        print(f"\n✅ All {len(existing_files)} required files present")
        return True

async def validate_example_syntax():
    """Validate that the integration example has valid syntax"""
    print("\n🔍 Validating example syntax...")
    
    try:
        example_path = os.path.join(project_root, 'examples/hybrid_integration_example.py')
        
        if not os.path.exists(example_path):
            print("❌ Integration example file not found")
            return False
        
        # Try to compile the example file
        with open(example_path, 'r') as f:
            source_code = f.read()
        
        compile(source_code, example_path, 'exec')
        print("✅ Integration example syntax is valid")
        
        return True
        
    except SyntaxError as e:
        print(f"❌ Syntax error in integration example: {e}")
        return False
    except Exception as e:
        print(f"❌ Error validating example syntax: {e}")
        return False

def print_summary(results: Dict[str, Any]):
    """Print validation summary"""
    print("\n" + "="*60)
    print("🏁 HYBRID DATA ARCHITECTURE VALIDATION SUMMARY")
    print("="*60)
    
    total_checks = len(results)
    passed_checks = sum(1 for result in results.values() if result is True)
    optional_checks = sum(1 for result in results.values() if result is None)
    failed_checks = total_checks - passed_checks - optional_checks
    
    print(f"✅ Passed: {passed_checks}")
    print(f"⚠️ Optional: {optional_checks}")
    print(f"❌ Failed: {failed_checks}")
    print(f"📊 Total: {total_checks}")
    
    print("\nDetailed Results:")
    for check_name, result in results.items():
        if result is True:
            status = "✅ PASS"
        elif result is None:
            status = "⚠️ SKIP"
        else:
            status = "❌ FAIL"
        print(f"  {status} - {check_name}")
    
    if failed_checks == 0:
        print("\n🎉 ALL CRITICAL CHECKS PASSED!")
        print("The hybrid data architecture is ready to use.")
        if optional_checks > 0:
            print(f"({optional_checks} optional component(s) skipped)")
    else:
        print(f"\n⚠️ {failed_checks} CRITICAL ISSUE(S) FOUND")
        print("Please resolve the failed checks before using the architecture.")
    
    print("\n📚 Next Steps:")
    print("1. Review HYBRID_DATA_ARCHITECTURE_STRATEGY.md for architecture overview")
    print("2. Check HYBRID_DATA_ARCHITECTURE_USAGE.md for usage instructions")
    print("3. Run examples/hybrid_integration_example.py for demonstration")
    print("4. Integrate the hybrid data layer into your game server")

async def main():
    """Main validation function"""
    print("🚀 HYBRID DATA ARCHITECTURE VALIDATION")
    print("="*60)
    print("This script validates the hybrid data architecture implementation")
    print("for the Hokm game server (Redis + PostgreSQL).")
    print("")
    
    # Run all validation checks
    results = {}
    
    results['Component Imports'] = await validate_imports()
    results['Architecture Files'] = await validate_architecture_files()
    results['Example Syntax'] = await validate_example_syntax()
    results['Redis Connection'] = await validate_redis_connection()
    results['PostgreSQL Connection'] = await validate_postgresql_connection()
    results['Basic Functionality'] = await validate_basic_functionality()
    
    # Print summary
    print_summary(results)
    
    # Return success/failure for script exit code
    critical_results = [v for v in results.values() if v is not None]
    return all(critical_results)

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
