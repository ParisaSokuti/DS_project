#!/usr/bin/env python3
"""
Redis Game State Monitor for Hokm Game
Real-time monitoring of game state during fault tolerance demonstration
"""

import redis
import json
import time
import os
import sys
from datetime import datetime

class HokmRedisMonitor:
    def __init__(self):
        try:
            self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            # Test connection
            self.redis_client.ping()
            print("✅ Connected to Redis")
        except Exception as e:
            print(f"❌ Failed to connect to Redis: {e}")
            sys.exit(1)
    
    def clear_screen(self):
        """Clear terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def format_json(self, data):
        """Format JSON data for display"""
        if isinstance(data, str):
            try:
                data = json.loads(data)
                return json.dumps(data, indent=2)
            except:
                return data
        elif isinstance(data, dict):
            return json.dumps(data, indent=2)
        return str(data)
    
    def display_game_state(self):
        """Display current game state"""
        print("\n" + "="*80)
        print(f"🎮 HOKM GAME REDIS STATE MONITOR - {datetime.now().strftime('%H:%M:%S')}")
        print("="*80)
        
        try:
            # Get all keys
            all_keys = self.redis_client.keys('*')
            
            if not all_keys:
                print("📭 No data in Redis")
                return
            
            # Organize keys by category
            room_keys = [k for k in all_keys if k.startswith('room:')]
            game_state_keys = [k for k in all_keys if k.startswith('game_state:')]
            session_keys = [k for k in all_keys if 'session' in k]
            player_keys = [k for k in all_keys if k.startswith('player:')]
            circuit_keys = [k for k in all_keys if 'circuit' in k]
            other_keys = [k for k in all_keys if not any(k.startswith(prefix) for prefix in ['room:', 'game_state:', 'player:']) and 'session' not in k and 'circuit' not in k]
            
            # Display Room Information
            if room_keys:
                print("\n🏠 ROOM DATA:")
                print("-" * 40)
                for key in room_keys:
                    print(f"📍 {key}")
                    try:
                        if self.redis_client.type(key) == 'hash':
                            data = self.redis_client.hgetall(key)
                            for field, value in data.items():
                                print(f"   {field}: {value}")
                        elif self.redis_client.type(key) == 'list':
                            data = self.redis_client.lrange(key, 0, -1)
                            for i, item in enumerate(data):
                                print(f"   [{i}]: {item}")
                        else:
                            data = self.redis_client.get(key)
                            print(f"   Value: {data}")
                    except Exception as e:
                        print(f"   ❌ Error reading {key}: {e}")
                    print()
            
            # Display Game State
            if game_state_keys:
                print("\n🎯 GAME STATE:")
                print("-" * 40)
                for key in game_state_keys:
                    print(f"🎮 {key}")
                    try:
                        if self.redis_client.type(key) == 'hash':
                            data = self.redis_client.hgetall(key)
                            for field, value in data.items():
                                if field in ['hands', 'tricks', 'game_board']:
                                    # Format complex JSON data
                                    formatted = self.format_json(value)
                                    if len(formatted) > 200:
                                        print(f"   {field}: {formatted[:200]}...")
                                    else:
                                        print(f"   {field}: {formatted}")
                                else:
                                    print(f"   {field}: {value}")
                        else:
                            data = self.redis_client.get(key)
                            print(f"   Value: {self.format_json(data)}")
                    except Exception as e:
                        print(f"   ❌ Error reading {key}: {e}")
                    print()
            
            # Display Player Sessions
            if session_keys:
                print("\n👤 PLAYER SESSIONS:")
                print("-" * 40)
                active_sessions = 0
                for key in session_keys:
                    try:
                        if self.redis_client.type(key) == 'hash':
                            data = self.redis_client.hgetall(key)
                            if data:
                                active_sessions += 1
                                print(f"🔑 {key}")
                                print(f"   Username: {data.get('username', 'Unknown')}")
                                print(f"   Room: {data.get('room_code', 'None')}")
                                print(f"   Status: {data.get('connection_status', 'Unknown')}")
                                print(f"   Connected: {data.get('connected_at', 'Unknown')}")
                                print()
                        else:
                            data = self.redis_client.get(key)
                            if data:
                                active_sessions += 1
                                print(f"🔑 {key}: {data}")
                    except Exception as e:
                        print(f"   ❌ Error reading {key}: {e}")
                
                print(f"📊 Total Active Sessions: {active_sessions}")
            
            # Display Circuit Breaker Status
            if circuit_keys:
                print("\n🔌 CIRCUIT BREAKER STATUS:")
                print("-" * 40)
                for key in circuit_keys:
                    try:
                        data = self.redis_client.get(key)
                        print(f"⚡ {key}: {data}")
                    except Exception as e:
                        print(f"   ❌ Error reading {key}: {e}")
            
            # Display Other Keys
            if other_keys:
                print("\n📦 OTHER DATA:")
                print("-" * 40)
                for key in other_keys[:10]:  # Limit to first 10
                    try:
                        data_type = self.redis_client.type(key)
                        if data_type == 'string':
                            data = self.redis_client.get(key)
                            print(f"📄 {key}: {data}")
                        elif data_type == 'hash':
                            count = self.redis_client.hlen(key)
                            print(f"📊 {key}: Hash with {count} fields")
                        elif data_type == 'list':
                            count = self.redis_client.llen(key)
                            print(f"📋 {key}: List with {count} items")
                        elif data_type == 'set':
                            count = self.redis_client.scard(key)
                            print(f"🎯 {key}: Set with {count} members")
                    except Exception as e:
                        print(f"   ❌ Error reading {key}: {e}")
                
                if len(other_keys) > 10:
                    print(f"   ... and {len(other_keys) - 10} more keys")
            
            print(f"\n📊 SUMMARY:")
            print(f"   Total Keys: {len(all_keys)}")
            print(f"   Rooms: {len(room_keys)}")
            print(f"   Game States: {len(game_state_keys)}")
            print(f"   Sessions: {len(session_keys)}")
            
        except Exception as e:
            print(f"❌ Error monitoring Redis: {e}")
    
    def monitor_live(self, refresh_interval=2):
        """Monitor Redis with live updates"""
        print("🔴 Starting live Redis monitoring...")
        print("Press Ctrl+C to stop")
        
        try:
            while True:
                self.clear_screen()
                self.display_game_state()
                print(f"\n⏱️  Refreshing every {refresh_interval} seconds... (Ctrl+C to stop)")
                time.sleep(refresh_interval)
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped")
    
    def monitor_changes(self):
        """Monitor Redis changes in real-time using Redis MONITOR command"""
        print("🔴 Starting Redis MONITOR - showing all operations...")
        print("Press Ctrl+C to stop")
        
        try:
            # Create a separate Redis connection for monitoring
            monitor_client = redis.Redis(host='localhost', port=6379, db=0)
            
            # Start monitoring
            with monitor_client.monitor() as m:
                for command in m.listen():
                    if command['command']:
                        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                        cmd_str = ' '.join(str(arg, 'utf-8') if isinstance(arg, bytes) else str(arg) for arg in command['command'])
                        
                        # Highlight game-related operations
                        if any(keyword in cmd_str.lower() for keyword in ['room:', 'game_state:', 'session:', 'hokm', 'player']):
                            print(f"🎮 {timestamp} | {cmd_str}")
                        else:
                            print(f"   {timestamp} | {cmd_str}")
                            
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped")
        except Exception as e:
            print(f"❌ Monitor error: {e}")
    
    def interactive_mode(self):
        """Interactive Redis exploration"""
        print("\n🔍 Interactive Redis Explorer")
        print("Commands: keys <pattern>, get <key>, hgetall <key>, monitor, live, quit")
        
        while True:
            try:
                command = input("\nRedis> ").strip()
                
                if command.lower() in ['quit', 'exit', 'q']:
                    break
                elif command.lower() == 'monitor':
                    self.monitor_changes()
                elif command.lower() == 'live':
                    self.monitor_live()
                elif command.startswith('keys '):
                    pattern = command[5:]
                    keys = self.redis_client.keys(pattern)
                    print(f"Found {len(keys)} keys:")
                    for key in keys:
                        print(f"  {key}")
                elif command.startswith('get '):
                    key = command[4:]
                    try:
                        value = self.redis_client.get(key)
                        print(f"{key}: {value}")
                    except Exception as e:
                        print(f"Error: {e}")
                elif command.startswith('hgetall '):
                    key = command[8:]
                    try:
                        data = self.redis_client.hgetall(key)
                        for field, value in data.items():
                            print(f"  {field}: {value}")
                    except Exception as e:
                        print(f"Error: {e}")
                elif command == 'help':
                    print("Available commands:")
                    print("  keys <pattern>   - List keys matching pattern")
                    print("  get <key>        - Get string value")
                    print("  hgetall <key>    - Get all hash fields")
                    print("  monitor          - Show real-time operations")
                    print("  live             - Live state display")
                    print("  quit             - Exit")
                else:
                    print("Unknown command. Type 'help' for available commands.")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")

def main():
    print("🛡️ Hokm Game Redis Monitor")
    
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
    else:
        mode = None
    
    monitor = HokmRedisMonitor()
    
    if mode == 'live':
        monitor.monitor_live()
    elif mode == 'monitor':
        monitor.monitor_changes()
    elif mode == 'interactive':
        monitor.interactive_mode()
    else:
        print("\nChoose monitoring mode:")
        print("1. Live State Display (refreshes every 2 seconds)")
        print("2. Real-time Operations Monitor (shows all Redis commands)")
        print("3. Interactive Explorer")
        print("4. One-time State Display")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == '1':
            monitor.monitor_live()
        elif choice == '2':
            monitor.monitor_changes()
        elif choice == '3':
            monitor.interactive_mode()
        elif choice == '4':
            monitor.display_game_state()
        else:
            print("Invalid choice")

if __name__ == "__main__":
    main()
