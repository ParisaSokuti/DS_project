#!/usr/bin/env python3
"""
Minimal server test to isolate the hanging issue
"""

import asyncio
import websockets
import json
import sys
import os

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from network import NetworkManager
from redis_manager_resilient import ResilientRedisManager as RedisManager
from circuit_breaker_monitor import CircuitBreakerMonitor

class MinimalGameServer:
    def __init__(self):
        print("[DEBUG] Creating Redis manager...")
        self.redis_manager = RedisManager()
        print("[DEBUG] Creating circuit breaker monitor...")
        self.circuit_breaker_monitor = CircuitBreakerMonitor(self.redis_manager)
        print("[DEBUG] Creating network manager...")
        self.network_manager = NetworkManager()
        print("[DEBUG] Creating active games...")
        self.active_games = {}
        print("[DEBUG] Server initialization complete")

async def handle_connection(websocket, path):
    print(f"[LOG] New connection from {websocket.remote_address}")
    try:
        async for message in websocket:
            print(f"[LOG] Received: {message}")
            await websocket.send(json.dumps({"type": "echo", "data": message}))
    except websockets.ConnectionClosed:
        print(f"[LOG] Connection closed")

async def main():
    print("Starting minimal WebSocket server on ws://0.0.0.0:8765")
    
    print("[DEBUG] Creating server instance...")
    server = MinimalGameServer()
    
    print("[DEBUG] Starting WebSocket server...")
    async with websockets.serve(
        handle_connection, 
        "0.0.0.0", 
        8765,
        ping_interval=60,      # Send ping every 60 seconds
        ping_timeout=300,      # 5 minutes timeout for ping response
        close_timeout=300,     # 5 minutes timeout for close handshake
        max_size=1024*1024,    # 1MB max message size
        max_queue=100          # Max queued messages
    ):
        print("[LOG] WebSocket server is now listening on ws://0.0.0.0:8765")
        await asyncio.sleep(5)  # Run for 5 seconds
        print("[LOG] Test complete")

if __name__ == "__main__":
    asyncio.run(main())
