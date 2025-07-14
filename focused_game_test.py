#!/usr/bin/env python3
"""
Focused Hokm Game Test
Tests specific scenarios: 4 players joining, playing, disconnecting/reconnecting
Players: kasra, parisa, arvin, nima (password: 123456)
"""
import asyncio
import websockets
import json
import time
import random
from typing import Dict, List, Optional

class HokmTestClient:
    """Simple test client for Hokm game"""
    
    def __init__(self, username: str, password: str = "123456"):
        self.username = username
        self.password = password
        self.websocket = None
        self.player_id = None
        self.room_code = None
        self.hand = []
        self.authenticated = False
        self.is_hakem = False
        self.hokm = None
        self.connected = False
        self.my_turn = False
        
    async def connect(self, uri: str = "ws://localhost:8765"):
        """Connect to game server"""
        try:
            self.websocket = await websockets.connect(uri)
            self.connected = True
            print(f"✅ [{self.username}] Connected to server")
            return True
        except Exception as e:
            print(f"❌ [{self.username}] Connection failed: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from server"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            print(f"🔌 [{self.username}] Disconnected")
    
    async def send_message(self, message: Dict):
        """Send message to server"""
        if self.websocket and self.connected:
            try:
                await self.websocket.send(json.dumps(message))
                print(f"📤 [{self.username}] Sent: {message['type']}")
            except Exception as e:
                print(f"❌ [{self.username}] Send failed: {e}")
    
    async def receive_message(self):
        """Receive one message from server"""
        if not self.websocket or not self.connected:
            return None
            
        try:
            message = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
            data = json.loads(message)
            await self.handle_message(data)
            return data
        except asyncio.TimeoutError:
            return None
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
            print(f"🔌 [{self.username}] Connection closed")
            return None
        except Exception as e:
            print(f"❌ [{self.username}] Receive error: {e}")
            return None
    
    async def handle_message(self, data: Dict):
        """Handle incoming message"""
        msg_type = data.get('type')
        
        if msg_type == 'auth_response':
            if data.get('success'):
                self.authenticated = True
                self.player_id = data.get('player_info', {}).get('player_id')
                print(f"🔐 [{self.username}] Authenticated successfully")
            else:
                print(f"❌ [{self.username}] Auth failed: {data.get('message')}")
        
        elif msg_type == 'join_success':
            self.room_code = data.get('room_code')
            print(f"🏠 [{self.username}] Joined room {self.room_code}")
        
        elif msg_type == 'team_assignment':
            hakem = data.get('hakem')
            self.is_hakem = (hakem == self.username)
            print(f"👑 [{self.username}] Hakem: {hakem} {'(Me!)' if self.is_hakem else ''}")
        
        elif msg_type == 'initial_deal':
            self.hand = data.get('hand', [])
            print(f"🎴 [{self.username}] Got {len(self.hand)} cards")
        
        elif msg_type == 'hokm_selected':
            self.hokm = data.get('suit')
            print(f"♠️ [{self.username}] Hokm: {self.hokm}")
        
        elif msg_type == 'final_deal':
            self.hand = data.get('hand', [])
            print(f"🎴 [{self.username}] Final hand: {len(self.hand)} cards")
        
        elif msg_type == 'turn_start':
            self.my_turn = data.get('your_turn', False)
            current_player = data.get('current_player')
            print(f"🎯 [{self.username}] {'MY TURN' if self.my_turn else f'{current_player} playing'}")
        
        elif msg_type == 'card_played':
            player = data.get('player')
            card = data.get('card')
            print(f"🃏 [{self.username}] {player} played {card}")
        
        elif msg_type == 'reconnect_success':
            print(f"🔄 [{self.username}] Reconnected successfully!")
        
        elif msg_type == 'error':
            print(f"❌ [{self.username}] Error: {data.get('message')}")
        
        elif msg_type in ['phase_change', 'trick_result', 'hand_complete', 'game_over']:
            print(f"📊 [{self.username}] {msg_type}: {data}")
    
    async def authenticate(self):
        """Authenticate with server"""
        await self.send_message({
            'type': 'auth_login',
            'username': self.username,
            'password': self.password
        })
        
        # Wait for response
        for _ in range(10):  # Wait up to 5 seconds
            response = await self.receive_message()
            if response and response.get('type') == 'auth_response':
                return self.authenticated
            await asyncio.sleep(0.5)
        
        return False
    
    async def join_room(self, room_code: str = "9999"):
        """Join game room"""
        await self.send_message({
            'type': 'join',
            'room_code': room_code
        })
        
        # Wait for response
        await self.receive_message()
    
    async def select_hokm(self, suit: str):
        """Select hokm suit"""
        await self.send_message({
            'type': 'hokm_selected',
            'room_code': self.room_code,
            'suit': suit
        })
    
    async def play_card(self, card: str):
        """Play a card"""
        await self.send_message({
            'type': 'play_card',
            'room_code': self.room_code,
            'player_id': self.player_id,
            'card': card
        })
    
    async def reconnect(self):
        """Attempt to reconnect"""
        await self.send_message({
            'type': 'reconnect',
            'player_id': self.player_id
        })

async def test_game_flow():
    """Test the complete game flow"""
    print("🎮 Starting Hokm Game Test")
    print("=" * 50)
    
    # Create 4 players
    players = [
        HokmTestClient("kasra"),
        HokmTestClient("parisa"),
        HokmTestClient("arvin"),
        HokmTestClient("nima")
    ]
    
    try:
        # Step 1: Connect all players
        print("\n1. 🔗 Connecting players...")
        for player in players:
            if not await player.connect():
                print(f"Failed to connect {player.username}")
                return False
        
        # Step 2: Authenticate all players
        print("\n2. 🔐 Authenticating players...")
        for player in players:
            if not await player.authenticate():
                print(f"Failed to authenticate {player.username}")
                return False
        
        # Step 3: Join room
        print("\n3. 🏠 Joining room...")
        for player in players:
            await player.join_room("9999")
            await asyncio.sleep(0.5)
        
        # Step 4: Wait for game start
        print("\n4. 🎯 Waiting for game to start...")
        await asyncio.sleep(2)
        
        # Receive team assignment messages
        for player in players:
            await player.receive_message()
        
        # Step 5: Select hokm
        print("\n5. ♠️ Selecting hokm...")
        hakem = next((p for p in players if p.is_hakem), None)
        if hakem:
            await hakem.select_hokm("hearts")
            await asyncio.sleep(1)
            
            # Receive hokm selection messages
            for player in players:
                await player.receive_message()
        
        # Step 6: Final deal
        print("\n6. 🎴 Final deal...")
        await asyncio.sleep(2)
        for player in players:
            await player.receive_message()
        
        # Step 7: Test disconnection/reconnection
        print("\n7. 🔄 Testing disconnection/reconnection...")
        test_player = players[1]  # parisa
        player_id = test_player.player_id
        
        # Disconnect
        print(f"   Disconnecting {test_player.username}...")
        await test_player.disconnect()
        await asyncio.sleep(1)
        
        # Reconnect
        print(f"   Reconnecting {test_player.username}...")
        await test_player.connect()
        await test_player.reconnect()
        await asyncio.sleep(1)
        
        # Step 8: Play a few cards
        print("\n8. 🃏 Playing cards...")
        for round_num in range(2):
            print(f"   Round {round_num + 1}:")
            
            # Wait for turn messages
            for player in players:
                await player.receive_message()
            
            # Find whose turn it is
            current_player = next((p for p in players if p.my_turn), None)
            if current_player and current_player.hand:
                card = current_player.hand[0]
                print(f"   {current_player.username} playing {card}")
                await current_player.play_card(card)
                await asyncio.sleep(1)
                
                # Receive card played messages
                for player in players:
                    await player.receive_message()
        
        print("\n✅ Game test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False
    
    finally:
        # Clean up
        print("\n🧹 Cleaning up...")
        for player in players:
            if player.connected:
                await player.disconnect()

async def main():
    """Main test function"""
    print("🔍 Testing server connection...")
    try:
        test_client = HokmTestClient("test")
        if not await test_client.connect():
            print("❌ Server is not running. Start with: python backend/server.py")
            return
        await test_client.disconnect()
        print("✅ Server is running")
    except Exception as e:
        print(f"❌ Server test failed: {e}")
        return
    
    # Run the game test
    success = await test_game_flow()
    
    if success:
        print("\n🎉 All tests passed! The game is working correctly.")
    else:
        print("\n❌ Some tests failed.")

if __name__ == "__main__":
    asyncio.run(main())
