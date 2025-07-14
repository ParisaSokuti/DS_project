#!/usr/bin/env python3
"""
Simple Reconnection Test

This test simulates a basic scenario where:
1. Client connects and joins a game
2. Simulates disconnection
3. Reconnects to continue the game
"""

import asyncio
import websockets
import json
import sys
import os
import time

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from client_auth_manager import ClientAuthManager
    from game_states import GameState
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

SERVER_URI = "ws://192.168.1.26:8765"

class SimpleTest:
    def __init__(self):
        self.auth_manager = ClientAuthManager()
        self.player_id = None
        self.session_file = ".simple_test_session"
        
    async def cleanup(self):
        """Clean up session file"""
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
                print("🗑️  Session file cleaned up")
        except:
            pass
    
    async def save_session(self):
        """Save session for reconnection"""
        if self.player_id:
            with open(self.session_file, 'w') as f:
                f.write(self.player_id)
            print(f"💾 Session saved: {self.player_id[:12]}...")
    
    async def load_session(self):
        """Load session for reconnection"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r') as f:
                    session_id = f.read().strip()
                print(f"📂 Session loaded: {session_id[:12]}...")
                return session_id
        except Exception as e:
            print(f"❌ Error loading session: {e}")
        return None
    
    async def connect_and_authenticate(self):
        """Connect and authenticate with server"""
        print("🔗 Connecting to server...")
        ws = await websockets.connect(SERVER_URI)
        
        print("🔐 Authenticating...")
        authenticated = await self.auth_manager.authenticate_with_server(ws)
        
        if authenticated:
            player_info = self.auth_manager.get_player_info()
            self.player_id = player_info['player_id']
            print(f"✅ Authenticated as {player_info['username']}")
            print(f"🆔 Player ID: {self.player_id[:12]}...")
            return ws
        else:
            print("❌ Authentication failed")
            await ws.close()
            return None
    
    async def test_basic_join_and_reconnect(self):
        """Test basic join and reconnect functionality"""
        print("🎮 Starting Simple Reconnection Test")
        print("=" * 50)
        
        # Phase 1: Join game
        print("\n📋 Phase 1: Join game")
        ws = await self.connect_and_authenticate()
        if not ws:
            return False
        
        await self.save_session()
        
        # Join the game
        print("🎯 Joining game...")
        await ws.send(json.dumps({
            "type": "join",
            "room_code": "9999"
        }))
        
        # Wait for join response
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=10.0)
            data = json.loads(response)
            
            if data.get('type') == 'join_success':
                print("✅ Successfully joined game!")
                print(f"   Player ID: {data.get('player_id', 'Unknown')[:12]}...")
                print(f"   Username: {data.get('username', 'Unknown')}")
            else:
                print(f"❌ Unexpected response: {data}")
                await ws.close()
                return False
                
        except asyncio.TimeoutError:
            print("❌ Timeout waiting for join response")
            await ws.close()
            return False
        except Exception as e:
            print(f"❌ Error during join: {e}")
            await ws.close()
            return False
        
        # Close connection to simulate disconnection
        await ws.close()
        print("📴 Disconnected from server")
        
        # Phase 2: Reconnect
        print("\n📋 Phase 2: Reconnect to game")
        await asyncio.sleep(2)  # Wait a bit before reconnecting
        
        ws = await self.connect_and_authenticate()
        if not ws:
            return False
        
        # Load session and attempt reconnection
        session_id = await self.load_session()
        if not session_id:
            print("❌ No session to reconnect with")
            await ws.close()
            return False
        
        print("🔄 Attempting reconnection...")
        await ws.send(json.dumps({
            "type": "reconnect",
            "player_id": session_id,
            "room_code": "9999"
        }))
        
        # Wait for reconnection response
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=15.0)
            data = json.loads(response)
            
            if data.get('type') == 'reconnect_success':
                print("✅ Successfully reconnected!")
                game_state = data.get('game_state', {})
                print(f"   Game phase: {game_state.get('phase', 'unknown')}")
                print(f"   Hand size: {len(game_state.get('hand', []))}")
                print(f"   Your turn: {game_state.get('your_turn', False)}")
                result = True
            elif data.get('type') == 'error':
                print(f"❌ Reconnection failed: {data.get('message', 'Unknown error')}")
                result = False
            else:
                print(f"❌ Unexpected reconnection response: {data}")
                result = False
                
        except asyncio.TimeoutError:
            print("❌ Timeout waiting for reconnection response")
            result = False
        except Exception as e:
            print(f"❌ Error during reconnection: {e}")
            result = False
        
        await ws.close()
        
        # Results
        print("\n" + "=" * 50)
        print("🔍 TEST RESULTS:")
        print("=" * 50)
        if result:
            print("🎉 SUCCESS: Basic reconnection is working!")
        else:
            print("❌ FAILED: Reconnection is not working properly")
        
        await self.cleanup()
        return result

async def main():
    test = SimpleTest()
    success = await test.test_basic_join_and_reconnect()
    return 0 if success else 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Test interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
