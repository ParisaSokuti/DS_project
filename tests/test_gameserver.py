#!/usr/bin/env python3
import sys
import os

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from backend.server import GameServer
    print('Creating GameServer...')
    server = GameServer()
    print('GameServer created successfully')
    
    # Test Redis connection
    print('Testing Redis connection...')
    result = server.redis_manager.redis.ping()
    print(f'Redis ping result: {result}')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
